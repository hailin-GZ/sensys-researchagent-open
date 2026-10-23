"""Interruption recovery must expose saved work without false review status."""
import json,time,unittest
from unittest.mock import patch
import test_agent
from agent import store as s,progress,models,dialogue,engine,http_api
from agent.tools import Executor,r

class ProgressTests(unittest.TestCase):
    setUp=test_agent.AgentTests.setUp
    tearDown=test_agent.AgentTests.tearDown
    job=test_agent.AgentTests.job

    def captured(self):
        jid=self.job();ex=Executor(jid);ex.tool_configure_research(['synthesis'],'Synthetic interruption test')
        source=self.root/'fixture.txt';source.write_text('Synthetic original observation for interruption testing.',encoding='utf-8')
        record=r.capture(ex.root,file=str(source));block=ex.tool_read_evidence([record['source_id']])['blocks'][0]
        e=ex.tool_register_evidence(record['source_id'],block['block_id'],'Synthetic original observation for interruption testing.')
        item={'finding_id':'test_f1','statement':'\u5408\u6210\u6d4b\u8bd5\u660e\u7ec6, \u4e0d\u662f\u516c\u53f8\u4e8b\u5b9e.','kind':'source_opinion','evidence_refs':[e['evidence_id']],'limitations':['\u5408\u6210\u8d44\u6599']}
        ex.tool_record_findings([item]);return jid,ex

    def test_paused_body_and_findings_visible_without_review(self):
        jid,ex=self.captured();s.update(jid,status='paused',error='Task time limit reached, Existing materials retained.')
        b=s.bundle(jid,self.kid);p=b['progress']
        self.assertEqual(p['counts']['findings'],1);self.assertEqual(p['counts']['evidence'],1)
        self.assertEqual(p['stop_reason']['code'],'time_budget')
        self.assertEqual(p['review_status'],'unreviewed');self.assertFalse((b.get('result') or {}).get('support_reviewed'))
        self.assertEqual(b['report'],'');self.assertNotIn('artifact_root',json.dumps(p))
        with self.assertRaises(s.control().Error):s.bundle(jid,self.other)

    def test_state_reason_is_not_partial_report_state(self):
        jid,ex=self.captured();s.update(jid,status='paused',error='Model API call failed(APIConnectionError), Task retained.')
        self.assertEqual(s.public(jid,self.kid)['stop_reason']['code'],'provider_connection')
        s.update(jid,error='Model API call failed(APITimeoutError), Task retained.')
        self.assertEqual(progress.reason(s.get(jid))['code'],'provider_connection')
        s.update(jid,status='partial',error='');self.assertIsNone(s.bundle(jid)['progress']['stop_reason'])

    def test_continuation_preserves_spend_and_adds_current_run_allowance(self):
        jid,ex=self.captured()
        with s.control().store() as db:db.execute("UPDATE research_jobs SET status='paused',tokens=999999,model_calls=200,elapsed_ms=4000000 WHERE id=?",(jid,))
        previous=s.get(jid);s.action(self.kid,{'id':jid,'action':'continue','question':'\u7ee7\u7eed\u6838\u5b9e\u5df2\u6709\u8d44\u6599'})
        fresh=s.get(jid);limits=json.loads(fresh['config']);allowance=s.settings()[fresh['depth']]
        self.assertEqual(limits['model_tokens'],previous['tokens']+allowance['model_tokens'])
        self.assertEqual(limits['model_calls'],200+allowance['model_calls'])
        self.assertEqual(limits['seconds'],4000+allowance['seconds'])
        self.assertEqual(fresh['tokens'],previous['tokens']);self.assertEqual(fresh['question'],previous['question'])

    def test_queued_stop_is_immediate_and_finished_cancel_is_noop(self):
        jid=self.job();s.action(self.kid,{'id':jid,'action':'cancel'})
        self.assertEqual(s.get(jid)['status'],'cancelled')
        self.assertEqual(progress.reason(s.get(jid))['code'],'user_stop')
        s.update(jid,status='complete',cancel_requested=0);s.action(self.kid,{'id':jid,'action':'cancel'})
        self.assertEqual(s.get(jid)['cancel_requested'],0)

    def test_stream_cancellation_retains_original_exception_and_settles_once(self):
        jid=self.job()
        with patch.object(models,'response',side_effect=InterruptedError('User requested stop')):
            with self.assertRaises(InterruptedError):models.call(jid,'decision','medium','','test',[{'role':'user','content':'test'}],cap=100)
        with s.control().store() as db:
            quota=db.execute('SELECT used,reserved FROM quotas WHERE key_id=?',(self.kid,)).fetchone()
            call=db.execute('SELECT total_tokens,status FROM research_calls WHERE job_id=?',(jid,)).fetchone()
        self.assertEqual(quota['reserved'],0);self.assertEqual(quota['used'],call['total_tokens'])

    def test_dialogue_receives_real_reason_and_progress_not_empty_result(self):
        jid,ex=self.captured();s.update(jid,status='paused',error='Task time limit reached.')
        job=s.submit(self.kid,{'question':'\u4e3a\u4ec0\u4e48\u6682\u505c\u4e86?','conversation_id':s.get(jid)['thread_id']},conversational=True)
        data=dialogue.context(s.get(job['id']))
        self.assertEqual(data['live_research']['stop_reason']['code'],'time_budget')
        self.assertEqual(data['live_research']['counts']['findings'],1)
        self.assertIsNone(data['reviewed_result'])

    def test_followup_reuses_existing_job_instead_of_losing_archives(self):
        jid,ex=self.captured();s.update(jid,status='paused',error='Task time limit reached.')
        job=s.submit(self.kid,{'question':'\u7ee7\u7eed\u7814\u7a76','conversation_id':s.get(jid)['thread_id']},conversational=True)
        route={'intent':'research','answer':'\u7ee7\u7eed\u5df2\u6709\u7814\u7a76.','research_question':s.get(jid)['question'],'research_scope':'broad','resume_existing':True,'followup_questions':[]}
        response={'status':'completed','usage':{'input_tokens':100,'output_tokens':100},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(route)}]}]}
        with patch.object(models,'response',return_value=response):engine.run(job['id'])
        self.assertEqual(s.get(jid)['status'],'queued');self.assertEqual(s.get(job['id'])['kind'],'dialog')
        self.assertEqual(len(r.read_json(ex.root/'evidence.json')),1)

    def test_interruption_export_contains_saved_work_without_internal_receipts(self):
        jid,ex=self.captured();s.update(jid,status='paused',error='\u6838\u9a8c\u672a\u5b8c\u6210.')
        import io,zipfile
        class Handler:
            def send(self,status,body,*args,**kw):self.body=body
        handler=Handler();http_api.package(handler,jid,self.kid,False)
        archive=zipfile.ZipFile(io.BytesIO(handler.body));self.assertIn('progress.md',archive.namelist())
        p=json.loads(archive.read('progress.json'));self.assertEqual(p['counts']['findings'],1)
        self.assertFalse(any('model-receipts' in x or x.startswith('runs/') for x in archive.namelist()))

    def test_continue_source_allowance_matches_brief_and_preserves_used_counts(self):
        jid,ex=self.captured();s.update(jid,status='paused')
        budget=r.read_json(ex.root/'research-budget.json');budget['used']['captures']=100
        r.write_json(ex.root/'research-budget.json',budget)
        s.action(self.kid,{'id':jid,'action':'continue'})
        with patch.object(models,'call',side_effect=ValueError('Stop synthetic test before API')):engine.run(jid)
        saved=r.depth.load(ex.root)
        self.assertEqual(saved['used']['captures'],100)
        self.assertEqual(saved['limits']['captures'],100+s.settings()[s.get(jid)['depth']]['captures'])

    def test_time_budget_reserves_closing_before_hard_deadline(self):
        jid,ex=self.captured();cfg=json.loads(s.get(jid)['config']);cfg['seconds']=90
        s.update(jid,config=json.dumps(cfg),elapsed_ms=70000)
        with patch.object(engine,'finish_draft') as finish,patch.object(engine,'review',return_value={'status':'partial'}),patch.object(models,'call') as model:
            (ex.root/'report.md').write_text('Synthetic test report only.',encoding='utf-8')
            engine.run(jid);finish.assert_called_once();model.assert_not_called()
        self.assertEqual(s.get(jid)['status'],'partial')

    def test_image_stop_preserves_body_and_avoids_further_downloads(self):
        folder=self.root/'html';folder.mkdir()
        raw=b'<html><title>Fixture</title><body><p>Retained test body.</p><img src="https://example.com/a.png"><img src="https://example.com/b.png"></body></html>'
        with patch.object(r,'download') as network:
            parsed,md=r.html_document(raw,'https://example.com',folder,max_images=20,stop_requested=lambda:True)
            network.assert_not_called()
        self.assertIn('Retained test body.',md)
        self.assertTrue(all(x['status']=='omitted_stop' for x in parsed['assets']))

    def test_failed_url_reused_across_batches_only_in_same_run(self):
        jid,ex=self.captured();a='https://example.com/a';b='https://example.com/b'
        def failure(*args,**kw):return {'source_id':'synthetic','requested_url':kw['url'],'status':'network_error','http_status':404}
        with patch.object(r,'capture',side_effect=failure) as network:
            ex.tool_capture_sources([a]);result=ex.tool_capture_sources([a,b])
            self.assertEqual(network.call_count,2);self.assertTrue(result['sources'][0]['cached_failure'])
            s.update(jid,run=s.get(jid)['run']+1);ex.tool_capture_sources([a]);self.assertEqual(network.call_count,3)

    def test_stop_between_batch_queries_preserves_first_and_skips_second(self):
        jid,ex=self.captured()
        def first(*args,**kw):
            s.update(jid,cancel_requested=1);return {'status':'captured','query':args[1]}
        with patch.object(s,'settings',return_value={'native_web_search':False}),patch.object(r,'discover',side_effect=first) as query:
            with self.assertRaises(InterruptedError):ex.invoke('search_sources',{'queries':['first','second']})
            self.assertEqual(query.call_count,1)
        self.assertTrue((ex.root/'progress.md').exists())

    def test_historical_recovery_skips_analysis_when_time_needed_for_closing(self):
        jid,ex=self.captured();cfg=json.loads(s.get(jid)['config']);cfg['seconds']=100
        s.update(jid,config=json.dumps(cfg),elapsed_ms=70000)
        with patch.object(models,'call') as model:
            from agent import long_research
            long_research.analyze_archived_windows(ex);model.assert_not_called()

    def test_silent_provider_can_be_stopped_without_waiting_for_headers(self):
        import asyncio
        closed=[];cancelled=[]
        class Client:
            def __init__(self,**kw):self.responses=self
            async def create(self,**kw):
                try:await asyncio.sleep(5)
                finally:cancelled.append(True)
            async def close(self):
                self_test.assertTrue(cancelled);closed.append(True)
        def cancel(*args):raise InterruptedError('Synthetic user stop')
        self_test=self;control=s.control();start=time.monotonic()
        with patch('openai.AsyncOpenAI',Client),patch.object(control,'public_address'),patch.object(control,'crypt',return_value='synthetic-test-key'),patch.object(s,'control',return_value=control):
            with self.assertRaises(InterruptedError):models.response({'secret':'synthetic','base_url':'https://example.com','model':'synthetic'},'',[],[],'medium',100,cancel)
        self.assertLess(time.monotonic()-start,2);self.assertTrue(closed)

    def test_twelve_item_task_persists_reads_before_analysis_failure(self):
        jid,ex=self.captured();ex.tool_set_deliverable_plan(12,['comparison'],'Explicit twelve-item coverage')
        from agent import long_research
        sid=r.read_json(ex.root/'sources.json')[0]['source_id']
        with patch.object(long_research,'analyze',side_effect=ValueError('Synthetic analysis interruption')):
            out=ex.invoke('read_evidence',{'source_ids':[sid]})
        self.assertEqual(out['execution_status'],'failed')
        saved=r.read_json(ex.root/'checkpoint.json');self.assertTrue(saved['read'])
        self.assertIn('Synthetic original observation',saved['read'][0]['windows'][0])
        self.assertEqual(s.bundle(jid,self.kid)['progress']['counts']['usable_sources'],1)

    def test_research_cannot_shortcut_to_conversational_answer(self):
        jid,ex=self.captured()
        with self.assertRaises(ValueError):ex.tool_answer_existing('Synthetic short answer cannot replace the research report.')
        self.assertIsNone(ex.answer);self.assertEqual(len(r.read_json(ex.root/'evidence.json')),1)

    def test_collection_batch_stops_for_closing_between_tool_requests(self):
        jid,ex=self.captured();ex.tool_set_deliverable_plan(12,['comparison'],'Synthetic budget test')
        cfg=json.loads(s.get(jid)['config']);cfg['seconds']=90;s.update(jid,config=json.dumps(cfg))
        r.write_json(ex.root/'research-plan.json',{'schema_version':'2.0','decision':'Test','selected_capability_ids':[],'excluded_modes':[],'roles':[]})
        (ex.root/'report.md').write_text('Synthetic test report only.',encoding='utf-8')
        def first(self,*args,**kw):
            s.update(jid,elapsed_ms=70000);return {'sources':[]}
        calls=[{'type':'function_call','name':'capture_sources','call_id':str(i),'arguments':json.dumps({'urls':['https://example.com/'+str(i)]})} for i in range(2)]
        with patch.object(models,'call',return_value={'status':'completed','output':calls}),patch.object(Executor,'tool_capture_sources',autospec=True,side_effect=first) as capture,patch.object(engine,'finish_draft'),patch.object(engine,'review',return_value={'status':'partial'}):
            engine.run(jid)
        self.assertEqual(capture.call_count,1);self.assertEqual(s.get(jid)['status'],'partial')
