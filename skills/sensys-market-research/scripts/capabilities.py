"""Bounded capability discovery, evidence retrieval and cross-skill handoff. No installs."""
from __future__ import annotations
import argparse
import collections
import json
import re
from pathlib import Path
import research as r

CATALOG = r.SKILL/'references/capability-catalog.json'
MODE_PATHS = {
 'needs':['vendor/coreyhaines31/marketingskills/skills/customer-research/SKILL.md'],
 'synthesis':['vendor/anthropics/knowledge-work-plugins/design/skills/research-synthesis/SKILL.md'],
 'competitors':['vendor/anthropics/knowledge-work-plugins/product-management/skills/competitive-brief/SKILL.md'],
 'voices':['vendor/ScrapeCreators/social-media-research-skills/skills/comment-mining/SKILL.md','references/voices.md'],
 'demand':['vendor/ScrapeCreators/social-media-research-skills/skills/product-demand-research/SKILL.md'],
 'crowdfunding':['references/crowdfunding.md'], 'sizing':['references/market-sizing.md'],
 'trends':['references/sources.md'],
 'validation':['vendor/anthropics/knowledge-work-plugins/design/skills/user-research/SKILL.md','references/methods.md'],
}
ROLE_STATES={'captured','partial','blocked','missing','not_relevant'}


def catalog(path=CATALOG):
    value=r.read_json(path)
    return value['items']


def lookup(query, kind=None, stage=None, limit=6, executable_only=False, path=CATALOG, offset=0):
    if not 1 <= limit <= 20: raise ValueError('Lookup limit must be between 1 and 20')
    if type(offset) is not int or offset<0:raise ValueError('Lookup offset must be a nonnegative integer')
    tokens=set(re.findall(r'[\w-]+',query.casefold()))
    rows=[]
    for item in catalog(path):
        if kind and item['kind']!=kind: continue
        if stage and stage not in item['stages']: continue
        if executable_only and item['availability']!='local_executor': continue
        names=' '.join([item['name'],*item.get('aliases',[])]).casefold()
        tags=' '.join(item.get('tags',[])).casefold()
        words=' '.join([names,tags,item['description']]).casefold()
        score=sum(5*(token in names)+2*(token in tags)+(token in item['description'].casefold()) for token in tokens)
        if tokens and all(token in words for token in tokens):score+=3
        if tokens and not score: continue
        boost=3 if item['availability']=='local_executor' else 2 if item['availability']=='bundled_instructions' else 0
        rows.append((score+boost,item))
    rows.sort(key=lambda x:(-x[0],x[1]['id']))
    unique=[];seen=set()
    for scored in rows:
        item=scored[1]
        key=(item['kind'],item.get('package_path') or item.get('upstream_url') or item['id'])
        if key not in seen:unique.append(scored);seen.add(key)
    rows=unique
    fields=['id','name','kind','description','stages','availability','resource_class','package_path']
    cards=[{k:v for k,v in x.items() if k in fields} for _,x in rows[offset:offset+limit]]
    more=offset+limit<len(rows)
    return {'matches':cards,'total_matches':len(rows),'truncated':more,'next_offset':offset+limit if more else None,
            'note':'Discovery metadata only; describe selected IDs and check actual executor/credentials before use.'}


def describe(item_id, path=CATALOG):
    return next((x for x in catalog(path) if x['id']==item_id),None) or (_ for _ in ()).throw(ValueError('Unknown capability ID'))


def context_manifest(modes, research_depth=None):
    if not modes or set(modes)-r.MODES: raise ValueError('Select valid modes')
    paths=['SKILL.md']
    for mode in modes: paths.extend(MODE_PATHS[mode])
    paths=list(dict.fromkeys(paths))
    rows=[]
    for rel in paths:
        path=r.inside(r.SKILL,rel)
        rows.append(dict(path=rel,sha256=r.sha(path.read_bytes()),bytes=path.stat().st_size))
    out = {'selected_modes':list(dict.fromkeys(modes)),'files':rows,
            'context_identity':r.sha(json.dumps(rows,sort_keys=True).encode()),
            'instruction':'Load only the current stage files. Stable ordering permits reuse; this is not proof of model-provider prompt-cache hits.'}
    if research_depth:
        # Selected profile only, rather than the full capability catalog or all methods.
        out['research_depth'] = research_depth
        out['profile'] = r.depth.profile(research_depth)
        out['context_identity'] = r.sha(json.dumps([rows, research_depth, out['profile']],sort_keys=True).encode())
    return out


