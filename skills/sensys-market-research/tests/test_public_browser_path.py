"""A source-only checkout must use an explicitly installed browser or cache."""
import os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from browser_path import chromium_path

class PublicBrowserPathTests(unittest.TestCase):
    def test_explicit_existing_executable_is_used(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'browser';path.write_text('synthetic fixture')
            with patch.dict(os.environ,{'SENSYS_CHROMIUM_PATH':str(path)}):
                self.assertEqual(chromium_path(),path)

    def test_default_playwright_cache_is_used_on_every_platform(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'browser';path.write_text('synthetic fixture')
            manager=MagicMock();manager.__enter__.return_value=SimpleNamespace(chromium=SimpleNamespace(executable_path=str(path)))
            with patch.dict(os.environ,{'SENSYS_CHROMIUM_PATH':''}),patch('playwright.sync_api.sync_playwright',return_value=manager) as lookup:
                self.assertEqual(chromium_path(),path);lookup.assert_called_once_with()

    def test_missing_installation_remains_an_explicit_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{'SENSYS_CHROMIUM_PATH':str(Path(folder)/'missing')}):
                with self.assertRaisesRegex(ValueError,'Chromium is missing'):chromium_path()

if __name__=='__main__':unittest.main()
