"""Shared admin store, encrypted API profiles and low-budget model adapter."""
import base64, ctypes, hashlib, http.client, ipaddress, json, secrets, socket, sqlite3, ssl, time, os
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('SENSYS_DATA_DIR') or ROOT/'data')/'access.sqlite3'
SKILL=ROOT.parent/'skills/sensys-market-research/SKILL.md'
CONSENT='admin-records-v1'
class Error(Exception):
    def __init__(self,message,status=400): super().__init__(message); self.status=status

def day(): return datetime.now(timezone(timedelta(hours=8))).date().isoformat()
@contextmanager
def store():
    DB.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DB,timeout=15);db.row_factory=sqlite3.Row
    try:
        with db: yield db
    finally: db.close()

def init_store():
    with store() as d:
        d.executescript('''
        CREATE TABLE IF NOT EXISTS access_keys(id TEXT PRIMARY KEY,digest TEXT UNIQUE NOT NULL,label TEXT NOT NULL,expires REAL NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,key_id TEXT,expires REAL);
        CREATE TABLE IF NOT EXISTS admin_auth(id INTEGER PRIMARY KEY CHECK(id=1),digest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_sessions(digest TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS quotas(key_id TEXT PRIMARY KEY,total INTEGER NOT NULL,daily INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0,reserved INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS quota_days(key_id TEXT,day TEXT,used INTEGER DEFAULT 0,reserved INTEGER DEFAULT 0,PRIMARY KEY(key_id,day));
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,key_id TEXT,created REAL,question TEXT,answer TEXT,status TEXT,model TEXT,tokens INTEGER,consent TEXT,attachments TEXT);
        CREATE INDEX IF NOT EXISTS records_created ON conversations(created);
        CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,name TEXT,base_url TEXT,protocol TEXT,model TEXT,secret TEXT,input_price REAL,output_price REAL,active INTEGER DEFAULT 0,created REAL);
        CREATE TABLE IF NOT EXISTS checks(id TEXT PRIMARY KEY,profile_id TEXT,created REAL,ok INTEGER,detail TEXT,requests INTEGER,tokens INTEGER,elapsed INTEGER,mode TEXT);
        CREATE TABLE IF NOT EXISTS audits(id INTEGER PRIMARY KEY,created REAL,action TEXT,subject TEXT);
        ''')
        d.execute('INSERT OR IGNORE INTO quotas(key_id,total,daily) SELECT id,100000,20000 FROM access_keys')
        if 'deleted' not in {r['name'] for r in d.execute('PRAGMA table_info(access_keys)')}:d.execute('ALTER TABLE access_keys ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0')
        if 'initial_total' not in {r['name'] for r in d.execute('PRAGMA table_info(quotas)')}:d.execute('ALTER TABLE quotas ADD COLUMN initial_total INTEGER')
        cols={r['name'] for r in d.execute('PRAGMA table_info(conversations)')}
        for name,definition in [('usage_estimated','INTEGER DEFAULT 0'),('reserve_amount','INTEGER DEFAULT 0'),('quota_day','TEXT')]:
            if name not in cols:d.execute(f'ALTER TABLE conversations ADD COLUMN {name} {definition}')
        # Requests time out in 15 seconds. Reclaim only abandoned reservations over five minutes old.
        for r in d.execute("SELECT * FROM conversations WHERE status='running' AND created<?",(time.time()-300,)).fetchall():
            d.execute('UPDATE quotas SET reserved=MAX(0,reserved-?) WHERE key_id=?',(r['reserve_amount'],r['key_id']))
            d.execute('UPDATE quota_days SET reserved=MAX(0,reserved-?) WHERE key_id=? AND day=?',(r['reserve_amount'],r['key_id'],r['quota_day']))
            d.execute("UPDATE conversations SET status='failed',answer='Service interrupted, Reserved quota released.',reserve_amount=0 WHERE id=?",(r['id'],))

