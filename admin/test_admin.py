import sys,unittest,tempfile,threading,json,http.client,time,importlib.util
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web-redesign'))
import control as c
import server as public
spec=importlib.util.spec_from_file_location('admin_server',Path(__file__).with_name('server.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();c.DB=public.DB=Path(self.tmp.name)/'db.sqlite';a.research_store.init();self.key=c.init_admin();self.h=a.Server(('127.0.0.1',0));threading.Thread(target=self.h.serve_forever,daemon=True).start();self.cookie='';self.csrf=''
 def tearDown(self):self.h.shutdown();self.h.server_close();self.tmp.cleanup()
 def req(self,path,data=None,origin=None,csrf=True):
  conn=http.client.HTTPConnection('127.0.0.1',self.h.server_port);headers={'Cookie':self.cookie}
  if data is not None:headers.update({'Content-Type':'application/json','Origin':origin or f'http://127.0.0.1:{self.h.server_port}','X-CSRF-Token':self.csrf if csrf else ''})
  conn.request('POST' if data is not None else 'GET',path,json.dumps(data) if data is not None else None,headers);r=conn.getresponse();body=r.read();hdr=dict(r.getheaders());conn.close();return r.status,json.loads(body),hdr
 def login(self):
  code,x,h=self.req('/api/login',{'key':self.key});self.assertEqual(code,200);self.cookie=h['Set-Cookie'].split(';')[0];self.csrf=x['csrf']
 def create(self):
  code,x,_=self.req('/api/keys/create',{'label':'Test','days':7,'total':100000,'daily':20000});self.assertEqual(code,200);return x
 def profile(self,protocol='responses'):
  return c.save_profile({'name':'mock','base_url':'https://example.com/v1','protocol':protocol,'model':'mock-model','api_key':'testing-only-123'})
 def test_roles_csrf_and_secret(self):
  self.assertEqual(self.req('/api/state')[0],401);self.assertEqual(self.req('/api/export')[0],401);self.login();x=self.create();self.assertEqual(self.req('/api/keys/create',{},csrf=False)[0],403);self.assertEqual(self.req('/api/keys/create',{},origin='https://evil.example')[0],403)
  state=self.req('/api/state')[1];self.assertNotIn(x['key'],json.dumps(state));self.cookie='sensys_redesign_session=anything';self.assertEqual(self.req('/api/state')[0],401);self.assertEqual(self.req('/api/login',{'key':x['key']})[0],401)
 def test_disable_and_consent(self):
  self.login();x=self.create()
  with c.store() as d:d.execute('INSERT INTO sessions VALUES(?,?,?)',(c.digest('user-token'),x['id'],time.time()+1000))
  with self.assertRaises(c.Error):c.chat_reply(x['id'],{'question':'q'})
  with c.store() as d:self.assertEqual(d.execute('SELECT COUNT(*) FROM conversations').fetchone()[0],0)
  r=c.chat_reply(x['id'],{'question':'test question','consent':c.CONSENT});self.assertEqual(r['status'],'preview');self.assertEqual(r['tokens'],0)
  self.assertEqual(self.req('/api/keys/update',{'id':x['id'],'days':7,'total':100000,'daily':20000,'enabled':False})[0],200)
  with c.store() as d:self.assertEqual(d.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
  with self.assertRaises(c.Error):c.chat_reply(x['id'],{'question':'q','consent':c.CONSENT})
 def test_encryption_and_activation_gate(self):
  self.login();pid=self.profile();self.assertEqual(self.req('/api/profiles/activate',{'id':pid})[0],400)
  with c.store() as d:p=d.execute('SELECT * FROM profiles').fetchone();self.assertNotIn('testing-only-123',p['secret']);self.assertEqual(c.crypt(p['secret'],True),'testing-only-123')
  self.assertNotIn('testing-only-123',json.dumps(self.req('/api/state')[1]))
 def test_low_budget_and_tool_roundtrip(self):
  for protocol in ('responses','chat'):
   pid=self.profile(protocol)
   ok={'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}],'usage':{'input_tokens':10,'output_tokens':2}} if protocol=='responses' else {'choices':[{'message':{'content':'OK'}}],'usage':{'prompt_tokens':10,'completion_tokens':2}}
   tool={'output':[{'type':'function_call','name':'research_skill_selfcheck','arguments':'{}','call_id':'one'}],'usage':{'input_tokens':12,'output_tokens':3}} if protocol=='responses' else {'choices':[{'message':{'role':'assistant','tool_calls':[{'id':'one','type':'function','function':{'name':'research_skill_selfcheck','arguments':'{}'}}]}}],'usage':{'prompt_tokens':12,'completion_tokens':3}}
   with patch.object(c,'remote',return_value=ok) as m:r=c.light_test(pid,'connect');self.assertTrue(r['ok']);self.assertEqual(m.call_count,1)
   with patch.object(c,'remote',side_effect=[tool,ok]) as m:
    r=c.light_test(pid,'tool');self.assertTrue(r['ok'],r);self.assertEqual(m.call_count,2);self.assertEqual(r['tokens'],27)
    for call in m.call_args_list:
     self.assertEqual(call.args[1].get('max_output_tokens',call.args[1].get('max_completion_tokens')),1024)
     self.assertEqual(call.args[1].get('reasoning',{}).get('effort',call.args[1].get('reasoning_effort')),'low')
 def test_failed_request_releases_quota(self):
  self.login();x=self.create();pid=self.profile()
  with c.store() as d:d.execute('UPDATE profiles SET active=1 WHERE id=?',(pid,))
  with patch.object(c,'remote',side_effect=c.Error('API invalid')):r=c.chat_reply(x['id'],{'question':'q','consent':c.CONSENT})
  self.assertEqual(r['status'],'failed');self.assertEqual(r['tokens'],0)
  with c.store() as d:q=d.execute('SELECT * FROM quotas').fetchone();self.assertEqual(q['reserved'],0);self.assertEqual(q['used'],0)
  with patch.object(c,'remote',return_value={'output':42}):r=c.chat_reply(x['id'],{'question':'q','consent':c.CONSENT});self.assertEqual(r['status'],'failed')
  with c.store() as d:self.assertEqual(d.execute('SELECT reserved FROM quotas').fetchone()[0],0)
 def test_private_network_blocked(self):
  with patch.object(c.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
   with self.assertRaises(c.Error):c.public_address('example.com')
 def test_activate_and_later_failure_blocks(self):
  self.login();pid=self.profile();ok={'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}],'usage':{'input_tokens':10,'output_tokens':2}};tool={'output':[{'type':'function_call','name':'research_skill_selfcheck','arguments':'{}','call_id':'one'}]}
  with patch.object(c,'remote',return_value=ok):c.light_test(pid,'connect')
  with patch.object(c,'remote',side_effect=[tool,ok]):c.light_test(pid,'tool')
  self.assertEqual(self.req('/api/profiles/activate',{'id':pid})[0],200)
  with patch.object(c,'remote',side_effect=c.Error('mock fail')):c.light_test(pid,'connect')
  self.assertEqual(self.req('/api/profiles/activate',{'id':pid})[0],400)
 def test_atomic_quota_and_usage_settlement(self):
  self.login();x=self.create();pid=self.profile();started=threading.Event();release=threading.Event();result=[]
  with c.store() as d:d.execute('UPDATE profiles SET active=1');d.execute('UPDATE quotas SET daily=2000,total=2000')
  def remote(p,b):
   started.set();release.wait(5);return {'output':[{'type':'message','content':[{'type':'output_text','text':'answer'}]}],'usage':{'input_tokens':10,'output_tokens':5}}
  with patch.object(c,'remote',side_effect=remote):
   t=threading.Thread(target=lambda:result.append(c.chat_reply(x['id'],{'question':'q','consent':c.CONSENT})));t.start();self.assertTrue(started.wait(5))
   try:
    with self.assertRaises(c.Error) as error:c.chat_reply(x['id'],{'question':'q','consent':c.CONSENT})
    self.assertEqual(error.exception.status,429)
   finally:release.set();t.join(5)
  self.assertEqual(result[0]['tokens'],15)
  with c.store() as d:q=d.execute('SELECT * FROM quotas').fetchone();self.assertEqual(q['used'],15);self.assertEqual(q['reserved'],0)
 def test_stale_reservation_reclaimed(self):
  self.login();x=self.create()
  with c.store() as d:
   d.execute('UPDATE quotas SET reserved=100')
   d.execute('INSERT INTO quota_days VALUES(?,?,0,100)',(x['id'],c.day()))
   d.execute("INSERT INTO conversations(id,key_id,created,status,reserve_amount,quota_day) VALUES('stale',?,?,'running',100,?)",(x['id'],time.time()-600,c.day()))
  c.init_store()
  with c.store() as d:self.assertEqual(d.execute('SELECT reserved FROM quotas').fetchone()[0],0);self.assertEqual(d.execute("SELECT status FROM conversations WHERE id='stale'").fetchone()[0],'failed')

 def test_points_recharge_and_key_delete_preserve_ledger(self):
  self.login();code,key,_=self.req('/api/keys/create',{'label':'Points test','days':7,'total_points':1000});self.assertEqual(code,200)
  with c.store() as d:
   d.execute('UPDATE quotas SET used=123456 WHERE key_id=?',(key['id'],))
   d.execute('INSERT INTO sessions VALUES(?,?,?)',(c.digest('fixture-session'),key['id'],time.time()+1000))
  self.assertEqual(self.req('/api/keys/update',{'id':key['id'],'label':'Updated holder','days':7,'total_points':1500,'enabled':True,'used':0})[0],200)
  row=next(k for k in self.req('/api/state')[1]['keys'] if k['id']==key['id'])
  self.assertEqual(row['initial_points'],1000);self.assertEqual(row['total_points'],1500);self.assertEqual(row['used_points'],123.456);self.assertEqual(row['remaining_points'],1376.544)
  self.assertEqual(self.req('/api/keys/delete',{'id':key['id']},csrf=False)[0],403)
  self.assertEqual(self.req('/api/keys/delete',{'id':key['id']})[0],200)
  self.assertFalse(any(k['id']==key['id'] for k in self.req('/api/state')[1]['keys']))
  with c.store() as d:
   self.assertEqual(d.execute('SELECT COUNT(*) FROM sessions WHERE key_id=?',(key['id'],)).fetchone()[0],0)
   self.assertEqual(d.execute('SELECT used FROM quotas WHERE key_id=?',(key['id'],)).fetchone()[0],123456)
   self.assertEqual(d.execute('SELECT label,deleted FROM access_keys WHERE id=?',(key['id'],)).fetchone()['deleted'],1)

if __name__=='__main__':unittest.main(verbosity=2)
