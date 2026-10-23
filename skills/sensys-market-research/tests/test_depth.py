"""Depth selection, real execution bounds and unchanged evidence standards."""
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research as r
import capabilities as c
import research_depth as d

HTML = b'<html><article><p>A synthetic customer mentions privacy concerns in a bedside conversation.</p><p>This fixture is sufficient for testing exact citation and archive boundaries, but is not market research.</p></article></html>'


class Depth(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'task'
    def tearDown(self):
        self.temp.cleanup()
    def init(self, tier=None, **limits):
        brief = dict(question='Synthetic fixture only', constraints=dict(research_limits=limits))
        return r.init_task(self.root, brief, ['synthesis'], tier)
    def fetch(self, url, *args, **kwargs):
        return HTML, url, 200, 'text/html'
    def source(self):
        with patch.object(r, 'download', side_effect=self.fetch):
            return r.capture(self.root, url='https://example.org/fixture', max_images=0)
    def findings(self, source):
        blocks = r.read_json(self.root / source['artifacts']['blocks'])
        e = r.add_evidence(self.root, source['source_id'], blocks[0]['block_id'], 'privacy concerns')
        result = r.read_json(self.root / 'result.json')
        result.update(summary='Synthetic test, not market evidence', support_reviewed=True,
                      findings=[dict(finding_id='f1', kind='fact', statement='The fixture mentions a privacy concern.', evidence_refs=[e['evidence_id']], limitations=['Synthetic fixture.'])])
        r.write_json(self.root / 'result.json', result)
        return result
    def review(self, result, tier):
        result['depth_review'] = dict(research_depth=tier, checks=[dict(check=key, status='not_relevant', reason='Synthetic citation test only; no product decision.', finding_refs=[]) for key in d.profile(tier)['review_checks']])
        return result
    def coverage(self, source):
        c.save_plan(self.root, dict(schema_version='2.0', roles=[dict(role='supplied', required=True, reason='Test supplied text integrity only', status='captured', source_ids=[source['source_id']])]))

    def test_default_is_standard_in_brief_result_and_budget(self):
        self.init()
        self.assertEqual(r.read_json(self.root / 'brief.json')['research_depth'], 'standard')
        self.assertEqual(r.read_json(self.root / 'result.json')['research_depth'], 'standard')
        self.assertEqual(d.status(self.root)['research_depth'], 'standard')

    def test_explicit_brief_selection_is_honored(self):
        r.init_task(self.root, dict(question='Fixture', research_depth='deep'), ['competitors'])
        self.assertEqual(d.status(self.root)['limits']['captures'], 72)

    def test_conflicting_cli_selection_does_not_create_task(self):
        with self.assertRaises(ValueError):
            r.init_task(self.root, dict(research_depth='deep'), ['synthesis'], 'standard')
        self.assertFalse(self.root.exists())

    def test_invalid_profile_does_not_create_task(self):
        with self.assertRaises(ValueError):
            self.init('exhaustive')
        self.assertFalse(self.root.exists())

    def test_invalid_constraints_fail_before_creation(self):
        for constraints in [None, {'research_limits': {'captures': True}}, {'research_limits': {'all_tools': 760}}]:
            with self.assertRaises(ValueError):
                r.init_task(self.root, dict(constraints=constraints), ['synthesis'])
            self.assertFalse(self.root.exists())

    def test_capture_ceiling_stops_fetch_but_preserves_cached_access(self):
        self.init(captures=1)
        with patch.object(r, 'download', side_effect=self.fetch) as fetch:
            first = r.capture(self.root, url='https://example.org/a', max_images=0)
            with self.assertRaisesRegex(ValueError, 'budget exhausted'):
                r.capture(self.root, url='https://example.org/b', max_images=0)
            cached = r.capture(self.root, url='https://example.org/a', max_images=0)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(cached['retrieved_at'], first['retrieved_at'])
        self.assertTrue(cached['reused'])
        self.assertEqual(d.status(self.root)['used']['captures'], 1)
        self.assertEqual(len(r.read_json(self.root / 'sources.json')), 1)

    def test_failed_capture_and_refresh_consume_attempts(self):
        self.init(captures=1)
        with patch.object(r, 'download', side_effect=OSError('Fixture failure')) as fetch:
            failed = r.capture(self.root, url='https://example.org/a')
            with self.assertRaisesRegex(ValueError, 'budget exhausted'):
                r.capture(self.root, url='https://example.org/a', refresh=True)
        self.assertEqual(failed['status'], 'network_error')
        self.assertEqual(fetch.call_count, 1)

    def test_imports_also_have_bounded_attempts(self):
        self.init(captures=1)
        p = Path(self.temp.name) / 'supplied.txt'
        p.write_text('Synthetic supplied text.', encoding='utf-8')
        r.capture(self.root, file=p)
        p.write_text('Changed supplied text.', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            r.capture(self.root, file=p)

    def test_oversized_import_is_rejected_before_reading_bytes(self):
        self.init()
        p = Path(self.temp.name) / 'large.txt'
        with p.open('wb') as stream:
            stream.seek(25000000)
            stream.write(b'x')
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Must not allocate the oversized file')), self.assertRaisesRegex(ValueError, '25 MB'):
            r.capture(self.root, file=p)
        self.assertEqual(d.status(self.root)['used']['captures'], 0)

    def test_search_ceiling_and_cache_do_not_spawn_extra_workers(self):
        self.init(search_queries=1)
        worker = subprocess.CompletedProcess([], 0, json.dumps([dict(href='https://example.org/a', title='Fixture', body='Lead only')]), '')
        with patch.object(r.subprocess, 'run', return_value=worker) as run:
            r.discover(self.root, 'fixture')
            self.assertTrue(r.discover(self.root, 'fixture')['reused'])
            with self.assertRaisesRegex(ValueError, 'budget exhausted'):
                r.discover(self.root, 'different fixture')
        self.assertEqual(run.call_count, 1)

    def test_query_return_limit_is_enforced_on_worker_arguments(self):
        self.init(results_per_query=3)
        with patch.object(r.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '[]', '')) as run:
            out = r.discover(self.root, 'fixture', limit=50)
        args = run.call_args.args[0]
        self.assertEqual(args[args.index('--limit') + 1], '3')
        self.assertEqual(out['effective_limit'], 3)

    def test_image_cap_does_not_increase_with_a_large_request(self):
        self.init(images_per_source=0)
        html = HTML.replace(b'</article>', b'<img src="https://example.org/chart.png"></article>')
        with patch.object(r, 'download', return_value=(html, 'https://example.org/a', 200, 'text/html')) as fetch:
            source = r.capture(self.root, url='https://example.org/a', max_images=10000)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(source['assets'][0]['status'], 'omitted_budget')
        self.assertEqual(source['capture_request']['max_images'], 0)

    def test_overlapping_acquisition_is_rejected(self):
        self.init()
        entered, release = threading.Event(), threading.Event()
        def wait_fetch(url, *args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return self.fetch(url)
        with patch.object(r, 'download', side_effect=wait_fetch), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(r.capture, self.root, url='https://example.org/a', max_images=0)
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaisesRegex(ValueError, 'Task is busy'):
                    r.capture(self.root, url='https://example.org/b', max_images=0)
                with self.assertRaisesRegex(ValueError, 'Task is busy'):
                    d.select(self.root, 'deep', 'Fixture continuation')
            finally:
                release.set()
            self.assertEqual(future.result()['status'], 'complete_body')

    def test_depth_upgrade_preserves_archives_ids_time_and_usage(self):
        self.init()
        source = self.source()
        self.findings(source)
        original = {name: (self.root / name).read_bytes() for name in ['sources.json', 'evidence.json', source['artifacts']['raw']]}
        d.select(self.root, 'deep', 'Explicit user deep selection')
        for name, data in original.items():
            self.assertEqual((self.root / name).read_bytes(), data)
        with patch.object(r, 'download') as fetch:
            cached = r.capture(self.root, url='https://example.org/fixture', max_images=0)
        fetch.assert_not_called()
        self.assertEqual(cached['source_id'], source['source_id'])
        self.assertEqual(cached['retrieved_at'], source['retrieved_at'])
        self.assertEqual(d.status(self.root)['used']['captures'], 1)
        self.assertFalse(r.read_json(self.root / 'result.json')['support_reviewed'])

    def test_deep_adds_followup_capacity_without_resetting_rounds(self):
        self.init()
        d.next_round(self.root, 'Investigate contrary evidence', ['Unresolved objections'])
        with self.assertRaisesRegex(ValueError, 'budget exhausted'):
            d.next_round(self.root, 'Another pass', ['Unresolved objections'])
        d.select(self.root, 'deep', 'Explicit deep request')
        out = d.next_round(self.root, 'Resolve payment gap', ['No observed payment evidence'])
        self.assertEqual(out['used']['research_rounds'], 3)
        self.assertEqual(out['remaining']['research_rounds'], 1)

    def test_followup_requires_specific_gaps(self):
        self.init()
        for gaps in [[], [''], 'do everything']:
            with self.assertRaises(ValueError):
                d.next_round(self.root, 'Fixture', gaps)
        self.assertEqual(d.status(self.root)['used']['research_rounds'], 1)

    def test_explicit_tighter_constraints_survive_upgrade(self):
        self.init(captures=1)
        self.source()
        d.select(self.root, 'deep', 'User-selected deep, same hard constraint')
        with patch.object(r, 'download') as fetch, self.assertRaisesRegex(ValueError, 'budget exhausted'):
            r.capture(self.root, url='https://example.org/another')
        fetch.assert_not_called()

    def test_complete_requires_coverage_and_selected_tier_review(self):
        self.init('deep')
        source = self.source()
        result = self.findings(source)
        result['status'] = 'complete'
        r.write_json(self.root / 'result.json', result)
        self.assertFalse(r.validate(self.root)['ok'])
        self.coverage(source)
        self.review(result, 'standard')
        r.write_json(self.root / 'result.json', result)
        self.assertFalse(r.validate(self.root)['ok'])
        self.review(result, 'deep')
        r.write_json(self.root / 'result.json', result)
        self.assertTrue(r.validate(self.root)['ok'])

    def test_deep_review_cannot_hide_payment_gap(self):
        self.init('deep')
        source = self.source()
        result = self.review(self.findings(source), 'deep')
        self.coverage(source)
        result.update(status='complete')
        for check in result['depth_review']['checks']:
            if check['check'] == 'payment_evidence':
                check.update(status='gap', reason='No observed payment by the target segment')
        r.write_json(self.root / 'result.json', result)
        self.assertFalse(r.validate(self.root)['ok'])

    def test_both_tiers_reject_fabricated_quotes_and_decisive_gaps(self):
        for tier in ['standard', 'deep']:
            with self.subTest(tier=tier):
                self.root = Path(self.temp.name) / tier
                self.init(tier)
                source = self.source()
                with self.assertRaises(ValueError):
                    r.add_evidence(self.root, source['source_id'], 'p0001', 'An invented purchase')
                result = self.review(self.findings(source), tier)
                self.coverage(source)
                result.update(status='complete', missing_evidence=['Decisive primary evidence missing'])
                r.write_json(self.root / 'result.json', result)
                self.assertFalse(r.validate(self.root)['ok'])

    def test_report_and_handoff_expose_profile_and_real_usage(self):
        self.init('deep')
        source = self.source()
        self.findings(source)
        r.finalize(self.root)
        envelope = c.handoff(self.root)
        self.assertEqual(envelope['research_depth'], 'deep')
        self.assertEqual(envelope['research_budget']['used']['captures'], 1)
        self.assertIn('Research depth: deep', (self.root / 'report.md').read_text('utf-8'))
        self.assertIn('research-budget.json', r.read_json(self.root / 'result.json')['artifact_paths'])

    def test_switch_invalidates_prior_finalization_and_review(self):
        self.init()
        source = self.source()
        result = self.review(self.findings(source), 'standard')
        r.write_json(self.root / 'result.json', result)
        r.finalize(self.root)
        d.select(self.root, 'deep', 'Deep continuation')
        updated = r.read_json(self.root / 'result.json')
        self.assertNotIn('finalized_at', updated)
        self.assertNotIn('depth_review', updated)
        self.assertEqual(updated['previous_depth_reviews'][0]['research_depth'], 'standard')
        self.assertIn('report.md', updated['invalidated_artifacts'])

    def test_legacy_task_does_not_silently_acquire_limits(self):
        self.init()
        brief = r.read_json(self.root / 'brief.json'); brief.pop('research_depth')
        result = r.read_json(self.root / 'result.json'); result.pop('research_depth')
        r.write_json(self.root / 'brief.json', brief); r.write_json(self.root / 'result.json', result)
        (self.root / 'research-budget.json').unlink()
        self.findings(self.source())
        self.assertIsNone(d.status(self.root)['research_depth'])
        self.assertTrue(r.validate(self.root)['ok'])
        self.assertFalse((self.root / 'research-budget.json').exists())
        d.select(self.root, 'standard', 'Assign legacy task explicitly')
        self.assertEqual(d.status(self.root)['used']['captures'], 1)

    def test_missing_profile_ledger_is_not_an_unlimited_bypass(self):
        self.init()
        (self.root / 'research-budget.json').unlink()
        with patch.object(r, 'download') as fetch, self.assertRaisesRegex(ValueError, 'missing research-budget'):
            r.capture(self.root, url='https://example.org/a')
        fetch.assert_not_called()

    def test_modified_limits_are_not_a_budget_bypass(self):
        self.init(captures=1)
        state = r.read_json(self.root / 'research-budget.json')
        state['limits']['captures'] = 1000
        r.write_json(self.root / 'research-budget.json', state)
        with patch.object(r, 'download') as fetch, self.assertRaisesRegex(ValueError, 'limits differ'):
            r.capture(self.root, url='https://example.org/a')
        fetch.assert_not_called()

    def test_downgrade_keeps_usage_and_does_not_reopen_capacity(self):
        self.init('deep', captures=1)
        self.source()
        d.select(self.root, 'standard', 'Explicit narrower continuation')
        self.assertEqual(d.status(self.root)['used']['captures'], 1)
        with patch.object(r, 'download') as fetch, self.assertRaisesRegex(ValueError, 'budget exhausted'):
            r.capture(self.root, url='https://example.org/another')
        fetch.assert_not_called()

    def test_no_findings_or_unknown_review_checks_cannot_complete(self):
        self.init('deep')
        source = self.source()
        self.coverage(source)
        result = self.review(self.findings(source), 'deep')
        result.update(status='complete', findings=[])
        r.write_json(self.root / 'result.json', result)
        self.assertFalse(r.validate(self.root)['ok'])
        result = self.review(self.findings(source), 'deep')
        result.update(status='complete')
        result['depth_review']['checks'].append(dict(check='all_websites', status='assessed', reason='Invalid review field', finding_refs=[]))
        r.write_json(self.root / 'result.json', result)
        self.assertFalse(r.validate(self.root)['ok'])

    def test_context_loads_selected_profile_and_methods_only(self):
        out = c.context_manifest(['competitors'], 'deep')
        self.assertEqual(out['research_depth'], 'deep')
        self.assertEqual(len(out['files']), 2)
        self.assertFalse(any('capability-catalog' in item['path'] for item in out['files']))

    def test_cli_choice_and_upgrade_are_usable(self):
        brief = Path(self.temp.name) / 'brief.json'
        brief.write_text(json.dumps(dict(question='Fixture')), encoding='utf-8')
        command = [sys.executable, str(r.SKILL / 'scripts/research.py'), 'init', '--task', str(self.root), '--brief', str(brief), '--modes', 'competitors', '--depth', 'standard']
        out = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json.loads(out.stdout)['research_depth'], 'standard')
        command = [sys.executable, str(r.SKILL / 'scripts/capabilities.py'), 'depth', '--task', str(self.root), '--select', 'deep', '--reason', 'Explicit CLI continuation']
        out = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json.loads(out.stdout)['research_depth'], 'deep')


if __name__ == '__main__':
    unittest.main()
