"""Fixed, read-only public API adapters. All bytes are archived before use."""
import json,re,secrets
from urllib.parse import urlencode,quote

ROUTES=('worldbank','dbnomics_search','gdelt','github_search','github_repo','github_issues','stackexchange','stackexchange_answers','arxiv','appstore_reviews','wikidata')
HELP='Additional public routes: worldbank (country/indicator, e.g. CN/SP.POP.TOTL; latest non-null observations), dbnomics_search (terms, dataset discovery metadata only), gdelt (news terms; last 30 days links only), github_search (repository query), github_repo/github_issues (owner/repo; public repository metadata or issues), stackexchange (Stack Overflow query with body), stackexchange_answers (actual numeric question ID), arxiv (terms; bibliographic metadata/abstracts only), appstore_reviews (actual numeric US App Store app ID; first page only), wikidata (entity name; identity leads only). Public samples, not exhaustive datasets; rate limits and blocked routes remain failures.'

def endpoint(route,target,limit):
    if route not in ROUTES:raise ValueError('Unknown public data route')
    if not isinstance(target,str) or not 1<=len(target)<=300 or type(limit) is not int or not 1<=limit<=30:raise ValueError('Invalid bounded public API arguments')
    if route=='worldbank':
        if not re.fullmatch(r'[A-Za-z]{2,3}/[A-Za-z0-9_.]{1,100}',target):raise ValueError('Use country/indicator')
        country,indicator=target.split('/')
        return 'https://api.worldbank.org/v2/country/'+country+'/indicator/'+indicator+'?'+urlencode({'format':'json','mrv':limit,'per_page':limit}), 'Official indicator observations; units, dates, missing values and revisions require interpretation, not a direct market size.'
    if route=='dbnomics_search':return 'https://api.db.nomics.world/v22/search?'+urlencode({'q':target,'limit':limit}), 'Dataset discovery metadata only; acquire identified observations before asserting values.'
    if route=='gdelt':return 'https://api.gdeltproject.org/api/v2/doc/doc?'+urlencode({'query':target,'mode':'artlist','format':'json','maxrecords':limit,'timespan':'30d','sort':'datedesc'}), 'News index links/titles only, last 30 days, not article bodies or representative sentiment.'
    if route=='github_search':return 'https://api.github.com/search/repositories?'+urlencode({'q':target,'per_page':limit}), 'Public repository metadata, not verified product capability or adoption.'
    if route in ('github_repo','github_issues'):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}',target):raise ValueError('Use owner/repo')
        return 'https://api.github.com/repos/'+target+('/issues?'+urlencode({'state':'all','per_page':limit}) if route=='github_issues' else ''), 'Public repository/issue sample only. Issues may include pull requests, duplicates and unsupported allegations; no private repositories.'
    if route in ('stackexchange','stackexchange_answers'):
        if route=='stackexchange_answers' and not re.fullmatch(r'\d{1,12}',target):raise ValueError('Use an actual numeric question ID')
        return 'https://api.stackexchange.com/2.3/'+('search/advanced?'+urlencode({'q':target,'site':'stackoverflow','pagesize':limit,'filter':'withbody','sort':'relevance'}) if route=='stackexchange' else 'questions/'+target+'/answers?'+urlencode({'site':'stackoverflow','pagesize':limit,'filter':'withbody'})), 'Stack Overflow bounded question/answer sample, not representative user demand.'
    if route=='arxiv':return 'https://export.arxiv.org/api/query?'+urlencode({'search_query':'all:'+target,'start':0,'max_results':limit}), 'Bibliographic metadata and abstracts only, not paper full text or reviewed research outcomes.'
    if route=='appstore_reviews':
        if not re.fullmatch(r'\d{5,15}',target):raise ValueError('Use actual numeric App Store app ID')
        return 'https://itunes.apple.com/us/rss/customerreviews/page=1/id='+target+'/sortby=mostrecent/json', 'US locale, first page newest-first public reviews only; no account analytics or representativeness.'
    return 'https://www.wikidata.org/w/api.php?'+urlencode({'action':'wbsearchentities','search':target,'language':'en','format':'json','limit':limit}), 'Entity search leads only; resolve identity and independently confirm company facts.'

