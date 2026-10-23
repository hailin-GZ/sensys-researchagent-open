"""Authenticated task routes and bounded, task-owned artifact downloads."""
import hashlib, json, re, secrets, time
import tempfile,zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from . import store as s

def get(handler,key_id=None,admin=False):
    u=urlsplit(handler.path);args=parse_qs(u.query);jid=args.get('id',[''])[0]
    from . import conversations
    if u.path=='/api/conversations':return handler.send(200,{'conversations':conversations.list_threads(key_id)})
    if u.path=='/api/conversation':return handler.send(200,conversations.detail(jid,key_id,include_reports=admin))
    if u.path=='/api/conversation/stages':
        if not admin:raise s.control().Error('Endpoint not found.',404)
        return handler.send(200,conversations.stages(jid,key_id))
    if u.path=='/api/jobs':return handler.send(200,{'jobs':s.records(key_id),'settings':s.settings() if admin else None})
    if u.path=='/api/job/status':
        j=s.get(jid,key_id)
        value={k:j[k] for k in ('id','kind','thread_id','status','stage','run','tokens','elapsed_ms','error','cancel_requested')}
        from .progress import reason
        value['stop_reason']=reason(j)
        if not admin:
            from .confidentiality import clean_text
            value['stage']=clean_text(value['stage']);value['error']=(value['stop_reason'] or {}).get('message','This turn is incomplete, Continue later.') if value['error'] else ''
        if j['started']:value['elapsed_ms']+=int((time.time()-j['started'])*1000)
        return handler.send(200,value)
    if u.path=='/api/job':
        try:after=int(args.get('after',['0'])[0])
        except ValueError:raise s.control().Error('Invalid event position.')
        detail=s.detail(jid,key_id,after)
        if not admin:
            # Tool arguments can be huge and belong to the optimization console.
            detail.pop('calls',None)
        return handler.send(200,detail)
    if u.path=='/api/job/result':return handler.send(200,s.bundle(jid,key_id))
    if u.path=='/api/job/export':return handler.send(200,s.bundle(jid,key_id),download=True)
    if u.path=='/api/job/package':return package(handler,jid,key_id,admin)
    if u.path=='/api/artifact':
        j=s.get(jid,key_id);root=Path(j['artifact_root']);name=args.get('path',[''])[0]
        # Only artifacts explicitly registered by the helper may be served.
        allowed={'report.md','brief.json','result.json','sources.json','evidence.json','research-plan.json','research-budget.json','validation.json','support-review.json','handoff.json'} if admin else set(user_artifacts(root))
        if not admin and name in {'result.json','sources.json','evidence.json','report.md','validation.json'}:
            bundle=s.bundle(jid,key_id);value=bundle['report'] if name=='report.md' else json.dumps(bundle[name.removesuffix('.json')],ensure_ascii=False,indent=2)
            return handler.send(200,value.encode('utf-8'),'application/octet-stream',download=True)
        manifest=root/'sources.json'
        if admin and manifest.exists():
            for source in json.loads(manifest.read_text(encoding='utf-8')):
                allowed.update(v for v in source.get('artifacts',{}).values() if isinstance(v,str))
                registry=source.get('artifacts',{}).get('assets')
                if registry and (root/registry).exists():
                    for row in json.loads((root/registry).read_text(encoding='utf-8')):
                        if isinstance(row,dict) and row.get('status')=='saved' and row.get('path'):allowed.add((Path(source['artifacts']['markdown']).parent/row['path']).as_posix())
        path=(root/name).resolve()
        if name not in allowed or not path.is_relative_to(root.resolve()) or not path.is_file():raise s.control().Error('Material not found or access denied.',404)
        if not admin and not artifact_safe(path):raise s.control().Error('This original contains protected information, See the evidence excerpts in the report.',403)
        # Force attachment for imported HTML/SVG/documents; never execute source content in app origin.
        return handler.send(200,path.read_bytes(),'application/octet-stream',download=True)
    return handler.send(404,{'error':'Endpoint not found.'})

