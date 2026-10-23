"""Exercise admin HTTPS origin, host isolation and CSRF over actual HTTP."""
import http.client, importlib.util, json, os, sys, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web-redesign'))
import control as c
import server as public
spec=importlib.util.spec_from_file_location('production_admin',Path(__file__).with_name('server.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class AdminProductionTests(unittest.TestCase):
    def test_https_login_cookie_origin_host_and_csrf(self):
        origin='https://admin.example.com'
        with tempfile.TemporaryDirectory() as folder, patch.object(c,'DB',Path(folder)/'db.sqlite'), patch.dict(os.environ,{'SENSYS_ADMIN_ORIGIN':origin,'SENSYS_PUBLIC_ORIGIN':'https://research.example.com'}):
            a.research_store.init();key=c.init_admin();server=a.Server(('127.0.0.1',0))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            def request(path,body=None,host=origin.split('//')[1],source=origin,cookie='',csrf=''):
                conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
                conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,{'Host':host,'Origin':source,'Content-Type':'application/json','Cookie':cookie,'X-CSRF-Token':csrf})
                response=conn.getresponse();out=(response.status,json.loads(response.read()),dict(response.getheaders()));conn.close();return out
            try:
                self.assertEqual(request('/api/session',host='evil.example')[0],400)
                self.assertEqual(request('/api/login',{'key':key},source='https://research.example.com')[0],403)
                status,body,headers=request('/api/login',{'key':key});self.assertEqual(status,200)
                cookie=headers['Set-Cookie'];self.assertIn('; Secure',cookie);self.assertIn('HttpOnly',cookie);self.assertNotIn('Domain=',cookie)
                cookie=cookie.split(';')[0]
                self.assertEqual(request('/api/state',cookie=cookie)[0],200)
                self.assertEqual(request('/api/logout',{},cookie=cookie)[0],403)
                self.assertEqual(request('/api/logout',{},cookie=cookie,csrf=body['csrf'])[0],200)
                self.assertEqual(request('/api/state',cookie=cookie)[0],401)
                self.assertEqual(request('/api/state',cookie='sensys_redesign_session=synthetic-user-session')[0],401)
            finally:server.shutdown();server.server_close()
