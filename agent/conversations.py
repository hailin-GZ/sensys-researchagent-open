"""Owner-scoped conversations group research jobs without rewriting old evidence."""
import json, secrets, time
from pathlib import Path
from . import store as s

def migrate(d):
    d.execute('CREATE TABLE IF NOT EXISTS research_threads(id TEXT PRIMARY KEY,key_id TEXT NOT NULL,title TEXT NOT NULL,created REAL NOT NULL,legacy_id TEXT)')
    if 'thread_id' not in {x['name'] for x in d.execute('PRAGMA table_info(research_jobs)')}:
        d.execute('ALTER TABLE research_jobs ADD COLUMN thread_id TEXT')
    d.execute('CREATE INDEX IF NOT EXISTS research_jobs_thread ON research_jobs(thread_id)')
    for j in d.execute('SELECT id,key_id,question,created FROM research_jobs WHERE thread_id IS NULL').fetchall():
        tid='chat-'+j['id'];d.execute('INSERT OR IGNORE INTO research_threads VALUES(?,?,?,?,NULL)',(tid,j['key_id'],j['question'][:80],j['created']))
        d.execute('UPDATE research_jobs SET thread_id=? WHERE id=?',(tid,j['id']))
    for j in d.execute('SELECT id,key_id,question,created FROM conversations').fetchall():
        d.execute('INSERT OR IGNORE INTO research_threads VALUES(?,?,?,?,?)',('legacy-'+j['id'],j['key_id'],j['question'][:80],j['created'],j['id']))

def owned(d,tid,key_id=None):
    row=d.execute('SELECT * FROM research_threads WHERE id=?',(tid,)).fetchone()
    if not row or key_id is not None and row['key_id']!=key_id:raise s.control().Error('Conversation not found or access denied.',404)
    return dict(row)

def attach(d,key_id,question,tid=None):
    if tid:
        if not isinstance(tid,str) or len(tid)>80:raise s.control().Error('Invalid conversation identifier.')
        t=owned(d,tid,key_id)
        if t['legacy_id']:raise s.control().Error('Legacy records are read-only, Start a new chat.')
        return tid
    tid=secrets.token_hex(12);d.execute('INSERT INTO research_threads VALUES(?,?,?,?,NULL)',(tid,key_id,question[:80],time.time()));return tid

def list_threads(key_id=None):
    with s.control().store() as d:
        rows=d.execute('SELECT t.*,k.label,k.deleted FROM research_threads t LEFT JOIN access_keys k ON k.id=t.key_id '+('WHERE t.key_id=? ' if key_id is not None else '')+'ORDER BY t.created DESC',(key_id,) if key_id is not None else ()).fetchall()
        out=[]
        for row in rows:
            t=dict(row);jobs=d.execute('SELECT id,kind,status,created,tokens FROM research_jobs WHERE thread_id=? ORDER BY created',(t['id'],)).fetchall()
            t.update(job_count=sum(x['kind']=='research' for x in jobs),message_count=len(jobs),latest_job=jobs[-1]['id'] if jobs else None,status=jobs[-1]['status'] if jobs else 'answered',tokens=sum(x['tokens'] for x in jobs),updated=jobs[-1]['created'] if jobs else t['created'])
            if t['legacy_id']:
                old=d.execute('SELECT tokens,status FROM conversations WHERE id=?',(t['legacy_id'],)).fetchone();t.update(tokens=old['tokens'],status=old['status'])
            out.append(t)
        return sorted(out,key=lambda x:x['updated'],reverse=True)