def user_artifacts(root):
    """Explicit source data only. Never include source.json, runs or model receipts."""
    from .confidentiality import source_view
    allowed=set();manifest=root/'sources.json'
    for source in json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else []:
        artifacts=source_view(source)['artifacts'];allowed.update(artifacts.values())
        registry=artifacts.get('assets')
        if registry and (root/registry).resolve().is_relative_to(root.resolve()) and (root/registry).is_file():
            for row in json.loads((root/registry).read_text(encoding='utf-8')):
                if row.get('status')=='saved' and row.get('path'):
                    name=(Path(artifacts['markdown']).parent/row['path']).as_posix()
                    if (root/name).resolve().is_relative_to(root.resolve()):allowed.add(name)
    return allowed

def artifact_safe(path):
    from .confidentiality import contains_secret
    # Preserve original bytes/hashes. Suppress a contaminated original rather than
    # silently editing it and calling the edited bytes an original.
    data=path.read_bytes()
    return not contains_secret(data.decode('utf-8',errors='ignore'))

def upload(handler,key_id):
    c=s.control();s.init()
    # Closed-beta notice is agreed before access keys are issued.
    try:length=int(handler.headers.get('Content-Length','0'))
    except ValueError:raise c.Error('Invalid material size.')
    if not 0<length<=20*1024*1024:raise c.Error('Materials must be within20MBwithin.',413)
    from urllib.parse import unquote
    name=unquote(handler.headers.get('X-File-Name','material.txt'))
    if not 1<=len(name)<=200 or '/' in name or '\\' in name:raise c.Error('Invalid file name.')
    suffix=Path(name).suffix.lower()
    if suffix not in ('.pdf','.docx','.xlsx','.csv','.txt','.md','.json','.png','.jpg','.jpeg'):raise c.Error('Unsupported material format.')
    with c.store() as d:
        s.check_key(d,key_id)
        if d.execute('SELECT COUNT(*) FROM research_uploads WHERE key_id=?',(key_id,)).fetchone()[0]>=80:raise c.Error('Material storage limit reached, Ask your administrator to review the task.',429)
    raw=handler.rfile.read(length)
    if len(raw)!=length:raise c.Error('Material upload incomplete.')
    uid=secrets.token_hex(16);folder=s.RUNTIME/'uploads';folder.mkdir(parents=True,exist_ok=True);path=folder/(uid+suffix);path.write_bytes(raw)
    with c.store() as d:d.execute('INSERT INTO research_uploads VALUES(?,?,?,?,?,?,?)',(uid,key_id,name,str(path),length,hashlib.sha256(raw).hexdigest(),time.time()))
    return handler.send(200,{'id':uid,'name':name,'bytes':length})


def package(handler,jid,key_id,admin):
    j=s.get(jid,key_id);root=Path(j['artifact_root']);buffer=tempfile.SpooledTemporaryFile(max_size=2*1024*1024,mode='w+b');bundle=s.bundle(jid,key_id)
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        names=('brief.json','result.json','sources.json','evidence.json','report.md','research-plan.json','research-budget.json','validation.json','support-review.json','handoff.json') if admin else ('result.json','sources.json','evidence.json','report.md','validation.json')
        for name in names:
            path=root/name
            key=name.removesuffix('.json').replace('-','_')
            if name=='report.md' and bundle.get('report'):archive.writestr(name,bundle['report'])
            elif name.endswith('.json') and bundle.get(key) is not None:archive.writestr(name,json.dumps(bundle[key],ensure_ascii=False,indent=2))
            elif admin and path.is_file():archive.write(path,name)
        if not admin:
            from .progress import markdown
            if bundle.get('progress'):
                archive.writestr('progress.json',json.dumps(bundle['progress'],ensure_ascii=False,indent=2))
                archive.writestr('progress.md',markdown(j,bundle['progress']))
            for name in user_artifacts(root):
                path=(root/name).resolve()
                if path.is_file() and path.is_relative_to(root.resolve()) and artifact_safe(path):archive.write(path,name)
        for folder in ('sources','runs') if admin else ():
            for path in (root/folder).rglob('*') if (root/folder).exists() else []:
                if path.is_file() and path.resolve().is_relative_to(root.resolve()):archive.write(path,path.relative_to(root).as_posix())
    try:
        if hasattr(handler,'send_stream'):return handler.send_stream(200,buffer,'application/zip','sensys-evidence-package.zip')
        buffer.seek(0);return handler.send(200,buffer.read(),'application/zip',download=True)
    finally:buffer.close()
