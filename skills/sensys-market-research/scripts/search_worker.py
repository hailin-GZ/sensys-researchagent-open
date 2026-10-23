"""Isolate upstream metasearch so the caller can enforce a total deadline."""
import argparse
import json
import sys
import time
from ddgs import DDGS

def search(query,limit,backend='auto',factory=DDGS,deadline_seconds=24):
    """Try genuinely distinct engines and pages; retain acquired leads on later failure."""
    results=[];attempts=[];seen=set();started=time.monotonic()
    engines=['yandex','google','duckduckgo','bing'] if backend=='auto' else [backend]
    for engine in engines:
        page=1
        while len(results)<limit and time.monotonic()-started<deadline_seconds:
            remaining=deadline_seconds-(time.monotonic()-started)
            try:
                rows=factory(timeout=max(1,min(4,remaining))).text(query,max_results=min(limit-len(results),30),backend=engine,page=page)
                added=0
                for row in rows:
                    url=row.get('href')
                    if not url or url in seen:continue
                    seen.add(url);results.append(row);added+=1
                    if len(results)>=limit:break
                attempts.append({'backend':engine,'page':page,'status':'leads_found' if rows else 'no_results','count':len(rows),'new_unique_results':added})
                if not added:break
                page+=1
            except Exception as exc:
                attempts.append({'backend':engine,'page':page,'status':'failed','error':type(exc).__name__,'diagnostic':str(exc)[-500:]});break
        if len(results)>=limit:break
    return results,attempts

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--query',required=True)
    parser.add_argument('--limit',type=int,default=8)
    parser.add_argument('--backend',default='auto')
    args=parser.parse_args()
    results,attempts=search(args.query,args.limit,args.backend)
    print(json.dumps(results,ensure_ascii=False))
    print(json.dumps(attempts,ensure_ascii=False),file=sys.stderr)
    if not results and all(x['status']=='failed' for x in attempts):sys.exit(1)
