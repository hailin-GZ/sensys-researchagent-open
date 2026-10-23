"""Strict provider schemas and local validation share one declared tool contract."""
import copy, inspect, json
from jsonschema import Draft202012Validator
from . import schemas
from .public_data import ROUTES as PUBLIC_DATA_ROUTES

MODES=['needs','synthesis','competitors','voices','demand','crowdfunding','sizing','trends','validation']
ROLES=['official_product','user_voices','crowdfunding','statistics_surveys','independent_reports','scientific_research','patents','supplied_research']
STATES=['captured','partial','blocked','missing','not_relevant']
ROLE=schemas.obj({'role':{'type':'string','enum':ROLES},'required':{'type':'boolean'},'reason':schemas.STRING,'status':{'type':'string','enum':STATES},'source_ids':schemas.strings(),'gap':schemas.STRING})
PLAN=schemas.obj({'schema_version':{'type':'string','enum':['2.0']},'decision':schemas.STRING,'selected_capability_ids':schemas.strings(),'excluded_modes':{'type':'array','items':schemas.obj({'mode':{'type':'string','enum':MODES},'reason':schemas.STRING})},'roles':{'type':'array','items':ROLE,'minItems':1,'maxItems':8}})
QUOTE=schemas.obj({'source_id':schemas.STRING,'block_id':schemas.STRING,'quote':schemas.STRING,'role':{'type':['string','null']},'context':{'type':['string','null']}})

def build(executor, definitions):
    out=copy.deepcopy(definitions)
    for tool in out:
        name=tool['name'];p=tool['parameters']['properties']
        if name in ('configure_research','prepare_research','load_methods'):p['modes']={'type':'array','items':{'type':'string','enum':MODES},'maxItems':9}
        if name=='configure_research':p['modes']['minItems']=1
        if name=='prepare_research':p['coverage_plan']=copy.deepcopy(PLAN);p['modes']['minItems']=1
        if name=='set_phase':
            p['phase']={'type':'string','enum':['decision','execution','analysis','review','explanation']}
            p['effort']={'type':'string','enum':['low','medium','high']}
        if name=='platform_read':p['route']={'type':'string','enum':['google_play_reviews','rss','hackernews','hackernews_comments','discourse_thread','crossref','pubmed','pubmed_abstract','europepmc_search','europepmc_fulltext',*PUBLIC_DATA_ROUTES]}
        if name=='register_evidence_batch':p['items']={'type':'array','items':QUOTE,'minItems':1,'maxItems':12}
        if name=='record_findings':p['items']={'type':'array','items':copy.deepcopy(schemas.FINDING),'minItems':1,'maxItems':20}
        if name=='save_coverage_plan':
            p['json']=copy.deepcopy(PLAN);tool['description']='Save the structured source-role coverage plan. Keep every role current after acquisition; incomplete required roles prevent complete status.'
        if name=='save_research_result':
            p['json']=copy.deepcopy(schemas.RESULT);tool['description']='Save a structured draft using already registered evidence IDs. The host independently reviews claims AND refreshes coverage before publishing. Missing decisive evidence means partial.'
        signature=inspect.signature(getattr(executor,'tool_'+name))
        params={k:v for k,v in signature.parameters.items() if k!='self'}
        if set(params)!=set(p):raise ValueError('Tool declaration/handler mismatch: '+name)
        for key,param in params.items():
            if param.default is not inspect.Parameter.empty:
                spec=p[key];types=spec.get('type');spec['type']=[types,'null'] if isinstance(types,str) else list(dict.fromkeys((types or [])+['null']))
                if 'enum' in spec:spec['enum'].append(None)
        tool['parameters']['required']=list(p);tool['strict']=True
        Draft202012Validator.check_schema(tool['parameters'])
    return out

def clean_nulls(value):
    if isinstance(value,dict):return {k:clean_nulls(v) for k,v in value.items() if v is not None}
    if isinstance(value,list):return [clean_nulls(v) for v in value]
    return value

def prepare(executor,name,args,definitions):
    declared=next((t for t in definitions if t['name']==name),None)
    if declared is None:raise ValueError('Unknown tool. Registered names: '+', '.join(t['name'] for t in definitions))
    if isinstance(args,str):
        try:args=json.loads(args)
        except json.JSONDecodeError:raise ValueError('Invalid JSON arguments; send one complete object, not truncated JSON') from None
    if not isinstance(args,dict):raise ValueError('Tool arguments must be an object')
    value=copy.deepcopy(args)
    for key,param in inspect.signature(getattr(executor,'tool_'+name)).parameters.items():
        if key!='self' and key not in value and param.default is not inspect.Parameter.empty:value[key]=None
    if name in ('save_coverage_plan','save_research_result') and isinstance(value.get('json'),str):
        try:value['json']=json.loads(value['json'])
        except json.JSONDecodeError:raise ValueError('Invalid saved JSON; pass the structured object') from None
    if name=='register_evidence_batch' and isinstance(value.get('items'),list):
        for q in value['items']:
            if isinstance(q,dict):q.setdefault('role',None);q.setdefault('context',None)
    schema=copy.deepcopy(declared['parameters'])
    if name=='save_research_result':
        result=schema['properties']['json'];result.pop('required',None);result['additionalProperties']=True
    errors=list(Draft202012Validator(schema).iter_errors(value))
    if errors:
        error=errors[0];where='.'.join(str(x) for x in error.absolute_path) or 'arguments'
        raise ValueError(f'{where}: violates {error.validator}; correct the declared tool schema before retrying')
    return clean_nulls(value)

def for_task(definitions,evidence_ids,depth):
    out=copy.deepcopy(definitions)
    if depth=='standard':next(x for x in out if x['name']=='set_phase')['parameters']['properties']['effort']['enum']=['low','medium',None]
    target=next(x for x in out if x['name']=='save_research_result')['parameters']['properties']['json']
    refs=target['properties']['findings']['items']['properties']['evidence_refs']
    if evidence_ids:refs['items']={'type':'string','enum':list(evidence_ids)}
    else:refs['maxItems']=0
    target['properties']['depth_review']['properties']['research_depth']['enum']=[depth]
    return out
