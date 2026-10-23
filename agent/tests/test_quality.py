import json,unittest
from unittest.mock import patch
import test_breadth
from agent import quality,store as s
from agent.tools import r,annotate_source

class QualityTests(unittest.TestCase):
    setUp=test_breadth.BreadthTests.setUp
    tearDown=test_breadth.BreadthTests.tearDown
    job=test_breadth.BreadthTests.job
    fixture=test_breadth.BreadthTests.fixture

    def prepared(self):
        jid,ex,items=self.fixture(8);ex.tool_record_findings(items)
        src=r.read_json(ex.root/'sources.json')[0]
        annotate_source(ex.root,src,{'source_url':'https://example.com/official','final_url':'https://example.com/official'})
        ex.draft_saved=True;r.write_json(ex.root/'draft-ready.json',{'path':'result.json'})
        return jid,ex
    def reply(self,needs_more=True):
        return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'needs_more':needs_more,'gaps':['\u8bb8\u53ef\u8303\u56f4\u5c1a\u672a\u8986\u76d6'],'queries':['official product license commercial use'],'reason':'\u6309\u4e3b\u9898\u8986\u76d6, \u4e0d\u80fd\u4ec5\u6309\u6570\u91cf\u7ed3\u6848.'})}]}]}
    def test_count_target_does_not_prevent_one_scope_followup(self):
        jid,ex=self.prepared()
        with patch('agent.engine.closing_due',return_value=False),patch.object(quality.models,'call',return_value=self.reply()) as call:
            prompt=quality.coverage_followup(ex)
            self.assertIn('official product license',prompt);self.assertFalse(ex.draft_saved)
            self.assertFalse((ex.root/'draft-ready.json').exists())
            self.assertEqual(len(r.read_json(ex.root/'findings-ledger.json')),8)
            self.assertIsNone(quality.coverage_followup(ex));self.assertEqual(call.call_count,1)
    def test_no_new_collection_for_existing_material_only(self):
        jid,ex=self.prepared();req=json.loads(s.get(jid)['request']);req['question']='\u4ec5\u6574\u7406\u73b0\u6709\u6750\u6599\u5e76\u6838\u9a8c, \u4e0d\u8ffd\u52a0\u7f51\u7edc\u91c7\u96c6.';s.update(jid,request=json.dumps(req))
        with patch('agent.engine.closing_due',return_value=False),patch.object(quality.models,'call') as call:
            self.assertIsNone(quality.coverage_followup(ex));call.assert_not_called();self.assertTrue(ex.draft_saved)
    def test_budget_closing_does_not_add_quality_calls(self):
        jid,ex=self.prepared()
        with patch('agent.engine.closing_due',return_value=True),patch.object(quality.models,'call') as call:
            self.assertIsNone(quality.coverage_followup(ex));call.assert_not_called()
    def test_failed_structure_keeps_original_draft(self):
        jid,ex=self.prepared()
        with patch('agent.engine.closing_due',return_value=False),patch.object(quality.models,'call',return_value={'status':'completed','output':[]}):
            self.assertIsNone(quality.coverage_followup(ex));self.assertTrue(ex.draft_saved)
