"""Durable breadth contract and incremental evidence-backed research ledger."""
import json,re
from . import store as s, schemas

def requested_count(question):
    matches=re.findall(r'(?:\u81f3\u5c11|\u4e0d\u5c11\u4e8e|\u627e\u51fa|\u5bfb\u627e|\u5217\u51fa|\u6536\u96c6|\u6574\u7406|\u5bf9\u6bd4|\u63a8\u8350|\u8c03\u7814|\u8c03\u67e5|\u641c\u96c6|\u8986\u76d6)\s*(\d+)\s*(?:\u79cd|\u4e2a|\u9879|\u6b3e|\u5bb6|\u6761|\u7c7b)',question)
    return max(map(int,matches),default=0)

def plan(ex):
    from .tools import r
    p=ex.root/'deliverable-plan.json'
    return r.read_json(p) if p.exists() else {'target_findings':requested_count(s.get(ex.job_id)['question']),'dimensions':[],'rationale':'Explicit user breadth, if stated'}

def set_plan(ex,target_findings,dimensions,rationale):
    from .tools import r
    if type(target_findings) is not int or target_findings<1 or not dimensions or any(not isinstance(x,str) or not x.strip() for x in dimensions) or not rationale.strip():
        raise ValueError('Define a positive breadth target, research dimensions and rationale')
    old=plan(ex)
    if target_findings<old['target_findings']:raise ValueError('Cannot silently lower requested/planned breadth; retain the target and disclose actual shortfall')
    value={'target_findings':target_findings,'dimensions':list(dict.fromkeys(dimensions)),'rationale':rationale}
    r.write_json(ex.root/'deliverable-plan.json',value)
    return {**value,'note':'A target is a coverage commitment, not permission to fabricate or repeat items. Persist supported items with record_findings.'}

def ledger(ex):
    from .tools import r
    p=ex.root/'findings-ledger.json'
    return r.read_json(p) if p.exists() else []

def record(ex,items):
    from .tools import r
    from jsonschema import Draft202012Validator
    if not isinstance(items,list) or not 1<=len(items)<=20:raise ValueError('Record 1–20 findings per batch; repeat batches for larger deliverables')
    known={e['evidence_id'] for e in r.read_json(ex.root/'evidence.json')}
    validator=Draft202012Validator(schemas.FINDING)
    merged={f['finding_id']:f for f in ledger(ex)}
    for f in items:
        validator.validate(f)
        if not f['finding_id'].strip() or not f['statement'].strip():raise ValueError('Finding identity and statement are required')
        if set(f['evidence_refs'])-known:raise ValueError('Register actual evidence before recording a finding')
        if f['kind'] in ('fact','source_opinion','inference') and not f['evidence_refs']:raise ValueError('Supported findings require actual citations')
        if f['kind'] in ('unknown','hypothesis') and not f['limitations']:raise ValueError('Unsupported findings require explicit limitations')
        if any(x['finding_id']!=f['finding_id'] and x['statement'].strip()==f['statement'].strip() for x in merged.values()):raise ValueError('Duplicate statement; update the existing finding instead')
        merged[f['finding_id']]=f
    r.write_json(ex.root/'findings-ledger.json',list(merged.values()))
    return {'recorded':len(items),'total_findings':len(merged),**readiness(ex,list(merged.values()))}

def readiness(ex,findings):
    target=plan(ex)['target_findings']
    actual=len({f['statement'].strip() for f in findings if f.get('kind') in ('fact','source_opinion','inference') and f.get('evidence_refs')})
    gap=f'Delivery coverage is incomplete: Plan {target} independent evidence-backed results, Actual {actual} items.'
    return {'target_findings':target,'supported_findings':actual,'needs_more':actual<target,'coverage_gap':gap if actual<target else ''}

def batches(rows,size=20):
    for start in range(0,len(rows),size):yield rows[start:start+size]

