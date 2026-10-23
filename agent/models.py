"""Official Responses SDK transport, effort policy and atomic usage settlement."""
import json, re, secrets, time, math, asyncio
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlsplit
from . import store as s

class TransportPreflightError(ValueError):
    """Host rejected configuration before a provider request could start."""
    pass

def effort_allowed(depth, effort, phase, reason=''):
    if effort not in ('low','medium','high'): raise ValueError('Reasoning effort is prohibited')
    if effort=='high' and (depth!='deep' or phase not in ('analysis','review') or not reason.strip()):
        raise ValueError('High effort requires deep research and a justified analysis/review')
    if effort=='low' and phase not in ('execution','explanation','selfcheck'):
        raise ValueError('Research decisions require medium or permitted high effort')
    return effort

def read_credentials(path):
    values={}
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        if '=' in line:
            k,v=line.split('=',1);values[k.strip().upper()]=v.strip().strip('"\'')
    url=values.get('API_BASE_URL') or values.get('BASE_URL')
    key=values.get('API_KEY') or values.get('OPENAI_API_KEY')
    model=values.get('MODEL') or values.get('API_MODEL') or values.get('MODEL_NAME')
    if not (url and key and model): raise ValueError('Credential file needs API_BASE_URL, API_KEY and MODEL')
    if model!=s.settings()['model']: raise ValueError('MODEL must match the configured deployment model')
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.port not in (None,443): raise ValueError('Invalid API base URL')
    url=url.rstrip('/')
    if not p.path or p.path=='/': url+='/v1'
    return {'base_url':url,'api_key':key,'model':model,'protocol':'responses'}

def response(profile, instructions, items, tools, effort, cap,on_progress=None,format_schema=None):
    if effort not in ('low','medium','high'):raise ValueError('Prohibited reasoning effort')
    from openai import AsyncOpenAI, DefaultAsyncHttpxClient
    c=s.control()
    try:
        c.public_address(urlsplit(profile['base_url']).hostname)
        secret=c.crypt(profile['secret'],True)
    except Exception as exc:raise TransportPreflightError('Model configuration check failed before request') from exc
    async def exchange():
        client=AsyncOpenAI(api_key=secret,base_url=profile['base_url'],
            timeout=s.settings()['api_timeout_seconds'],max_retries=0,
            http_client=DefaultAsyncHttpxClient(follow_redirects=False,trust_env=False))
        kw={'model':profile['model'],'instructions':instructions,'input':items,'store':False,
            'reasoning':{'effort':effort},'max_output_tokens':cap,'include':['reasoning.encrypted_content']}
        # The model may batch independent calls in one response. The host executes
        # each handler sequentially, so acquisition concurrency stays at one.
        if tools:kw.update(tools=tools,parallel_tool_calls=True)
        elif format_schema:kw['text']={'format':{'type':'json_schema','name':'research_output','schema':format_schema,'strict':True}}
        elif effort!='low':kw['text']={'format':{'type':'json_object'}}
        if tools and any(t.get('type') in ('web_search','web_search_preview') for t in tools):
            kw['include'].append('web_search_call.action.sources')
            if all(t.get('type') in ('web_search','web_search_preview') for t in tools):kw['tool_choice']='required'
        # SSE keeps long synthesis observable and avoids a silent full-body wait.
        # A provider can be silent before headers or between SSE events. Keep
        # cancellation/deadlines observable even then, without resending a call.
        # Reading, cancellation and closing share one event loop and OS thread.
        # Cross-thread client.close() can release a socket FD while its SSL BIO
        # still uses it; SQLite may then reuse that FD and receive TLS bytes.
        events=asyncio.Queue(maxsize=128)
        async def receive():
            try:
                stream=await client.responses.create(**kw,stream=True)
                iterator=stream.__aiter__()
                try:
                    async for item in iterator:await events.put(('event',item))
                finally:
                    try:
                        close_iterator=getattr(iterator,'aclose',None)
                        if close_iterator:await close_iterator()
                    finally:await stream.close()
            except Exception as exc:await events.put(('error',exc))
            finally:
                # An aborted consumer will never drain the queue. Do not block
                # task teardown trying to enqueue a terminal marker in that case.
                if not asyncio.current_task().cancelling():await events.put(('end',None))
        reader=asyncio.create_task(receive(),name='sensys-response-reader')
        completed=None;characters=0
        try:
            while True:
                try:kind,item=await asyncio.wait_for(events.get(),timeout=.5)
                except asyncio.TimeoutError:
                    if on_progress:on_progress('host_heartbeat',characters)
                    continue
                if kind=='end':break
                if kind=='error':raise item
                if item.type in ('response.output_text.delta','response.function_call_arguments.delta'):characters+=len(getattr(item,'delta',''))
                if on_progress:on_progress(item.type,characters)
                if item.type in ('response.completed','response.incomplete','response.failed'):
                    completed=item.response.model_dump(exclude_none=True)
                    break
        finally:
            reader.cancel()
            try:
                with suppress(asyncio.CancelledError):await reader
            finally:await client.close()
        if completed is None:raise ValueError('Provider stream ended without a final response/usage receipt')
        return completed
    return asyncio.run(exchange())

