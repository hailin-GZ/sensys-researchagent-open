"""Behavioral access-control checks using an isolated temporary database."""
import http.client
import json
import tempfile
import threading
import time
import unittest
import os
from unittest.mock import patch
from pathlib import Path
import server


class AccessTests(unittest.TestCase):
    def test_proxy_client_identity_requires_opt_in_and_loopback(self):
        class Peer:
            client_address=('127.0.0.1',1234)
            headers={'X-Real-IP':'203.0.113.5'}
        peer=Peer()
        with patch.dict(os.environ,{'SENSYS_TRUST_LOOPBACK_PROXY':'0'}):
            self.assertEqual(server.Handler.client_ip(peer),'127.0.0.1')
        with patch.dict(os.environ,{'SENSYS_TRUST_LOOPBACK_PROXY':'1'}):
            self.assertEqual(server.Handler.client_ip(peer),'203.0.113.5')
            peer.client_address=('203.0.113.6',1234)
            self.assertEqual(server.Handler.client_ip(peer),'203.0.113.6')
            peer.client_address=('127.0.0.1',1234);peer.headers={'X-Real-IP':'malformed'}
            self.assertEqual(server.Handler.client_ip(peer),'127.0.0.1')

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.DB = Path(cls.tmp.name) / 'access.sqlite3'
        cls.http = server.Server(('127.0.0.1', 0))
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.tmp.cleanup()

    def setUp(self):
        self.http.attempts.clear()
        self.key_id, self.key = server.create_key('isolated test', 1)

    def request(self, path, body=None, cookie=None, origin=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        headers = {}
        if cookie: headers['Cookie'] = cookie
        if body is not None:
            headers['Content-Type'] = 'application/json'
            headers['Origin'] = origin or f'http://127.0.0.1:{self.http.server_port}'
        conn.request('POST' if body is not None else 'GET', path,
                     json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse(); data = response.read()
        output = (response.status, dict(response.getheaders()), data)
        conn.close(); return output

    def login(self):
        status, headers, _ = self.request('/api/login', {'key': self.key})
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        return headers['Set-Cookie'].split(';')[0]

    def test_unauthenticated_and_invalid_key(self):
        self.assertEqual(self.request('/api/example')[0], 401)
        self.assertEqual(self.request('/api/export')[0], 401)
        self.assertEqual(self.request('/api/login', {'key':'not-a-key'})[0], 401)

    def test_persistent_session_and_shared_example_removed(self):
        cookie=self.login()
        self.assertTrue(json.loads(self.request('/api/session',cookie=cookie)[2])['authenticated'])
        self.assertEqual(self.request('/api/example',cookie=cookie)[0],404)
        self.assertEqual(self.request('/api/export',cookie=cookie)[0],404)

    def test_local_cookie_is_port_scoped_with_legacy_session_compatibility(self):
        cookie=self.login();name,token=cookie.split('=',1)
        self.assertEqual(name,server.COOKIE+'_'+str(self.http.server_port))
        legacy=server.COOKIE+'='+token
        self.assertTrue(json.loads(self.request('/api/session',cookie=legacy)[2])['authenticated'])
        self.assertEqual(self.request('/api/logout',{},cookie=legacy)[0],200)
        self.assertFalse(json.loads(self.request('/api/session',cookie=cookie)[2])['authenticated'])

    def test_revocation_invalidates_existing_session(self):
        cookie = self.login(); server.revoke_key(self.key_id)
        self.assertEqual(self.request('/api/example', cookie=cookie)[0], 401)
        self.assertEqual(self.request('/api/login', {'key':self.key})[0], 401)

    def test_expiration_invalidates_existing_session(self):
        cookie = self.login()
        with server.connect() as db:
            db.execute('UPDATE access_keys SET expires=? WHERE id=?', (time.time()-1, self.key_id))
        self.assertEqual(self.request('/api/example', cookie=cookie)[0], 401)
        self.assertEqual(self.request('/api/login', {'key':self.key})[0], 401)

    def test_logout_revokes_cookie(self):
        cookie = self.login()
        self.assertEqual(self.request('/api/logout', {}, cookie=cookie)[0], 200)
        self.assertEqual(self.request('/api/example', cookie=cookie)[0], 401)

    def test_cross_origin_and_rate_limit(self):
        self.assertEqual(self.request('/api/login', {'key':self.key}, origin='https://other.example')[0], 403)
        for _ in range(10): self.assertEqual(self.request('/api/login', {'key':'bad'})[0], 401)
        self.assertEqual(self.request('/api/login', {'key':self.key})[0], 429)

    def test_no_private_file_serving_or_plaintext_storage(self):
        self.login()
        for path in ['/data/access.sqlite3','/server.py','/../server.py','/references/frontend-design-SKILL.md']:
            self.assertEqual(self.request(path)[0], 404)
        with server.connect() as db:
            key = db.execute('SELECT * FROM access_keys WHERE id=?', (self.key_id,)).fetchone()
            self.assertNotIn(self.key, str(dict(key)))
            self.assertEqual(key['digest'], server.digest(self.key))


if __name__ == '__main__':
    unittest.main(verbosity=2)
