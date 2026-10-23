"""Durable task, event and usage records. All mutations use SQLite transactions."""
import json, secrets, time, os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get('SENSYS_RUNTIME_DIR') or ROOT/'runtime')
ARTIFACTS = RUNTIME / 'tasks'
SETTINGS = Path(os.environ.get('SENSYS_SETTINGS_FILE') or Path(__file__).with_name('settings.json'))
ACTIVE = ('queued', 'running')

def control():
    import control as c
    return c

def settings():
    value=json.loads(SETTINGS.read_text(encoding='utf-8'))
    value['model']=__import__('os').environ.get('SENSYS_MODEL',value['model'])
    return value

def init():
    c = control(); c.init_store()
    with c.store() as d:
        d.executescript('''
        CREATE TABLE IF NOT EXISTS research_jobs(
          id TEXT PRIMARY KEY,key_id TEXT NOT NULL,question TEXT NOT NULL,depth TEXT NOT NULL,
          status TEXT NOT NULL,stage TEXT NOT NULL,created REAL NOT NULL,started REAL,finished REAL,
          elapsed_ms INTEGER DEFAULT 0,tokens INTEGER DEFAULT 0,input_tokens INTEGER DEFAULT 0,
          output_tokens INTEGER DEFAULT 0,cached_tokens INTEGER DEFAULT 0,reasoning_tokens INTEGER DEFAULT 0,
          model_calls INTEGER DEFAULT 0,tool_calls INTEGER DEFAULT 0,profile_id TEXT NOT NULL,
          config TEXT NOT NULL,request TEXT NOT NULL,answer TEXT DEFAULT '',error TEXT DEFAULT '',
          cancel_requested INTEGER DEFAULT 0,artifact_root TEXT NOT NULL,run INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS research_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,created REAL,kind TEXT,message TEXT,data TEXT);
        CREATE INDEX IF NOT EXISTS research_events_job ON research_events(job_id,id);
        CREATE TABLE IF NOT EXISTS research_calls(
          id TEXT PRIMARY KEY,job_id TEXT,run INTEGER,kind TEXT,name TEXT,effort TEXT,stage TEXT,
          started REAL,finished REAL,elapsed_ms INTEGER DEFAULT 0,status TEXT,input_tokens INTEGER DEFAULT 0,
          output_tokens INTEGER DEFAULT 0,cached_tokens INTEGER DEFAULT 0,reasoning_tokens INTEGER DEFAULT 0,
          total_tokens INTEGER DEFAULT 0,reserved INTEGER DEFAULT 0,quota_day TEXT,usage_known INTEGER DEFAULT 1,
          response_id TEXT,details TEXT);
        CREATE TABLE IF NOT EXISTS research_uploads(
          id TEXT PRIMARY KEY,key_id TEXT,name TEXT,path TEXT,bytes INTEGER,sha256 TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS research_messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,created REAL,role TEXT,text TEXT);
        ''')
        from . import conversations
        conversations.migrate(d)
        if 'kind' not in {x['name'] for x in d.execute('PRAGMA table_info(research_jobs)')}:
            d.execute("ALTER TABLE research_jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'research'")

def get(job_id, key_id=None):
    c = control()
    with c.store() as d:
        row = d.execute('SELECT * FROM research_jobs WHERE id=?', (job_id,)).fetchone()
    if not row or (key_id is not None and row['key_id'] != key_id):
        raise c.Error('Research task not found or access denied.', 404)
    return dict(row)

def event(job_id, kind, message, data=None):
    with control().store() as d:
        d.execute('INSERT INTO research_events(job_id,created,kind,message,data) VALUES(?,?,?,?,?)',
                  (job_id, time.time(), kind, message, json.dumps(data or {}, ensure_ascii=False)))

