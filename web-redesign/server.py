"""Local research UI with server-side access keys and durable Agent task routes."""
from control import init_store, chat_reply, Error, DB as CONTROL_DB
import argparse
from contextlib import contextmanager
import hashlib
import ipaddress
import json
import os
import secrets
import sqlite3
import threading
import time
import sys
from urllib.parse import urlsplit
from collections import defaultdict, deque
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from agent import store as research_store
from agent import http_api as research_api
DB = CONTROL_DB
COOKIE = 'sensys_redesign_session'

def public_origin(port):
    """Explicit deployment origin; never trust client-controlled forwarded headers."""
    value=os.environ.get('SENSYS_PUBLIC_ORIGIN','').strip()
    if not value:return f'http://127.0.0.1:{port}'
    u=urlsplit(value)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError('SENSYS_PUBLIC_ORIGIN must be an HTTPS origin without a path')
    return value


@contextmanager
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript('''
    CREATE TABLE IF NOT EXISTS access_keys (
        id TEXT PRIMARY KEY, digest TEXT UNIQUE NOT NULL, label TEXT NOT NULL,
        expires REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS sessions (
        digest TEXT PRIMARY KEY, key_id TEXT NOT NULL, expires REAL NOT NULL);
    ''')
    try:
        with db:
            yield db
    finally:
        db.close()


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def create_key(label, days):
    if not 0 < days <= 3650:
        raise ValueError('days must be between 0 and 3650')
    key, key_id = secrets.token_urlsafe(32), secrets.token_hex(6)
    with connect() as db:
        db.execute('INSERT INTO access_keys(id,digest,label,expires,enabled) VALUES (?,?,?,?,1)',
                   (key_id, digest(key), label, time.time() + days * 86400))
    return key_id, key


def revoke_key(key_id):
    with connect() as db:
        count = db.execute('UPDATE access_keys SET enabled=0 WHERE id=?', (key_id,)).rowcount
        db.execute('DELETE FROM sessions WHERE key_id=?', (key_id,))
    return count