def audit(d,action,subject): d.execute('INSERT INTO audits(created,action,subject) VALUES(?,?,?)',(time.time(),action,subject))
def digest(v):return hashlib.sha256(v.encode()).hexdigest()
def init_admin():
    init_store()
    with store() as d:
        if d.execute('SELECT 1 FROM admin_auth').fetchone(): raise Error('Administrator credential already exists, Already initialized; initialization cannot be repeated.')
        key=secrets.token_urlsafe(32);d.execute('INSERT INTO admin_auth VALUES(1,?)',(digest(key),));audit(d,'Initialize administrator','local')
    return key

class Blob(ctypes.Structure):_fields_=[('size',ctypes.c_uint32),('data',ctypes.POINTER(ctypes.c_ubyte))]
def crypt(value,unprotect=False):
    if os.name != 'nt' or (unprotect and value.startswith('fernet:v1:')):
        try:
            from portable_secret import encrypt, decrypt
            return decrypt(value) if unprotect else encrypt(value)
        except (OSError, ValueError) as exc:
            raise Error('Server credential encryption is unavailable, Check the private key file and migration settings.',500) from exc
    # Windows DPAPI: ciphertext can only be opened under the same Windows account.
    raw=base64.b64decode(value) if unprotect else value.encode()
    buf=ctypes.create_string_buffer(raw);src=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));out=Blob()
    dll=ctypes.WinDLL('crypt32',use_last_error=True)
    fun=dll.CryptUnprotectData if unprotect else dll.CryptProtectData
    fun.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.POINTER(Blob)];fun.restype=ctypes.c_int
    if not fun(ctypes.byref(src),None,None,None,None,1,ctypes.byref(out)):raise Error('Cannot encrypt or decrypt API Key. Please use the configuration owner account Windows Account.',500)
    try:r=ctypes.string_at(out.data,out.size)
    finally:
        free=ctypes.WinDLL('kernel32').LocalFree;free.argtypes=[ctypes.c_void_p];free(ctypes.cast(out.data,ctypes.c_void_p))
    return r.decode() if unprotect else base64.b64encode(r).decode()

def integer(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi:raise Error(f'Quota must be {lo}–{hi} an integer within the range.')
    return v

def profile_public(r):
    return {k:r[k] for k in ('id','name','base_url','protocol','model','input_price','output_price','active','created')}|{'secret_mask':'Saved with encryption'}
def save_profile(data):
    name=str(data.get('name','')).strip();model=str(data.get('model','')).strip();url=str(data.get('base_url','')).rstrip('/');protocol=data.get('protocol');key=data.get('api_key','')
    p=urlsplit(url)
    if not name or len(name)>80 or not model or len(model)>100:raise Error('Enter a configuration name and exact model name.')
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.port not in (None,443):raise Error('The API address must have no embedded credentials, without query parameters HTTPS Address, port is 443.')
    if len(url)>300 or protocol not in ('responses','chat'):raise Error('Invalid API type or address.')
    if not isinstance(key,str) or not 8<=len(key)<=4096 or any(ord(c)<33 or ord(c)>126 for c in key):raise Error('Enter a valid API Key.')
    prices=[]
    for f in ('input_price','output_price'):
        v=data.get(f);v=None if v in (None,'') else float(v)
        if v is not None and (not 0<=v<=100000):raise Error('Prices must be nonnegative.')
        prices.append(v)
    pid=secrets.token_hex(8)
    with store() as d:
        d.execute('INSERT INTO profiles VALUES(?,?,?,?,?,?,?,?,0,?)',(pid,name,url,protocol,model,crypt(key),*prices,time.time()));audit(d,'Save API Draft',pid)
    return pid

def public_address(host):
    try:rows=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    except OSError:raise Error('Cannot resolve the provider hostname.')
    addresses=[r[4][0] for r in rows]
    try:ipaddress.ip_address(host);literal=True
    except ValueError:literal=False
    def permitted(ip):
        addr=ipaddress.ip_address(ip)
        return addr.is_global or (not literal and os.environ.get('SENSYS_ALLOW_BENCHMARK_DNS')=='1' and addr in ipaddress.ip_network('198.18.0.0/15'))
    if not addresses or any(not permitted(ip) for ip in addresses):raise Error('The API address must not point to this machine, Private or reserved network address.')
    return addresses[0]

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip):super().__init__(host,timeout=15,context=ssl.create_default_context());self.ip=ip
    def connect(self):self.sock=self._context.wrap_socket(socket.create_connection((self.ip,443),self.timeout),server_hostname=self.host)