def check_plan(root, plan, complete=False):
    errors=[]
    if not isinstance(plan,dict): return ['Coverage plan must be an object']
    if plan.get('schema_version')!='2.0': errors.append('Coverage plan schema_version must be 2.0')
    rows=plan.get('roles',[])
    if not isinstance(rows,list): return errors+['Coverage roles must be a list']
    if not rows: errors.append('Coverage plan needs decision-relevant roles')
    sources={s['source_id']:s for s in r.read_json(Path(root)/'sources.json')}
    seen=set()
    for role in rows:
        if not isinstance(role,dict):
            errors.append('Coverage role must be an object');continue
        key=role.get('role')
        if not isinstance(key,str):
            errors.append('Coverage role needs a string identifier');continue
        if not key or key in seen: errors.append('Missing/duplicate coverage role')
        seen.add(key)
        state=role.get('status')
        if state not in ROLE_STATES: errors.append(f'{key}: invalid coverage status')
        if not role.get('reason'): errors.append(f'{key}: scope reason required')
        refs=role.get('source_ids',[])
        if not isinstance(refs,list) or any(not isinstance(sid,str) for sid in refs):
            errors.append(f'{key}: source_ids must be a string list');continue
        if state in {'captured','partial'} and not refs: errors.append(f'{key}: captured role needs sources')
        for sid in refs:
            if sid not in sources: errors.append(f'{key}: unknown source {sid}')
            elif state in {'captured','partial'} and sources[sid]['status'] in r.BAD_SOURCE: errors.append(f'{key}: unusable source {sid}')
            elif state=='captured' and sources[sid]['status'] in {'snippet_only','partial_body'}: errors.append(f'{key}: excerpts/incomplete bodies require partial coverage')
        if state in {'partial','blocked','missing'} and not role.get('gap'): errors.append(f'{key}: missing coverage needs a gap')
        if role.get('required') and state=='not_relevant': errors.append(f'{key}: required role cannot be not_relevant')
        if complete and role.get('required') and state!='captured': errors.append(f'{key}: incomplete required role prevents complete status')
    return errors


def save_plan(root, plan):
    errors=check_plan(root,plan)
    if errors: raise ValueError('; '.join(errors))
    r.write_json(Path(root)/'research-plan.json',plan)
    return {'status':'saved','path':'research-plan.json','roles':len(plan['roles'])}


