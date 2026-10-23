"""Task-local research profiles and acquisition ceilings; no model or paid API calls."""
from __future__ import annotations
from contextlib import contextmanager
from functools import wraps
import json
import os
from pathlib import Path

PROFILE_PATH = Path(__file__).resolve().parents[1] / 'references/research-profiles.json'
COUNTERS = ('search_queries', 'captures', 'research_rounds')


def profiles():
    return json.loads(PROFILE_PATH.read_text(encoding='utf-8'))


def profile(name):
    if not isinstance(name, str) or name not in profiles()['profiles']:
        raise ValueError('Research depth must be standard or deep')
    return profiles()['profiles'][name]


def effective_limits(name, brief):
    limits = dict(profile(name)['limits'])
    constraints = brief.get('constraints', {})
    if not isinstance(constraints, dict):
        raise ValueError('Brief constraints must be an object')
    overrides = constraints.get('research_limits', {})
    if not isinstance(overrides, dict) or set(overrides) - set(limits):
        raise ValueError('Unknown research_limits; use the documented local acquisition limits')
    for key, value in overrides.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < (0 if key == 'images_per_source' else 1):
            raise ValueError('Research limits must be positive integers; image limit may be zero')
        limits[key] = value
    return limits


@contextmanager
def task_lock(root):
    """Reject overlapping local writers rather than queuing extra memory-heavy workers."""
    from file_lock import exclusive_lock
    manager = exclusive_lock(Path(root) / '.research-operation.lock')
    try:
        manager.__enter__()
    except OSError:
        raise ValueError('Task is busy; use one acquisition/management worker per task') from None
    try:
        yield
    finally:
        manager.__exit__(None, None, None)


def serial_task(function):
    @wraps(function)
    def wrapped(root, *args, **kwargs):
        # Legacy tasks keep their original contract until explicitly assigned a depth.
        if not (Path(root) / 'research-budget.json').exists():
            return function(root, *args, **kwargs)
        with task_lock(root):
            return function(root, *args, **kwargs)
    return wrapped


def create(root, brief, name):
    import research as r
    state = dict(schema_version='2.1', research_depth=name,
                 limits=effective_limits(name, brief),
                 used=dict(search_queries=0, captures=0, research_rounds=1),
                 round_log=[dict(round=1, reason='Initial decision-relevant coverage', gaps=[])],
                 selection_history=[dict(depth=name, selected_at=r.now(), reason='Initial selection')],
                 blocked_operations=[])
    r.write_json(Path(root) / 'research-budget.json', state)
    return state


def load(root):
    import research as r
    path = Path(root) / 'research-budget.json'
    if not path.exists():
        if r.read_json(Path(root) / 'brief.json').get('research_depth'):
            raise ValueError('Profile task is missing research-budget.json; restore its recorded state')
        return None
    state = r.read_json(path)
    profile(state['research_depth'])
    if state['limits'] != effective_limits(state['research_depth'], r.read_json(Path(root) / 'brief.json')):
        raise ValueError('Research budget limits differ from the selected profile and trusted brief')
    for key in COUNTERS:
        if isinstance(state['used'][key], bool) or not isinstance(state['used'][key], int) or state['used'][key] < 0:
            raise ValueError('Invalid research usage counters')
    return state


def capped(root, key, requested):
    state = load(root)
    return min(requested, state['limits'][key]) if state else requested


def reserve(root, key):
    """Called after cache checks and before work; failed attempts still consume budget."""
    import research as r
    state = load(root)
    if not state:
        return
    if state['used'][key] >= state['limits'][key]:
        state['blocked_operations'].append(dict(operation=key, blocked_at=r.now(), reason='Acquisition ceiling reached'))
        state['blocked_operations'] = state['blocked_operations'][-100:]
        r.write_json(Path(root) / 'research-budget.json', state)
        raise ValueError(f'Research budget exhausted: {key}; return existing evidence and disclose gaps')
    state['used'][key] += 1
    r.write_json(Path(root) / 'research-budget.json', state)


def status(root):
    state = load(root)
    if state is None:
        return dict(research_depth=None, enforcement='Legacy task; no profile ceilings assigned')
    return dict(**state, remaining={k: max(0, state['limits'][k] - state['used'][k]) for k in COUNTERS},
                enforcement='Local discover/capture attempts and managed rounds only; cache hits are free.',
                host_limits='Model tokens, money, external MCP/API calls and elapsed time require host enforcement; no savings estimate.')


