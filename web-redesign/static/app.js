const $ = (selector) => document.querySelector(selector);
const state = { authenticated: false, example: null, tab: 'overview', files: [], draft: '', sending: false };
const kinds = { fact: 'Fact', source_opinion: 'Source opinion', inference: 'Inference', hypothesis: 'Hypothesis to validate', unknown: 'Unknown' };
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' })[c]);
const icon = (name) => `<svg aria-hidden="true"><use href="#icon-${name}"/></svg>`;
let toastTimer;
function toast(text) { $('#toast').textContent = text; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').hidden = true, 4500); }
async function api(path, body) {
  const response = await fetch(path, { method: body ? 'POST' : 'GET', headers: body ? { 'Content-Type':'application/json' } : {}, body: body ? JSON.stringify(body) : undefined, credentials: 'same-origin' });
  let data;
  try { data = await response.json(); }
  catch { throw new Error(response.status >= 500 ? 'Service temporarily unavailable, Retry later. ' : 'Unexpected server response, Refresh and try again. '); }
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login') lockWorkspace();
    throw new Error(data.error || 'Request failed, Try again. ');
  }
  return data;
}
function showAccess(message = '') {
  $('#access-error').textContent = message;
  if (!$('#access-dialog').open) $('#access-dialog').showModal();
  $('#access-key').focus();
}
function lockWorkspace() {
  state.authenticated = false; state.example = null; state.job = null; state.turn=null; state.draft = ''; state.files = [];
  $('#workspace').hidden = true; $('#prompt').value = ''; $('#send').disabled = true;
  renderAttachments(); resetMessages(); renderResults();
  if(typeof updateResearchControls==='function'){updateResearchControls();$('#conversation-list').innerHTML='';state.conversation=null;researchSelection++;}
  window.scrollTo({ top:0, behavior:'instant' });
  showAccess('Access permission expired, Enter the access key again. ');
}
function enterWorkspace() {
  $('#workspace').hidden = false;
  $('#workspace').scrollIntoView({ behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant':'smooth', block:'start' });
  $('#access-dialog').close(); $('#access-key').value = '';
  if (typeof restoreResearch === 'function') restoreResearch();
}
$('#start').addEventListener('click', async () => {
  try { state.authenticated = (await api('/api/session')).authenticated; state.authenticated ? enterWorkspace() : showAccess(); }
  catch { toast('Cannot connect to the local service, Check that the service is running. '); }
});
$('.dialog-close').addEventListener('click', () => $('#access-dialog').close());
$('#access-dialog').addEventListener('close', () => $('#access-key').value = '');
$('#access-form').addEventListener('submit', async (event) => {
  event.preventDefault(); $('#verify').disabled = true; $('#verify').textContent = 'Verifying…'; $('#access-error').textContent = '';
  try { await api('/api/login', { key:$('#access-key').value }); state.authenticated = true; enterWorkspace(); }
  catch (error) { $('#access-error').textContent = error.message; }
  finally { $('#verify').disabled = false; $('#verify').textContent = 'Verify and enter'; }
});
$('#logout').addEventListener('click', async () => {
  try { await api('/api/logout', {}); lockWorkspace(); $('#access-dialog').close(); toast('Signed out. '); }
  catch (error) { toast(error.message); }
});
function resetMessages() {
  $('#messages').innerHTML = `<div class="message assistant"><span class="message-label">Research assistant</span><p>Hello. What would you like to explore?</p><p>Tell me about your product idea, or the group of people you want to understand. Let us start here. </p><div class="suggestions"><span class="suggestion-title">You can also start here</span><button type="button" data-prompt="Help me identify an unmet need in an everyday situation. ">${icon('spark')}<span>Discover real needs</span>${icon('out')}</button><button type="button" data-prompt="Help me compare the positioning of similar products, Pricing and user feedback. ">${icon('document')}<span>Compare products and alternatives</span>${icon('out')}</button></div></div>`;
}
function emptyState() {
  const copy = { overview:['Let good questions lead to new discoveries. ','Start with a product idea, a target group, or a specific situation. Connect need signals with evidence, then choose the next step. '], needs:['See the context, See needs that remain unmet. ','User experience, Usage barriers and need signals will be organized here; Leave room to validate every judgment. '], competitors:['Find differences between products, Meaningful differences. ','Compare positioning from the same perspective, Features and alternatives, Keep a source for each judgment. '], evidence:['Make every judgment, traceable to its source. ','Original materials, User quotations and acquisition records will appear here, Traceable evidence for research. '] }[state.tab];
  return `<div class="empty-state"><div class="research-intro"><div class="intro-copy"><h4>${copy[0]}</h4><p>${copy[1]}</p></div><div class="research-lens" aria-hidden="true"><i></i><i></i><i></i><span>${icon('spark')}</span></div></div><div class="research-guide"><h5>Your findings come together here</h5><div class="guide-row"><span class="guide-icon">${icon('spark')}</span><div><strong>Needs and opportunities</strong><p>Understand user context and identify directions worth validating</p></div></div><div class="guide-row"><span class="guide-icon">${icon('document')}</span><div><strong>Competitors and alternatives</strong><p>Compare existing alternatives to see what makes a product different</p></div></div><div class="guide-row"><span class="guide-icon">${icon('out')}</span><div><strong>Evidence and sources</strong><p>Connect conclusions to quotations and traceable sources</p></div></div></div></div>`;
}
function findingHTML(finding) {
  return `<article class="finding"><span class="kind ${escapeHTML(finding.kind)}">${escapeHTML(kinds[finding.kind])}</span><p>${escapeHTML(finding.statement)}</p>${(finding.evidence_refs || []).map(id => `<button class="evidence-button" data-evidence="${escapeHTML(id)}">View evidence ${escapeHTML(id)}</button>`).join('')}${finding.limitations?.length ? `<details><summary>Scope and limitations</summary><ul>${finding.limitations.map(x => `<li>${escapeHTML(x)}</li>`).join('')}</ul></details>` : ''}</article>`;
}
function safeURL(value) { try { const u = new URL(value); return ['https:','http:'].includes(u.protocol) ? u.href : null; } catch { return null; } }
function renderResults() {
  const tabs=SensysReport.tabs(state.example);
  if(!tabs.some(t=>t.id===state.tab))state.tab='overview';
  $('.tablist').innerHTML=tabs.map(t=>`<button role="tab" id="tab-${t.id}" aria-selected="${t.id===state.tab}" tabindex="${t.id===state.tab?0:-1}" aria-controls="result-body" data-tab="${t.id}">${escapeHTML(t.title)}</button>`).join('');
  $('#result-body').setAttribute('aria-labelledby','tab-'+state.tab);
  $('#export').disabled = !state.example;
  $('#result-status').textContent = state.job ? `${state.job.depth==='deep'?'Deep':'Standard'}Research · ${researchStatus(state.job.status)} · ${state.job.stage}` : state.example ? 'Historical examples · Partially complete · Not from this live research task' : 'Waiting for a new research question';
  if (!state.example) {
    $('#result-body').innerHTML = state.job ? `<div class="report-banner">${escapeHTML(state.job.stage)} · ${researchStatus(state.job.status)}</div><h4 class="report-title">Your research question</h4><p class="report-intro">${escapeHTML(state.job.question)}</p><p class="report-intro">Archiving materials and evidence. Results are displayed after citation and conclusion review. </p>${state.job.error?'<p class="report-banner">'+escapeHTML(state.job.error)+'</p>':''}` : emptyState();
    return;
  }
  $('#result-body').innerHTML=SensysReport.render(state.example,state.tab,state.job?.id);
}
function selectTab(name) {
  state.tab = name;
  document.querySelectorAll('[role=tab]').forEach(button => { const active = button.dataset.tab === name; button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; });
  $('#result-body').setAttribute('aria-labelledby', `tab-${name}`); renderResults(); $('#result-body').scrollTop = 0;
}
$('.tablist').addEventListener('click', e => { if (e.target.dataset.tab) selectTab(e.target.dataset.tab); });
$('.tablist').addEventListener('keydown', e => {
  const tabs = [...document.querySelectorAll('[role=tab]')]; const index = tabs.indexOf(document.activeElement);
  if (index < 0 || !['ArrowRight','ArrowLeft','Home','End'].includes(e.key)) return;
  e.preventDefault(); const next = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (index + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
  const name=tabs[next].dataset.tab;selectTab(name);document.getElementById('tab-'+name)?.focus();
});
document.addEventListener('click', async e => {
  const target = e.target.closest('button'); if (!target) return;
  if (target.dataset.prompt) { $('#prompt').value = target.dataset.prompt; updateResearchControls(); $('#prompt').focus(); if(target.dataset.followup==='true'&&!isActive(state.turn))$('#chat-form').requestSubmit(); }
  if (target.dataset.evidence) { selectTab('evidence'); document.getElementById(`evidence-${target.dataset.evidence}`)?.scrollIntoView({ block:'start', behavior:'smooth' }); }
});
$('#prompt').addEventListener('input', () => updateResearchControls());
$('#prompt').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if ($('#prompt').value.trim()) $('#chat-form').requestSubmit(); } });
$('#chat-form').addEventListener('submit', async e => {
  e.preventDefault(); const text = $('#prompt').value.trim(); if (!text || state.sending) return;
  state.sending = true; $('#send').disabled = true; $('#prompt').disabled = true;
  try {
    if (!(await api('/api/session')).authenticated) { lockWorkspace(); return; }
    await submitResearch(text);
    $('#prompt').value = ''; renderResults(); $('#messages').scrollTop = $('#messages').scrollHeight;
  } catch (error) { toast(error.message || 'Cannot connect to the service, Question not sent yet. '); }
  finally { state.sending = false; $('#prompt').disabled = false; updateResearchControls(); }
});
$('#new-study').addEventListener('click', () => {
  if (($('#prompt').value.trim() || state.files.length) && !confirm('Discard the unsent question and attachments, Start a new chat?')) return;
  state.job = null; state.turn=null; state.conversation=null; state.example = null; state.draft = ''; state.files = []; $('#prompt').value = ''; $('#send').disabled = true; resetMessages(); renderAttachments(); selectTab('overview'); $('#prompt').focus(); if(typeof updateResearchControls==='function')updateResearchControls();
});
$('#attach').addEventListener('click', () => $('#files').click());
$('#files').addEventListener('change', () => {
  const files = [...$('#files').files];
  if (files.some(x => x.size > 20 * 1024 * 1024) || files.length + state.files.length > 8 || [...files,...state.files].reduce((n,f)=>n+f.size,0)>30*1024*1024) { toast('At most8attachments, Each must not exceed20MB, Combined total must not exceed30MB. '); $('#files').value = ''; return; }
  state.files.push(...files); $('#files').value = ''; renderAttachments(); toast('Material selected on the page; Not uploaded or analyzed yet. ');
});
function renderAttachments() {
  $('#attachments').innerHTML = state.files.map((f,i) => `<div class="attachment"><span>${escapeHTML(f.name)}</span><button type="button" data-remove="${i}" aria-label="Remove ${escapeHTML(f.name)}">${icon('close')}</button></div>`).join('');
}
$('#attachments').addEventListener('click', e => { const b = e.target.closest('[data-remove]'); if (b) { state.files.splice(Number(b.dataset.remove),1); renderAttachments(); } });
$('#export').addEventListener('click', async () => {
  try { if (!(await api('/api/session')).authenticated) { lockWorkspace(); return; } }
  catch { toast('Cannot connect to the service, No record exported. '); return; }
  if (!state.example) return;
  const a = document.createElement('a'); a.href = state.job ? '/api/job/export?id='+state.job.id : '/api/export'; a.download = 'Market research record.json'; a.click();
});
// Recheck permission while an already-open page is in use.
setInterval(async () => { if (!state.authenticated) return; try { if (!(await api('/api/session')).authenticated) lockWorkspace(); } catch { /* Next protected action reports network failure. */ } }, 15000);
resetMessages(); renderResults();