def remote(profile,payload):
    u=urlsplit(profile['base_url']);ip=public_address(u.hostname);conn=PinnedHTTPS(u.hostname,ip)
    try:
        path=u.path.rstrip('/')+('/responses' if profile['protocol']=='responses' else '/chat/completions')
        conn.request('POST',path,body=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+crypt(profile['secret'],True)})
        r=conn.getresponse();raw=r.read(1024*1024+1)
        if len(raw)>1024*1024:raise Error('Provider response exceeds the allowed size.')
        if r.status!=200:
            label={401:'API Invalid key',403:'Provider denied access',404:'Endpoint or model not found',429:'Provider rate limit or insufficient balance'}.get(r.status,'Provider request failed')
            raise Error(f'{label}(HTTP {r.status}), Stopped, No automatic retries.')
        out=json.loads(raw)
        if not isinstance(out,dict):raise Error('Invalid provider result format.')
        return out
    except Error:raise
    except (OSError,ValueError,http.client.HTTPException):raise Error('Connection timed out, TLS Verification failed or response could not be parsed, Stopped, No automatic retries.')
    finally:conn.close()

def usage(r):
    u=r.get('usage') or {}
    if not isinstance(u,dict):raise Error('Invalid provider usage format.')
    i=int(u.get('input_tokens',u.get('prompt_tokens',0)) or 0);o=int(u.get('output_tokens',u.get('completion_tokens',0)) or 0)
    return max(i,0),max(o,0)
def text_of(r,protocol):
    if protocol=='chat':return str((r.get('choices') or [{}])[0].get('message',{}).get('content') or '')
    return ''.join(c.get('text','') for x in r.get('output',[]) if x.get('type')=='message' for c in x.get('content',[]) if c.get('type')=='output_text')
def request_body(p,text,cap=1024,effort='medium'):
    common={'model':p['model'],'store':False}
    if effort not in ('low','medium'):raise Error('This reasoning effort is not allowed for the basic probe.')
    if p['protocol']=='responses':return common|{'input':[{'role':'user','content':text}],'max_output_tokens':cap,'reasoning':{'effort':effort},'include':['reasoning.encrypted_content']}
    return common|{'messages':[{'role':'user','content':text}],'max_completion_tokens':cap,'reasoning_effort':effort}

