"""Live, explicitly unreviewed work and actionable interruption reasons."""
import hashlib,json,time
from pathlib import Path
from . import store as s

def read(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return default

def reason(job):
    error=job.get('error','');text=error.casefold();code=None
    if job.get('cancel_requested') or job['status']=='cancelled':code='user_stop'
    elif error:
        if 'TransportPreflightError' in error:code='provider_configuration'
        elif 'APIConnectionError' in error or 'APITimeoutError' in error:code='provider_connection'
        elif any(x in text for x in ('time limit','execution seconds','timeouterror')):code='time_budget'
        elif 'quota' in text:code='account_quota'
        elif any(x in text for x in ('budget','step limit')):code='task_budget'
        elif 'api' in text or 'provider' in text:code='provider_response'
        elif 'interrupted' in text or 'restart' in job.get('stage','').casefold():code='service_interrupted'
        elif 'review' in text or 'validation' in text:code='review_incomplete'
        elif 'progress' in text or 'output incomplete' in text:code='execution_stalled'
        else:code='execution_error'
    elif job['status']=='paused':code='unknown_legacy_stop'
    if not code:return None
    labels={
        'user_stop':('You requested that this task stop.','Existing materials can be viewed and downloaded; Continue when needed.'),
        'time_budget':('Execution time limit reached for this turn.','Current progress saved; Continuation receives a new turn budget from current administrator settings.'),
        'account_quota':('Account or daily quota is insufficient to reserve the next call.','Existing materials are available; Continue after the administrator replenishes quota.'),
        'task_budget':('Model calls this turn or Token Budget exhausted.','Current progress saved; Continuation uses a new turn budget, Accumulated cost is retained.'),
        'provider_connection':('Model service connection interrupted or response timed out.','This turn stopped, Do not automatically repeat potentially billable requests; Review the available materials before continuing.'),
        'provider_configuration':('Model configuration or service address check failed, No request sent yet.','This preflight did not consume model Token; Existing materials retained, Ask the administrator to check the configuration before continuing.'),
        'provider_response':('Model service returned an error or incomplete response.','Existing materials retained; Continue later, or ask your administrator to check the model service.'),
        'service_interrupted':('Execution service interrupted or restarted.','Existing materials and usage retained, Potentially billable requests were not automatically resent.'),
        'review_incomplete':('Conclusion review is incomplete.','View original sources and the unreviewed ledger first, Finish review before relying on final conclusions.'),
        'execution_stalled':('Execution made no valid progress or returned incomplete output.','Repeated requests stopped, Existing materials are available; Adjust the research direction when continuing.'),
        'execution_error':('An error occurred during execution.','Existing materials are available; The administrator can inspect the corresponding error record.'),
        'unknown_legacy_stop':('This historical task has no recorded identifiable stop reason.','Existing materials are available; New tasks record a specific stop reason.'),
    }
    message,next_step=labels[code]
    return {'code':code,'message':message,'next_step':next_step}

def snapshot(job):
    from .confidentiality import source_view,evidence_view,clean_value
    from .tools import r
    root=Path(job['artifact_root']);sources=read(root/'sources.json',[]);evidence=read(root/'evidence.json',[])
    draft=read(root/'result.json',{})
    findings={f['finding_id']:f for f in draft.get('findings',[]) if f.get('finding_id')}
    findings.update({f['finding_id']:f for f in read(root/'findings-ledger.json',[]) if f.get('finding_id')})
    # A published report is a separate, reviewed snapshot. Never grant this live
    # inventory reviewed status, even when some quotations are mechanically valid.
    rows=clean_value([{k:f.get(k) for k in ('finding_id','statement','kind','evidence_refs','limitations')} for f in findings.values()])
    def has_text(source):
        name=(source.get('artifacts') or {}).get('blocks','');path=(root/name).resolve()
        if not name.startswith('sources/') or not path.is_relative_to(root.resolve()):return False
        return any(str(b.get('text','')).strip() for b in read(path,[]))
    usable=sum(x.get('status') in ('complete_body','partial_body','snippet_only','supplied_text','structured_data') and has_text(x) for x in sources)
    files={p for row in sources for p in (row.get('artifacts') or {}).values() if isinstance(p,str) and p.startswith('sources/') and (root/p).resolve().is_relative_to(root.resolve()) and (root/p).is_file()}
    version=':'.join(str((root/name).stat().st_mtime_ns) if (root/name).exists() else '0' for name in ('sources.json','evidence.json','findings-ledger.json','result.json'))+f":{job['run']}:{job['status']}:{job.get('error','')}"
    version=hashlib.sha256(version.encode()).hexdigest()
    return {'updated_at':time.time(),'version':version,'run':job['run'],'status':job['status'],'stage':clean_value(job['stage']),
            'review_status':'unreviewed','stop_reason':reason(job),
            'counts':{'sources':len(sources),'usable_sources':usable,'failed_sources':sum(x.get('status') in r.BAD_SOURCE for x in sources),'evidence':len(evidence),'findings':len(rows),'archived_files':len(files)},
            'sources':[source_view(x) for x in sources],'evidence':[evidence_view(x) for x in evidence],'findings':rows}

def markdown(job,progress):
    lines=['# Stage materials(Conclusion review is not complete)','',job['question'],'',f"Task status: {job['status']}; Stage {job['run']} executions."]
    if progress['stop_reason']:lines.extend([progress['stop_reason']['message'],progress['stop_reason']['next_step']])
    lines+=['','The following work records were actually saved, Cannot be treated as a completed research conclusion.','',json.dumps(progress['counts'],ensure_ascii=False),'','## Unreviewed analysis ledger']
    for f in progress['findings']:lines.extend([f"- [{f['finding_id']}] {f['statement']}",f"  Type: {f['kind']}; Citation: {', '.join(f.get('evidence_refs') or [])}",*['  Limitations: '+x for x in (f.get('limitations') or [])]])
    lines+=['','## Archive sources']
    for source in progress['sources']:lines.append(f"- [{source['source_id']}] {source.get('title') or source.get('source_url') or 'Sources'} · {source.get('status')} · {source.get('final_url') or source.get('source_url') or ''}")
    return '\n'.join(lines)+'\n'

def checkpoint(job_id):
    job=s.get(job_id);root=Path(job['artifact_root']);root.mkdir(parents=True,exist_ok=True)
    progress=snapshot(job)
    from .tools import r
    r.write_json(root/'progress.json',progress)
    target=root/'progress.md';tmp=target.with_suffix('.md.tmp');tmp.write_text(markdown(job,progress),encoding='utf-8');tmp.replace(target)
    return progress
