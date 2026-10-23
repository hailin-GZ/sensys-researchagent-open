"""Acquire bounded public web samples or Bilibili comments with provenance."""
import argparse, json, sys, time
from pathlib import Path
from urllib.parse import quote, urljoin
import research

def curl_download(url, timeout=15, max_bytes=25_000_000):
    from curl_cffi.requests import Session
    started=time.monotonic()
    with Session(trust_env=False, impersonate='chrome') as session:
        for _ in range(6):
            research.public_url(url)
            with session.stream('GET',url,timeout=timeout,allow_redirects=False) as response:
                if response.status_code in {301,302,303,307,308}:
                    url=urljoin(url,response.headers['location']);continue
                chunks=[];size=0
                for chunk in response.iter_content():
                    size+=len(chunk)
                    if size>max_bytes or time.monotonic()-started>timeout*2: raise ValueError('Download budget exceeded')
                    chunks.append(chunk)
                return b''.join(chunks),url,response.status_code,response.headers.get('content-type','')
    raise ValueError('Redirect budget exceeded')

def public_replies(payload, source_url, retrieved_at):
    if not isinstance(payload,dict) or payload.get('code') != 0 or not isinstance(payload.get('data'),dict):
        raise ValueError('Platform application error; HTTP 200 is insufficient')
    rows=[]
    def visit(reply,pointer,parent=None):
        if not isinstance(reply,dict): return
        content=reply.get('content')
        text=content.get('message') if isinstance(content,dict) else None
        if isinstance(text,str) and text.strip():
            rows.append({'platform':'bilibili','source_url':source_url,'comment_id':str(reply.get('rpid')),'parent_id':parent,'text':text,'published_at_unix':reply.get('ctime'),'likes':reply.get('like'),'retrieved_at':retrieved_at,'raw_json_pointer':pointer+'/content/message'})
        children=reply.get('replies') or []
        if not isinstance(children,list): raise ValueError('Unexpected child reply schema')
        for i,child in enumerate(children): visit(child,f'{pointer}/replies/{i}',str(reply.get('rpid')))
    replies=payload['data'].get('replies') or []
    if not isinstance(replies,list): raise ValueError('Unexpected reply schema')
    for i,reply in enumerate(replies): visit(reply,f'/data/replies/{i}')
    return rows

def acquire(root,url):
    return research.capture(root,url=url,category='public_platform',max_images=0,timeout=12,method='curl_cffi_public_http')

def bilibili(root, query, limit=3):
    url='https://api.bilibili.com/x/web-interface/search/type?search_type=video&keyword='+quote(query)
    source=acquire(root,url)
    if source['status']!='structured_data': raise ValueError('Search JSON was not obtained')
    payload=research.read_json(root/source['artifacts']['raw'])
    if payload.get('code')!=0 or not isinstance(payload.get('data'),dict): raise ValueError('Search API application error')
    videos=payload['data'].get('result',[])
    if not isinstance(videos,list): raise ValueError('Unexpected search result schema')
    selected=sorted((x for x in videos if isinstance(x,dict) and x.get('aid')),key=lambda x:x.get('video_review',0),reverse=True)[:limit]
    comments=[];attempts=[]
    for video in selected:
        url=f"https://api.bilibili.com/x/v2/reply?type=1&oid={int(video['aid'])}&pn=1&ps=20&sort=2"
        source=acquire(root,url)
        try:
            if source['status']!='structured_data': raise ValueError('Reply JSON unavailable')
            rows=public_replies(research.read_json(root/source['artifacts']['raw']),url,source['retrieved_at'])
            for row in rows: row.update(video_id=video.get('bvid'),source_id=source['source_id'])
            comments.extend(rows);attempts.append({'source_id':source['source_id'],'comments_obtained':len(rows),'coverage':'first page and embedded replies only'})
        except (ValueError,KeyError) as exc: attempts.append({'source_id':source['source_id'],'error':str(exc),'comments_obtained':0})
        time.sleep(.5)
    result={'status':'sample_obtained' if comments else 'no_comment_sample','query':query,'selected_videos':selected,'comments':comments,'attempts':attempts,'limitations':['No exhaustive pagination, representativeness or account-level access is established.']}
    research.write_json(root/'platform-sample.json',result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',required=True);p.add_argument('--platform',choices=['web','bilibili'],required=True);p.add_argument('--url');p.add_argument('--query');p.add_argument('--limit',type=int,default=3);args=p.parse_args()
    root=Path(args.task)
    if not 1<=args.limit<=5: p.error('limit must be between 1 and 5')
    if not (root/'brief.json').exists(): research.init_task(root,{'question':args.query or args.url,'purpose':'Public information connectivity sample'},['voices' if args.platform=='bilibili' else 'competitors'])
    research.download=curl_download
    try:
        if args.platform=='web':
            if not args.url: p.error('--url is required for web')
            result=acquire(root,args.url)
        else:
            if not args.query: p.error('--query is required for bilibili')
            result=bilibili(root,args.query,args.limit)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as exc:
        print(json.dumps({'status':'failed','error':str(exc)},ensure_ascii=False));return 2

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');raise SystemExit(main())
