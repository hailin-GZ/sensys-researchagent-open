"""Structured output contracts: topic labels cannot replace evidence-confidence kinds."""
import copy
STRING={'type':'string'}
def strings():return {'type':'array','items':STRING}
def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
FINDING=obj({'finding_id':STRING,'statement':STRING,'kind':{'type':'string','enum':['fact','source_opinion','inference','hypothesis','unknown']},'evidence_refs':strings(),'limitations':strings()})
CHECK=obj({'check':{'type':'string','enum':['decision_scope','source_roles','contrary_evidence','next_validation','segments_and_situations','payment_evidence','product_risks','independent_crosschecks']},'status':{'type':'string','enum':['assessed','gap','not_relevant']},'reason':STRING,'finding_refs':strings()})
RESULT=obj({'status':{'type':'string','enum':['complete','partial','needs_input']},'summary':STRING,'findings':{'type':'array','items':FINDING},'conflicts':strings(),'missing_evidence':strings(),'assumptions':strings(),'next_steps':strings(),'depth_review':obj({'research_depth':{'type':'string','enum':['standard','deep']},'checks':{'type':'array','items':CHECK}})})
QUOTE=obj({k:STRING for k in ('source_id','block_id','quote','role','context','ref')})
DRAFT=obj({'new_quotes':{'type':'array','items':QUOTE},'result':RESULT})
COVERAGE_UPDATE=obj({'role':STRING,'status':{'type':'string','enum':['captured','partial','blocked','missing','not_relevant']},'source_ids':strings(),'gap':STRING})
MODULE=obj({'module_id':STRING,'title':STRING,'intro':STRING,'finding_refs':strings(),'gaps':strings()})
REVIEW_RESULT=copy.deepcopy(RESULT)
REVIEW_RESULT['properties']['modules']={'type':'array','items':MODULE,'minItems':1,'maxItems':8}
REVIEW_RESULT['required'].append('modules')
REVIEW=obj({'result':REVIEW_RESULT,'review_notes':strings(),'coverage_updates':{'type':'array','items':COVERAGE_UPDATE}})

def validate_modules(result):
    """Topic grouping is distinct from evidence confidence; no invented refs."""
    modules=result.get('modules')
    if modules is None:return  # old deliveries
    import re
    if not isinstance(modules,list) or not 1<=len(modules)<=8:raise ValueError('Invalid result modules')
    findings={f['finding_id'] for f in result.get('findings',[])};seen=set();assigned=set()
    for m in modules:
        mid=m.get('module_id','');title=m.get('title','');refs=m.get('finding_refs');gaps=m.get('gaps')
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}',mid) or mid in seen or mid in ('overview','evidence','needs','competitors'):raise ValueError('Invalid or duplicate module ID')
        if not isinstance(title,str) or not 1<=len(title.strip())<=24:raise ValueError('Invalid module title')
        if not isinstance(refs,list) or not set(refs)<=findings or len(refs)!=len(set(refs)):raise ValueError('Module cites unknown/duplicate finding')
        if not isinstance(gaps,list) or (not refs and not gaps):raise ValueError('Empty module without findings or explicit gaps')
        if not isinstance(m.get('intro'),str) or len(m['intro'])>800:raise ValueError('Invalid module introduction')
        seen.add(mid);assigned.update(refs)
    if assigned!=findings:raise ValueError('Modules must organize every actual finding')

def draft_schema(evidence_ids,new_quote_limit=6):
    value=copy.deepcopy(DRAFT)
    value['properties']['new_quotes']['maxItems']=new_quote_limit
    value['properties']['result']['properties']['findings']['items']['properties']['evidence_refs']['items']={'type':'string','enum':list(evidence_ids)+[f'q{i}' for i in range(1,new_quote_limit+1)]}
    return value

def review_schema(evidence_ids,roles=None,source_ids=None):
    value=copy.deepcopy(REVIEW);refs=value['properties']['result']['properties']['findings']['items']['properties']['evidence_refs']
    if evidence_ids:refs['items']={'type':'string','enum':list(evidence_ids)}
    else:refs['maxItems']=0
    updates=value['properties']['coverage_updates']
    if roles:
        updates['items']['properties']['role']={'type':'string','enum':list(roles)}
        if source_ids:updates['items']['properties']['source_ids']['items']={'type':'string','enum':list(source_ids)}
        else:updates['items']['properties']['source_ids']['maxItems']=0
    else:updates['maxItems']=0
    return value

def normalize_findings(value):
    """Conservatively accept legacy topical kind labels while keeping the original label."""
    for f in value.get('findings',[]):
        kind=f.get('kind')
        if kind not in ('fact','source_opinion','inference','hypothesis','unknown'):
            f['dimension']=str(kind)
            f['kind']='unknown' if kind in ('evidence_gap','scientific_gap','commercial_unknown') or not f.get('evidence_refs') else 'inference'
    return value