def light_test(pid,mode):
    if mode not in ('connect','tool'):raise Error('Choose a connectivity or basic-call test.')
    with store() as d:p=d.execute('SELECT * FROM profiles WHERE id=?',(pid,)).fetchone()
    if not p:raise Error('Configuration not found.',404)
    count=0;total=0;inputs=0;outputs=0;start=time.monotonic();ok=False;detail=''
    def call(body):
        nonlocal count,total,inputs,outputs
        count+=1
        if count>2:raise Error('Test request limit reached.')
        r=remote(p,body);i,o=usage(r);inputs+=i;outputs+=o;total+=i+o;return r
    try:
        body=request_body(p,'Reply exactly OK.' if mode=='connect' else 'Call research_skill_selfcheck with no arguments. Do not do research.',effort='low')
        if mode=='tool':
            schema={'type':'object','properties':{},'required':[],'additionalProperties':False}
            fn={'name':'research_skill_selfcheck','description':'Checks local research skill entry only; no web requests.','parameters':schema,'strict':True}
            body['tools']=[{'type':'function',**fn}] if p['protocol']=='responses' else [{'type':'function','function':fn}]
            body['tool_choice']={'type':'function','name':fn['name']} if p['protocol']=='responses' else {'type':'function','function':{'name':fn['name']}}
        r=call(body)
        if mode=='connect':
            if text_of(r,p['protocol']).strip()!='OK':raise Error('API responded, but the required confirmation was not returned; Insufficient budget or compatibility needs further verification.')
            detail='Connection successful: The specified model returned OK.'
        else:
            if not SKILL.exists() or not SKILL.read_text(encoding='utf-8-sig').startswith('---'):raise Error('Model responded, but the local research Skill Entry point cannot be loaded.')
            result='{"available":true,"scope":"entry_selfcheck_only"}'
            if p['protocol']=='responses':
                calls=[x for x in r.get('output',[]) if x.get('type')=='function_call']
                if len(calls)!=1 or calls[0].get('name')!='research_skill_selfcheck' or json.loads(calls[0].get('arguments','null'))!={}:raise Error('Model did not call the self-test tool as required.')
                items=r.get('output',[])
                if len(json.dumps(items))>12000:raise Error('Tool response exceeds the lightweight probe budget.')
                follow=request_body(p,'',effort='low');follow['input']=body['input']+items+[{'type':'function_call_output','call_id':calls[0]['call_id'],'output':result},{'role':'user','content':'Reply exactly OK.'}]
            else:
                m=(r.get('choices') or [{}])[0].get('message',{});calls=m.get('tool_calls',[])
                if len(json.dumps(m))>12000:raise Error('Tool response exceeds the lightweight probe budget.')
                if len(calls)!=1 or calls[0].get('function',{}).get('name')!='research_skill_selfcheck' or json.loads(calls[0]['function'].get('arguments','null'))!={}:raise Error('Model did not call the self-test tool as required.')
                follow=request_body(p,'',effort='low');follow['messages']=body['messages']+[m,{'role':'tool','tool_call_id':calls[0]['id'],'content':result},{'role':'user','content':'Reply exactly OK.'}]
            r=call(follow)
            if text_of(r,p['protocol']).strip()!='OK':raise Error('Tool request started successfully, but the returned result was not received correctly.')
            detail='Basic call succeeded: Model calls → Local Skill Entry point check → Result returned. No search or research was executed.'
        ok=True
    except (Error,KeyError,TypeError,ValueError,AttributeError,IndexError) as e:detail=str(e) if isinstance(e,Error) else 'Provider tool response does not match the required contract.'
    elapsed=int((time.monotonic()-start)*1000)
    cost=(inputs*p['input_price']+outputs*p['output_price'])/1000000 if p['input_price'] is not None and p['output_price'] is not None else None
    with store() as d:
        d.execute('INSERT INTO checks VALUES(?,?,?,?,?,?,?,?,?)',(secrets.token_hex(8),pid,time.time(),int(ok),detail,count,total,elapsed,mode));audit(d,'Lightweight probe',pid)
    return {'ok':ok,'detail':detail,'requests':count,'tokens':total,'usage_reported':total>0,'elapsed_ms':elapsed,'estimated_cost':cost,'mode':mode}