class Server(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address):
        super().__init__(address, Handler)
        self.attempts = defaultdict(deque)
        self.lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def client_ip(self):
        peer=self.client_address[0]
        if os.environ.get('SENSYS_TRUST_LOOPBACK_PROXY')=='1' and ipaddress.ip_address(peer).is_loopback:
            try:return str(ipaddress.ip_address(self.headers.get('X-Real-IP','')))
            except ValueError:pass
        return peer

    def log_message(self, fmt, *args):
        # Never include request bodies, cookies, or credentials in logs.
        pass

    def send(self, status, value, content_type='application/json; charset=utf-8', cookie=None, download=False):
        body = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        if download:
            name='sensys-evidence-package.zip' if content_type=='application/zip' else 'sensys-research-record.json' if content_type.startswith('application/json') else 'sensys-source-artifact.bin'
            self.send_header('Content-Disposition', 'attachment; filename="'+name+'"')
        self.end_headers()
        self.wfile.write(body)

    def send_stream(self, status, stream, content_type, filename):
        """Bounded-memory downloads, including large evidence packages."""
        stream.seek(0,2);size=stream.tell();stream.seek(0)
        self.send_response(status)
        for name,value in {'Content-Type':content_type,'Content-Length':str(size),'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Disposition':'attachment; filename="'+filename+'"','Content-Security-Policy':"default-src 'none'; sandbox"}.items():self.send_header(name,value)
        self.end_headers()
        try:
            while chunk:=stream.read(65536):self.wfile.write(chunk)
        except (BrokenPipeError,ConnectionResetError):pass

    def cookie_name(self):
        return COOKIE if os.environ.get('SENSYS_PUBLIC_ORIGIN','').strip() else COOKIE+'_'+str(self.server.server_port)

    def session_token(self):
        cookies=SimpleCookie(self.headers.get('Cookie',''));name=self.cookie_name()
        return cookies[name].value if name in cookies else cookies[COOKIE].value if COOKIE in cookies else ''

    def cookie(self, token='', max_age=0):
        # Local preview is loopback HTTP. Enable only behind HTTPS in deployment.
        secure = '; Secure' if os.environ.get('SENSYS_SECURE_COOKIE') == '1' or public_origin(self.server.server_port).startswith('https:') else ''
        return f'{self.cookie_name()}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}{secure}'

    def session(self):
        try:
            token = self.session_token()
        except Exception:
            return None
        with connect() as db:
            return db.execute('''SELECT k.id,k.label,k.expires FROM sessions s
                JOIN access_keys k ON k.id=s.key_id
                WHERE s.digest=? AND s.expires>? AND k.expires>? AND k.enabled=1''',
                (digest(token), time.time(), time.time())).fetchone()

    def valid_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',urlsplit(public_origin(self.server.server_port)).netloc)

    def do_GET(self):
        if not self.valid_host():
            return self.send(400, {'error': 'Use the local preview address.'})
        path = self.path.split('?', 1)[0]
        if path in ('/api/conversations','/api/conversation','/api/conversation/stages','/api/jobs','/api/job','/api/job/status','/api/job/result','/api/job/export','/api/job/package','/api/artifact'):
            row=self.session()
            if not row:return self.send(401,{'error':'Access permission expired.'})
            try:return research_api.get(self,row['id'])
            except Error as e:return self.send(e.status,{'error':str(e)})
        if path == '/api/session':
            row = self.session()
            return self.send(200, {'authenticated': bool(row), 'label': row['label'] if row else None})
        if path in ('/api/example','/api/export'):
            if not self.session():return self.send(401,{'error':'Access permission expired.'})
            return self.send(404,{'error':'Trial examples removed, View your own conversations.'})
        if path=='/api/quota':
            row=self.session()
            if not row:return self.send(401,{'error':'Access permission expired.'})
            return self.send(200,research_store.control().quota_public(row['id']))
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8')}
        files['/report-view.js']=('report-view.js','text/javascript; charset=utf-8')
        files['/research.js']=('research.js','text/javascript; charset=utf-8')
        files['/interaction.css']=('interaction.css','text/css; charset=utf-8')
        if path in files:
            name, kind = files[path]
            return self.send(200, (ROOT / 'static' / name).read_bytes(), kind)
        self.send(404, {'error': 'Page not found.'})

    def do_POST(self):
        if not self.valid_host():
            return self.send(400, {'error': 'Invalid access address.'})
        origin = public_origin(self.server.server_port)
        if self.path=='/api/upload':
            if self.headers.get('Origin')!=origin:return self.send(403,{'error':'Request origin failed verification.'})
            row=self.session()
            if not row:return self.send(401,{'error':'Access permission expired.'})
            try:return research_api.upload(self,row['id'])
            except Error as e:return self.send(e.status,{'error':str(e)})
        if self.headers.get('Origin') != origin or not self.headers.get('Content-Type','').startswith('application/json'):
            return self.send(403, {'error': 'Request origin failed verification.'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 24000:
                return self.send(413, {'error': 'Request content too long.'})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            return self.send(400, {'error': 'Invalid request format.'})
        if self.path in ('/api/message','/api/research','/api/job/action'):
            row=self.session()
            if not row:return self.send(401,{'error':'Access permission expired.'})
            try:return self.send(200,research_store.submit(row['id'],data,conversational=self.path=='/api/message') if self.path!='/api/job/action' else research_store.action(row['id'],data))
            except Error as e:return self.send(e.status,{'error':str(e)})
        if self.path == '/api/chat':
            row = self.session()
            if not row:
                return self.send(401, {'error': 'Access permission expired.'})
            try:
                return self.send(200, chat_reply(row['id'], data))
            except Error as error:
                return self.send(error.status, {'error': str(error)})
        if self.path == '/api/logout':
            try:
                c = SimpleCookie(self.headers.get('Cookie',''))
                token = self.session_token()
            except Exception:
                token = ''
            with connect() as db:
                db.execute('DELETE FROM sessions WHERE digest=?', (digest(token),))
            return self.send(200, {'ok': True}, cookie=self.cookie())
        if self.path != '/api/login':
            return self.send(404, {'error': 'Endpoint not found.'})
        now = time.time()
        with self.server.lock:
            attempts = self.server.attempts[self.client_ip()]
            while attempts and attempts[0] < now - 60:
                attempts.popleft()
            if len(attempts) >= 10:
                return self.send(429, {'error': 'Too many attempts, Please try again in one minute.'})
            attempts.append(now)
        key = data.get('key')
        if not isinstance(key, str) or not 1 <= len(key) <= 200:
            return self.send(401, {'error': 'Invalid key, Expired or disabled.'})
        with connect() as db:
            row = db.execute('SELECT * FROM access_keys WHERE digest=? AND enabled=1 AND expires>?',
                             (digest(key.strip()), now)).fetchone()
            if not row:
                return self.send(401, {'error': 'Invalid key, Expired or disabled.'})
            token = secrets.token_urlsafe(32)
            expires = min(row['expires'], now + 7 * 86400)
            db.execute('DELETE FROM sessions WHERE expires<=?', (now,))
            db.execute('INSERT INTO sessions VALUES (?,?,?)', (digest(token), row['id'], expires))
        self.send(200, {'authenticated': True, 'label': row['label']}, cookie=self.cookie(token, int(expires-now)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve'); serve.add_argument('--port', type=int, default=8766)
    create = sub.add_parser('create-key'); create.add_argument('--label', required=True); create.add_argument('--days', type=float, default=7)
    sub.add_parser('list-keys')
    revoke = sub.add_parser('revoke-key'); revoke.add_argument('id')
    args = parser.parse_args()
    if args.command == 'create-key':
        key_id, key = create_key(args.label, args.days)
        print(json.dumps({'id': key_id, 'key': key, 'note': 'Copy now; plaintext is not stored.'}, ensure_ascii=False))
    elif args.command == 'list-keys':
        with connect() as db:
            print(json.dumps([dict(x) for x in db.execute('SELECT id,label,expires,enabled FROM access_keys')], ensure_ascii=False))
    elif args.command == 'revoke-key':
        print(json.dumps({'revoked': revoke_key(args.id)}))
    else:
        with connect():
            pass
        research_store.init()
        print(f'Preview: http://127.0.0.1:{args.port}', flush=True)
        Server(('127.0.0.1', args.port)).serve_forever()
