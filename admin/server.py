"""Loopback-only administrator console, independent of end-user access keys."""
import argparse,json,secrets,sys,threading,time,os
from pathlib import Path
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web-redesign'))
import control as c
import server as public
from agent import store as research_store
from agent import http_api as research_api
ROOT=Path(__file__).resolve().parent
COOKIE='sensys_admin_session'
def admin_origin(port):
    value=os.environ.get('SENSYS_ADMIN_ORIGIN','').strip()
    if not value:return f'http://127.0.0.1:{port}'
    u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError('SENSYS_ADMIN_ORIGIN must be an HTTPS origin without a path')
    if value==os.environ.get('SENSYS_PUBLIC_ORIGIN','').strip():
        raise ValueError('Admin and user origins must be separate')
    return value
class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address):
        admin_origin(address[1])
        super().__init__(address,Handler);self.attempts={};self.lock=threading.Lock();self.test_lock=threading.Lock()
class Handler(public.Handler):
    def valid_host(self):return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',urlsplit(admin_origin(self.server.server_port)).netloc)
    def cookie_name(self):return COOKIE if os.environ.get('SENSYS_ADMIN_ORIGIN','').strip() else COOKIE+'_'+str(self.server.server_port)
    def cookie(self,token='',max_age=0):
        secure='; Secure' if admin_origin(self.server.server_port).startswith('https:') else ''
        return f'{self.cookie_name()}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}{secure}'
    def admin(self):
        try:
            x=SimpleCookie(self.headers.get('Cookie',''));name=self.cookie_name();token=x[name].value if name in x else x[COOKIE].value if COOKIE in x else ''
        except Exception:return None
        with c.store() as d:return d.execute('SELECT * FROM admin_sessions WHERE digest=? AND expires>?',(c.digest(token),time.time())).fetchone()
    def do_GET(self):
        if not self.valid_host():return self.send(400,{'error':'Use the local administrator address.'})
        u=urlsplit(self.path);path=u.path
        if path=='/api/session':
            s=self.admin();return self.send(200,{'authenticated':bool(s),'csrf':s['csrf'] if s else None})
        files={'/':('index.html','text/html; charset=utf-8'),'/admin.css':('admin.css','text/css; charset=utf-8'),'/admin.js':('admin.js','text/javascript; charset=utf-8'),'/research.js':('research.js','text/javascript; charset=utf-8')}
        if path=='/report-view.js':return self.send(200,(ROOT.parent/'web-redesign/static/report-view.js').read_bytes(),'text/javascript; charset=utf-8')
        if path in files:
            name,mime=files[path];return self.send(200,(ROOT/'static'/name).read_bytes(),mime)
        if not self.admin():return self.send(401,{'error':'Sign in with administrator credentials.'})
        if path in ('/api/conversations','/api/conversation','/api/conversation/stages','/api/jobs','/api/job','/api/job/result','/api/job/export','/api/job/package','/api/artifact'):
            try:return research_api.get(self,admin=True)
            except c.Error as e:return self.send(e.status,{'error':str(e)})
        with c.store() as d:
            if path=='/api/state':
                keys=[dict(x) for x in d.execute('''SELECT k.id,k.label,k.expires,k.enabled,q.total,q.daily,q.used,q.reserved,q.initial_total,COALESCE(t.used,0) daily_used FROM access_keys k JOIN quotas q ON q.key_id=k.id LEFT JOIN quota_days t ON t.key_id=k.id AND t.day=? WHERE k.deleted=0 ORDER BY k.rowid DESC''',(c.day(),))]
                for key in keys:key.update(c.quota_public(key['id']))
                profiles=[c.profile_public(x) for x in d.execute('SELECT * FROM profiles ORDER BY created DESC')]
                for profile in profiles:
                    profile['can_activate']=all((lambda t:bool(t and t['ok'] and t['created']>time.time()-7*86400))(d.execute('SELECT ok,created FROM checks WHERE profile_id=? AND mode=? ORDER BY created DESC LIMIT 1',(profile['id'],mode)).fetchone()) for mode in ('connect','tool'))
                checks=[dict(x) for x in d.execute('SELECT * FROM checks ORDER BY created DESC LIMIT 30')]
                summary={'records':d.execute('SELECT COUNT(*) FROM conversations').fetchone()[0],'keys':len(keys),'enabled':sum(bool(x['enabled'] and x['expires']>time.time()) for x in keys),'tokens':d.execute('SELECT COALESCE(SUM(tokens),0) FROM conversations').fetchone()[0]}
                if d.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_jobs'").fetchone():
                    summary['jobs']=d.execute('SELECT COUNT(*) FROM research_jobs').fetchone()[0]
                    summary['tokens']+=d.execute('SELECT COALESCE(SUM(tokens),0) FROM research_jobs').fetchone()[0]
                else:summary['jobs']=0
                summary['threads']=d.execute('SELECT COUNT(*) FROM research_threads').fetchone()[0] if d.execute("SELECT 1 FROM sqlite_master WHERE name='research_threads'").fetchone() else summary['records']+summary['jobs']
                audits=[dict(x) for x in d.execute('SELECT * FROM audits ORDER BY id DESC LIMIT 20')]
                return self.send(200,{'keys':keys,'profiles':profiles,'checks':checks,'summary':summary,'audits':audits,'skill_available':c.SKILL.exists()})
            if path=='/api/records':
                args=parse_qs(u.query);search=args.get('q',[''])[0][:200];page=max(1,min(int(args.get('page',['1'])[0]) if args.get('page',['1'])[0].isdigit() else 1,100000));kid=args.get('key',[''])[0]
                where='WHERE (c.question LIKE ? OR c.answer LIKE ? OR k.label LIKE ?)';params=['%'+search+'%']*3
                if kid:where+=' AND c.key_id=?';params.append(kid)
                total=d.execute('SELECT COUNT(*) FROM conversations c LEFT JOIN access_keys k ON k.id=c.key_id '+where,params).fetchone()[0]
                records=[dict(x) for x in d.execute('SELECT c.*,k.label FROM conversations c LEFT JOIN access_keys k ON k.id=c.key_id '+where+' ORDER BY c.created DESC LIMIT 30 OFFSET ?',params+[(page-1)*30])]
                return self.send(200,{'records':records,'total':total,'page':page})
            if path=='/api/export':
                rows=[dict(x) for x in d.execute('SELECT c.*,k.label FROM conversations c LEFT JOIN access_keys k ON k.id=c.key_id ORDER BY c.created')]
                return self.send(200,{'records':rows},download=True)
        self.send(404,{'error':'Endpoint not found.'})
    def do_POST(self):
        if not self.valid_host():return self.send(400,{'error':'Invalid address.'})
        if self.headers.get('Origin')!=admin_origin(self.server.server_port) or not self.headers.get('Content-Type','').startswith('application/json'):return self.send(403,{'error':'Request origin failed verification.'})
        try:
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=24000:raise c.Error('Invalid request size.')
            data=json.loads(self.rfile.read(n))
            if not isinstance(data,dict):raise c.Error('Invalid request format.')
            if self.path=='/api/login':
                with self.server.lock:
                    client=self.client_ip();now=time.time();a=[t for t in self.server.attempts.get(client,[]) if t>now-60]
                    if len(a)>=10:raise c.Error('Too many attempts, Retry later.',429)
                    a.append(now);self.server.attempts[client]=a
                key=data.get('key')
                with c.store() as d:
                    auth=d.execute('SELECT digest FROM admin_auth WHERE id=1').fetchone()
                    if not isinstance(key,str) or len(key)>200 or not auth or not secrets.compare_digest(c.digest(key.strip()),auth['digest']):raise c.Error('Incorrect administrator credential.',401)
                    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24);d.execute('DELETE FROM admin_sessions WHERE expires<=?',(time.time(),));d.execute('INSERT INTO admin_sessions VALUES(?,?,?)',(c.digest(token),csrf,time.time()+8*3600))
                    c.audit(d,'Administrator sign-in','local')
                return self.send(200,{'authenticated':True,'csrf':csrf},cookie=self.cookie(token,8*3600))
            s=self.admin()
            if not s:raise c.Error('Administrator session expired.',401)
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']):raise c.Error('Request validation failed, Refresh and try again.',403)
            if self.path=='/api/logout':
                with c.store() as d:d.execute('DELETE FROM admin_sessions WHERE digest=?',(s['digest'],))
                return self.send(200,{'ok':True},cookie=self.cookie())
            if self.path=='/api/research/settings':
                result=research_store.save_settings(data)
                with c.store() as d:c.audit(d,'Adjust research tier parameters','new_tasks')
                return self.send(200,result)
            if self.path=='/api/job/action':
                j=research_store.get(data.get('id'))
                return self.send(200,research_store.action(j['key_id'],data))
            if self.path=='/api/keys/delete':
                kid=data.get('id')
                with c.store() as d:
                    d.execute('BEGIN IMMEDIATE')
                    if not d.execute('SELECT 1 FROM access_keys WHERE id=? AND deleted=0',(kid,)).fetchone():raise c.Error('Key not found.',404)
                    d.execute('UPDATE access_keys SET enabled=0,deleted=1 WHERE id=?',(kid,))
                    d.execute('DELETE FROM sessions WHERE key_id=?',(kid,))
                    d.execute("UPDATE research_jobs SET cancel_requested=1 WHERE key_id=? AND status IN ('queued','running')",(kid,))
                    c.audit(d,'Delete access key, Preserve usage history',kid)
                return self.send(200,{'ok':True})
            if self.path=='/api/keys/create':
                label=str(data.get('label','')).strip()
                if not 1<=len(label)<=100:raise c.Error('Enter a user or purpose, At most 100 characters.')
                days=c.integer(data.get('days'),1,3650);total=c.point_tokens(data['total_points']) if 'total_points' in data else c.integer(data.get('total'),0,1000000000);daily=total if 'total_points' in data else c.integer(data.get('daily'),0,1000000000)
                kid=secrets.token_hex(6);key=secrets.token_urlsafe(32)
                with c.store() as d:
                    d.execute('INSERT INTO access_keys(id,digest,label,expires,enabled) VALUES(?,?,?,?,1)',(kid,c.digest(key),label,time.time()+days*86400));d.execute('INSERT INTO quotas(key_id,total,daily,initial_total) VALUES(?,?,?,?)',(kid,total,daily,total));c.audit(d,'Generate access key',kid)
                return self.send(200,{'id':kid,'key':key})
            if self.path=='/api/keys/update':
                kid=data.get('id');total=c.point_tokens(data['total_points']) if 'total_points' in data else c.integer(data.get('total'),0,1000000000);daily=total if 'total_points' in data else c.integer(data.get('daily'),0,1000000000);days=c.integer(data.get('days'),1,3650);enabled=data.get('enabled')
                if type(enabled) is not bool:raise c.Error('Invalid status.')
                with c.store() as d:
                    q=d.execute('SELECT * FROM quotas WHERE key_id=?',(kid,)).fetchone()
                    if not q or not d.execute('SELECT 1 FROM access_keys WHERE id=? AND deleted=0',(kid,)).fetchone():raise c.Error('Key not found.',404)
                    if total<q['used']+q['reserved']:raise c.Error('Total quota cannot be below used plus reserved quota.')
                    d.execute('UPDATE quotas SET total=?,daily=? WHERE key_id=?',(total,daily,kid));d.execute('UPDATE access_keys SET enabled=?,expires=? WHERE id=?',(int(enabled),time.time()+days*86400,kid))
                    if not enabled:d.execute('DELETE FROM sessions WHERE key_id=?',(kid,))
                    if 'label' in data:
                        label=str(data['label']).strip()
                        if not 1<=len(label)<=100:raise c.Error('The note must contain1to100characters.')
                        d.execute('UPDATE access_keys SET label=? WHERE id=?',(label,kid))
                    c.audit(d,'Adjust key and quota',kid)
                return self.send(200,{'ok':True})
            if self.path=='/api/profiles/save':return self.send(200,{'id':c.save_profile(data)})
            if self.path=='/api/profiles/test':
                if not self.server.test_lock.acquire(blocking=False):raise c.Error('A test is already running, Wait for the result.',429)
                try:
                    with c.store() as d:
                        last=d.execute('SELECT created FROM checks ORDER BY created DESC LIMIT 1').fetchone()
                    if last and last['created']>time.time()-5:raise c.Error('Please wait 5 seconds before testing again.',429)
                    return self.send(200,c.light_test(data.get('id'),data.get('mode')))
                finally:self.server.test_lock.release()
            if self.path=='/api/profiles/activate':
                pid=data.get('id')
                with c.store() as d:
                    if not d.execute('SELECT 1 FROM profiles WHERE id=?',(pid,)).fetchone():raise c.Error('Configuration not found.',404)
                    for mode in ('connect','tool'):
                        check=d.execute('SELECT * FROM checks WHERE profile_id=? AND mode=? ORDER BY created DESC LIMIT 1',(pid,mode)).fetchone()
                        if not check or not check['ok'] or check['created']<time.time()-7*86400:raise c.Error('Pass both connectivity and basic-call tests first(7 within days).')
                    d.execute('UPDATE profiles SET active=0');d.execute('UPDATE profiles SET active=1 WHERE id=?',(pid,));c.audit(d,'Enable API Configuration',pid)
                return self.send(200,{'ok':True})
            if self.path=='/api/profiles/pause':
                with c.store() as d:d.execute('UPDATE profiles SET active=0');c.audit(d,'Pause model connection','all')
                return self.send(200,{'ok':True})
            if self.path=='/api/profiles/delete':
                with c.store() as d:
                    p=d.execute('SELECT active FROM profiles WHERE id=?',(data.get('id'),)).fetchone()
                    if not p or p['active']:raise c.Error('Only inactive configurations may be deleted.')
                    d.execute('DELETE FROM profiles WHERE id=?',(data['id'],));c.audit(d,'Delete API Draft',data['id'])
                return self.send(200,{'ok':True})
            raise c.Error('Endpoint not found.',404)
        except c.Error as e:self.send(e.status,{'error':str(e)})
        except (ValueError,TypeError,OverflowError):self.send(400,{'error':'Invalid input format.'})
        except Exception:self.send(500,{'error':'Operation failed, Check the local service. Details are not included in the page.'})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['serve','init']);p.add_argument('--port',type=int,default=8767);a=p.parse_args()
    research_store.init()
    if a.command=='init':print(json.dumps({'admin_key':c.init_admin(),'note':'Shown only once, Save this for the administrator only.'},ensure_ascii=False))
    else:print(f'Admin: http://127.0.0.1:{a.port}',flush=True);Server(('127.0.0.1',a.port)).serve_forever()
