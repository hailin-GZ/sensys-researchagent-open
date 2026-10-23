import hashlib,json,tempfile,unittest
from pathlib import Path
from agent.method_library import selected
from agent.public_data import endpoint,rows,ROUTES
class ResourceExpansionTests(unittest.TestCase):
    def test_method_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'references').mkdir();(root/'vendor').mkdir();p=root/'vendor/method.md';p.write_text('reference')
            (root/'references/method-library.json').write_text(json.dumps({'methods':[{'path':'vendor/method.md','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}]}))
            self.assertEqual(len(selected(['vendor/method.md'],root)),1)
            self.assertEqual(selected(['../../private.key'],root),[])
            p.write_text('changed')
            with self.assertRaises(ValueError):selected(['vendor/method.md'],root)
    def test_public_routes_cannot_target_arbitrary_hosts(self):
        for route in ROUTES:
            with self.assertRaises(ValueError):endpoint(route,'topic',0)
        for route in ('worldbank','github_repo','github_issues','stackexchange_answers','appstore_reviews'):
            with self.assertRaises(ValueError):endpoint(route,'https://127.0.0.1/private',3)
        url,scope=endpoint('github_search','topic&url=http://127.0.0.1',3)
        self.assertTrue(url.startswith('https://api.github.com/'));self.assertIn('%26',url)
    def test_application_errors_and_empty_data_are_not_evidence(self):
        with self.assertRaises(ValueError):rows('github_search',b'{"message":"rate limited"}')
        with self.assertRaises(ValueError):rows('worldbank',b'[{"message":[{"value":"invalid"}]}]')
        self.assertEqual(rows('worldbank',b'[{},[{"value":null},{"value":123,"date":"2024"}]]'),[{'value':123,'date':'2024'}])
        self.assertEqual(rows('appstore_reviews',b'{"feed":{"entry":[]}}'),[])
    def test_real_executor_contract_exposes_new_routes(self):
        from agent.tools import DEFINITIONS
        contract=next(x for x in DEFINITIONS if x['name']=='platform_read')['parameters']['properties']['route']['enum']
        self.assertTrue(set(ROUTES).issubset(contract))
    def test_downloaded_library_hashes_and_boundaries(self):
        root=Path(__file__).resolve().parents[2]/'skills/sensys-market-research'
        index=json.loads((root/'references/method-library.json').read_text(encoding='utf-8'))
        for row in index['methods']:
            self.assertEqual(len(selected([row['path']],root)),1)
            for file in row['files']:
                p=(root/file['path']).resolve();self.assertTrue(p.is_relative_to(root.resolve()))
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),file['sha256'])
if __name__=='__main__':unittest.main()