def rows(route,raw):
    if route=='arxiv':
        import xml.etree.ElementTree as ET
        root=ET.fromstring(raw);return [{'title':x.findtext('{http://www.w3.org/2005/Atom}title'),'url':x.findtext('{http://www.w3.org/2005/Atom}id'),'summary':x.findtext('{http://www.w3.org/2005/Atom}summary')} for x in root.findall('{http://www.w3.org/2005/Atom}entry')]
    d=json.loads(raw)
    if isinstance(d,dict) and ('error' in d or 'error_id' in d or 'errors' in d or (route.startswith('github') and 'message' in d)):raise ValueError('Public API application error')
    if route=='worldbank':
        if not isinstance(d,list) or len(d)!=2 or not isinstance(d[1],list):raise ValueError('Invalid World Bank payload')
        return [x for x in d[1] if x.get('value') is not None]
    if route=='github_repo':return [d] if isinstance(d,dict) and d.get('full_name') else []
    if route=='github_issues':return d if isinstance(d,list) else []
    if route in ('github_search','stackexchange','stackexchange_answers'):return d.get('items',[])
    if route=='dbnomics_search':return d.get('results',{}).get('docs',[])
    if route=='gdelt':return d.get('articles',[])
    if route=='appstore_reviews':
        entries=d.get('feed',{}).get('entry',[])
        return [x for x in (entries if isinstance(entries,list) else [entries]) if 'content' in x]
    if route=='wikidata':return d.get('search',[])
    raise ValueError('Unrecognized schema')

def acquire(ex,route,target,limit):
    from .tools import r,annotate_source,source_card
    url,scope=endpoint(route,target,limit)
    ex.check_running()
    if r.depth.status(ex.root)['remaining']['captures']<=0:raise ValueError('Capture allowance exhausted')
    # Reserve before network I/O, including failed calls. Never retries paid calls.
    with r.depth.task_lock(ex.root):r.depth.reserve(ex.root,'captures')
    folder=ex.root/'external-originals'/secrets.token_hex(8);folder.mkdir(parents=True,exist_ok=True)
    raw=b'';http=None;final=url;error=None;items=[]
    try:
        raw,final,http,ctype=r.download(url,timeout=18,max_bytes=5_000_000)
        ex.check_running()
        if http!=200:raise ValueError('Public endpoint returned HTTP '+str(http))
        items=rows(route,raw)
        if not isinstance(items,list):raise ValueError('Invalid sample schema')
    except Exception as exc:
        error=exc
    suffix='.xml' if route=='arxiv' else '.json' if raw.lstrip().startswith((b'{',b'[')) else '.txt'
    original=folder/('original'+suffix);original.write_bytes(raw);path=original
    if route=='arxiv' and not error:
        # The general file parser does not parse Atom XML. Preserve original
        # bytes separately and expose only faithfully extracted entry fields.
        path=folder/'atom-entries.json';path.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
    record=r.capture(ex.root,file=str(path),source_url=final,category='user_voices' if route in ('github_issues','stackexchange','stackexchange_answers','appstore_reviews') else 'research',method='registered_public_'+route,max_images=0,scope='excerpt',reserved=True)
    updates={'title':route+' · '+target,'requested_url':url,'final_url':final,'http_status':http,'sample_count':min(len(items),limit),'scope_warning':scope,'warnings':record['warnings']+[scope]}
    if path!=original:
        import hashlib
        raw_copy=ex.root/'sources'/record['source_id']/'original-response.xml';raw_copy.write_bytes(raw)
        updates.update(artifacts={**record['artifacts'],'original_response':raw_copy.relative_to(ex.root).as_posix()},original_response_sha256=hashlib.sha256(raw).hexdigest())
    if error:updates.update(status='login_required' if http==401 else 'network_error',diagnostic=str(error)[:600],warnings=updates['warnings']+['No usable evidence from this failed request.'])
    elif not items:updates.update(status='shell_only',warnings=updates['warnings']+['Zero entries returned; no evidence obtained.'])
    record=annotate_source(ex.root,record,updates)
    if isinstance(error,(InterruptedError,TimeoutError)):raise error
    card=source_card(record);card['scope_warning']=scope
    if not error:card['discovery_records']=[{k:x.get(k) for k in ('id','title','url','html_url','full_name','name','date','value','label','description','question_id','answer_id')} for x in items[:limit] if isinstance(x,dict)]
    return card
