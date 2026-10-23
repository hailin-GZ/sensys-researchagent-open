import sys,json,time,tempfile,unittest,threading,http.client
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'web-redesign')]
import control,server
from agent import store as s,models,engine,http_api
from agent.tools import Executor,r

def reviewed_fixture(result):
 return {**result,'modules':[{'module_id':'observations','title':'\u6d4b\u8bd5\u8d44\u6599\u89c2\u5bdf','intro':'\u4ec5\u9650\u6d4b\u8bd5\u8d44\u6599','finding_refs':[f['finding_id'] for f in result.get('findings',[])],'gaps':['\u4e0d\u80fd\u4f5c\u4e3a\u5e02\u573a\u8bc1\u636e']}]}

class AgentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.old=(control.DB,server.DB,s.ARTIFACTS,s.SETTINGS)
  control.DB=server.DB=self.root/'db.sqlite';s.ARTIFACTS=self.root/'tasks'
  original=s.settings();original['native_web_search']=False;s.SETTINGS=self.root/'settings.json';s.SETTINGS.write_text(json.dumps(original),encoding='utf-8');s.init()
  self.kid='owner';self.other='other'
  with control.store() as d:
   for kid in (self.kid,self.other):
    d.execute('INSERT INTO access_keys(id,digest,label,expires,enabled) VALUES(?,?,?,?,1)',(kid,control.digest(kid),kid,time.time()+86400))
    d.execute('INSERT INTO quotas(key_id,total,daily) VALUES(?,1000000,1000000)',(kid,))
  pid=control.save_profile({'name':'test','base_url':'https://example.com/v1','protocol':'responses','model':'example-model','api_key':'test-only-not-live'})
  with control.store() as d:d.execute('UPDATE profiles SET active=1 WHERE id=?',(pid,))
 def tearDown(self):
  control.DB,server.DB,s.ARTIFACTS,s.SETTINGS=self.old;self.tmp.cleanup()
 def job(self):return s.submit(self.kid,{'question':'\u771f\u5b9e\u8bc1\u636e\u7814\u7a76','consent':control.CONSENT})['id']
 def test_effort_policy(self):
  for depth in ('standard','deep'):
   for effort in ('xhigh','max','ultra','none'):
    with self.assertRaises(ValueError):models.effort_allowed(depth,effort,'review','reason')
  with self.assertRaises(ValueError):models.effort_allowed('standard','high','analysis','complex')
  with self.assertRaises(ValueError):models.effort_allowed('deep','high','decision','complex')
  with self.assertRaises(ValueError):models.effort_allowed('deep','low','decision')
  self.assertEqual(models.effort_allowed('deep','high','review','independent conflicting-source review'),'high')
 def test_owner_isolation_and_single_active_task(self):
  jid=self.job()
  with self.assertRaises(control.Error):s.get(jid,self.other)
  with self.assertRaises(control.Error):self.job()
  self.assertEqual(s.records(self.other),[])
 def test_usage_is_actual_and_cache_not_double_counted(self):
  jid=self.job();out={'id':'verified-response','usage':{'input_tokens':101,'output_tokens':20,'input_tokens_details':{'cached_tokens':75},'output_tokens_details':{'reasoning_tokens':12}},'output':[]}
  with patch.object(models,'response',return_value=out):models.call(jid,'decision','medium','','instructions',[{'role':'user','content':'q'}])
  j=s.get(jid);self.assertEqual(j['tokens'],121);self.assertEqual(j['cached_tokens'],75);self.assertEqual(j['reasoning_tokens'],12)
  with control.store() as d:q=d.execute('SELECT * FROM quotas WHERE key_id=?',(self.kid,)).fetchone();self.assertEqual(q['used'],121);self.assertEqual(q['reserved'],0)
 def test_unknown_usage_stops_and_conservatively_settles(self):
  jid=self.job()
  with patch.object(models,'response',return_value={'output':[]}):
   with self.assertRaises(control.Error):models.call(jid,'decision','medium','','instructions',[{'role':'user','content':'q'}])
  j=s.detail(jid);self.assertGreater(j['tokens'],4096);self.assertEqual(j['calls'][0]['usage_known'],0)
 def test_preflight_failure_before_request_releases_quota_without_model_charge(self):
  jid=self.job()
  with patch.object(control,'public_address',side_effect=control.Error('Synthetic invalid model address')),patch('openai.AsyncOpenAI') as transport:
   with self.assertRaises(control.Error):models.call(jid,'decision','medium','','instructions',[])
   transport.assert_not_called()
  j=s.detail(jid);self.assertEqual(j['tokens'],0);self.assertEqual(j['calls'][0]['usage_known'],1)
  self.assertFalse(json.loads(j['calls'][0]['details'])['request_started'])
  with control.store() as d:
   q=d.execute('SELECT used,reserved FROM quotas WHERE key_id=?',(self.kid,)).fetchone()
   self.assertEqual((q['used'],q['reserved']),(0,0))
 def test_cancel_before_paid_call(self):
  jid=self.job();s.action(self.kid,{'id':jid,'action':'cancel'})
  with patch.object(models,'response') as fn:
   with self.assertRaises(control.Error):models.call(jid,'decision','medium','','instructions',[])
   fn.assert_not_called()
 def test_atomic_quota_blocks_over_reservation(self):
  jid=self.job()
  with control.store() as d:d.execute('UPDATE quotas SET daily=10 WHERE key_id=?',(self.kid,))
  with patch.object(models,'response') as fn:
   with self.assertRaises(control.Error):models.call(jid,'decision','medium','','instructions',[])
   fn.assert_not_called()
 def test_cancel_during_stream_closes_response_and_settles_unknown_usage(self):
  jid=self.job()
  def supplier(profile,instructions,items,tools,effort,cap,on_progress=None,format_schema=None):
   s.action(self.kid,{'id':jid,'action':'cancel'});on_progress('response.output_text.delta',10)
   self.fail('Cancelled streaming response must not continue')
  with patch.object(models,'response',side_effect=supplier):
   with self.assertRaises(InterruptedError):models.call(jid,'analysis','medium','','fixture',[])
  with control.store() as d:
   quota=d.execute('SELECT used,reserved FROM quotas WHERE key_id=?',(self.kid,)).fetchone()
   self.assertEqual(quota['reserved'],0);self.assertGreater(quota['used'],0)
   call=d.execute('SELECT usage_known,status FROM research_calls WHERE job_id=?',(jid,)).fetchone()
   self.assertEqual(call['usage_known'],0);self.assertNotEqual(call['status'],'running')
 def test_recovery_charges_once_and_does_not_retry(self):
  jid=self.job();s.update(jid,status='running',started=time.time()-1)
  with control.store() as d:
   d.execute('UPDATE quotas SET reserved=200 WHERE key_id=?',(self.kid,))
   d.execute('INSERT INTO quota_days VALUES(?,?,0,200)',(self.kid,control.day()))
   d.execute("INSERT INTO research_calls(id,job_id,kind,status,reserved,quota_day) VALUES('call',?,'model','running',200,?)",(jid,control.day()))
  with patch.object(models,'response') as fn:engine.recover();engine.recover();fn.assert_not_called()
  j=s.get(jid);self.assertEqual(j['tokens'],200);self.assertEqual(j['status'],'paused')
 def test_upgrade_preserves_usage_evidence_and_ids(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  src=self.root/'feedback.txt';src.write_text('Actual evidence from a supplied document.',encoding='utf-8');rec=r.capture(ex.root,file=str(src));before=r.read_json(ex.root/'research-budget.json')['used'].copy()
  s.update(jid,status='partial');s.action(self.kid,{'id':jid,'action':'deepen'})
  self.assertEqual(s.get(jid)['depth'],'deep');r.depth.select(ex.root,'deep','explicit user selection')
  self.assertEqual(r.read_json(ex.root/'research-budget.json')['used'],before);self.assertEqual(r.read_json(ex.root/'sources.json')[0]['source_id'],rec['source_id'])
 def test_quotes_require_read_archive_and_reject_fabrication(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  src=self.root/'feedback.txt';src.write_text('Actual evidence from a supplied document.',encoding='utf-8');rec=r.capture(ex.root,file=str(src));sid=rec['source_id']
  with self.assertRaises(ValueError):ex.tool_register_evidence(sid,'p0001','invented')
  blocks=ex.tool_read_evidence([sid])['blocks'];b=blocks[0]
  with self.assertRaises(ValueError):ex.tool_register_evidence(sid,b['block_id'],'invented')
  e=ex.tool_register_evidence(sid,b['block_id'],b['text']);self.assertEqual(e['source_id'],sid)
 def test_required_coverage_and_partial_truth(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  plan={'schema_version':'2.0','decision':'decision','selected_capability_ids':[],'excluded_modes':[],'roles':[{'role':'user_voices','required':True,'reason':'needs','status':'missing','source_ids':[],'gap':'not acquired'}]}
  ex.tool_save_coverage_plan(json.dumps(plan));self.assertTrue((ex.root/'research-plan.json').exists())
  self.assertTrue(engine.c.check_plan(ex.root,plan,complete=True))
 def test_settings_cannot_enable_prohibited_effort(self):
  with self.assertRaises(control.Error):s.save_settings({'reasoning_effort':'xhigh'})
  with self.assertRaises(control.Error):s.save_settings({'deep':{'effort':'max'}})
  saved=s.save_settings({'standard':{'search_queries':16}});self.assertEqual(saved['standard']['search_queries'],16)
 def test_common_reference_loader_accepts_main_skill_paths(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  out=ex.tool_load_methods(paths=['references/coverage.md','references/evidence.md'])
  self.assertEqual(len(out['files']),2)
  with self.assertRaises(ValueError):ex.tool_load_methods(paths=['../../runtime/private/local-access.json'])
 def test_benchmark_compatibility_still_rejects_private_and_literal_ip(self):
  import os
  with patch.dict(os.environ,{'SENSYS_ALLOW_BENCHMARK_DNS':'1'}):
   for host,ip in [('private.example','127.0.0.1'),('private.example','192.168.1.1'),('198.18.0.68','198.18.0.68')]:
    with patch.object(control.socket,'getaddrinfo',return_value=[(2,1,6,'',(ip,443))]):
     with self.assertRaises(control.Error):control.public_address(host)
 def test_tool_replay_is_idempotent(self):
  jid=self.job();ex=Executor(jid);args={'modes':['needs'],'decision':'decision'}
  a=ex.invoke('configure_research',args,'unique-provider-id');b=ex.invoke('configure_research',args,'unique-provider-id')
  self.assertEqual(a,b);self.assertEqual(s.get(jid)['tool_calls'],1)
 def test_bounded_finish_produces_reviewed_report_with_real_archive(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  src=self.root/'document.txt';src.write_text('Original document states a verifiable observation.',encoding='utf-8');rec=r.capture(ex.root,file=str(src));b=ex.tool_read_evidence([rec['source_id']])['blocks'][0];e=ex.tool_register_evidence(rec['source_id'],b['block_id'],b['text'])
  draft={'status':'partial','summary':'\u53ef\u8ffd\u6eaf\u7684\u6d4b\u8bd5\u8d44\u6599; \u5916\u90e8\u5e02\u573a\u7ed3\u8bba\u672a\u77e5.','findings':[{'finding_id':'f1','statement':'\u5bfc\u5165\u8d44\u6599\u8bb0\u8f7d\u4e86\u4e00\u6761\u53ef\u5b9a\u4f4d\u7684\u89c2\u5bdf.','kind':'fact','evidence_refs':[e['evidence_id']],'limitations':['\u6d4b\u8bd5\u8d44\u6599, \u4e0d\u80fd\u7528\u4e8e\u5e02\u573a\u7ed3\u8bba']}],'conflicts':[],'missing_evidence':['\u672a\u91c7\u96c6\u5916\u90e8\u5e02\u573a\u8bc1\u636e'],'assumptions':[],'next_steps':['\u8865\u5145\u771f\u5b9e\u8d44\u6599']}
  calls=[]
  def provider(profile,instructions,items,tools,effort,cap,on_progress=None,format_schema=None):
   calls.append((effort,bool(tools)))
   value={'result':reviewed_fixture(draft),'review_notes':['\u4fdd\u7559\u6d4b\u8bd5\u8303\u56f4\u9650\u5236']} if 'Independently review' in instructions else {'new_quotes':[],'result':draft}
   return {'status':'completed','id':'fixture-only','usage':{'input_tokens':100,'output_tokens':50},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value,ensure_ascii=False)}]}]}
  with patch.object(models,'response',side_effect=provider):engine.finish_draft(ex);fixed=engine.review(ex)
  self.assertTrue(fixed['support_reviewed']);self.assertTrue((ex.root/'report.md').exists());self.assertTrue(r.read_json(ex.root/'validation.json')['ok']);self.assertEqual(calls,[('medium',False),('medium',False)])
 def test_imported_source_metadata_keeps_integrity_hashes(self):
  from agent.tools import annotate_source
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  src=self.root/'document.txt';src.write_text('Actual original text.',encoding='utf-8');rec=r.capture(ex.root,file=str(src));annotate_source(ex.root,rec,{'publisher':'Test fixture'})
  result=r.read_json(ex.root/'result.json');result['summary']='No market conclusion from a fixture';r.write_json(ex.root/'result.json',result)
  self.assertTrue(r.validate(ex.root)['ok'])
 def test_raw_artifact_download_has_owner_and_path_guards(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  src=self.root/'document.txt';src.write_text('Original text.',encoding='utf-8');rec=r.capture(ex.root,file=str(src))
  class Fake:
   def send(self,code,value,*args,**kw):return (code,value,args,kw)
  h=Fake();h.path='/api/artifact?id='+jid+'&path='+rec['artifacts']['raw'];out=http_api.get(h,self.kid);self.assertEqual(out[1],b'Original text.');self.assertTrue(out[3]['download'])
  with self.assertRaises(control.Error):http_api.get(h,self.other)
  h.path='/api/artifact?id='+jid+'&path=../../private/local-access.json'
  with self.assertRaises(control.Error):http_api.get(h,self.kid)
  h.path='/api/job/package?id='+jid;out=http_api.get(h,self.kid);import zipfile,io
  with zipfile.ZipFile(io.BytesIO(out[1])) as z:self.assertIn(rec['artifacts']['raw'],z.namelist());self.assertFalse(any('model-receipts' in p or 'checkpoint' in p for p in z.namelist()))
 def test_invalid_draft_is_isolated_until_review(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  draft={'status':'partial','summary':'\u672a\u7ecf\u6838\u9a8c\u7684\u8349\u7a3f','findings':[{'finding_id':'f1','kind':'fact','statement':'Needs evidence verification','evidence_refs':['s0001'],'limitations':['Unvalidated fixture']}],'missing_evidence':[]}
  out=ex.tool_save_research_result(json.dumps(draft));self.assertEqual(out['status'],'draft_saved_for_review');self.assertFalse(r.read_json(ex.root/'result.json')['support_reviewed']);self.assertFalse((ex.root/'report.md').exists());self.assertTrue(Executor(jid).draft_saved)
 def test_mixed_acquisition_is_not_reported_as_full_success(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  with patch.object(r,'capture',side_effect=[{'source_id':'s0001','status':'complete_body'},{'source_id':'s0002','status':'captcha'}]):ex.invoke('capture_sources',{'urls':['https://example.com/a','https://example.com/b']})
  call=s.detail(jid)['calls'][-1];self.assertEqual(call['status'],'partial')
 def test_sdk_swallowed_failure_is_not_empty_verified_reviews(self):
  import ssl
  factory=ssl._create_default_https_context
  import google_play_scraper.utils.request
  ssl._create_default_https_context=factory
  from urllib.error import URLError
  from unittest.mock import MagicMock
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['voices'],'decision');opener=MagicMock();opener.open.side_effect=URLError('fixture network failure')
  with patch('urllib.request.build_opener',return_value=opener),patch.object(r,'public_url',side_effect=lambda x:x):
   with self.assertRaises(ValueError):ex.tool_platform_read('google_play_reviews','com.test.app',10)
  self.assertEqual(opener.open.call_count,1);self.assertIs(ssl._create_default_https_context,factory);self.assertEqual(r.read_json(ex.root/'sources.json'),[])
 def test_chinese_adjacent_followup_citation_still_requires_real_evidence(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'decision')
  with self.assertRaises(ValueError):ex.tool_answer_existing('\u6839\u636ee9999\u53ef\u4ee5\u786e\u8ba4.')
 def test_uploaded_material_retains_name_owner_and_integrity(self):
  import hashlib
  folder=self.root/'runtime'/'uploads';folder.mkdir(parents=True);path=folder/'opaque-id.txt';raw='\u771f\u5b9e\u8bbf\u8c08\u6d4b\u8bd5\u8d44\u6599, \u4e0d\u662f\u5e02\u573a\u7ed3\u8bba.'.encode('utf-8');path.write_bytes(raw)
  with control.store() as d:d.execute('INSERT INTO research_uploads VALUES(?,?,?,?,?,?,?)',('upload-id',self.kid,'\u8bbf\u8c08\u8d44\u6599.txt',str(path),len(raw),hashlib.sha256(raw).hexdigest(),time.time()))
  with self.assertRaises(control.Error):s.submit(self.other,{'question':'test','consent':control.CONSENT,'uploads':['upload-id']})
  jid=s.submit(self.kid,{'question':'test','consent':control.CONSENT,'uploads':['upload-id']})['id'];ex=Executor(jid)
  with patch.object(s,'ROOT',self.root),patch.object(s,'RUNTIME',self.root/'runtime'):ex.tool_configure_research(['needs'],'decision')
  self.assertEqual(r.read_json(ex.root/'brief.json')['provided_materials'][0]['name'],'\u8bbf\u8c08\u8d44\u6599.txt');self.assertEqual(r.read_json(ex.root/'sources.json')[0]['title'],'\u8bbf\u8c08\u8d44\u6599.txt')
  result=r.read_json(ex.root/'result.json');result['summary']='\u4e0a\u4f20\u94fe\u8def\u9a8c\u8bc1\u8d44\u6599, \u672a\u4ea7\u751f\u5e02\u573a\u7ed3\u8bba.';r.write_json(ex.root/'result.json',result)
  self.assertTrue(r.validate(ex.root)['ok'])
 def test_declared_tools_are_strict_and_match_every_handler(self):
  import inspect
  from agent.tools import DEFINITIONS
  from jsonschema import Draft202012Validator
  def objects(schema):
   if schema.get('type')=='object':
    self.assertFalse(schema['additionalProperties']);self.assertEqual(set(schema['required']),set(schema['properties']))
   for sub in schema.get('properties',{}).values():objects(sub)
   if 'items' in schema:objects(schema['items'])
  for tool in DEFINITIONS:
   self.assertTrue(tool['strict']);Draft202012Validator.check_schema(tool['parameters']);objects(tool['parameters'])
   self.assertEqual(set(tool['parameters']['properties']),set(inspect.signature(getattr(Executor,'tool_'+tool['name'])).parameters)-{'self'})
 def test_invalid_tool_arguments_are_logged_without_executing(self):
  jid=self.job();ex=Executor(jid)
  for name,args in [('configure_research','{"modes":'),('configure_research',{'modes':['needs'],'decision':'test','unexpected':True}),('search_sources',{'queries':'not an array'}),('not_registered',{})]:
   with patch.object(r,'discover') as network:
    value=ex.invoke(name,args);self.assertEqual(value['status'],'failed');network.assert_not_called()
  self.assertEqual(len(s.detail(jid)['calls']),4)
 def test_null_optionals_use_real_handler_defaults(self):
  jid=self.job();ex=Executor(jid)
  out=ex.invoke('configure_research',{'modes':['needs'],'decision':'fixture only','population':None,'geography':None,'time_window':None})
  self.assertNotEqual(out.get('status'),'failed');self.assertIsNone(r.read_json(ex.root/'brief.json')['research_scope']['geography'])
 def test_failed_network_route_is_attempted_once_per_run(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  args={'urls':['https://example.com/unavailable']}
  with patch.object(r,'capture',return_value={'source_id':'s0001','status':'network_error'}) as network, patch.object(ex,'tool_scrapling_capture',return_value={'source_id':'s0002','status':'network_error'}) as alternative:
   ex.invoke('capture_sources',args,'first');out=ex.invoke('capture_sources',args,'second')
   self.assertTrue(out['cached_failure']);self.assertEqual(network.call_count,1)
   s.update(jid,run=1);ex.invoke('capture_sources',args,'explicit-new-run');self.assertEqual(network.call_count,2)
   self.assertEqual(alternative.call_count,2)
 def test_malformed_usage_is_conservatively_settled(self):
  jid=self.job()
  for u in [{'input_tokens':'10','output_tokens':20},{'input_tokens':True,'output_tokens':20},{'input_tokens':-1,'output_tokens':20}]:self.assertFalse(models.metrics({'usage':u})['known'])
  with patch.object(models,'response',return_value={'usage':{'input_tokens':'bad','output_tokens':20},'output':[]}):
   with self.assertRaises(control.Error):models.call(jid,'decision','medium','','fixture',[])
  with control.store() as d:self.assertEqual(d.execute('SELECT reserved FROM quotas WHERE key_id=?',(self.kid,)).fetchone()[0],0)
 def test_compaction_keeps_multiple_tool_outputs_with_their_calls(self):
  items=[{'role':'user','content':'old'*20000},{'type':'function_call','call_id':'a'},{'type':'function_call','call_id':'b'},{'type':'function_call_output','call_id':'a','output':'one'},{'type':'function_call_output','call_id':'b','output':'two'},{'type':'reasoning','summary':[]},{'type':'function_call','call_id':'c'},{'type':'function_call_output','call_id':'c','output':'three'}]
  compacted=engine.compact(None,items);calls={x['call_id'] for x in compacted if x.get('type')=='function_call'}
  self.assertEqual({x['call_id'] for x in compacted if x.get('type')=='function_call_output'},calls)
 def test_published_report_survives_new_invalid_draft(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  result=r.read_json(ex.root/'result.json');result.update(summary='Reviewed fixture, not market evidence',support_reviewed=True);r.write_json(ex.root/'result.json',result)
  r.write_json(ex.root/'validation.json',{'ok':True});(ex.root/'report.md').write_text('Reviewed fixture report',encoding='utf-8');s.publish_bundle(jid)
  result.update(summary='Unvalidated replacement',support_reviewed=False);r.write_json(ex.root/'result.json',result);r.write_json(ex.root/'validation.json',{'ok':False})
  bundle=s.bundle(jid,self.kid);self.assertEqual(bundle['result']['summary'],'Reviewed fixture, not market evidence');self.assertTrue(bundle['validation']['ok'])
 def test_coverage_review_updates_sources_without_changing_scope(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  src=self.root/'paper.txt';src.write_text('A test fixture only.',encoding='utf-8');rec=r.capture(ex.root,file=str(src))
  plan={'schema_version':'2.0','decision':'fixture','selected_capability_ids':[],'excluded_modes':[],'roles':[{'role':'scientific_research','required':True,'reason':'original scope','status':'missing','source_ids':[],'gap':'not read'}]}
  engine.apply_coverage_review(ex,plan,[{'role':'scientific_research','status':'partial','source_ids':[rec['source_id']],'gap':'fixture does not establish research evidence'}])
  saved=r.read_json(ex.root/'research-plan.json');self.assertEqual(saved['roles'][0]['reason'],'original scope');self.assertTrue(saved['roles'][0]['required']);self.assertEqual(saved['roles'][0]['status'],'partial')
  with self.assertRaises(ValueError):engine.apply_coverage_review(ex,plan,[{'role':'unplanned','status':'missing','source_ids':[],'gap':'test'}])
 def test_complete_runtime_path_archives_reviews_and_publishes(self):
  import hashlib
  folder=self.root/'runtime/uploads';folder.mkdir(parents=True);src=folder/'fixture.txt';text='Fixture observation from a supplied document, not a market conclusion.';src.write_text(text,encoding='utf-8')
  with control.store() as d:d.execute('INSERT INTO research_uploads VALUES(?,?,?,?,?,?,?)',('fixture',self.kid,'fixture.txt',str(src),len(src.read_bytes()),hashlib.sha256(src.read_bytes()).hexdigest(),time.time()))
  jid=s.submit(self.kid,{'question':'Explain fixture only','consent':control.CONSENT,'uploads':['fixture']})['id'];root=s.ARTIFACTS/jid;steps=[]
  checks=[{'check':c,'status':'gap','reason':'fixture only','finding_refs':['f1']} for c in ['decision_scope','source_roles','contrary_evidence','next_validation']]
  draft={'status':'partial','summary':'Fixture only; no market evidence.','findings':[{'finding_id':'f1','statement':'Supplied test document contains an observation.','kind':'source_opinion','evidence_refs':['e0001'],'limitations':['Fixture, not market evidence']}],'conflicts':[],'missing_evidence':['Real market evidence'],'assumptions':[],'next_steps':['Collect real evidence'],'depth_review':{'research_depth':'standard','checks':checks}}
  plan={'schema_version':'2.0','decision':'fixture','selected_capability_ids':[],'excluded_modes':[],'roles':[{'role':'supplied_research','required':True,'reason':'fixture scope','status':'captured','source_ids':['s0001'],'gap':''}]}
  def provider(profile,instructions,items,tools,effort,cap,on_progress=None,format_schema=None):
   steps.append(effort)
   if 'Independently review' in instructions:value={'result':reviewed_fixture(draft),'review_notes':['Fixture scope preserved'],'coverage_updates':[{'role':'supplied_research','status':'captured','source_ids':['s0001'],'gap':''}]};output=[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]
   else:
    n=len(steps)
    if n==1:name,args='configure_research',{'modes':['needs'],'decision':'fixture'}
    elif n==2:name,args='save_coverage_plan',{'json':plan}
    elif n==3:name,args='set_deliverable_plan',{'target_findings':1,'dimensions':['fixture observation'],'rationale':'One supplied synthetic observation only'}
    elif n==4:name,args='read_evidence',{'source_ids':['s0001']}
    elif n==5:
     block=r.read_json(root/'sources/s0001/blocks.json')[0];name,args='register_evidence',{'source_id':'s0001','block_id':block['block_id'],'quote':block['text']}
    elif n==6:name,args='save_research_result',{'json':draft}
    else:raise AssertionError('Unexpected model loop')
    self.assertIn(name,{t['name'] for t in tools})
    output=[{'type':'function_call','name':name,'arguments':json.dumps(args),'call_id':'fixture-'+str(n)}]
   return {'status':'completed','id':'fixture-only','usage':{'input_tokens':100,'output_tokens':20},'output':output}
  with patch.object(s,'ROOT',self.root),patch.object(s,'RUNTIME',self.root/'runtime'),patch.object(models,'response',side_effect=provider):engine.run(jid)
  self.assertEqual(s.get(jid)['status'],'partial',s.get(jid)['error']);self.assertEqual(len(steps),7);self.assertTrue(s.bundle(jid)['validation']['ok']);self.assertTrue((root/'published.json').exists());self.assertTrue((root/'runs/1-standard/report.md').exists());self.assertTrue((root/'coverage-review.json').exists())
 def test_unoffered_tool_cannot_execute_even_if_registered(self):
  jid=self.job();ex=Executor(jid)
  with patch.object(r,'discover') as network:
   out=ex.invoke('search_sources',{'queries':['test']},allowed_names={'configure_research'});self.assertEqual(out['execution_status'],'failed');network.assert_not_called()
 def test_source_listing_has_consistent_result_envelope(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  out=ex.invoke('list_sources',{});self.assertIsInstance(out,dict);self.assertEqual(out['sources'],[]);self.assertEqual(out['execution_status'],'succeeded')
 def test_long_task_detail_returns_latest_events(self):
  jid=self.job()
  for n in range(305):s.event(jid,'fixture',str(n))
  events=s.detail(jid)['events'];self.assertEqual(len(events),300);self.assertEqual(events[-1]['message'],'304');self.assertLess(events[0]['id'],events[-1]['id'])
 def test_invalid_review_coverage_gets_one_bounded_correction(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  src=self.root/'fixture.txt';src.write_text('Supplied fixture observation.',encoding='utf-8');record=r.capture(ex.root,file=str(src));block=ex.tool_read_evidence([record['source_id']])['blocks'][0];quote=ex.tool_register_evidence(record['source_id'],block['block_id'],block['text'])
  plan={'schema_version':'2.0','decision':'fixture','selected_capability_ids':[],'excluded_modes':[],'roles':[{'role':'supplied_research','required':True,'reason':'fixture','status':'partial','source_ids':[record['source_id']],'gap':'test only'}]};ex.tool_save_coverage_plan(json.dumps(plan))
  ex.tool_save_research_result(json.dumps({'status':'partial','summary':'Fixture only','findings':[{'finding_id':'f1','statement':'Fixture observation','kind':'source_opinion','evidence_refs':[quote['evidence_id']],'limitations':['Not market evidence']}],'missing_evidence':['Real market data']}))
  count=[]
  def provider(profile,instructions,items,tools,effort,cap,on_progress=None,format_schema=None):
   count.append(effort);update={'role':'wrong' if len(count)==1 else 'supplied_research','status':'partial','source_ids':[record['source_id']],'gap':'Fixture only'}
   value={'result':reviewed_fixture(r.read_json(ex.root/'result.json')),'review_notes':['Fixture only'],'coverage_updates':[update]}
   return {'status':'completed','id':'review-fixture-'+str(len(count)),'usage':{'input_tokens':100,'output_tokens':20},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
  with patch.object(models,'response',side_effect=provider):engine.review(ex)
  review=r.read_json(ex.root/'support-review.json');self.assertEqual(count,['medium','medium']);self.assertEqual(len(review['reviews']),2);self.assertEqual(review['response_id'],'review-fixture-2');self.assertTrue(s.bundle(jid)['validation']['ok'])
 def test_three_nonproductive_turns_stop_without_unbounded_paid_loop(self):
  jid=self.job();out={'status':'completed','id':'fixture','usage':{'input_tokens':100,'output_tokens':20},'output':[{'type':'message','content':[{'type':'output_text','text':'No action fixture'}]}]}
  with patch.object(models,'response',return_value=out) as provider:engine.run(jid)
  self.assertEqual(provider.call_count,3);self.assertEqual(s.get(jid)['status'],'paused')

 def test_bounded_draft_rejects_inexact_quote_without_publishing_it(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  value={'new_quotes':[{'source_id':'s9999','block_id':'p0001','quote':'Invented fixture quote','role':'observation','context':'','ref':'q1'}],'result':{'status':'partial','summary':'Unverified fixture draft','findings':[{'finding_id':'f1','statement':'Unverified fixture claim','kind':'source_opinion','evidence_refs':['q1'],'limitations':['Must be reviewed']}],'missing_evidence':['Actual original support']}}
  output={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
  with patch.object(models,'call',return_value=output):engine.finish_draft(ex)
  self.assertTrue(ex.draft_saved);self.assertEqual(r.read_json(ex.root/'evidence.json'),[])
  self.assertTrue((ex.root/'unvalidated-draft.json').exists());self.assertFalse((ex.root/'published.json').exists())
  self.assertTrue(any(x['kind']=='quote_rejected' for x in s.detail(jid)['events']))

 def test_batch_quote_preflight_prevents_partial_registration(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  src=self.root/'fixture.txt';src.write_text('Actual fixture observation.',encoding='utf-8');record=r.capture(ex.root,file=str(src))
  block=ex.tool_read_evidence([record['source_id']])['blocks'][0]
  valid={'source_id':record['source_id'],'block_id':block['block_id'],'quote':block['text']}
  with self.assertRaises(ValueError):ex.tool_register_evidence_batch([valid,{**valid,'quote':'Not in the fixture'}])
  self.assertEqual(r.read_json(ex.root/'evidence.json'),[])
  first=ex.tool_register_evidence(**valid);again=ex.tool_register_evidence(**valid)
  self.assertEqual(first['evidence_id'],again['evidence_id']);self.assertEqual(len(r.read_json(ex.root/'evidence.json')),1)

 def test_default_method_loading_advances_without_repeating_full_text(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  first=ex.tool_load_methods(['needs']);second=ex.tool_load_methods(['needs'])
  a={x['path'] for x in first['files']};b={x['path'] for x in second['files']}
  self.assertTrue(a and b);self.assertFalse(a&b)
  explicit=ex.tool_load_methods(['needs'],paths=[first['files'][0]['path']])
  self.assertEqual(explicit['files'][0]['path'],first['files'][0]['path'])

 def test_existing_followup_uses_two_bounded_calls_and_preserves_publication(self):
  jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'fixture')
  result=r.read_json(ex.root/'result.json');result.update(summary='Reviewed fixture only',support_reviewed=True);r.write_json(ex.root/'result.json',result)
  r.write_json(ex.root/'validation.json',{'ok':True});(ex.root/'report.md').write_text('Reviewed fixture report',encoding='utf-8');s.publish_bundle(jid)
  original=(ex.root/'published.json').read_bytes();s.update(jid,status='partial')
  s.action(self.kid,{'id':jid,'action':'ask','question':'What is still unknown?'})
  value={'answer':'Fixture only; real user needs remain unknown.','evidence_refs':[],'remaining_gaps':['Real evidence']}
  out={'status':'completed','id':'followup-fixture','usage':{'input_tokens':100,'output_tokens':20},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
  with patch.object(models,'response',return_value=out) as provider:engine.run(jid)
  self.assertEqual(provider.call_count,2);self.assertEqual(s.get(jid)['status'],'answered',s.get(jid)['error'])
  self.assertEqual((ex.root/'published.json').read_bytes(),original);self.assertEqual(s.get(jid)['tool_calls'],0)
  self.assertTrue((ex.root/'followup-review-1.json').exists())

 def test_multiple_research_questions_share_owner_scoped_conversation(self):
  from agent import conversations as chats
  first=s.submit(self.kid,{'question':'Fixture first question'})
  s.update(first['id'],status='partial')
  second=s.submit(self.kid,{'question':'Fixture follow-up research','conversation_id':first['thread_id']})
  self.assertEqual(first['thread_id'],second['thread_id'])
  detail=chats.detail(first['thread_id'],self.kid)
  self.assertEqual(len(detail['jobs']),2);self.assertEqual(len(detail['messages']),2)
  self.assertEqual(len(chats.list_threads(self.kid)),1);self.assertEqual(chats.list_threads(self.other),[])
  with self.assertRaises(control.Error):chats.detail(first['thread_id'],self.other)
  with self.assertRaises(control.Error):chats.stages(first['thread_id'],self.other)
  with self.assertRaises(control.Error):s.submit(self.other,{'question':'cross owner','conversation_id':first['thread_id']})

 def test_thread_migration_is_idempotent_and_preserves_messages(self):
  from agent import conversations as chats
  j=s.submit(self.kid,{'question':'Fixture migration'})
  with control.store() as d:d.execute('UPDATE research_jobs SET thread_id=NULL WHERE id=?',(j['id'],))
  s.init();s.init();after=s.public(j['id']);self.assertEqual(after['question'],j['question']);self.assertEqual(after['messages'],j['messages'])
  self.assertEqual(chats.detail(after['thread_id'],self.kid)['jobs'][0]['id'],j['id'])

 def test_attachment_total_limit_is_enforced_on_server(self):
  for uid,size in [('one',20*1024*1024),('two',11*1024*1024)]:
   with control.store() as d:d.execute('INSERT INTO research_uploads VALUES(?,?,?,?,?,?,?)',(uid,self.kid,uid+'.txt','fixture-path',size,'fixture-sha',time.time()))
  with self.assertRaises(control.Error) as failure:s.submit(self.kid,{'question':'Fixture upload bounds','uploads':['one','two']})
  self.assertEqual(failure.exception.status,413);self.assertEqual(s.records(self.kid),[])

 def test_point_conversion_never_changes_actual_usage(self):
  self.assertEqual(control.point_tokens(1000),1000000);self.assertEqual(control.point_tokens('0.001'),1)
  for bad in [True,-1,'NaN','Infinity','0.0001']:
   with self.assertRaises(control.Error):control.point_tokens(bad)
  with control.store() as d:d.execute('UPDATE quotas SET used=1001,reserved=2000,initial_total=1000000 WHERE key_id=?',(self.kid,))
  q=control.quota_public(self.kid);self.assertEqual(q['used_points'],1.001);self.assertEqual(q['remaining_points'],996.999)


 def test_historical_truncated_receipt_recovers_full_trace(self):
  from agent import conversations as chats
  jid=self.job();s.update(jid,status='partial',run=1);root=Path(s.get(jid)['artifact_root']);trace=root/'tool-results';trace.mkdir(parents=True)
  with control.store() as d:d.execute("INSERT INTO research_calls(id,job_id,run,kind,name,status,details,started,finished) VALUES('old-receipt',?,1,'tool','load_methods','succeeded','{broken',?,?)",(jid,time.time(),time.time()))
  trace.joinpath('old-receipt.json').write_text(json.dumps({'files':[{'path':'references/evidence.md'}]}),encoding='utf-8')
  stage=chats.stages(s.get(jid)['thread_id'])['stages'][0];self.assertEqual(stage['method_count'],1);self.assertFalse(stage['method_details_incomplete'])
  trace.joinpath('old-receipt.json').unlink();self.assertTrue(chats.stages(s.get(jid)['thread_id'])['stages'][0]['method_details_incomplete'])
 def test_large_method_receipt_stays_valid_json(self):
  jid=self.job();ex=Executor(jid)
  with patch.object(ex,'tool_load_methods',return_value={'files':[{'path':'references/evidence.md','instructions':'x'*30000}]}):ex.invoke('load_methods',{})
  call=s.detail(jid)['calls'][-1];record=json.loads(call['details']);self.assertTrue(record['truncated']);self.assertEqual(record['result']['files'][0]['path'],'references/evidence.md')

if __name__=='__main__':unittest.main()
