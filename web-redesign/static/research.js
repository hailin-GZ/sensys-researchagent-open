const researchStatus=s=>({queued:'Queued',running:'Researching',complete:'Completed',partial:'Partially complete',needs_input:'More information needed',paused:'Paused',cancelled:'Stopped',answered:'Answered'}[s]||s);
const isActive=j=>!!j&&['queued','running'].includes(j.status);
let researchSelection=0,researchPolling=false,pollDelay=2000;
$('.agent-status').textContent='AI assistant';
$('.chat-bottom').insertAdjacentHTML('afterbegin','<div id="research-progress" class="research-progress" role="status"></div>');
$('#send').insertAdjacentHTML('beforebegin',`<label class="depth-control"><span class="sr-only">Research depth</span><select id="research-depth" aria-label="Research depth"><option value="standard">Standard research</option><option value="deep">Deep research</option></select></label>`);
$('.panel-heading').insertAdjacentHTML('beforeend','<select id="delivery-select" aria-label="Select results from this conversation" hidden></select>');
$('#new-study').hidden=true;
$('#export').insertAdjacentHTML('afterend','<button type="button" id="export-package" class="example-link" hidden>Download source evidence package</button>');
function updateResearchControls(){
 const j=state.job,active=isActive(j),pending=isActive(state.turn);
 const stopping=(pending?state.turn:j)?.cancel_requested;
 $('#research-progress').textContent=stopping?'Stopping and saving existing materials…':pending?'Replying…':j?`${researchStatus(j.status)} · ${j.stage} · ${Math.round(j.elapsed_ms/1000)}seconds`:'';
 $('#research-progress').classList.toggle('is-working',(active||pending)&&!stopping);
 const stop=active||pending,b=$('#send');b.dataset.mode=stop?'stop':'send';b.type=stop?'button':'submit';b.classList.toggle('is-stop',stop);b.setAttribute('aria-label',stop?'Stop':'Send question');b.title=stop?'Stop':'Send question';
 b.innerHTML=stop?'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor" stroke="none"/></svg>':icon('send');
 b.disabled=stop?!!stopping:state.sending||!$('#prompt').value.trim();
 $('#research-depth').disabled=pending;$('#export-package').hidden=!state.job;
 $('.agent-status').textContent=pending?'Replying':active?'Researching':'AI assistant';
}
function followupHTML(job){
 let questions=job?.suggestions||[];
 // Legacy reports have no generated questions; never turn a long experiment
 // plan into a misleading execution button. Fresh deliveries supply questions.
 if(!questions.length&&state.example?.progress?.stop_reason)questions=['Continue the current research, Reuse acquired source text and analysis. ','First summarize what the available materials support, and which key evidence is still missing. '];
 return questions.length?`<div class="suggestions followup-suggestions" aria-label="Suggested follow-up questions">${questions.slice(0,3).map(q=>`<button type="button" data-followup="true" data-prompt="${escapeHTML(q)}" ${isActive(state.turn)||isActive(state.job)?'disabled':''}>${escapeHTML(q)}${icon('out')}</button>`).join('')}</div>`:'';
}
function renderResearchMessages(messages){
 const a=messages||state.conversation?.messages||[];
 if(!a.length){resetMessages();return;}
 const latestAssistant=a.findLastIndex(m=>m.role==='assistant');
 $('#messages').innerHTML=a.map((m,i)=>`<div class="message ${m.role==='user'?'user':'assistant'}"><span class="message-label">${m.role==='user'?'You':'Research assistant'}</span>${m.role==='assistant'&&m.report?.result?.support_reviewed?`<p>Research delivered, View the full report and original sources on the left. </p><button type="button" class="message-report-link" data-message-job="${escapeHTML(m.job_id)}">View these results</button>`:`<div class="message-content">${SensysReport.markdown(m.text)}</div>`}${i===latestAssistant?followupHTML(state.conversation?.jobs.find(j=>j.id===m.job_id)):''}</div>`).join('')+(isActive(state.turn)?'<div class="message assistant"><span class="message-label">Research assistant</span><p class="is-working" role="status">Replying…</p></div>':'')+(state.turn?.error?`<div class="message assistant"><p>${escapeHTML(state.turn.error)}</p></div>`:'');
}
async function refreshPoints(){if(!state.authenticated)return;const q=await api('/api/quota');if(state.authenticated)$('#remaining-points').textContent='Remaining '+q.remaining_points.toLocaleString('en-US',{maximumFractionDigits:3})+' credits';}
async function loadHistory(){
 const data=await api('/api/conversations');if(!state.authenticated)return;
 $('#conversation-list').innerHTML=data.conversations.length?data.conversations.map(c=>`<button type="button" class="conversation-item ${state.conversation?.id===c.id?'active':''}" data-conversation="${escapeHTML(c.id)}" ${state.conversation?.id===c.id?'aria-current="true"':''}><strong>${escapeHTML(c.title)}</strong><small>${new Date(c.updated*1000).toLocaleDateString('en-US')} · ${c.job_count?c.job_count+'research turns':'Conversation'}</small></button>`).join(''):'<p class="history-empty">No conversations yet. Start with your idea. </p>';return data.conversations;
}
async function chooseConversation(id,jobId){
 const previousThread=state.conversation?.id,previousScroll=$('#messages').scrollTop;
 const selection=++researchSelection;const chat=await api('/api/conversation?id='+encodeURIComponent(id));
 const research=chat.jobs.filter(j=>j.kind==='research'),j=jobId?research.find(j=>j.id===jobId)||research.at(-1):research.at(-1);
 const bundle=j?await api('/api/job/result?id='+j.id):null;
 if(selection!==researchSelection||!state.authenticated)return;
 if(j&&state.job?.id!==j.id)$('#research-depth').value=j.depth;
 state.conversation=chat;state.job=j||null;state.turn=chat.jobs.filter(j=>j.kind==='dialog').at(-1)||null;
 state.example=bundle;
 state.draft=j?.question||chat.title;$('#chat-title').textContent='Research assistant';
 $('#delivery-select').hidden=!research.length;
 $('#delivery-select').innerHTML=research.map((j,i)=>`<option value="${j.id}">Stage${i+1}turns · ${escapeHTML(j.question.slice(0,22))}</option>`).join('');if(j)$('#delivery-select').value=j.id;
 renderResearchMessages(chat.messages);updateResearchControls();renderResults();
 $('#messages').scrollTop=previousThread===chat.id?previousScroll:$('#messages').scrollHeight;
 if(state.example?.result?.support_reviewed&&state.example.validation?.ok&&['queued','running','paused','cancelled'].includes(j.status))$('#result-status').textContent+=' · Previous reviewed result';
 await loadHistory();
}
async function chooseResearch(id){const j=await api('/api/job/status?id='+encodeURIComponent(id));return chooseConversation(j.thread_id,id);}
async function restoreResearch(){try{await refreshPoints();const chats=await loadHistory();if(chats?.length)await chooseConversation(chats[0].id);}catch(e){toast(e.message);}}
$('#conversation-list').onclick=e=>{const b=e.target.closest('[data-conversation]');if(b){toggleHistory(false);chooseConversation(b.dataset.conversation).catch(e=>toast(e.message));}};
$('#delivery-select').onchange=e=>chooseConversation(state.conversation.id,e.target.value).catch(e=>toast(e.message));
$('#messages').addEventListener('click',e=>{const b=e.target.closest('[data-message-job]');if(b&&state.conversation)chooseConversation(state.conversation.id,b.dataset.messageJob).catch(e=>toast(e.message));});
let historyMotion=null,historyOpen=false;
function toggleHistory(open,restore=false){const panel=$('#chat-history');historyOpen=open;historyMotion?.cancel();$('#history-toggle').setAttribute('aria-expanded',String(open));const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;if(open){panel.hidden=false;if(!reduced)historyMotion=panel.animate([{transform:'translateX(-18px)',opacity:.4},{transform:'translateX(0)',opacity:1}],{duration:220,easing:'cubic-bezier(.16,1,.3,1)'});loadHistory().catch(e=>toast(e.message));}else if(!panel.hidden&&!reduced){historyMotion=panel.animate([{transform:'translateX(0)',opacity:1},{transform:'translateX(-12px)',opacity:0}],{duration:140,easing:'ease-in'});historyMotion.onfinish=()=>{if(!historyOpen)panel.hidden=true;};}else panel.hidden=true;if(restore)$('#history-toggle').focus();}
$('#history-toggle').onclick=()=>toggleHistory(!historyOpen);$('#history-close').onclick=()=>toggleHistory(false,true);
document.addEventListener('pointerdown',e=>{if(!$('#chat-history').hidden&&!e.target.closest('#chat-history,#history-toggle'))toggleHistory(false);});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!$('#chat-history').hidden){toggleHistory(false,true);e.preventDefault();}});
$('#rail-new').onclick=()=>{toggleHistory(false);$('#new-study').click();};
$('#new-study').addEventListener('click',()=>{if(!state.job&&!state.conversation){researchSelection++;state.turn=null;$('#delivery-select').hidden=true;$('#chat-title').textContent='Research assistant';updateResearchControls();if(!matchMedia('(prefers-reduced-motion: reduce)').matches)$('#messages').animate([{opacity:.4,transform:'translateY(6px)'},{opacity:1,transform:'translateY(0)'}],{duration:180,easing:'ease-out'});loadHistory().catch(e=>toast(e.message));}});
async function uploadResearchFiles(){const ids=[];for(const f of state.files){const response=await fetch('/api/upload',{method:'POST',headers:{'Content-Type':'application/octet-stream','X-File-Name':encodeURIComponent(f.name)},body:f});const out=await response.json();if(!response.ok)throw Error(out.error||'Attachment upload failed');ids.push(out.id);}return ids;}
async function submitResearch(text){
 if(isActive(state.turn))throw Error('The previous message is still being processed, Send later. ');
 const uploads=await uploadResearchFiles();
 const turn=await api('/api/message',{question:text,research_depth:$('#research-depth').value,conversation_id:state.conversation?.id,uploads});
 state.files=[];renderAttachments();await chooseConversation(turn.thread_id);await refreshPoints();pollDelay=1500;
}
$('#send').addEventListener('click',async e=>{if($('#send').dataset.mode!=='stop')return;e.preventDefault();const j=isActive(state.turn)?state.turn:state.job;if(!j)return;$('#send').disabled=true;try{await api('/api/job/action',{id:j.id,action:'cancel'});if(state.conversation)await chooseConversation(state.conversation.id);}catch(e){toast(e.message);updateResearchControls();}});
$('#export-package').onclick=()=>{if(state.job){const a=document.createElement('a');a.href='/api/job/package?id='+state.job.id;a.download='Research source evidence package.zip';a.click();}};
async function pollResearch(){
 if(!state.authenticated||researchPolling||document.hidden){setTimeout(pollResearch,5000);return;}
 const active=[state.turn,state.job].filter(isActive);if(!active.length){setTimeout(pollResearch,2000);return;}
 researchPolling=true;const selection=researchSelection;
 try{
  const updates=await Promise.all(active.map(j=>api('/api/job/status?id='+j.id)));
  if(selection===researchSelection&&state.authenticated){
   const changed=updates.some((j,i)=>j.status!==active[i].status||j.kind!==active[i].kind||j.run!==active[i].run);
   for(const j of updates){if(state.turn?.id===j.id)Object.assign(state.turn,j);if(state.job?.id===j.id)Object.assign(state.job,j);}
   if(changed){const promoted=updates.some(j=>j.kind==='research'&&state.turn?.id===j.id);await chooseConversation(state.conversation.id,promoted?undefined:state.job?.id);await refreshPoints();$('#messages').scrollTop=$('#messages').scrollHeight;}
   else {updateResearchControls();if(state.job){const before=$('#result-body').scrollTop,live=await api('/api/job/result?id='+state.job.id);if(selection===researchSelection&&(live.progress?.version!==state.example?.progress?.version||live.publication?.published_at!==state.example?.publication?.published_at)){state.example=live;renderResults();$('#result-body').scrollTop=before;}}}
  }
  pollDelay=isActive(state.turn)?1500:5000;
 }catch(e){pollDelay=Math.min(30000,pollDelay*2);toast(e.message);}finally{researchPolling=false;setTimeout(pollResearch,pollDelay);}
}
setTimeout(pollResearch,1500);
document.addEventListener('visibilitychange',()=>document.body.classList.toggle('page-idle',document.hidden));
setInterval(()=>{if(state.authenticated&&!document.hidden)refreshPoints().catch(()=>{});},60000);