def retrieve(root, query='', source_id=None, limit=6, max_chars=1800, offset=0, char_start=None):
    if not 1<=limit<=20 or not 100<=max_chars<=10000: raise ValueError('Evidence retrieval budget out of range')
    if type(offset) is not int or offset<0 or (char_start is not None and (type(char_start) is not int or char_start<0)):
        raise ValueError('Evidence offsets must be nonnegative integers')
    tokens=set(re.findall(r'[\w-]+',query.casefold())); hits=[]
    for source in r.read_json(Path(root)/'sources.json'):
        if source_id and source['source_id']!=source_id: continue
        if source['status'] in r.BAD_SOURCE: continue
        if not r.source_integrity(root,source): raise ValueError('Evidence archive failed integrity verification')
        for block in r.read_json(r.inside(root,source['artifacts']['blocks'])):
            text=block['text']; score=sum(token in text.casefold() for token in tokens)
            if tokens and not score: continue
            positions=[match.start() for token in tokens for match in re.finditer(re.escape(token),text,re.I)]
            start=max(0,min(positions)-max_chars//3) if positions and len(text)>max_chars else 0
            start=min(start,max(0,len(text)-max_chars)) if char_start is None else min(char_start,len(text))
            end=min(len(text),start+max_chars)
            hits.append((score,{'source_id':source['source_id'],'block_id':block['block_id'],
               'text':text[start:end],'char_start':start,'char_end':end,'truncated':start>0 or end<len(text),
               'original_url':source.get('source_url') or source['final_url'],
               'acquisition_status':source['status'],'retrieved_at':source['retrieved_at'],
               'origin_id':source['origin_id'],'raw_path':source['artifacts']['raw']}))
    hits.sort(key=lambda x:-x[0])
    more=offset+limit<len(hits)
    return {'blocks':[x for _,x in hits[offset:offset+limit]],'total_matches':len(hits),'truncated':more,'next_offset':offset+limit if more else None}


def handoff(root):
    root=Path(root);result=r.read_json(root/'result.json')
    sources=r.read_json(root/'sources.json');evidence=r.read_json(root/'evidence.json')
    plan=r.read_json(root/'research-plan.json') if (root/'research-plan.json').exists() else None
    checked=r.validate(root)
    envelope=dict(schema_version='2.0',task_id=result['task_id'],status=result['status'],
         executed_scope=result.get('executed_scope',[]),summary=result['summary'],findings=result['findings'],
         validation=checked,coverage=plan,
         provenance=[{k:s.get(k) for k in ['source_id','origin_id','duplicate_of','status','source_url','requested_url','final_url','retrieved_at','published_at','acquisition_method','artifacts','raw_sha256']} for s in sources],
         evidence_index=[{k:e.get(k) for k in ['evidence_id','source_id','block_id','evidence_role']} for e in evidence],
         conflicts=result.get('conflicts',[]),missing_evidence=result.get('missing_evidence',[]),
         assumptions=result.get('assumptions',[]),next_steps=result.get('next_steps',[]),
         failed_sources=list(dict.fromkeys(s['source_id'] for s in sources if s['status'] in r.BAD_SOURCE)),
         artifact_root='.',created_at=r.now(),note='Paths are relative to the accompanying task bundle; IDs are scoped by task_id. Validation is mechanical plus declared host semantic review.')
    if (root/'research-budget.json').exists():
        envelope.update(research_depth=result.get('research_depth'), research_budget=r.depth.status(root), depth_review=result.get('depth_review'))
    r.write_json(root/'handoff.json',envelope)
    return envelope


def cache_stats(root):
    p=Path(root)/'cache-events.json';events=r.read_json(p) if p.exists() else []
    counts=collections.Counter((x['operation'],x['status']) for x in events)
    return {'recorded_events':len(events),'counts':{f'{op}_{state}':n for (op,state),n in counts.items()},
            'note':'Task artifact/query reuse, not model-provider prompt-cache or estimated token savings.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('lookup');p.add_argument('--query',default='');p.add_argument('--kind',choices=['tool','skill','source','host_skill']);p.add_argument('--stage');p.add_argument('--limit',type=int,default=6);p.add_argument('--executable-only',action='store_true')
    p=commands.add_parser('describe');p.add_argument('--id',required=True)
    p=commands.add_parser('context');p.add_argument('--modes',required=True);p.add_argument('--depth',choices=['standard','deep'])
    commands.add_parser('profiles')
    p=commands.add_parser('depth');p.add_argument('--task',required=True);p.add_argument('--select',choices=['standard','deep'],required=True);p.add_argument('--reason',required=True)
    p=commands.add_parser('round');p.add_argument('--task',required=True);p.add_argument('--reason',required=True);p.add_argument('--gap',action='append',required=True)
    p=commands.add_parser('plan');p.add_argument('--task',required=True);p.add_argument('--file',required=True)
    p=commands.add_parser('retrieve');p.add_argument('--task',required=True);p.add_argument('--query',default='');p.add_argument('--source');p.add_argument('--limit',type=int,default=6);p.add_argument('--max-chars',type=int,default=1800)
    for name in ['handoff','cache-stats','budget']:
        p=commands.add_parser(name);p.add_argument('--task',required=True)
    args=parser.parse_args()
    try:
        if args.command=='lookup':out=lookup(args.query,args.kind,args.stage,args.limit,args.executable_only)
        elif args.command=='describe':out=describe(args.id)
        elif args.command=='context':out=context_manifest(args.modes.split(','),args.depth)
        elif args.command=='profiles':out=r.depth.profiles()
        elif args.command=='depth':out=r.depth.select(args.task,args.select,args.reason)
        elif args.command=='round':out=r.depth.next_round(args.task,args.reason,args.gap)
        elif args.command=='budget':out=r.depth.status(args.task)
        elif args.command=='plan':out=save_plan(args.task,r.read_json(args.file))
        elif args.command=='retrieve':out=retrieve(args.task,args.query,args.source,args.limit,args.max_chars)
        elif args.command=='handoff':out=handoff(args.task)
        else:out=cache_stats(args.task)
        print(json.dumps(out,ensure_ascii=False,indent=2));return 0
    except (ValueError,KeyError,OSError) as exc:
        print(json.dumps({'status':'failed','error':type(exc).__name__,'message':str(exc)}));return 2


if __name__=='__main__': raise SystemExit(main())
