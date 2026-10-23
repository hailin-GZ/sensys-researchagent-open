"""Observable cache, routing and handoff invariants; synthetic fixtures are not research."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import research as r
import capabilities as c
HTML=b'<html><article><p>A synthetic observation describes a privacy concern during a bedside voice interaction.</p><p>A separate fixture paragraph provides enough content to exercise archive integrity and exact quote checks.</p></article></html>'


class Upgrade(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'task'
        r.init_task(self.root,{'question':'Fixture only','decision_to_support':'Test behavior'},['synthesis'])
    def tearDown(self):self.temp.cleanup()
    def capture(self,**kwargs):
        return r.capture(self.root,url='https://example.org/test',max_images=0,**kwargs)
    def fetch(self,*args,**kwargs):return HTML,'https://example.org/test',200,'text/html'
    def result(self,s):
        b=r.read_json(self.root/s['artifacts']['blocks'])[0]
        e=r.add_evidence(self.root,s['source_id'],b['block_id'],'privacy concern')
        value=r.read_json(self.root/'result.json');value.update(summary='Fixture only',support_reviewed=True,
            findings=[dict(finding_id='f1',kind='fact',statement='The fixture includes a concern.',evidence_refs=[e['evidence_id']],limitations=['Synthetic fixture.'])])
        r.write_json(self.root/'result.json',value)
    def test_cache_hit_does_not_fetch_or_change_time(self):
        with patch.object(r,'download',side_effect=self.fetch) as fetch:
            first=self.capture();second=self.capture()
            self.assertEqual(fetch.call_count,1);self.assertTrue(second['reused'])
            self.assertEqual(first['retrieved_at'],second['retrieved_at'])
    def test_refresh_retains_original_and_fetches_again(self):
        with patch.object(r,'download',side_effect=self.fetch) as fetch:
            first=self.capture();second=self.capture(refresh=True)
            self.assertEqual(fetch.call_count,2);self.assertNotEqual(first['source_id'],second['source_id'])
            self.assertEqual(len(r.read_json(self.root/'sources.json')),2)
    def test_expired_cache_is_not_used(self):
        with patch.object(r,'download',side_effect=self.fetch) as fetch:
            self.capture()
            with patch.object(r,'age_seconds',return_value=90000):self.capture()
            self.assertEqual(fetch.call_count,2)
    def test_selector_and_scope_are_separate_cache_entries(self):
        with patch.object(r,'download',side_effect=self.fetch) as fetch:
            first=self.capture();second=self.capture(selector='article');third=self.capture(scope='excerpt')
            self.assertEqual(fetch.call_count,3);self.assertEqual(third['status'],'snippet_only')
            self.assertNotEqual(first['capture_key'],second['capture_key'])
    def test_corrupt_cached_artifact_is_reacquired(self):
        with patch.object(r,'download',side_effect=self.fetch) as fetch:
            s=self.capture();(self.root/s['artifacts']['raw']).write_bytes(b'corruption')
            second=self.capture();self.assertEqual(fetch.call_count,2)
            self.assertFalse(second.get('reused',False))
    def test_changed_local_file_is_not_reused(self):
        p=Path(self.temp.name)/'supplied.txt';p.write_text('Synthetic old observation.',encoding='utf-8')
        first=r.capture(self.root,file=p);p.write_text('Synthetic changed observation.',encoding='utf-8')
        second=r.capture(self.root,file=p);self.assertNotEqual(first['source_id'],second['source_id'])
    def test_failed_capture_is_not_successfully_cached(self):
        with patch.object(r,'download',return_value=(b'denied','https://example.org/test',403,'text/plain')) as fetch:
            self.capture();self.capture();self.assertEqual(fetch.call_count,2)
    def test_search_cache_avoids_worker_and_preserves_query(self):
        worker=type('Result',(),dict(returncode=0,stdout=json.dumps([dict(href='https://example.org/a',title='Fixture',body='Synthetic lead')])))()
        with patch.object(r.subprocess,'run',return_value=worker) as run:
            first=r.discover(self.root,'fixture');second=r.discover(self.root,'fixture')
            self.assertEqual(run.call_count,1);self.assertTrue(second['reused'])
            self.assertEqual(first['retrieved_at'],second['retrieved_at'])
    def test_lookup_is_bounded_and_deduplicates_bundled_files(self):
        out=c.lookup('research synthesis',kind='skill',stage='analyze',limit=4)
        self.assertLessEqual(len(out['matches']),4)
        paths=[x['package_path'] for x in out['matches'] if x.get('package_path')]
        self.assertEqual(len(paths),len(set(paths)))
        self.assertTrue(any('research-synthesis' in x for x in paths))
    def test_main_container_is_preferred_over_nested_article_card(self):
        html=b'<html><main><article><p>A synthetic teaser card describes only one feature.</p></article><p>Important content after the card: other product features, limitations and context must also be retained for a complete comparison.</p></main></html>'
        with patch.object(r,'download',return_value=(html,'https://example.org/test',200,'text/html')):s=self.capture()
        self.assertEqual(s['status'],'complete_body');self.assertIn('Important content',(self.root/s['artifacts']['markdown']).read_text('utf-8'))
    def test_multiple_article_cards_do_not_claim_complete_first_card(self):
        html=b'<html><body><article><p>First synthetic card describes a product feature but cannot represent the whole page.</p></article><article><p>Second synthetic card describes a different feature and needs to remain available for review.</p></article></body></html>'
        with patch.object(r,'download',return_value=(html,'https://example.org/test',200,'text/html')):s=self.capture()
        self.assertEqual(s['status'],'partial_body');self.assertIn('Second synthetic card',(self.root/s['artifacts']['markdown']).read_text('utf-8'))
    def test_relative_video_poster_is_registered_and_resolves_with_zero_image_budget(self):
        html=b'<html><article><p>A substantive synthetic product paragraph describes enough context to test a poster whose bytes are deliberately not downloaded.</p><video poster="assets/demo.jpg" src="assets/demo.mp4"></video></article></html>'
        with patch.object(r,'download',return_value=(html,'https://example.org/test',200,'text/html')):s=self.capture()
        self.assertEqual(s['assets'][0]['original_url'],'https://example.org/assets/demo.jpg')
        self.assertEqual(s['assets'][0]['status'],'omitted_budget')
        self.assertIn('https://example.org/assets/demo.jpg',(self.root/s['artifacts']['markdown']).read_text('utf-8'))
        value=r.read_json(self.root/'result.json');value.update(summary='Synthetic fixture',support_reviewed=True);r.write_json(self.root/'result.json',value)
        self.assertTrue(r.validate(self.root)['ok'])
    def test_executable_filter_does_not_enable_candidates(self):
        out=c.lookup('',kind='tool',executable_only=True)
        self.assertEqual({x['package_path'] for x in out['matches']},{'scripts/research.py','scripts/capabilities.py'})
    def test_context_only_contains_selected_methods(self):
        out=c.context_manifest(['synthesis'])
        self.assertEqual(len(out['files']),2)
        self.assertFalse(any('customer-research' in x['path'] for x in out['files']))
    def test_search_excerpt_cannot_complete_required_role(self):
        p=Path(self.temp.name)/'excerpt.txt';p.write_text('Synthetic search excerpt, not original body.',encoding='utf-8')
        s=r.capture(self.root,file=p,scope='excerpt',source_url='https://example.org/a')
        plan=dict(schema_version='2.0',roles=[dict(role='voices',required=True,reason='Need original experience',status='captured',source_ids=[s['source_id']],gap='')])
        self.assertTrue(c.check_plan(self.root,plan))
    def test_required_coverage_gap_prevents_completion(self):
        plan=dict(schema_version='2.0',roles=[dict(role='voices',required=True,reason='Need user evidence',status='missing',source_ids=[],gap='Unavailable')])
        c.save_plan(self.root,plan)
        with patch.object(r,'download',side_effect=self.fetch):s=self.capture()
        self.result(s);out=r.read_json(self.root/'result.json');out['status']='complete';r.write_json(self.root/'result.json',out)
        self.assertFalse(r.validate(self.root)['ok'])
    def test_incomplete_body_cannot_complete_required_role(self):
        p=Path(self.temp.name)/'partial.html';p.write_text('<html><body>Partial unselected material without a reviewed body container. There is enough substantive text to archive, but the body boundary has not been identified and completeness must not be assumed.</body></html>',encoding='utf-8')
        s=r.capture(self.root,file=p)
        self.assertEqual(s['status'],'partial_body')
        plan=dict(schema_version='2.0',roles=[dict(role='official',required=True,reason='Need full specification',status='captured',source_ids=[s['source_id']])])
        self.assertTrue(c.check_plan(self.root,plan))
    def test_malformed_coverage_has_reviewable_errors(self):
        for plan in [[],dict(schema_version='2.0',roles={}),dict(schema_version='2.0',roles=['bad role']),dict(schema_version='2.0',roles=[dict(role='voices',status='captured',source_ids='s0001')])]:
            self.assertTrue(c.check_plan(self.root,plan))
    def test_bounded_retrieval_preserves_exact_locator(self):
        with patch.object(r,'download',side_effect=self.fetch):s=self.capture()
        out=c.retrieve(self.root,query='privacy',limit=1,max_chars=100)
        self.assertEqual(len(out['blocks']),1);self.assertEqual(out['blocks'][0]['source_id'],s['source_id'])
        self.assertIn('privacy concern',out['blocks'][0]['text'])
        self.assertTrue(out['blocks'][0]['block_id'])
    def test_tampered_archive_is_not_returned_as_evidence(self):
        with patch.object(r,'download',side_effect=self.fetch):s=self.capture()
        (self.root/s['artifacts']['blocks']).write_text('[]',encoding='utf-8')
        with self.assertRaises(ValueError):c.retrieve(self.root,'privacy')
    def test_large_block_returns_matching_window_with_exact_offsets(self):
        p=Path(self.temp.name)/'large.txt';text='Synthetic navigation '*200+'a privacy concern near the end.';p.write_text(text,encoding='utf-8')
        s=r.capture(self.root,file=p);b=c.retrieve(self.root,'privacy',source_id=s['source_id'],limit=1,max_chars=100)['blocks'][0]
        self.assertIn('privacy concern',b['text']);self.assertGreater(b['char_start'],0)
        original=r.read_json(self.root/s['artifacts']['blocks'])[0]['text']
        self.assertEqual(b['text'],original[b['char_start']:b['char_end']]);self.assertTrue(b['truncated'])
    def test_handoff_carries_scope_and_retrievable_provenance(self):
        with patch.object(r,'download',side_effect=self.fetch):s=self.capture()
        self.result(s);out=c.handoff(self.root)
        self.assertTrue(out['validation']['ok']);self.assertEqual(out['status'],'partial')
        self.assertEqual(out['schema_version'],'2.0');self.assertEqual(out['provenance'][0]['source_id'],s['source_id'])
        for path in out['provenance'][0]['artifacts'].values():self.assertTrue((self.root/path).exists())


if __name__=='__main__':unittest.main()