PREVIEW='Question recorded. The full research executor is not connected yet, No search or market analysis performed.'
def chat_reply(key_id,data):
    question=data.get('question','');files=data.get('attachments',[])
    if data.get('consent')!=CONSENT:raise Error('Please agree to administrator review of this submission and reply.',403)
    if not isinstance(question,str) or not 1<=len(question.strip())<=4000:raise Error('The question must contain 1–4000 characters.')
    if not isinstance(files,list) or len(files)>8 or any(not isinstance(x,str) or len(x)>200 for x in files):raise Error('Invalid material list.')
    # Material bodies are not uploaded by this UI. Files remain local.
    init_store();cid=secrets.token_hex(12);today=day();reserve=len(question.encode())+1536
    with store() as d:
        d.execute('BEGIN IMMEDIATE')
        k=d.execute('SELECT * FROM access_keys WHERE id=? AND enabled=1 AND expires>?',(key_id,time.time())).fetchone()
        if not k:raise Error('Access key expired.',401)
        p=d.execute('SELECT * FROM profiles WHERE active=1').fetchone()
        if p:
            q=d.execute('SELECT * FROM quotas WHERE key_id=?',(key_id,)).fetchone();d.execute('INSERT OR IGNORE INTO quota_days(key_id,day) VALUES(?,?)',(key_id,today));daily=d.execute('SELECT * FROM quota_days WHERE key_id=? AND day=?',(key_id,today)).fetchone()
            if q['total']-q['used']-q['reserved']<reserve or q['daily']-daily['used']-daily['reserved']<reserve:raise Error('Insufficient remaining quota to reserve this request, Contact your administrator.',429)
            d.execute('UPDATE quotas SET reserved=reserved+? WHERE key_id=?',(reserve,key_id));d.execute('UPDATE quota_days SET reserved=reserved+? WHERE key_id=? AND day=?',(reserve,key_id,today))
        d.execute('INSERT INTO conversations(id,key_id,created,question,answer,status,model,tokens,consent,attachments,reserve_amount,quota_day) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(cid,key_id,time.time(),question,'','running' if p else 'preview',p['model'] if p else 'Not configured',0,CONSENT,json.dumps(files,ensure_ascii=False),reserve if p else 0,today))
    used=0;answer=PREVIEW;status='preview';missing=False
    if p:
        try:
            from agent.confidentiality import POLICY as DISCLOSURE_POLICY
            payload=request_body(p,'You are a research assistant. Do not claim to have searched online or executed research. Only conversational advice is currently available. \nUser question: '+question,512)
            if p['protocol']=='responses':payload['instructions']=DISCLOSURE_POLICY
            else:payload['messages'].insert(0,{'role':'system','content':DISCLOSURE_POLICY})
            r=remote(p,payload);i,o=usage(r);used=i+o
            if not r.get('usage'):used=reserve;missing=True
            answer=text_of(r,p['protocol']);status='answered'
            if not answer:raise Error('Model returned no visible response; Generation allowance may be consumed by internal reasoning.')
        except (Error,KeyError,TypeError,ValueError,AttributeError,IndexError) as e:
            answer=str(e) if isinstance(e,Error) else 'Invalid provider response format.';status='failed';missing=missing or not bool(used)
    with store() as d:
        if p:
            d.execute('UPDATE quotas SET reserved=reserved-?,used=used+? WHERE key_id=?',(reserve,used,key_id));d.execute('UPDATE quota_days SET reserved=reserved-?,used=used+? WHERE key_id=? AND day=?',(reserve,used,key_id,today))
        d.execute('UPDATE conversations SET answer=?,status=?,tokens=?,usage_estimated=?,reserve_amount=0 WHERE id=?',(answer,status,used,int(missing),cid))
    from agent.confidentiality import clean_answer
    return {'id':cid,'answer':clean_answer(answer,question),'status':status,'tokens':used,'usage_estimated':missing,'model':p['model'] if p else None}


def point_tokens(value):
    from decimal import Decimal, InvalidOperation
    try:
        if isinstance(value,bool):raise ValueError()
        amount=Decimal(str(value))*1000
        if not amount.is_finite() or amount!=amount.to_integral_value() or not 0<=amount<=1000000000:raise ValueError()
        return int(amount)
    except (InvalidOperation,ValueError,TypeError):raise Error('Credits must be0to1,000,000values between, Up to three decimal places.')

def quota_public(key_id):
    with store() as d:
        row=d.execute('SELECT q.*,k.label FROM quotas q JOIN access_keys k ON k.id=q.key_id WHERE q.key_id=?',(key_id,)).fetchone()
    if not row:raise Error('Quota not found.',404)
    q=dict(row)
    return {'label':q['label'],'initial_points':q['initial_total']/1000 if q['initial_total'] is not None else None,'total_points':q['total']/1000,'used_points':q['used']/1000,'reserved_points':q['reserved']/1000,'remaining_points':max(0,q['total']-q['used']-q['reserved'])/1000,'tokens_per_point':1000}
