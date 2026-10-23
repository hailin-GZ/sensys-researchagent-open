"""Bounded Scrapling public-page fetch. No accounts, ambient cookies or auto retries."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urljoin, urlsplit

MAX_BYTES=5_000_000

def fetch_http(url, timeout=20, max_bytes=MAX_BYTES):
    from scrapling.fetchers import Fetcher
    from research import public_url
    started=time.monotonic()
    for _ in range(6):
        public_url(url);chunks=[];size=0
        def bounded(chunk):
            nonlocal size
            size+=len(chunk)
            if size>max_bytes or time.monotonic()-started>timeout*2:raise ValueError('Response byte/time ceiling exceeded')
            chunks.append(chunk)
            return len(chunk)
        page=Fetcher.get(url,timeout=timeout,retries=1,follow_redirects=False,
                         verify=True,impersonate='chrome',content_callback=bounded)
        headers={str(k).lower():str(v) for k,v in page.headers.items()}
        if page.status in (301,302,303,307,308) and headers.get('location'):
            url=urljoin(url,headers['location']);continue
        data=b''.join(chunks) or bytes(page.body)
        if len(data)>max_bytes:raise ValueError('Response byte ceiling exceeded')
        return data,str(page.url),page.status,headers.get('content-type',''),{'transport':'scrapling_http','body_kind':'http_response'}
    raise ValueError('Redirect limit exceeded')

def fetch_browser(url, mode, timeout=25, max_bytes=MAX_BYTES):
    from scrapling.fetchers import DynamicFetcher,StealthyFetcher
    from research import public_url
    public_url(url);guard={'ready':False,'blocked':False}
    def setup(page):
        # All navigations, scripts, frames and XHR pass the same destination check.
        # Block service workers so they cannot bypass request interception.
        def route(request):
            try:
                if request.request.resource_type in ('image','media','font'):return request.abort()
                public_url(request.request.url);request.continue_()
            except Exception:
                guard['blocked']=True;request.abort()
        try:
            page.route('**/*',route)
            page.context.route_web_socket('**/*',lambda socket:socket.close())
            page.context.add_init_script('window.RTCPeerConnection = undefined; window.webkitRTCPeerConnection = undefined;')
            guard['ready']=True
        except Exception:
            # Upstream logs hook exceptions instead of propagating them; closing
            # the page makes the subsequent navigation fail without network work.
            page.close();raise
    from browser_path import chromium_path
    executable=chromium_path()
    kwargs=dict(headless=True,timeout=timeout*1000,retries=1,wait=600,network_idle=False,
                google_search=False,page_setup=setup,executable_path=str(executable),
                additional_args={'service_workers':'block','accept_downloads':False,'ignore_https_errors':False,'permissions':[]},
                extra_flags=['--disable-quic','--disable-background-networking','--no-proxy-server'])
    if mode=='stealth':kwargs['solve_cloudflare']=False
    page=(StealthyFetcher if mode=='stealth' else DynamicFetcher).fetch(url,**kwargs)
    if not guard['ready']:raise ValueError('Browser public destination guard was not installed')
    public_url(str(page.url));data=bytes(page.body)
    if len(data)>max_bytes:raise ValueError('Rendered document byte ceiling exceeded')
    return data,str(page.url),page.status,'text/html',{'transport':'scrapling_'+mode,'body_kind':'rendered_dom','blocked_requests':guard['blocked']}

def fetch(url,mode='http',timeout=20):
    if mode not in ('http','dynamic','stealth'):raise ValueError('Unknown fetch mode')
    return fetch_http(url,timeout) if mode=='http' else fetch_browser(url,mode,timeout)

def isolated_fetch(url,folder,mode='http',timeout=20):
    """Hard process deadline; kill browser descendants too on timeout."""
    import psutil
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    env={k:v for k,v in os.environ.items() if k.lower() not in ('http_proxy','https_proxy','all_proxy','no_proxy')}
    env['PYTHONIOENCODING']='utf-8'
    command=[sys.executable,str(Path(__file__).resolve()),'--url',url,'--folder',str(folder),'--mode',mode,'--timeout',str(timeout)]
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        stdout,stderr=proc.communicate(timeout=timeout*2+10)
    except subprocess.TimeoutExpired:
        try:children=psutil.Process(proc.pid).children(recursive=True)
        except psutil.Error:children=[]
        for child in reversed(children):
            try:child.kill()
            except psutil.Error:pass
        proc.kill();proc.communicate();raise TimeoutError('Public capture total deadline exceeded') from None
    if proc.returncode:
        raise RuntimeError('Scrapling worker failed: '+stderr.decode('utf-8',errors='replace')[-800:])
    metadata=json.loads((folder/'response.json').read_text(encoding='utf-8'))
    return (folder/'response.bin').read_bytes(),metadata

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',required=True);parser.add_argument('--folder',required=True)
    parser.add_argument('--mode',choices=['http','dynamic','stealth'],default='http');parser.add_argument('--timeout',type=int,default=20)
    args=parser.parse_args();data,url,status,ctype,meta=fetch(args.url,args.mode,args.timeout)
    folder=Path(args.folder);folder.mkdir(parents=True,exist_ok=True)
    (folder/'response.bin').write_bytes(data)
    (folder/'response.json').write_text(json.dumps({**meta,'url':url,'status':status,'content_type':ctype}),encoding='utf-8')
