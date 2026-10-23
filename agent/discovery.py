"""Native grounded discovery; only real hosted citations become research leads."""
import json,time
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from . import store as s,models

def url_key(url):
    p=urlsplit(url)
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode([(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_')]),''))

def search(ex,query,limit):
    from .tools import r
    limit=r.depth.capped(ex.root,'results_per_query',limit)
    key=r.sha(json.dumps(['native_web_search_v1',query,limit],ensure_ascii=False).encode())
    records=r.read_json(ex.root/'discoveries.json')
    for old in reversed(records):
        if old.get('cache_key')==key and old.get('status')=='leads_found' and r.age_seconds(old['retrieved_at'])<3600:
            return {**old,'reused':True}
    r.depth.reserve(ex.root,'search_queries')
    prompt='''Use exactly one focused hosted web search for the supplied query, not an entire investigation. Return a JSON object {"results":[{"url","title","snippet"}]}, using ONLY URLs actually returned by hosted search and citation annotations. Prefer relevant primary originals and original customer experiences; exclude generic SEO portals, fake registry sites, irrelevant patents and duplicate reposts. Respect exact company-name disambiguation. Up to the requested limit, but fewer real results are better than invented or unrelated links. Snippets are discovery leads, never verified original quotations or a final report. No private context disclosure.'''
    out=models.call(ex.job_id,'execution','medium','',prompt,[{'role':'user','content':json.dumps({'query':query,'limit':limit},ensure_ascii=False)}],tools=[{'type':'web_search','search_context_size':'low','user_location':{'type':'approximate'}}],cap=4096)
    calls=[x for x in out.get('output',[]) if x.get('type')=='web_search_call']
    if out.get('status')!='completed' or not calls:raise ValueError('No completed native web search receipt; cannot treat model memory as search')
    actual={}
    for call in calls:
        for source in call.get('action',{}).get('sources',[]):
            if source.get('url'):actual[url_key(source['url'])]=source
    for message in out.get('output',[]):
        for content in message.get('content',[]):
            for annotation in content.get('annotations',[]):
                if annotation.get('type')=='url_citation':actual[url_key(annotation['url'])]=annotation
    try:proposed=json.loads(models.text(out)).get('results',[])
    except (ValueError,TypeError,AttributeError):proposed=[]
    rows=[];seen=set()
    for candidate in proposed:
        if not isinstance(candidate,dict) or not isinstance(candidate.get('url'),str):continue
        url=url_key(candidate['url'])
        if url not in actual or url in seen:continue
        try:r.public_url(url)
        except ValueError:continue
        seen.add(url);rows.append({'url':url,'title':actual[url].get('title') or candidate.get('title'),'snippet':candidate.get('snippet'),'scope':'hosted_search_lead_original_body_not_verified'})
    # A prose answer is not parsed into invented search cards. Actual source
    # records are still usable leads even if the provider omitted JSON formatting.
    for url,source in actual.items():
        if url in seen:continue
        try:r.public_url(url)
        except ValueError:continue
        seen.add(url);rows.append({'url':url,'title':source.get('title') or url,'snippet':'','scope':'hosted_search_lead_original_body_not_verified'})
    rows=rows[:limit]
    item={'query':query,'provider':'responses_native_web_search','backend':'native','retrieved_at':r.now(),'results':rows,'effective_limit':limit,'status':'leads_found' if rows else 'no_results','response_id':out.get('id'),'native_calls':len(calls),'cache_key':key,'results_sha256':r.sha(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()),'scope_warning':'Actual native web-search receipts and source clues; Search snippets are not verified original text.'}
    with r.depth.task_lock(ex.root):
        records=r.read_json(ex.root/'discoveries.json');records.append(item);r.write_json(ex.root/'discoveries.json',records)
    return item
