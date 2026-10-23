"""Acceptance failures must not become market evidence."""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import research
from platform_probe import public_replies

class AccessTests(unittest.TestCase):
    def test_application_error_rejected_even_with_data(self):
        with self.assertRaises(ValueError): public_replies({'code':-101,'data':{'replies':[]}},'https://api.bilibili.com/', 'now')

    def test_empty_comments_are_not_invented(self):
        self.assertEqual(public_replies({'code':0,'data':{'replies':None}},'https://api.bilibili.com/','now'),[])

    def test_reply_pointer_preserves_exact_text_and_parent(self):
        payload={'code':0,'data':{'replies':[{'rpid':1,'content':{'message':'An actual objection'},'replies':[{'rpid':2,'content':{'message':'A reply'}}]}]}}
        rows=public_replies(payload,'https://api.bilibili.com/','now')
        for row in rows:
            node=payload
            for part in row['raw_json_pointer'].strip('/').split('/'): node=node[int(part)] if isinstance(node,list) else node[part]
            self.assertEqual(node,row['text'])
        self.assertEqual(rows[1]['parent_id'],'1')

    def test_wechat_migration_notice_is_not_an_article(self):
        html='<html><title>Account moved</title><main>\u8be5\u516c\u4f17\u53f7\u5df2\u8fc1\u79fb\u81f3\u65b0\u7684\u8d26\u53f7, \u539f\u8d26\u53f7\u5df2\u56de\u6536.'+('Migration notice.'*30)+'</main></html>'
        with tempfile.TemporaryDirectory() as folder:
            result,markdown=research.html_document(html.encode('utf-8'),'https://mp.weixin.qq.com/s/example',Path(folder),max_images=0)
        self.assertEqual(result['status'],'shell_only');self.assertFalse(result['blocks']);self.assertFalse(markdown)

    def test_challenge_form_is_not_public_content(self):
        html='<html><title>Just a moment...</title><main><form id="challenge-form">Verification</form>'+('Security.'*60)+'</main></html>'
        with tempfile.TemporaryDirectory() as folder:
            result,markdown=research.html_document(html.encode(),'https://example.com/',Path(folder),max_images=0)
        self.assertEqual(result['status'],'captcha');self.assertFalse(markdown)

if __name__=='__main__': unittest.main()