def metrics(out):
    u=out.get('usage');valid=lambda n:type(n) is int and n>=0
    known=isinstance(u,dict) and valid(u.get('input_tokens')) and valid(u.get('output_tokens'))
    u=u if isinstance(u,dict) else {}
    inp=u.get('input_tokens') if known else 0;output=u.get('output_tokens') if known else 0
    cached=u.get('input_tokens_details');reasoning=u.get('output_tokens_details')
    cached=cached.get('cached_tokens',0) if isinstance(cached,dict) else 0
    reasoning=reasoning.get('reasoning_tokens',0) if isinstance(reasoning,dict) else 0
    return {'known':known,'input':inp,'output':output,'cached':min(inp,cached) if valid(cached) else 0,'reasoning':min(output,reasoning) if valid(reasoning) else 0}

def text(out):
    return ''.join(x.get('text','') for item in out.get('output',[]) if item.get('type')=='message' for x in item.get('content',[]) if x.get('type')=='output_text')

def call(job_id,phase,effort,reason,instructions,items,tools=None,cap=None,format_schema=None):
    from .confidentiality import POLICY as DISCLOSURE_POLICY
    # Reapplied outside all history/checkpoint compaction, on every paid call.
    instructions=DISCLOSURE_POLICY+'\n'+instructions+'\n'+DISCLOSURE_POLICY
    j=s.get(job_id);config=json.loads(j['config']);effort_allowed(j['depth'],effort,phase,reason)
    c=s.control();cap=cap or s.settings()['output_tokens_per_call']
    # Local token estimation is a reservation only, never presented as supplier usage.
    import tiktoken
    serialized=json.dumps({'instructions':instructions,'input':items,'tools':tools or [],'output_schema':format_schema},ensure_ascii=False)
    input_bound=math.ceil(len(tiktoken.get_encoding('o200k_base').encode(serialized,disallowed_special=()))*1.25)+2048
    # Hosted search injects supplier-side context not present in local input.
    # Pre-reserve additional retrieval context; actual receipts still settle cost.
    native_reserve=24000 if tools and any(t.get('type') in ('web_search','web_search_preview') for t in tools) else 0
    reserve=input_bound+cap+native_reserve;cid=secrets.token_hex(10);today=c.day();now=time.time()
    with c.store() as d:
        d.execute('BEGIN IMMEDIATE');s.check_key(d,j['key_id'])
        latest=d.execute('SELECT * FROM research_jobs WHERE id=?',(job_id,)).fetchone()
        if latest['cancel_requested']: raise c.Error('Research stop requested.',409)
        if latest['model_calls']>=config['model_calls'] or latest['tokens']+reserve>config['model_tokens']: raise c.Error('Research model budget reached; Retain existing evidence.',429)
        quota=d.execute('SELECT * FROM quotas WHERE key_id=?',(j['key_id'],)).fetchone()
        d.execute('INSERT OR IGNORE INTO quota_days(key_id,day) VALUES(?,?)',(j['key_id'],today))
        daily=d.execute('SELECT * FROM quota_days WHERE key_id=? AND day=?',(j['key_id'],today)).fetchone()
        if not quota or quota['used']+quota['reserved']+reserve>quota['total'] or daily['used']+daily['reserved']+reserve>quota['daily']: raise c.Error('UserTokenQuota cannot reserve this call; Adjustable in the admin console.',429)
        profile=d.execute('SELECT * FROM profiles WHERE id=? AND active=1',(j['profile_id'],)).fetchone()
        if not profile or profile['model']!=s.settings()['model'] or profile['protocol']!='responses':raise c.Error('Model configuration paused or incompatible with research requirements.',409)
        d.execute('UPDATE quotas SET reserved=reserved+? WHERE key_id=?',(reserve,j['key_id']))
        d.execute('UPDATE quota_days SET reserved=reserved+? WHERE key_id=? AND day=?',(reserve,j['key_id'],today))
        d.execute('UPDATE research_jobs SET model_calls=model_calls+1 WHERE id=?',(job_id,))
        d.execute('INSERT INTO research_calls(id,job_id,run,kind,name,effort,stage,started,status,reserved,quota_day,details) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (cid,job_id,j['run'],'model',profile['model'],effort,phase,now,'running',reserve,today,json.dumps({'reason':reason,'output_cap':cap,'input_reservation':input_bound})))
    s.event(job_id,'model_started','The model is'+{'decision':'Plan research','execution':'Execute planned steps','analysis':'Analyze evidence','review':'Review conclusions','explanation':'Explain existing results'}.get(phase,phase),{'effort':effort,'call_id':cid})
    out=None;error=None;error_meta={};interruption=None;start=time.monotonic();last_progress=0
    def progress(kind,characters):
        nonlocal last_progress
        current=s.get(job_id)
        if current['cancel_requested']:raise InterruptedError('Research stop requested, Close the active model stream and preserve acquired materials.')
        if current['started'] and current['elapsed_ms']/1000+time.time()-current['started']>=config['seconds']:
            raise TimeoutError('Task time limit reached, Close the active model stream and preserve acquired materials.')
        if time.monotonic()-last_progress<5:return
        last_progress=time.monotonic()
        with c.store() as d:
            row=d.execute('SELECT details FROM research_calls WHERE id=?',(cid,)).fetchone();details=json.loads(row['details']);details.update(stream_event=kind,stream_output_chars=characters,last_progress=time.time())
            d.execute('UPDATE research_calls SET details=? WHERE id=?',(json.dumps(details),cid))
        if phase in ('analysis','review'):s.update(job_id,stage=('Generating report' if phase=='analysis' else 'Independently reviewing evidence')+' · Received '+str(characters)+' characters')
    try:out=response(dict(profile),instructions,items,tools or [],effort,cap,progress,format_schema)
    except Exception as exc:
        if isinstance(exc,(InterruptedError,TimeoutError)):interruption=exc
        code=getattr(exc,'status_code',None);error=f'Model API call failed({type(exc).__name__}'+(f' / HTTP {code}' if code else '')+'), Task retained, No automatic retries.'
        error_meta={'error_type':type(exc).__name__,'http_status':code}
        if isinstance(exc,TransportPreflightError):error_meta['request_started']=False
        body=getattr(exc,'body',None)
        if isinstance(body,dict):
            detail=body.get('error',body)
            if isinstance(detail,dict):
                secret=c.crypt(profile['secret'],True)
                error_meta['provider_diagnostic']={k:str(detail[k])[:1200].replace(secret,'[redacted]') for k in ('code','type','param','message') if detail.get(k) is not None}
    elapsed=int((time.monotonic()-start)*1000);m=metrics(out or {});used=m['input']+m['output'] if m['known'] else reserve
    if error_meta.get('request_started') is False:
        # Unlike a network failure, this is known to precede all provider IO.
        # Release the reservation; no token consumption can have occurred.
        used=0;m={'known':True,'input':0,'output':0,'cached':0,'reasoning':0}
    if out:
        folder=Path(j['artifact_root'])/'model-receipts';folder.mkdir(parents=True,exist_ok=True);(folder/(cid+'.json')).write_text(json.dumps(out,ensure_ascii=False),encoding='utf-8')
        if out.get('status')=='failed':
            provider_error=out.get('error') or {};code=str(provider_error.get('code','unknown')) if isinstance(provider_error,dict) else 'unknown'
            error_meta={'provider_status':'failed','provider_error_code':code[:100]}
            error='Model provider temporarily unavailable, Materials and usage retained; You can continue later.' if code in ('server_error','rate_limit_exceeded') else 'Provider returned failed Response; Usage retained, No automatic retries.'
    # A timeout/unknown usage may still be billed. Reserve is charged conservatively and labeled.
    with c.store() as d:
        d.execute('BEGIN IMMEDIATE')
        row=d.execute('SELECT * FROM research_calls WHERE id=?',(cid,)).fetchone();details=json.loads(row['details']);details.update(error_meta)
        # Recovery may have conservatively settled a still-returning request.
        # Reconcile its actual receipt; never charge the same reservation twice or
        # release reservations belonging to another active request.
        previous_charge=row['total_tokens'] if row['status']=='interrupted' else 0
        delta=used-previous_charge;release=row['reserved']
        if previous_charge:details['reconciled_interrupted_charge']={'previous':previous_charge,'actual':used,'delta':delta}
        d.execute('UPDATE research_calls SET details=? WHERE id=?',(json.dumps(details),cid))
        d.execute('UPDATE quotas SET reserved=MAX(0,reserved-?),used=used+? WHERE key_id=?',(release,delta,j['key_id']))
        d.execute('UPDATE quota_days SET reserved=MAX(0,reserved-?),used=used+? WHERE key_id=? AND day=?',(release,delta,j['key_id'],today))
        d.execute('UPDATE research_jobs SET tokens=tokens+?,input_tokens=input_tokens+?,output_tokens=output_tokens+?,cached_tokens=cached_tokens+?,reasoning_tokens=reasoning_tokens+? WHERE id=?',(delta,m['input'],m['output'],m['cached'],m['reasoning'],job_id))
        d.execute('UPDATE research_calls SET finished=?,elapsed_ms=?,status=?,input_tokens=?,output_tokens=?,cached_tokens=?,reasoning_tokens=?,total_tokens=?,reserved=0,usage_known=?,response_id=? WHERE id=?',
                  (time.time(),elapsed,'failed' if error else 'succeeded',m['input'],m['output'],m['cached'],m['reasoning'],used,int(m['known']),(out or {}).get('id'),cid))
    s.event(job_id,'model_finished',error or 'Model call completed',{'call_id':cid,'effort':effort,'tokens':used,'usage_known':m['known'],'elapsed_ms':elapsed})
    if m['known'] and used>reserve:s.event(job_id,'reservation_exceeded','Actual provider usage exceeded the reserved input estimate; Settled using actual usage, Subsequent calls check quota again.',{'actual':used,'reserved':reserve})
    if interruption:raise interruption
    if error:raise c.Error(error,502)
    if not m['known']:raise c.Error('The API did not provide verifiableTokenUsage, Conservative usage recorded; execution stopped, Check in the admin console.',502)
    return out

def bootstrap(path):
    c=s.control();cfg=read_credentials(path)
    pid=c.save_profile({'name':'GPT 6.1 Sol · Agent 1.0',**cfg})
    with c.store() as d:profile=dict(d.execute('SELECT * FROM profiles WHERE id=?',(pid,)).fetchone())
    checks=[]
    for mode in ('connect','tool'):
        start=time.monotonic();items=[{'role':'user','content':'Reply exactly OK.' if mode=='connect' else 'Call entry_check with no arguments.'}]
        tools=[] if mode=='connect' else [{'type':'function','name':'entry_check','description':'Read-only check of the bundled research skill.','parameters':{'type':'object','properties':{},'additionalProperties':False},'strict':True}]
        count=1;total=0;ok=False
        try:
            out=response(profile,'Follow the requested check exactly.',items,tools,'low',1024);m=metrics(out);total+=m['input']+m['output']
            if not m['known']:raise ValueError('Provider usage is missing')
            if mode=='tool':
                calls=[x for x in out.get('output',[]) if x.get('type')=='function_call']
                if len(calls)!=1 or calls[0].get('name')!='entry_check':raise ValueError('Tool protocol check failed')
                items+=out['output']+[{'type':'function_call_output','call_id':calls[0]['call_id'],'output':json.dumps({'available':c.SKILL.exists()})},{'role':'user','content':'Reply exactly OK.'}]
                out=response(profile,'Follow the requested check exactly.',items,[],'low',1024);count+=1;m=metrics(out);total+=m['input']+m['output']
            ok=text(out).strip()=='OK' and m['known'];message='Real API round trip passed.' if ok else 'Response or usage failed validation.'
        except Exception as exc:message='Real API test failed: '+type(exc).__name__
        elapsed=int((time.monotonic()-start)*1000)
        with c.store() as d:d.execute('INSERT INTO checks VALUES(?,?,?,?,?,?,?,?,?)',(secrets.token_hex(8),pid,time.time(),int(ok),message,count,total,elapsed,mode))
        checks.append({'mode':mode,'ok':ok,'requests':count,'tokens':total,'elapsed_ms':elapsed,'detail':message})
        if not ok:break
    if len(checks)==2 and all(x['ok'] for x in checks):
        with c.store() as d:d.execute('UPDATE profiles SET active=0');d.execute('UPDATE profiles SET active=1 WHERE id=?',(pid,));c.audit(d,'Enable a testedAgentModel',pid)
    return {'profile_id':pid,'model':cfg['model'],'base_url':cfg['base_url'],'checks':checks,'active':len(checks)==2 and all(x['ok'] for x in checks)}