def finalization_reserve(ex):
    """Reserve synthesis/review pages according to actual accumulated material."""
    from .tools import r
    evidence=r.read_json(ex.root/'evidence.json') if (ex.root/'evidence.json').exists() else []
    findings=ledger(ex)
    if findings:
        pages=max(1,(len(findings)+19)//20)
        calls=pages*2+3  # each page may need one correction, plus synthesis/review
    else:
        pages=max(1,(len(evidence)+19)//20)
        calls=pages*2+2
    return max(4,calls),max(60000,calls*25000)

def assert_preserved(before,after):
    expected=[f['finding_id'] for f in before];actual=[f['finding_id'] for f in after]
    if len(actual)!=len(set(actual)) or set(expected)!=set(actual):
        raise ValueError('Review must preserve every finding ID; correct or downgrade unsupported items with limitations instead of silently dropping them')

def reconcile_count_gaps(ex,result):
    """Replace obsolete draft/page counting notes with current full-inventory counts.

    Keep substantive evidence gaps, including concerns about duplicated inferences.
    The count is a mechanical inventory count, not proof of independent facts.
    Original page review receipts retain the page-local counting observations.
    """
    state=readiness(ex,result['findings'])
    def page_count_note(text):
        if re.fullmatch(r'(?:This page actually provides\s*\d+\s*items?finding.*|Other pages and valid ledger counts for the full research.*|Combine all pages before checking at least\s*\d+.*|All pages must be merged before checking at least\s*\d+.*|Item inventory across all research pages.*)',text):return True
        return bool(re.fullmatch(r'(?:\u672c\u9875\u5b9e\u9645\u63d0\u4f9b\d+\u9879finding.*|\u5b8c\u6574\u7814\u7a76\u5176\u4ed6\u9875\u9762\u53ca\u6709\u6548\u660e\u7ec6\u8ba1\u6570：\u672c\u9875.*|\u9700\u5408\u5e76\u5168\u90e8\u9875\u9762\u540e\u6838\u5bf9\u81f3\u5c11\d+\u9879.*|\u9700\u8981\u5408\u5e76\u6240\u6709\u9875\u9762\u540e\u6838\u5bf9\u81f3\u5c11\d+\u9879.*|\u5b8c\u6574\u7814\u7a76\u6240\u6709\u9875\u9762\u7684\u660e\u7ec6\u6e05\u5355，\u4ee5\u6838\u5b9e\u81f3\u5c11\d+\u9879.*)',text))
    old=result.get('missing_evidence',[])
    removed=[x for x in old if x.startswith('Delivery coverage is incomplete: Plan ') or page_count_note(x)]
    result['missing_evidence']=[x for x in old if x not in removed]
    for module in result.get('modules',[]):
        module['gaps']=[x for x in module.get('gaps',[]) if x not in removed]
    if state['needs_more']:result['missing_evidence'].append(state['coverage_gap'])
    return state

def merge_reviews(original,values):
    """Merge reviewed pages without a lossy second full-report rewrite."""
    import copy
    out=copy.deepcopy(original);out['findings']=[f for v in values for f in v['result']['findings']]
    assert_preserved(original['findings'],out['findings'])
    modules={};checks={}
    for v in values:
        result=v['result']
        for key in ('conflicts','missing_evidence','assumptions','next_steps'):
            out[key]=list(dict.fromkeys(out.get(key,[])+result.get(key,[])))
        if result['status']!='complete':out['status']='partial'
        for m in result['modules']:
            key=m['module_id']
            if key not in modules:modules[key]=copy.deepcopy(m)
            else:
                modules[key]['finding_refs']=list(dict.fromkeys(modules[key]['finding_refs']+m['finding_refs']))
                modules[key]['gaps']=list(dict.fromkeys(modules[key]['gaps']+m['gaps']))
        for check in result['depth_review']['checks']:
            key=check['check']
            if key not in checks:checks[key]=copy.deepcopy(check)
            else:
                old=checks[key];old['finding_refs']=list(dict.fromkeys(old['finding_refs']+check['finding_refs']))
                if check['status']=='gap' or (old['status']=='not_relevant' and check['status']=='assessed'):old['status']=check['status']
                if check['reason'] not in old['reason']:old['reason']+='; '+check['reason']
    # Topic modules are optional organization; overflow retains all actual findings.
    if len(modules)>8:
        modules={'research_details':{'module_id':'research_details','title':'Complete research ledger','intro':'All batches reviewed independently; See each item of evidence and its limitations.','finding_refs':[f['finding_id'] for f in out['findings']],'gaps':out.get('missing_evidence',[])}}
    out['modules']=list(modules.values());out['depth_review']={'research_depth':original['research_depth'],'checks':list(checks.values())}
    # Use reviewed summary, never keep unsupported claims from the original summary.
    out['summary']='\n\n'.join(dict.fromkeys(v['result']['summary'] for v in values))
    return out
