import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from agent.tool_readiness import installation

class ReadinessTests(unittest.TestCase):
    def test_presence_does_not_create_callable_integration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'candidate.py').write_text('')
            value=installation({'id':'candidate','package_path':'candidate.py','availability':'local_executor'},root,{})
            self.assertEqual(value['installation_state'],'unregistered_local_file')
            self.assertIsNone(value['registered_route'])
    def test_catalog_and_host_skills_are_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            for availability,state in [('conditional','catalog_only'),('host_only','host_only')]:
                self.assertEqual(installation({'id':'candidate','availability':availability},tmp,{})['installation_state'],state)
    def test_missing_dependency_disables_registered_readiness(self):
        with tempfile.TemporaryDirectory() as tmp,patch('agent.tool_readiness.importlib.util.find_spec',return_value=None):
            value=installation({'id':'rss'},tmp,{'rss':'rss'})
            self.assertEqual(value['installation_state'],'missing_dependency')
            self.assertIn('feedparser',value['missing_dependencies'])
    def test_paths_outside_bundle_are_not_installed_methods(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'secret.txt').write_text('')
            inner=root/'bundle';inner.mkdir()
            value=installation({'id':'candidate','package_path':'../secret.txt','availability':'bundled_instructions'},inner,{})
            self.assertFalse(value['package_present'])