def update(job_id, **values):
    allowed={'status','stage','started','finished','elapsed_ms','answer','error','cancel_requested','config','depth','request','run','kind'}
    if not values or set(values)-allowed: raise ValueError('Invalid task update')
    with control().store() as d:
        d.execute('UPDATE research_jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?', [*values.values(),job_id])

def check_key(d, key_id):
    c = control(); k = d.execute('SELECT * FROM access_keys WHERE id=? AND enabled=1 AND expires>?', (key_id,time.time())).fetchone()
    if not k: raise c.Error('Access key expired or disabled.',401)
    return k

def submit(key_id, data, *, conversational=False):
    c = control(); init()
    # This private beta has a standing notice agreed outside the application.
    data={**data,'consent':c.CONSENT}
    question=data.get('question','');depth=data.get('research_depth','standard');uploads=data.get('uploads',[])
    if not isinstance(question,str) or not 1<=len(question.strip())<=4000: raise c.Error('Research questions must contain1–4000characters.')
    if depth not in ('standard','deep'): raise c.Error('Select standard or deep research.')
    if not isinstance(uploads,list) or len(uploads)>8 or any(not isinstance(x,str) for x in uploads): raise c.Error('Invalid material list.')
    config=settings()[depth]; jid=secrets.token_hex(12); folder=ARTIFACTS/jid
    with c.store() as d:
        d.execute('BEGIN IMMEDIATE');check_key(d,key_id)
        busy=d.execute("SELECT 1 FROM research_jobs WHERE key_id=? AND status IN ('queued','running')"+(" AND kind='dialog'" if conversational else ''),(key_id,)).fetchone()
        if busy: raise c.Error('The previous message is still being processed, Send again later.' if conversational else 'Research is already running, Wait or stop the current task before submitting.',409)
        p=d.execute('SELECT * FROM profiles WHERE active=1').fetchone()
        if not p: raise c.Error('The administrator has not enabled a model configuration, Contact your administrator.',409)
        if p['model']!=settings()['model'] or p['protocol']!='responses': raise c.Error('Research requires the configuredexample-model ResponsesConfiguration.',409)
        files=[]
        for uid in uploads:
            row=d.execute('SELECT * FROM research_uploads WHERE id=? AND key_id=?',(uid,key_id)).fetchone()
            if not row: raise c.Error('Material not found or not owned by this user.',403)
            files.append(dict(row))
        if sum(x['bytes'] for x in files)>30*1024*1024:raise c.Error('Total attachments per request must not exceed30MB.',413)
        from . import conversations
        thread_id=conversations.attach(d,key_id,question.strip(),data.get('conversation_id'))
        quota=d.execute('SELECT * FROM quotas WHERE key_id=?',(key_id,)).fetchone()
        if not quota or quota['total']-quota['used']-quota['reserved']<5000: raise c.Error('RemainingTokenInsufficient quota, Adjust quota in the admin console.',429)
        request={'question':question.strip(),'uploads':files,'action':'message' if conversational else 'research','consent':c.CONSENT}
        # Dialogue uses the administrator's actual allowance too. Large existing
        # reports must not fail before the first reply under a hidden 40k cap.
        d.execute('INSERT INTO research_jobs(id,key_id,question,depth,status,stage,created,profile_id,config,request,artifact_root) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                  (jid,key_id,question.strip(),depth,'queued','Waiting for execution',time.time(),p['id'],json.dumps(config),json.dumps(request,ensure_ascii=False),str(folder)))
        d.execute('UPDATE research_jobs SET thread_id=?,kind=?,stage=? WHERE id=?',(thread_id,'dialog' if conversational else 'research','Waiting for reply' if conversational else 'Waiting for execution',jid))
        d.execute('INSERT INTO research_messages(job_id,created,role,text) VALUES(?,?,?,?)',(jid,time.time(),'user',question.strip()))
    event(jid,'queued','Research queued',{'depth':depth});return public(jid,key_id)

def action(key_id,data):
    c=control();j=get(data.get('id'),key_id);op=data.get('action');question=data.get('question','')
    if op=='cancel':
        if j['status'] not in ACTIVE:return public(j['id'],key_id)
        update(j['id'],cancel_requested=1,**({'status':'cancelled','stage':'Stopped and saved materials','finished':time.time()} if j['status']=='queued' else {'stage':'Stopping and organizing existing materials'}))
        event(j['id'],'cancel_requested','Stop requested; Retain acquired materials')
        return public(j['id'],key_id)
    if j['kind']!='research':raise c.Error('Ordinary chat cannot be resumed as research, Send the message again.',409)
    if op not in ('continue','deepen','ask'): raise c.Error('Invalid operation.')
    if j['status'] in ACTIVE: raise c.Error('Research is running, Wait for the current turn to finish.',409)
    if not isinstance(question,str) or len(question)>4000: raise c.Error('Follow-up content too long.')
    with c.store() as d:
        d.execute('BEGIN IMMEDIATE');check_key(d,key_id)
        current=d.execute('SELECT status FROM research_jobs WHERE id=?',(j['id'],)).fetchone()
        if current['status'] in ACTIVE: raise c.Error('Research queued.',409)
        if d.execute("SELECT 1 FROM research_jobs WHERE key_id=? AND status IN ('queued','running')",(key_id,)).fetchone():raise c.Error('This user already has an active task.',409)
        depth='deep' if op=='deepen' else j['depth'];allowance=dict(settings()[depth])
        # Settings specify this execution's allowance; lifetime receipts remain
        # cumulative. A continuation must not immediately hit an exhausted cap.
        config={**allowance,'model_tokens':j['tokens']+allowance['model_tokens'],'model_calls':j['model_calls']+allowance['model_calls'],'seconds':j['elapsed_ms']/1000+allowance['seconds']}
        request={'action':op,'question':question or ('Investigate the key gaps using existing materials.' if op=='deepen' else 'Continue filling key evidence gaps.'),'uploads':[]}
        request['run_allowance']=allowance
        d.execute("UPDATE research_jobs SET status='queued',stage='Waiting to continue',request=?,depth=?,config=?,cancel_requested=0,finished=NULL,error='' WHERE id=?",
                  (json.dumps(request,ensure_ascii=False),depth,json.dumps(config),j['id']))
        d.execute('INSERT INTO research_messages(job_id,created,role,text) VALUES(?,?,?,?)',(j['id'],time.time(),'user',request['question']))
    event(j['id'],'queued','Original materials retained, Waiting to resume research',{'action':op,'depth':depth});return public(j['id'],key_id)

def public(job_id,key_id=None,*,include_messages=True):
    j=get(job_id,key_id)
    out={k:j[k] for k in ('id','kind','question','depth','status','stage','created','started','finished','elapsed_ms','tokens','input_tokens','output_tokens','cached_tokens','reasoning_tokens','model_calls','tool_calls','answer','error','cancel_requested','run','thread_id')}
    if j['status']=='running' and j['started']: out['elapsed_ms']+=int((time.time()-j['started'])*1000)
    out['limits']=json.loads(j['config'])
    from .progress import reason
    out['stop_reason']=reason(j)
    from .progress import read
    from .confidentiality import clean_value
    out['suggestions']=clean_value(read(Path(j['artifact_root'])/'suggestions.json',[]))
    out['known_tokens']=j['input_tokens']+j['output_tokens']
    out['unknown_tokens']=max(0,j['tokens']-out['known_tokens'])
    if include_messages:
        with control().store() as d:
            out['messages']=[dict(x) for x in d.execute('SELECT created,role,text FROM research_messages WHERE job_id=? ORDER BY id',(job_id,))]
    if key_id is not None:
        from .confidentiality import public_job,clean_answer
        out['answer']=clean_answer(out['answer'],json.loads(j['request']).get('question',''))
        out=public_job(out)
    return out

def records(key_id=None):
    with control().store() as d:
        rows=d.execute('SELECT id FROM research_jobs '+('WHERE key_id=? ' if key_id else '')+'ORDER BY created DESC LIMIT 100',(key_id,) if key_id else ()).fetchall()
    return [public(x['id'],key_id) for x in rows]

def detail(job_id,key_id=None,after=0):
    out=public(job_id,key_id)
    with control().store() as d:
        out['events']=[dict(x) for x in d.execute('SELECT * FROM research_events WHERE job_id=? AND id>? ORDER BY id '+('ASC' if after else 'DESC')+' LIMIT 300',(job_id,after))]
        if not after:out['events'].reverse()
        out['calls']=[dict(x) for x in d.execute('SELECT * FROM research_calls WHERE job_id=? ORDER BY started',(job_id,))]
    if key_id is not None:
        from .confidentiality import public_detail
        out=public_detail(out)
    return out

def artifact_bundle(root):
    out={}
    for name in ('brief','result','sources','evidence','research-plan','research-budget','validation','support-review','handoff'):
        p=root/(name+'.json');out[name.replace('-','_')]=json.loads(p.read_text(encoding='utf-8')) if p.exists() else None
    p=root/'report.md';out['report']=p.read_text(encoding='utf-8') if p.exists() else ''
    return out

def publish_bundle(job_id):
    j=get(job_id);root=Path(j['artifact_root']);out=artifact_bundle(root)
    if not ((out.get('result') or {}).get('support_reviewed') and (out.get('validation') or {}).get('ok') and out.get('report')):raise ValueError('Only reviewed and validated reports can be published')
    out['publication']={'run':j['run'],'depth':out['result']['research_depth'],'published_at':time.time()}
    target=root/'published.json';tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8');tmp.replace(target)

def bundle(job_id,key_id=None):
    j=get(job_id,key_id);root=Path(j['artifact_root']);published=root/'published.json'
    if published.exists():out=json.loads(published.read_text(encoding='utf-8'))
    else:
        out=artifact_bundle(root)
        valid=out.get('result',{}).get('support_reviewed') if out.get('result') else False
        valid=valid and bool((out.get('validation') or {}).get('ok')) and bool(out.get('report'))
        if not valid:
            snapshots=sorted((root/'runs').glob('*') if (root/'runs').exists() else [],key=lambda p:p.stat().st_mtime,reverse=True)
            for path in snapshots:
                if not path.is_dir():continue
                candidate=artifact_bundle(path)
                if candidate.get('result') and candidate['result'].get('support_reviewed') and (candidate.get('validation') or {}).get('ok') and candidate.get('report'):
                    out=candidate;out['report']=out['report'].replace('](../../sources/','](sources/');out['publication']={'depth':out['result']['research_depth'],'run':path.name,'restored_snapshot':True};break
    from .progress import snapshot
    value={**out,'job':public(job_id,key_id),'progress':snapshot(j)}
    if key_id is not None:
        from .confidentiality import public_bundle
        value=public_bundle(value)
    return value

def save_settings(data):
    c=control();old=settings()
    if not isinstance(data,dict) or set(data)-{'standard','deep'}:raise c.Error('Only standard and deep research budgets may be changed; Model and reasoning-effort policies are fixed.')
    for tier in ('standard','deep'):
        incoming=data.get(tier,{})
        if not isinstance(incoming,dict) or set(incoming)-set(old[tier]): raise c.Error('Invalid tier parameters.')
        for k,v in incoming.items():
            minimum=0 if k=='images_per_source' else 1
            # JS forms and SQLite counters must represent the configured integer exactly.
            if type(v) is not int or not minimum<=v<=9007199254740991:
                raise c.Error(f'{tier}.{k} must be an exactly representable integer, minimum value is {minimum}.')
            old[tier][k]=v
    tmp=SETTINGS.with_suffix('.tmp');tmp.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(SETTINGS)
    return old