def detail(tid,key_id=None,*,include_reports=True):
    with s.control().store() as d:
        t=owned(d,tid,key_id);t['label']=(d.execute('SELECT label FROM access_keys WHERE id=?',(t['key_id'],)).fetchone() or {'label':'Key deleted'})['label']
        ids=[x['id'] for x in d.execute('SELECT id FROM research_jobs WHERE thread_id=? ORDER BY created',(tid,))]
        messages=[dict(x) for x in d.execute('SELECT m.* FROM research_messages m JOIN research_jobs j ON j.id=m.job_id WHERE j.thread_id=? ORDER BY m.created,m.id',(tid,))]
        if t['legacy_id']:
            old=d.execute('SELECT * FROM conversations WHERE id=?',(t['legacy_id'],)).fetchone();messages=[{'role':'user','text':old['question'],'created':old['created']},{'role':'assistant','text':old['answer'],'created':old['created']}]
    jobs=[s.public(j,key_id,include_messages=False) for j in ids]
    if not include_reports:
        # Report bodies are fetched only for the selected delivery. The stored
        # delivery marker belongs to the host after publication, never the user.
        for m in messages:
            if m['role']=='assistant' and m['text'].startswith('# Research Result'):
                m['report']={'result':{'support_reviewed':True}}
        for j in jobs:j.pop('answer',None)
        out={**t,'jobs':jobs,'messages':messages}
        if key_id is not None:
            from .confidentiality import public_chat
            out=public_chat(out)
        return out
    deliveries={}
    for j in jobs:
        root=Path(s.get(j['id'],key_id)['artifact_root']);candidates=[]
        for path in (root/'runs').glob('*') if (root/'runs').exists() else []:
            if path.is_dir():candidates.append(s.artifact_bundle(path))
        candidates.append(s.bundle(j['id'],key_id))
        deliveries[j['id']]=[b for b in candidates if (b.get('result') or {}).get('support_reviewed') and (b.get('validation') or {}).get('ok')]
    for m in messages:
        if m['role']=='assistant' and m['text'].startswith('# Research Result'):
            eligible=[b for b in deliveries.get(m.get('job_id'),[]) if (b.get('support_review') or {}).get('reviewed_at',0)<=m['created']+2]
            if eligible:
                b=max(eligible,key=lambda b:(b.get('support_review') or {}).get('reviewed_at',0))
                m['report']={k:b.get(k) for k in ('result','evidence','sources')}
    for j in jobs:j.pop('messages',None);j.pop('answer',None)
    out={**t,'jobs':jobs,'messages':messages}
    if key_id is not None:
        from .confidentiality import public_chat
        out=public_chat(out)
    return out

def stages(tid,key_id=None):
    chat=detail(tid,key_id);out=[]
    for j in chat['jobs']:
        full=s.detail(j['id'],key_id)
        runs=sorted({x['run'] for x in full['calls']}|({j['run']} if j['run'] else {1}))
        for run in runs:
            calls=[x for x in full['calls'] if x['run']==run];events=[x for x in full['events'] if not calls or min(c['started'] for c in calls)<=x['created']<=max(c.get('finished') or time.time() for c in calls)+2]
            methods=set();tool_counts={};method_details_incomplete=False
            for x in calls:
                if x['kind']!='tool':continue
                tool_counts[x['name']]=tool_counts.get(x['name'],0)+1
                if x['name']=='load_methods' and x['status']=='succeeded':
                    try:value=json.loads(x['details']).get('result',{})
                    except (ValueError,TypeError):
                        trace=Path(s.get(j['id'],key_id)['artifact_root'])/'tool-results'/(x['id']+'.json')
                        try:value=json.loads(trace.read_text(encoding='utf-8'))
                        except (OSError,ValueError):
                            method_details_incomplete=True;continue
                    methods.update(y['path'] for y in value.get('files',[]))
            root=Path(s.get(j['id'],key_id)['artifact_root']);snapshot=next((p for p in (root/'runs').glob(str(run)+'-*') if p.is_dir()),None)
            bundle=s.artifact_bundle(snapshot) if snapshot else s.bundle(j['id'],key_id) if run==j['run'] else {}
            if not snapshot and bundle.get('publication',{}).get('run')!=run:bundle={}
            start=min((c['started'] for c in calls),default=j['created']);end=max((c.get('finished') or time.time() for c in calls),default=start)
            questions=[m for m in chat['messages'] if m.get('job_id')==j['id'] and m['role']=='user' and m['created']<=start+1]
            question=max(questions,key=lambda m:m['created'])['text'] if questions else j['question']
            replies=[m['text'] for m in chat['messages'] if m.get('job_id')==j['id'] and m['role']=='assistant' and start<=m['created']<=end+5]
            out.append({'id':j['id']+':'+str(run),'job_id':j['id'],'kind':j['kind'],'run':run,'question':j['question'],'depth':bundle.get('result',{}).get('research_depth',j['depth']) if bundle.get('result') else j['depth'],'status':j['status'] if run==j['run'] else (bundle.get('result') or {}).get('status','paused'),'tokens':sum(x['total_tokens'] for x in calls),'elapsed_ms':int((end-start)*1000),'answer':replies[-1] if replies and not replies[-1].startswith('# Research Result') else '', 'tools':tool_counts,'method_files':sorted(methods),'method_count':len(methods),'calls':calls,'events':events,'result':bundle.get('result'),'evidence':bundle.get('evidence',[]),'sources':bundle.get('sources',[]),'report':bundle.get('report',''),'validation':bundle.get('validation')})
            out[-1]['method_details_incomplete']=method_details_incomplete
            out[-1]['question']=question
    return {'conversation':{k:chat[k] for k in ['id','title','label']},'stages':out}
