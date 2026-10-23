"""Large deliverables use synthetic archives; no paid API calls in this suite."""
import copy,json,unittest
from unittest.mock import patch
import test_agent
from agent import store as s,engine,breadth,schemas,models
from agent.tools import Executor,r,c,DEFINITIONS
import search_worker

class BreadthTests(unittest.TestCase):
    setUp=test_agent.AgentTests.setUp
    tearDown=test_agent.AgentTests.tearDown
    job=test_agent.AgentTests.job

    def fixture(self,count=100):
        jid=self.job();ex=Executor(jid);ex.tool_configure_research(['synthesis'],'Synthetic archive test only')
        source=self.root/'synthetic.txt'
        sentences=[f'Synthetic test observation {i:03d}: feature group {i} has an explicitly numbered fixture value.' for i in range(count)]
        source.write_text('\n'.join(sentences),encoding='utf-8');record=r.capture(ex.root,file=str(source))
        blocks=ex.tool_read_evidence([record['source_id']],max_chars=10000,blocks_per_source=20)['blocks']
        findings=[]
        for i,sentence in enumerate(sentences):
            block=next(b for b in blocks if sentence in b['text'])
            e=ex.tool_register_evidence(record['source_id'],block['block_id'],sentence)
            findings.append({'finding_id':f'f{i+1}','statement':f'\u5408\u6210\u6d4b\u8bd5\u89c2\u5bdf {i+1}, \u53ea\u9a8c\u8bc1\u5f52\u6863\u548c\u4fdd\u7559, \u4e0d\u662f\u5e02\u573a\u4e8b\u5b9e.','kind':'source_opinion','evidence_refs':[e['evidence_id']],'limitations':['\u5408\u6210\u6d4b\u8bd5\u8d44\u6599, \u4e0d\u80fd\u4f5c\u4e3a\u771f\u5b9e\u7814\u7a76\u6210\u679c']})
        ex.tool_set_deliverable_plan(count,['synthetic inventory'],'Preserve all test items')
        return jid,ex,findings

    def draft(self,findings):
        return {'status':'partial','summary':'\u5408\u6210\u5f52\u6863\u6d41\u7a0b\u6d4b\u8bd5','findings':findings,'conflicts':[],'missing_evidence':['\u771f\u5b9e\u5e02\u573a\u8bc1\u636e'],'assumptions':[],'next_steps':['\u7528\u771f\u5b9e\u95ee\u9898\u6d4b\u8bd5'],'depth_review':{'research_depth':'standard','checks':[{'check':key,'status':'gap','reason':'\u5408\u6210\u6d4b\u8bd5, \u4e0d\u662f\u5e02\u573a\u7ed3\u8bba','finding_refs':[]} for key in ('decision_scope','source_roles','contrary_evidence','next_validation')]}}

    def test_admin_screenshot_values_and_larger_budgets_persist(self):
        data={'standard':{'model_tokens':2000000,'model_calls':150,'seconds':1800,'search_queries':50,'captures':90,'research_rounds':5,'results_per_query':15,'images_per_source':15},'deep':{'model_tokens':3000000,'model_calls':280,'seconds':3600,'search_queries':100,'captures':170,'research_rounds':10,'results_per_query':30,'images_per_source':25}}
        s.save_settings(data);self.assertEqual(s.settings()['deep'],data['deep'])
        s.save_settings({'deep':{'model_tokens':5000000,'model_calls':500,'results_per_query':100,'images_per_source':0}})
        self.assertEqual(s.settings()['deep']['model_tokens'],5000000)
        for value in (True,1.5,'3000000',-1,9007199254740992):
            with self.assertRaises(s.control().Error):s.save_settings({'deep':{'model_tokens':value}})

    def test_search_limit_uses_administrator_value_without_eight_result_clamp(self):
        s.save_settings({'standard':{'results_per_query':30}});jid=self.job();ex=Executor(jid);ex.tool_configure_research(['needs'],'test')
        with patch.object(r,'discover',return_value={'status':'leads_found','results':[]}) as discover:
            ex.invoke('search_sources',{'queries':['synthetic query'],'limit':None});self.assertEqual(discover.call_args.kwargs['limit'],30)

    def test_large_ledger_rehydrates_and_save_never_caps_at_thirty_five(self):
        jid,ex,findings=self.fixture()
        for page in breadth.batches(findings):ex.invoke('record_findings',{'items':page})
        self.assertEqual(len(breadth.ledger(Executor(jid))),100)
        saved=ex.invoke('save_research_result',{'json':self.draft(findings[:3])})
        self.assertEqual(saved['status'],'draft_saved');self.assertEqual(len(r.read_json(ex.root/'result.json')['findings']),100)

    def test_multi_page_review_and_corrections_close_before_collection_deadline(self):
        jid,ex,findings=self.fixture(40)
        for page in breadth.batches(findings):ex.tool_record_findings(page)
        cfg=json.loads(s.get(jid)['config']);cfg.update(seconds=1800,model_tokens=1000000)
        s.update(jid,config=json.dumps(cfg),elapsed_ms=1100000)
        # Several cheap selection calls must not predict that full-page reviews
        # and their possible corrections will each take just a few seconds.
        with s.control().store() as db:
            for i in range(5):db.execute('INSERT INTO research_calls(id,job_id,kind,status,elapsed_ms,started) VALUES(?,?,?,?,?,?)',(f'fast_{i}',jid,'model','succeeded',5000,i))
        (ex.root/'report.md').write_text('Synthetic retained report only.',encoding='utf-8')
        with patch.object(engine,'finish_draft') as finish,patch.object(engine,'review',return_value={'status':'partial'}),patch.object(models,'call') as model:
            engine.run(jid);finish.assert_called_once();model.assert_not_called()
        self.assertEqual(s.get(jid)['status'],'partial')
        self.assertEqual(len(breadth.ledger(ex)),40)

    def test_insufficient_coverage_rejects_false_completion(self):
        _,ex,findings=self.fixture(20)
        value=self.draft(findings[:3]);value['status']='complete'
        result=ex.invoke('save_research_result',{'json':value})
        self.assertEqual(result['status'],'more_research_needed');self.assertFalse(ex.draft_saved)
        value['status']='partial';value['missing_evidence'].append(result['coverage_gap'])
        self.assertEqual(ex.invoke('save_research_result',{'json':value})['status'],'more_research_needed')
        ex.bounded_finalization=True
        self.assertEqual(ex.invoke('save_research_result',{'json':value})['status'],'draft_saved')

    def test_final_counts_replace_page_notes_but_keep_substantive_gaps(self):
        _,ex,findings=self.fixture(3)
        old='Delivery coverage is incomplete: Plan 3 independent evidence-backed results, Actual 1 items.'
        local='This page actually provides1itemsfinding, \u8ddd\u79bb\u7528\u6237\u8981\u6c42\u7684\u81f3\u5c113\u9879\u72ec\u7acb, \u6709\u539f\u6587\u8bc1\u636e\u652f\u6301\u7684\u7ed3\u679c\u4ecd\u7f3a2items; \u4e0d\u80fd\u4ee5\u73b0\u67091\u9879\u58f0\u79f0\u4ea4\u4ed8\u8fbe\u6807.'
        substantive='\u90e8\u5206\u6761\u76ee\u91cd\u590d\u63a8\u8bba, \u7f3a\u5c11\u56fd\u5185\u4ed8\u8d39\u8bc1\u636e.'
        value=self.draft(findings);value['missing_evidence']=[old,local,substantive]
        value['modules']=[{'gaps':[old,local,substantive]}]
        state=breadth.reconcile_count_gaps(ex,value)
        self.assertFalse(state['needs_more'])
        self.assertEqual(value['missing_evidence'],[substantive])
        self.assertEqual(value['modules'][0]['gaps'],[substantive])
        value['findings']=findings[:1]
        breadth.reconcile_count_gaps(ex,value)
        self.assertIn(old,value['missing_evidence'])

    def test_compact_state_retains_complete_ledger_through_paged_retrieval(self):
        _,ex,findings=self.fixture(40)
        findings[-1]['statement']+=' \u5f88\u957f\u7684\u5b8c\u6574\u660e\u7ec6'*60
        for page in breadth.batches(findings):ex.tool_record_findings(page)
        ex.tool_save_research_result(self.draft(findings))
        state=json.loads(engine.context(ex))
        self.assertNotIn('findings',state['result'])
        self.assertEqual(state['findings_ledger']['readiness']['supported_findings'],40)
        first=ex.tool_read_findings(limit=20);last=ex.tool_read_findings(offset=first['next_offset'])
        self.assertEqual(last['items'][-1],findings[-1]);self.assertIsNone(last['next_offset'])
        selected=ex.tool_read_findings(finding_ids=[findings[-1]['finding_id']])
        self.assertEqual(selected['items'],[findings[-1]])

    def test_combined_preparation_archives_real_method_receipts(self):
        jid=self.job();ex=Executor(jid)
        plan={'schema_version':'2.0','decision':'synthetic scope','selected_capability_ids':[],'excluded_modes':[],'roles':[{'role':'user_voices','required':True,'reason':'synthetic plan','status':'missing','source_ids':[],'gap':'Not acquired'}]}
        value=ex.invoke('prepare_research',{'modes':['needs','voices'],'decision':'synthetic scope','population':'unknown','geography':'unknown','time_window':'current','target_findings':50,'dimensions':['product alternatives','user experiences'],'rationale':'Requested breadth','coverage_plan':plan})
        self.assertEqual(value['execution_status'],'succeeded')
        self.assertEqual(breadth.plan(ex)['target_findings'],50)
        self.assertEqual(len(value['load_methods']['files']),2)
        names=[x['name'] for x in s.detail(jid)['calls']]
        self.assertIn('load_methods',names);self.assertIn('save_coverage_plan',names)

    def test_unspecified_population_does_not_require_extra_paid_planning(self):
        jid=self.job();ex=Executor(jid)
        p={'schema_version':'2.0','decision':'company and business scope','selected_capability_ids':[],'excluded_modes':[],'roles':[{'role':'official_product','required':True,'reason':'Company facts','status':'missing','source_ids':[],'gap':'Not acquired'}]}
        value=ex.invoke('prepare_research',{'modes':['competitors'],'decision':'company and business scope','target_findings':45,'dimensions':['company identity','digital employee workflows'],'rationale':'Both user goals','coverage_plan':p})
        self.assertEqual(value['execution_status'],'succeeded')
        self.assertEqual(r.read_json(ex.root/'brief.json')['research_scope']['target_population'],'Not specified')

    def test_prepared_task_does_not_offer_reinitialization_in_collection(self):
        jid,ex,_=self.fixture(1)
        ex.tool_save_coverage_plan({'schema_version':'2.0','decision':'Synthetic scope','selected_capability_ids':[],'excluded_modes':[],'roles':[{'role':'user_voices','required':True,'reason':'Read original opinions','status':'missing','source_ids':[],'gap':'Need actual opinions'}]})
        def provider(*args,**kwargs):
            names={x['name'] for x in args[6]}
            self.assertNotIn('prepare_research',names);self.assertNotIn('configure_research',names)
            self.assertIn('search_sources',names);self.assertIn('save_coverage_plan',names)
            raise ValueError('End synthetic boundary test')
        with patch.object(models,'call',side_effect=provider):engine.run(jid)
        self.assertEqual(s.get(jid)['error'],'End synthetic boundary test')

    def test_failed_placeholder_does_not_merge_unrelated_source_origins(self):
        _,ex,_=self.fixture(1);p=self.root/'failed.txt';p.write_text('Connection failed',encoding='utf-8')
        first=r.capture(ex.root,file=str(p),source_url='https://example.org/first')
        from agent.tools import annotate_source
        annotate_source(ex.root,first,{'status':'network_error'})
        second=r.capture(ex.root,file=str(p),source_url='https://example.org/second')
        self.assertIsNone(second['duplicate_of']);self.assertEqual(second['origin_id'],'https://example.org/second')

    def test_coverage_duplicate_role_preserves_both_reasons_without_planning_loop(self):
        _,ex,_=self.fixture(1)
        a={'role':'user_voices','required':True,'reason':'pain points','status':'missing','source_ids':[],'gap':'Need comments'}
        b={**a,'reason':'payment experiences','gap':'Need purchase observations'}
        result=ex.tool_save_coverage_plan({'schema_version':'2.0','decision':'synthetic scope','selected_capability_ids':[],'excluded_modes':[],'roles':[a,b]})
        self.assertEqual(result['merged_duplicate_roles'],['user_voices'])
        roles=r.read_json(ex.root/'research-plan.json')['roles'];self.assertEqual(len(roles),1)
        self.assertIn('pain points',roles[0]['reason']);self.assertIn('payment experiences',roles[0]['reason'])

    def test_paged_review_preserves_one_hundred_findings_and_download(self):
        jid,ex,findings=self.fixture();ex.tool_save_research_result(self.draft(findings))
        sizes=[]
        def provider(job_id,phase,effort,reason,prompt,items,**kwargs):
            payload=json.loads(items[0]['content'])
            if 'reviewed_findings' in payload:
                self.assertEqual(len(payload['reviewed_findings']),100)
                value={'conclusions':[{'text':'\u5168\u90e8\u5408\u6210\u89c2\u5bdf\u5df2\u4fdd\u7559; \u8fd9\u662f\u5f52\u6863\u6d4b\u8bd5, \u5e02\u573a\u7ed3\u8bba\u5c1a\u672a\u786e\u8ba4.','kind':'unknown','finding_refs':[]}],'next_steps':['\u6d4b\u8bd5\u771f\u5b9e\u7814\u7a76']}
                return {'status':'completed','id':'synthetic-decision','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
            draft=payload['draft'];sizes.append(len(draft['findings']))
            self.assertLessEqual(len(payload['evidence']),20)
            value={'result':test_agent.reviewed_fixture(draft),'review_notes':['\u5408\u6210\u6d4b\u8bd5\u8303\u56f4\u5df2\u4fdd\u7559'],'coverage_updates':[]}
            return {'status':'completed','id':f'fixture-{len(sizes)}','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch.object(models,'call',side_effect=provider):fixed=engine.review(ex)
        self.assertEqual(sizes,[20]*5);self.assertEqual(len(fixed['findings']),100)
        self.assertEqual(len(s.bundle(jid)['result']['findings']),100)
        self.assertIn(findings[-1]['statement'],(ex.root/'report.md').read_text(encoding='utf-8'))
        self.assertTrue(r.read_json(ex.root/'validation.json')['ok']);schemas.validate_modules(fixed)
        self.assertTrue((ex.root/'decision-synthesis.json').exists())

    def test_decision_reasoning_cannot_turn_unknown_company_into_supported_fact(self):
        from agent.long_research import synthesize_decision
        _,ex,findings=self.fixture(1);findings[0].update(kind='unknown',evidence_refs=[])
        value={'conclusions':[{'text':'\u516c\u53f8\u4e1a\u52a1\u5df2\u7ecf\u8bc1\u5b9e.','kind':'supported','finding_refs':['f1']}],'next_steps':[]}
        response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch.object(models,'call',return_value=response) as provider:
            fixed=synthesize_decision(ex,self.draft(findings))
        self.assertEqual(provider.call_count,3)  # analysis + two bounded reviews
        self.assertNotIn('\u516c\u53f8\u4e1a\u52a1\u5df2\u7ecf\u8bc1\u5b9e',fixed['summary'])
        self.assertEqual(fixed['findings'],findings)
        self.assertIn('Not confirmed yet',fixed['summary'])
        self.assertTrue(r.read_json(ex.root/'decision-synthesis.json')['overview_fallback'])

    def test_decision_review_corrects_unknown_reference_once_without_losing_inventory(self):
        from agent.long_research import synthesize_decision
        _,ex,findings=self.fixture(1);findings[0].update(kind='unknown',evidence_refs=[])
        calls=[]
        def provider(job_id,phase,effort,reason,prompt,items,**kwargs):
            payload=json.loads(items[0]['content']);calls.append(phase)
            if len(calls)==3:
                self.assertIn('unverified findings',str(payload['validation_errors']))
                value={'conclusions':[{'text':'\u516c\u53f8\u4e1a\u52a1\u5c1a\u672a\u786e\u8ba4, \u9700\u8981\u516c\u5f00\u8eab\u4efd\u8d44\u6599.','kind':'unknown','finding_refs':['f1']}],'next_steps':['\u6838\u5bf9\u516c\u53f8\u8eab\u4efd']}
            else:value={'conclusions':[{'text':'\u516c\u53f8\u4e1a\u52a1\u5df2\u786e\u8ba4.','kind':'supported','finding_refs':['f1']}],'next_steps':[]}
            return {'status':'completed','id':str(len(calls)),'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch.object(models,'call',side_effect=provider):fixed=synthesize_decision(ex,self.draft(findings))
        self.assertEqual(calls,['analysis','review','review'])
        self.assertIn('Not confirmed yet',fixed['summary']);self.assertEqual(fixed['findings'],findings)
        self.assertFalse(r.read_json(ex.root/'decision-synthesis.json')['overview_fallback'])

    def test_reviewed_decision_supplies_short_contextual_questions_separate_from_steps(self):
        from agent.long_research import synthesize_decision
        _,ex,findings=self.fixture(1)
        questions=['\u8bf7\u6bd4\u8f83\u8fd9\u4e9b\u65b9\u6848\u7684\u4eba\u5de5\u5ba1\u6279\u8fb9\u754c.','\u600e\u6837\u8bbe\u8ba1\u4f4e\u6210\u672c\u7684\u6570\u5b57\u5458\u5de5\u8bd5\u70b9?']
        value={'conclusions':[{'text':'\u4ec5\u6709\u5408\u6210\u6d4b\u8bd5\u8d44\u6599, \u4e0d\u80fd\u4f5c\u4e3a\u5e02\u573a\u5224\u65ad.','kind':'unknown','finding_refs':[]}],'next_steps':['\u5f88\u957f\u7684\u5b9e\u9a8c\u8bbe\u8ba1\u6b65\u9aa4.'*50],'followup_questions':questions}
        response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch.object(models,'call',return_value=response) as provider:fixed=synthesize_decision(ex,self.draft(findings))
        self.assertEqual(r.read_json(ex.root/'suggestions.json'),questions)
        self.assertEqual(fixed['findings'],findings)
        self.assertIn('followup_questions',provider.call_args.kwargs['format_schema']['required'])

    def test_invalid_or_long_suggestions_are_not_cut_into_changed_user_messages(self):
        from agent import suggestions
        _,ex,_=self.fixture(1)
        values=['\u754c\u9762\u7814\u7a76\u95ee\u9898.','\u754c\u9762\u7814\u7a76\u95ee\u9898.','\u957f'*81,123]
        self.assertEqual(suggestions.save(ex.root,values),['\u754c\u9762\u7814\u7a76\u95ee\u9898.'])

    def test_public_documentation_reference_path_is_not_an_internal_file(self):
        from agent.confidentiality import contains_secret,clean_text
        url='https://developers.intercom.com/docs/references/unstable/rest-api/api.intercom.io/ai-content'
        self.assertFalse(contains_secret(url));self.assertEqual(clean_text(url),url)
        self.assertFalse(contains_secret('See https://example.org/docs/runtime/api for vendor documentation.'))

    def test_real_internal_paths_remain_protected_in_urls_queries_and_local_text(self):
        from agent.confidentiality import contains_secret
        for text in ('references/coverage.md','https://example.org/references/coverage.md','https://example.org/docs?path=references/private.md','https://example.org/.codex/auth.json','C:/runtime/private/file.txt'):
            self.assertTrue(contains_secret(text),text)

    def test_interrupted_decision_review_reuses_the_completed_draft(self):
        from agent.long_research import synthesize_decision
        _,ex,findings=self.fixture(1);result=self.draft(findings)
        calls=[];fail=True
        def provider(job_id,phase,*args,**kwargs):
            calls.append(phase)
            if phase=='review' and fail:raise ValueError('Synthetic interruption')
            value={'conclusions':[{'text':'\u5408\u6210\u6d4b\u8bd5\u8d44\u6599\u4fdd\u7559.','kind':'unknown','finding_refs':[]}],'next_steps':[]}
            return {'status':'completed','id':'synthetic-decision','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch.object(models,'call',side_effect=provider):
            with self.assertRaisesRegex(ValueError,'Synthetic interruption'):synthesize_decision(ex,copy.deepcopy(result))
            fail=False;fixed=synthesize_decision(ex,copy.deepcopy(result))
        self.assertEqual(calls,['analysis','review','review']);self.assertEqual(fixed['findings'],findings)

    def test_interrupted_review_reuses_only_identical_completed_pages(self):
        _,ex,findings=self.fixture(40);ex.tool_save_research_result(self.draft(findings))
        pages=[];fail=True;captured=[]
        def provider(job_id,phase,effort,reason,prompt,items,**kwargs):
            payload=json.loads(items[0]['content'])
            if 'reviewed_findings' in payload:
                value={'conclusions':[{'text':'\u5408\u6210\u6d4b\u8bd5\u7ed3\u679c\u4fdd\u7559.','kind':'unknown','finding_refs':[]}],'next_steps':[]}
            else:
                pages.append(payload['page'])
                if payload['page']==1:captured.append((prompt,payload))
                if fail and payload['page']==2:raise ValueError('Synthetic interruption')
                value={'result':test_agent.reviewed_fixture(payload['draft']),'review_notes':[],'coverage_updates':[]}
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch.object(models,'call',side_effect=provider):
            with self.assertRaisesRegex(ValueError,'Synthetic interruption'):engine.review(ex)
            # The previous transport printed every approved field. Its exact
            # semantic prompt/input hash remains compatible with nullable keeps.
            path=ex.root/'support-review-page-1.json';cached=r.read_json(path)
            prompt,payload=captured[0]
            payload={k:v for k,v in payload.items() if k!='validation_errors'}
            cached['input_sha256']=r.sha(json.dumps({'version':'support-page-v1','prompt':prompt.split(' Review every item fully')[0],'payload':payload},sort_keys=True,ensure_ascii=False).encode())
            r.write_json(path,cached)
            fail=False;fixed=engine.review(ex)
        self.assertEqual(pages,[1,2,2]);self.assertEqual(len(fixed['findings']),40)

    def test_reviewer_cannot_silently_drop_ninety_items(self):
        _,ex,findings=self.fixture(40);ex.tool_save_research_result(self.draft(findings))
        def shortened(*args,**kwargs):
            payload=json.loads(args[5][0]['content']);draft=payload['draft'];draft['findings']=draft['findings'][:1]
            value={'result':test_agent.reviewed_fixture(draft),'review_notes':[],'coverage_updates':[]}
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch.object(models,'call',side_effect=shortened):
            with self.assertRaisesRegex(ValueError,'preserve every finding'):engine.review(ex)
        self.assertFalse((ex.root/'published.json').exists())

    def test_reviewed_keep_decisions_preserve_full_text_without_reprinting(self):
        _,ex,findings=self.fixture(40);ex.tool_save_research_result(self.draft(findings))
        def provider(job_id,phase,effort,reason,prompt,items,**kwargs):
            payload=json.loads(items[0]['content'])
            if 'reviewed_findings' in payload:
                value={'conclusions':[{'text':'\u5408\u6210\u8d44\u6599\u5df2\u4fdd\u7559.','kind':'unknown','finding_refs':[]}],'next_steps':[]}
            else:
                draft=payload['draft'];value={'result':test_agent.reviewed_fixture(draft),'review_notes':['\u9010\u9879\u72ec\u7acb\u6838\u9a8c\u540e\u6279\u51c6\u4fdd\u7559\u539f\u5b57\u6bb5'],'coverage_updates':[]}
                for finding in value['result']['findings']:finding.update(statement=None,limitations=None)
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        with patch.object(models,'call',side_effect=provider):fixed=engine.review(ex)
        self.assertEqual(fixed['findings'],findings)

    def test_merged_coverage_retains_partial_body_and_all_real_gaps(self):
        from agent.long_research import merge_coverage_updates
        role={'role':'scientific_research','status':'captured','source_ids':['s1'],'gap':''}
        partial={**role,'status':'partial','source_ids':['s2'],'gap':'Need full methods'}
        value=merge_coverage_updates([{'coverage_updates':[role]},{'coverage_updates':[partial]}],[{'source_id':'s1','status':'complete_body'},{'source_id':'s2','status':'partial_body'}])[0]
        self.assertEqual(value['status'],'partial');self.assertEqual(value['source_ids'],['s1','s2'])
        self.assertIn('Need full methods',value['gap'])

    def test_body_retrieval_pages_reach_later_blocks_and_characters(self):
        _,ex,_=self.fixture(2)  # narrow cursor test; multi-item analysis is separately exercised
        sid=r.read_json(ex.root/'sources.json')[0]['source_id']
        first=ex.tool_read_evidence([sid],max_chars=100,blocks_per_source=1)
        next_window=ex.tool_read_evidence([sid],max_chars=100,blocks_per_source=1,char_start=first['blocks'][0]['char_end'])
        self.assertNotEqual(first['blocks'][0]['text'],next_window['blocks'][0]['text'])
        self.assertEqual(next_window['blocks'][0]['char_start'],100)
        self.assertTrue(first['blocks'][0]['truncated'])

    def test_full_catalog_can_be_paged_without_repeating_first_six(self):
        first=c.lookup('',limit=20);second=c.lookup('',limit=20,offset=first['next_offset'])
        self.assertEqual(first['total_matches'],second['total_matches'])
        self.assertFalse({x['id'] for x in first['matches']} & {x['id'] for x in second['matches']})

    def test_search_pages_accumulate_real_unique_results_despite_later_failures(self):
        class Search:
            def __init__(self,**kwargs):pass
            def text(self,query,**kwargs):
                if kwargs['backend']=='yandex':
                    page=kwargs['page']
                    if page>3:raise ValueError('provider unavailable after three pages')
                    return [{'href':f'https://example.org/{page}/{i}','title':f'Page {page} result {i}'} for i in range(10)]
                raise ValueError('other provider unavailable')
        rows,attempts=search_worker.search('synthetic',40,factory=Search)
        self.assertEqual(len(rows),30);self.assertEqual(len({x['href'] for x in rows}),30)
        self.assertTrue(any(x['status']=='failed' for x in attempts))

    def test_repeated_search_page_stops_without_fabricated_extra_results(self):
        class Search:
            def __init__(self,**kwargs):pass
            def text(self,*args,**kwargs):return [{'href':'https://example.org/only','title':'One lead'}]
        rows,attempts=search_worker.search('synthetic',100,factory=Search)
        self.assertEqual(len(rows),1);self.assertLessEqual(len(attempts),8)

    def test_large_research_body_read_immediately_persists_supported_observations(self):
        _,ex,findings=self.fixture(20)
        def analyze(job_id,phase,effort,reason,prompt,items,**kwargs):
            self.assertEqual(phase,'analysis');payload=json.loads(items[0]['content'])
            self.assertTrue(payload['read_windows']);self.assertTrue(payload['evidence'])
            value={'new_quotes':[],'result':self.draft(findings)}
            return {'status':'completed','id':'synthetic-analysis','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
        sid=r.read_json(ex.root/'sources.json')[0]['source_id']
        with patch.object(models,'call',side_effect=analyze):value=ex.invoke('read_evidence',{'source_ids':[sid],'max_chars':10000})
        self.assertEqual(value['execution_status'],'succeeded');self.assertEqual(value['analysis']['total_findings'],20)
        self.assertEqual(len(breadth.ledger(ex)),20)
        self.assertNotIn('blocks',value)  # Planner receives durable observations, not repeated full bodies.

    def test_quote_recovery_returns_original_text_and_rejects_changed_meaning(self):
        from agent.long_research import literal_quote
        _,ex,_=self.fixture(1)
        sid,bid=next(iter(ex.read));actual=ex.read[(sid,bid)][0]
        q={'source_id':sid,'block_id':bid,'quote':actual.replace(' ','  ').upper(),'role':'test','context':'Synthetic fixture'}
        exact=literal_quote(ex,q);self.assertEqual(exact['quote'],actual)
        q['quote']='Synthetic test observation 999: invented value'
        with self.assertRaises(ValueError):literal_quote(ex,q)

    def test_selected_passage_is_archived_literally_without_model_quote_translation(self):
        from agent.long_research import analyze
        _,ex,_=self.fixture(1);sid,bid=next(iter(ex.read));text=ex.read[(sid,bid)][0]
        def provider(*args,**kwargs):
            payload=json.loads(args[5][0]['content']);p=payload['read_windows'][0]
            f={'finding_id':'new','statement':'\u539f\u6587\u8bb0\u5f55\u4e86\u7b2c\u4e00\u9879\u5408\u6210\u89c2\u5bdf.','kind':'fact','evidence_refs':[p['passage_ref']],'limitations':['\u5408\u6210\u5f52\u6863\u6d4b\u8bd5']}
            return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'new_quotes':[],'result':self.draft([f])})}]}]}
        with patch.object(models,'call',side_effect=provider):receipt=analyze(ex,[{'source_id':sid,'block_id':bid,'text':text}])
        evidence=r.read_json(ex.root/'evidence.json');quoted=next(e for e in evidence if e['evidence_id']==receipt['evidence_refs'][0])
        self.assertIn(quoted['quote'],text);self.assertTrue(breadth.ledger(ex)[0]['evidence_refs'][0].startswith('e'))

    def test_native_search_rejects_invented_urls_and_keeps_real_cited_leads(self):
        from agent import discovery
        _,ex,_=self.fixture(1)
        value={'status':'completed','id':'synthetic-native-receipt','output':[{'type':'web_search_call','action':{'sources':[{'url':'https://example.org/actual','title':'Real fixture source'}]}},{'type':'message','content':[{'type':'output_text','text':json.dumps({'results':[{'url':'https://example.org/actual','title':'Actual','snippet':'Fixture lead'},{'url':'https://example.org/invented','title':'Invented','snippet':'Unsupported'}]})}]}]}
        # Citation gating and cache behavior are independent of this machine's
        # TUN DNS answers; URL destination validation has separate coverage.
        with patch.object(models,'call',return_value=value) as supplier, patch.object(r,'public_url',return_value=None):
            result=discovery.search(ex,'synthetic query',30);again=discovery.search(ex,'synthetic query',30)
        self.assertEqual(supplier.call_count,1);self.assertTrue(again['reused'])
        self.assertEqual([x['url'] for x in result['results']],['https://example.org/actual'])
        self.assertEqual(result['provider'],'responses_native_web_search')
        self.assertFalse(r.read_json(ex.root/'evidence.json')==[])  # Fixture quotations remain unchanged.

    def test_native_search_without_actual_tool_receipt_is_not_search(self):
        from agent import discovery
        _,ex,_=self.fixture(1)
        out={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'I searched and found many sources.'}]}]}
        with patch.object(models,'call',return_value=out):
            with self.assertRaisesRegex(ValueError,'No completed native'):discovery.search(ex,'synthetic query',30)

if __name__=='__main__':unittest.main()
