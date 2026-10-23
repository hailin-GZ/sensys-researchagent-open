"""Production regressions: credential integrity and process-lock recovery."""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'web-redesign'), str(ROOT/'skills/sensys-market-research/scripts')]
import portable_secret as secret
from file_lock import exclusive_lock
from cryptography.fernet import Fernet

class ProductionTests(unittest.TestCase):
    def test_credential_survives_restart_and_rejects_tampering_or_wrong_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'secret.key';path.write_bytes(Fernet.generate_key());path.chmod(0o600)
            with patch.dict(os.environ,{'SENSYS_SECRET_KEY_FILE':str(path)}):
                value=secret.encrypt('synthetic-test-secret')
                self.assertNotIn('synthetic-test-secret',value)
                self.assertEqual(secret.decrypt(value),'synthetic-test-secret')
                with self.assertRaises(ValueError):secret.decrypt(value[:-8]+'XXXXXXXX')
                path.write_bytes(Fernet.generate_key())
                with self.assertRaises(ValueError):secret.decrypt(value)

    def test_linux_refuses_unmigrated_dpapi_and_missing_key_configuration(self):
        with self.assertRaisesRegex(ValueError,'Windows'):secret.decrypt('old-dpapi-ciphertext')
        with patch.dict(os.environ,{'SENSYS_SECRET_KEY_FILE':''}):
            with self.assertRaises(ValueError):secret.encrypt('synthetic-secret')

    @unittest.skipIf(os.name=='nt','Unix file permission check')
    def test_shared_key_permissions_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'key';path.write_bytes(Fernet.generate_key());path.chmod(0o644)
            with patch.dict(os.environ,{'SENSYS_SECRET_KEY_FILE':str(path)}):
                with self.assertRaises(ValueError):secret.encrypt('synthetic-secret')

    def test_lock_released_when_holder_is_killed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'worker.lock'
            code="import sys,time;sys.path.insert(0,sys.argv[1]);from file_lock import exclusive_lock;\nwith exclusive_lock(sys.argv[2]):\n print('locked',flush=True);time.sleep(60)"
            child=subprocess.Popen([sys.executable,'-c',code,str(ROOT/'skills/sensys-market-research/scripts'),str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'locked')
                with self.assertRaises(OSError):
                    with exclusive_lock(path):pass
                child.kill();child.wait(timeout=5)
                # Windows can signal process exit before the kernel closes its handles.
                deadline=time.monotonic()+2
                while True:
                    try:
                        with exclusive_lock(path):pass
                        break
                    except OSError:
                        if time.monotonic()>=deadline:raise
                        time.sleep(.02)
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=5)
                child.stdout.close();child.stderr.close()