@serial_task
def select(root, name, reason):
    import research as r
    if not reason.strip():
        raise ValueError('Depth selection requires a reason')
    profile(name)
    root = Path(root)
    brief = r.read_json(root / 'brief.json')
    limits = effective_limits(name, brief)
    state = load(root)
    if state and state['research_depth'] == name:
        return status(root)
    if not state:
        state = create(root, brief, name)
        # Existing archives are retained; never reset prior recorded work to zero.
        state['used']['captures'] = len(r.read_json(root / 'sources.json'))
        state['used']['search_queries'] = len(r.read_json(root / 'discoveries.json'))
        state['selection_history'][0]['reason'] = reason
    else:
        state['selection_history'].append(dict(depth=name, selected_at=r.now(), reason=reason))
        state.update(research_depth=name, limits=limits)
    brief['research_depth'] = name
    r.write_json(root / 'brief.json', brief)
    r.write_json(root / 'research-budget.json', state)
    result = r.read_json(root / 'result.json')
    if result.get('depth_review'):
        result.setdefault('previous_depth_reviews', []).append(result.pop('depth_review'))
    result.update(research_depth=name, status='partial', support_reviewed=False)
    result['invalidated_artifacts'] = [p for p in ('report.md', 'handoff.json', 'validation.json') if (root/p).exists()]
    result.pop('finalized_at', None)
    r.write_json(root / 'result.json', result)
    return status(root)


@serial_task
def next_round(root, reason, gaps):
    import research as r
    if not reason.strip() or not isinstance(gaps, list) or not gaps or any(not isinstance(g, str) or not g.strip() for g in gaps):
        raise ValueError('A follow-up round requires a reason and specific unresolved gaps')
    reserve(root, 'research_rounds')
    state = load(root)
    if state is None:
        raise ValueError('Select a research depth before managing rounds')
    state['round_log'].append(dict(round=state['used']['research_rounds'], reason=reason, gaps=gaps))
    r.write_json(Path(root) / 'research-budget.json', state)
    return status(root)


def check_review(root, result):
    """Completion checks reflect declared host review, never automated claim entailment."""
    state = load(root)
    if state is None:
        return []
    errors = []
    if result.get('research_depth') != state['research_depth']:
        errors.append('Result research_depth differs from the selected task profile')
    import research as r
    if r.read_json(Path(root) / 'brief.json').get('research_depth') != state['research_depth']:
        errors.append('Brief research_depth differs from the selected task profile')
    review = result.get('depth_review')
    if review is None and result.get('status') != 'complete':
        return errors
    if not isinstance(review, dict):
        return errors + ['Complete profile tasks need a depth_review object']
    if review.get('research_depth') != state['research_depth']:
        errors.append('Depth review must assess the currently selected profile')
    checks = review.get('checks')
    if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
        return errors + ['Depth review checks must be objects in a list']
    ids = [c.get('check') for c in checks]
    if len(set(str(i) for i in ids)) != len(ids):
        errors.append('Duplicate depth review checks')
    if result.get('status') == 'complete':
        if not result.get('findings'):
            errors.append('Complete profile tasks need decision findings; report an unsupported decision as partial or needs_input')
        if not (Path(root) / 'research-plan.json').is_file():
            errors.append('Complete profile tasks require a source-role coverage plan')
        for key in profile(state['research_depth'])['review_checks']:
            if key not in ids:
                errors.append(f'Depth review missing {key}')
    findings = {f.get('finding_id') for f in result.get('findings', [])}
    for check in checks:
        key = check.get('check')
        if not isinstance(key, str) or key not in profile('deep')['review_checks']:
            errors.append('Unknown depth review check')
        if check.get('status') not in {'assessed', 'gap', 'not_relevant'} or not check.get('reason'):
            errors.append(f'{key}: review needs status and reason')
        refs = check.get('finding_refs', [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in findings for ref in refs):
            errors.append(f'{key}: unresolved finding references')
        if check.get('status') == 'gap' and result.get('status') == 'complete':
            errors.append(f'{key}: decisive review gap requires partial status')
    return errors
