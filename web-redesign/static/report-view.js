/* Shared report presentation: administrators see the same delivery as users. */
window.SensysReport=(()=>{
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const kinds={fact:'Fact',source_opinion:'Source opinion',inference:'Inference',hypothesis:'Hypothesis to validate',unknown:'Unknown'};
 const list=(title,a)=>a?.length?`<h5 class="report-section-title">${title}</h5><ul class="simple-list">${a.map(x=>`<li>${esc(typeof x==='string'?x:JSON.stringify(x))}</li>`).join('')}</ul>`:'';
 // Deliberately small, HTML-free Markdown presentation. Everything is escaped;
 // URLs are allowlisted rather than interpolated from model-produced HTML.
 function inline(text){
  const pattern=/(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^\s)]+\))/g;
  let html='',last=0;
  for(const match of text.matchAll(pattern)){
   html+=esc(text.slice(last,match.index));const token=match[0];last=match.index+token.length;
   if(token.startsWith('`'))html+='<code>'+esc(token.slice(1,-1))+'</code>';
   else if(token.startsWith('**'))html+='<strong>'+esc(token.slice(2,-2))+'</strong>';
   else{const link=/^\[([^\]]+)\]\((.+)\)$/.exec(token);let url='';try{const u=new URL(link[2]);if(['http:','https:'].includes(u.protocol)&&!u.username&&!u.password)url=u.href}catch{}html+=url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(link[1])}</a>`:esc(token);}
  }
  return html+esc(text.slice(last));
 }
 function markdown(text){
  const lines=String(text??'').replace(/\r\n/g,'\n').split('\n');let html='',i=0;
  while(i<lines.length){
   const line=lines[i];if(!line.trim()){i++;continue;}
   if(line.startsWith('```')){let code=[];i++;while(i<lines.length&&!lines[i].startsWith('```'))code.push(lines[i++]);i++;html+='<pre><code>'+esc(code.join('\n'))+'</code></pre>';continue;}
   const heading=/^#{1,6}\s+(.+)$/.exec(line);
   if(heading){html+='<h4>'+inline(heading[1])+'</h4>';i++;continue;}
   if(line.includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[i+1])){
    const cells=row=>row.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(x=>x.trim());
    const headers=cells(line);html+='<div class="markdown-table"><table><thead><tr>'+headers.map(x=>'<th>'+inline(x)+'</th>').join('')+'</tr></thead><tbody>';i+=2;
    while(i<lines.length&&lines[i].trim()&&lines[i].includes('|')){const row=cells(lines[i++]);html+='<tr>'+headers.map((_,n)=>'<td>'+inline(row[n]||'')+'</td>').join('')+'</tr>';}
    html+='</tbody></table></div>';continue;
   }
   if(/^\s*(?:[-*]|\d+\.)\s+/.test(line)){
    const ordered=/^\s*\d+\./.test(line),tag=ordered?'ol':'ul';html+='<'+tag+'>';
    while(i<lines.length&&new RegExp(ordered?'^\\s*\\d+\\.\\s+':'^\\s*[-*]\\s+').test(lines[i]))html+='<li>'+inline(lines[i++].replace(/^\s*(?:[-*]|\d+\.)\s+/,''))+'</li>';
    html+='</'+tag+'>';continue;
   }
   if(line.startsWith('> ')){html+='<blockquote>'+inline(line.slice(2))+'</blockquote>';i++;continue;}
   let para=[];while(i<lines.length&&lines[i].trim()&&!/^(?:#{1,6}\s|```|> |\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])){if(para.length&&lines[i].includes('|')&&i+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[i+1]))break;para.push(inline(lines[i++]));}
   html+='<p>'+para.join('<br>')+'</p>';
  }
  return html;
 }
 function tabs(bundle){
  const r=bundle?.result;
  const live=bundle?.progress;
  if(live&&(!r?.support_reviewed||!bundle.validation?.ok))return [{id:'overview',title:'Research overview'},{id:'work',title:'Stage ledger'},{id:'evidence',title:'Source materials'}];
  if(!r)return [{id:'overview',title:'Research overview'}];
  const modules=Array.isArray(r.modules)?r.modules.filter(m=>/^[a-z][a-z0-9_-]{0,39}$/.test(m.module_id)&&!['overview','evidence','needs','competitors'].includes(m.module_id)):null;
  return [{id:'overview',title:'Research overview'},...(modules?modules.map(m=>({id:m.module_id,title:m.title})): [{id:'needs',title:'Needs and opportunities'},{id:'competitors',title:'Competitive research'}]),...(live&&live.run>Number(bundle.publication?.run||live.run)?[{id:'work',title:'Progress this turn'}]:[]),{id:'evidence',title:'Evidence materials'}];
 }
 function sourceHTML(s,job){
  let url='';try{const u=new URL(s.final_url||s.source_url);if(['http:','https:'].includes(u.protocol)&&!u.username&&!u.password)url=u.href}catch{}
  const artifact=s.artifacts?.markdown,readable=['complete_body','partial_body','snippet_only','supplied_text','structured_data'].includes(s.status);
  const statuses={complete_body:'Full text',partial_body:'Partial text',snippet_only:'Abstract materials',supplied_text:'Text supplied by the user',structured_data:'Structured materials',image_only:'Original images · Content has not been read',login_required:'Source authorization required',network_error:'Connection failed',not_found:'Not found',shell_only:'Full text not obtained',parse_error:'Parsing failed'};
  return `<article class="source-row"><span class="kind">${esc(s.source_id)} · ${esc(statuses[s.status]||s.status)}</span><p>${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.title==='failed.txt'?url:s.title||url)}</a>`:esc(s.title||'Archived materials')}</p>${artifact&&job?`<a class="source-download" href="/api/artifact?id=${encodeURIComponent(job)}&path=${encodeURIComponent(artifact)}" download>${readable?'Download archived source':'Download acquisition records'}</a>`:''}</article>`;
 }
 function liveHTML(bundle,tab,job){
  const p=bundle.progress,counts=p.counts;
  const notice='<div class="report-banner draft-banner">Stage materials · Conclusion review is not complete. Source text and unreviewed analysis saved, Cannot be treated as a final conclusion. </div>';
  const stats=`<dl class="work-counts"><div><dt>Acquisition records</dt><dd>${counts.sources}</dd></div><div><dt>Readable sources</dt><dd>${counts.usable_sources}</dd></div><div><dt>Evidence excerpts</dt><dd>${counts.evidence}</dd></div><div><dt>Analysis ledger</dt><dd>${counts.findings}</dd></div><div><dt>Archived files</dt><dd>${counts.archived_files}</dd></div></dl>`;
  const stop=p.stop_reason?`<div class="stop-explanation" role="status"><strong>${esc(p.stop_reason.message)}</strong><p>${esc(p.stop_reason.next_step)}</p></div>`:'';
  if(tab==='overview')return notice+`<h4 class="report-title">Current research progress</h4>${stats}${stop}<p class="report-intro">${esc(bundle.job?.question||'')}</p><p class="report-intro">Acquisition records include failed attempts; Readable sources include abstracts, partial source text and uploaded materials. Stage records and source materials can be viewed and downloaded. </p>`+(counts.sources?`<h5 class="report-section-title">Recently archived materials</h5>${[...p.sources.filter(s=>['complete_body','partial_body','snippet_only','supplied_text','structured_data'].includes(s.status)).slice(-6).reverse(),...p.sources.filter(s=>!['complete_body','partial_body','snippet_only','supplied_text','structured_data'].includes(s.status)).slice(-2).reverse()].map(s=>sourceHTML(s,job)).join('')}`:'<p class="report-intro">No sources archived yet. This view updates with actual work; Materials that were not obtained are not counted as results. </p>');
  if(tab==='work')return notice+stats+stop+'<h4 class="report-title">Saved analysis ledger</h4>'+p.findings.map(f=>`<article class="finding"><span class="kind">Unreviewed · ${esc(kinds[f.kind]||'Analysis')}</span><p>${esc(f.statement)}</p>${(f.evidence_refs||[]).map(id=>`<button type="button" class="evidence-button" data-evidence="${esc(id)}">View evidence ${esc(id)}</button>`).join('')}${list('Scope and limitations',f.limitations)}</article>`).join('')+(p.findings.length?'':'<p class="report-intro">No analysis ledger saved yet; Acquired source text remains available in“Source materials”View. </p>');
  return notice+stop+'<h4 class="report-title">Evidence excerpts and archived originals</h4>'+p.evidence.map(e=>`<article class="evidence-block" id="evidence-${esc(e.evidence_id)}"><span class="kind">${esc(e.evidence_id)} / ${esc(e.block_id)}</span><blockquote>${esc(e.quote)}</blockquote><p>${esc(e.context)}</p>${sourceHTML(p.sources.find(s=>s.source_id===e.source_id)||{},job)}</article>`).join('')+'<h5 class="report-section-title">All acquisition records</h5>'+p.sources.map(s=>sourceHTML(s,job)).join('');
 }
 function render(bundle,tab='overview',job=''){
  if(bundle?.progress&&(tab==='work'||!bundle.result?.support_reviewed||!bundle.validation?.ok))return liveHTML(bundle,tab,job);
  const r=bundle?.result;if(!r?.support_reviewed)return '<div class="empty">Result has not passed review. Existing materials will be retained. </div>';
  const finding=f=>`<article class="finding"><span class="kind ${esc(f.kind)}">${esc(kinds[f.kind]||'Needs checking')}</span><p>${esc(f.statement)}</p>${(f.evidence_refs||[]).map(id=>`<button type="button" class="evidence-button" data-evidence="${esc(id)}">View evidence ${esc(id)}</button>`).join('')}${f.limitations?.length?`<details><summary>Scope and limitations</summary><ul>${f.limitations.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}</article>`;
  let html=`<div class="report-banner">${r.research_depth==='deep'?'Deep':'Standard'}Research · ${r.status==='complete'?'Completed':r.status==='needs_input'?'More information needed':'Partially complete'} · Independent evidence review passed</div>`;
  if(tab==='overview')return html+`<h4 class="report-title">Conclusions and next steps</h4><p class="report-intro">${esc(r.summary)}</p><h5 class="report-section-title">Research findings</h5>${(r.findings||[]).map(finding).join('')}`+list('Counterarguments and conflicts',r.conflicts)+list('Evidence still needed',r.missing_evidence)+list('Research assumptions',r.assumptions)+list('Next validation steps',r.next_steps);
  if(tab==='needs')return html+'<h4 class="report-title">Need signals and questions to validate</h4>'+(r.findings||[]).filter(f=>['inference','hypothesis','unknown'].includes(f.kind)).map(finding).join('');
  if(tab==='competitors')return html+'<h4 class="report-title">Existing products and usage feedback</h4>'+(r.findings||[]).filter(f=>['fact','source_opinion'].includes(f.kind)).map(finding).join('');
  const module=r.modules?.find(m=>m.module_id===tab);
  if(module)return html+`<h4 class="report-title">${esc(module.title)}</h4><p class="report-intro">${esc(module.intro)}</p>`+(r.findings||[]).filter(f=>module.finding_refs?.includes(f.finding_id)).map(finding).join('')+list('Evidence gaps and scope',module.gaps);
  return html+'<h4 class="report-title">Original evidence and sources</h4>'+(bundle.evidence||[]).map(e=>{
   const s=(bundle.sources||[]).find(s=>s.source_id===e.source_id)||{};let url='';try{const u=new URL(s.final_url||s.source_url);if(['http:','https:'].includes(u.protocol))url=u.href}catch{}
   const artifact=s.artifacts?.markdown;
   return `<article class="evidence-block" id="evidence-${esc(e.evidence_id)}"><span class="kind">${esc(e.evidence_id)} / ${esc(e.block_id)}</span><blockquote>${esc(e.quote)}</blockquote><p>${esc(e.context)}</p>${url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(s.title||url)}</a>`:''}${artifact&&job?`<a class="source-download" href="/api/artifact?id=${encodeURIComponent(job)}&path=${encodeURIComponent(artifact)}" download>Download archived source</a>`:''}<p>Get status: ${esc(s.status)} · ${esc(s.retrieved_at||'')}</p></article>`;
  }).join('');
 }
 return {render,tabs,markdown,esc};
})();
