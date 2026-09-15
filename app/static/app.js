'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state = null, serverOffset = 0, currentPage = 'today', editingId = null, previewState = null, ocrLines = [], polling = false, prayerSignature = '', connectionFailed = false;
let token = sessionStorage.getItem('azan-token') || '';
let draft = [{date:'',fajr:'',maghrib:'',notes:''}];
function message(text, error=false) { const el = $(error?'error':'toast'); el.textContent=text; el.hidden=false; if(!error) setTimeout(()=>{el.hidden=true;},7000); }
async function api(path, data, method='POST') {
  const options = {method:data===undefined?'GET':method,headers:{}};
  if(data!==undefined) {
    options.headers['X-Azan-Control']='1';
    if(token) options.headers.Authorization=`Bearer ${token}`;
    if(data instanceof FormData) options.body=data;
    else { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(data); }
  }
  const response = await fetch(path,options);
  const result = await response.json();
  if(!response.ok) throw new Error(result.error || 'The service is unavailable.');
  return result;
}
function localTime(value, seconds=false) {
  if(!value || !state) return '—';
  return new Intl.DateTimeFormat(undefined,{timeZone:state.settings.timezone,hour:'2-digit',minute:'2-digit',...(seconds?{second:'2-digit'}:{})}).format(new Date(value));
}
function localDate(value, options={}) {
  return new Intl.DateTimeFormat('en-CA',{timeZone:state.settings.timezone,...options}).format(new Date(value));
}
function updateClock() {
  if(!state) return;
  const now = Date.now()+serverOffset;
  $('clock').textContent=localTime(now,true);
  $('date-label').textContent=localDate(now,{weekday:'long',day:'numeric',month:'long',year:'numeric'}).toUpperCase();
  if(state.next) {
    const seconds=Math.max(0,Math.ceil((Date.parse(state.next.scheduled_at)-now)/1000));
    const parts=[Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60];
    $('countdown').textContent=parts.map(v=>String(v).padStart(2,'0')).join(':');
  } else $('countdown').textContent='—';
}
function countsHTML(data) {
  const c=data.counts;
  return [['PLAYED','Played'],['PENDING','Remaining'],['PLAYING','Playing'],['SKIPPED','Skipped'],['SUPPRESSED','Suppressed'],['DISABLED','Disabled'],['STOPPED_BY_USER','Stopped'],['FAILED','Failed'],['MISSED_DOWNTIME','Missed']]
    .map(([key,label])=>`<span><b>${c[key]||0}</b>${label}</span>`).join('');
}
function rowsHTML(rows, controls=false) {
  if(!rows.length) return '<article class="card"><p>No recorded schedule for this date. The system does not invent historical playback.</p></article>';
  return rows.map(r=>`<article class="prayer-row"><div><span class="prayer-name">${esc(r.prayer)}</span><small>${esc(r.timing_source)}</small></div><div class="prayer-time">${esc(localTime(r.scheduled_at))}</div><div><span class="badge ${esc(r.status.toLowerCase())}">${esc(r.status.replaceAll('_',' '))}</span>${r.started_at?`<small>Started ${esc(localTime(r.started_at,true))}${r.completed_at?` · Ended ${esc(localTime(r.completed_at,true))}`:''}</small>`:''}${r.audio_file?`<small>Audio: ${esc(r.audio_file)}</small>`:''}${r.failure_reason||r.suppression_reason?`<small>${esc(r.failure_reason||r.suppression_reason)}</small>`:''}</div>${controls?`<div class="row-controls">${r.status==='PENDING'?`<button data-skip="${r.id}">Skip this Azan</button>`:''}<label class="toggle"><input type="checkbox" data-prayer="${esc(r.prayer)}" ${state.settings.enabled[r.prayer]?'checked':''} aria-label="Persistently enable ${esc(r.prayer)} Azan">On</label></div>`:'<div></div>'}</article>`).join('');
}
function renderStatus() {
  $('timezone').textContent=state.settings.timezone;
  $('connection').textContent=state.health.ok?'● System online':state.health.scheduler_alive?'● Needs attention':'● Scheduler offline';
  $('played-summary').textContent=`${state.counts.PLAYED||0} of ${state.scheduled} Azans played today`;
  $('summary').innerHTML=countsHTML(state);
  const signature=JSON.stringify([state.occurrences,state.settings.enabled]);
  if(signature!==prayerSignature) {
    const focused=document.activeElement?.dataset?.prayer;
    $('prayers').innerHTML=rowsHTML(state.occurrences,true);
    if(focused) [...$('prayers').querySelectorAll('[data-prayer]')].find(e=>e.dataset.prayer===focused)?.focus();
    prayerSignature=signature;
  }
  const next=state.next;
  $('next-prayer').textContent=next?next.prayer:'No upcoming Azan';
  $('next-time').textContent=next?localTime(next.scheduled_at):'';
  $('next-source').textContent=next?next.timing_source:'Check prayer settings and schedule health.';
  $('next-date').textContent=next?localDate(next.scheduled_at,{weekday:'long',month:'short',day:'numeric'}):'Schedule unavailable or all prayers disabled';
  $('snooze-banner').hidden=!state.settings.snooze_until;
  $('snooze-label').textContent=state.settings.snooze_until?`AZAN SNOOZED UNTIL ${localTime(state.settings.snooze_until)} · due Azans will be suppressed`:'';
  $('playing-banner').hidden=!state.playing;
  if(document.activeElement!==$('volume')) $('volume').value=state.settings.volume;
  $('volume-label').textContent=`${$('volume').value}%`;
  updateClock();
  if(currentPage==='settings') renderSettings();
}
async function refresh() {
  if(polling) return;
  polling=true;
  const start=Date.now();
  try { state=await api('/api/status'); serverOffset=Date.parse(state.now)-(start+Date.now())/2; renderStatus(); if(connectionFailed){$('error').hidden=true;connectionFailed=false;} if(currentPage==='history')await loadHistory(); }
  catch(e) { connectionFailed=true; $('connection').textContent='● Connection lost'; message(`Unable to reach the controller. Displayed data may be stale. ${e.message}`,true); }
  finally { polling=false; }
}
async function perform(fn) {
  $('error').hidden=true;
  try { await fn(); await refresh(); } catch(e) { message(e.message,true); }
}
async function openPage(page) {
  currentPage=page;
  for(const name of ['today','history','ramadan','settings']) $(`page-${name}`).hidden=name!==page;
  document.querySelectorAll('[data-page]').forEach(b=>{b.classList.toggle('selected',b.dataset.page===page);b.setAttribute('aria-current',b.dataset.page===page?'page':'false');});
  if(page==='history') { if(!$('history-date').value && state) $('history-date').value=state.date; await loadHistory(); }
  if(page==='ramadan') await loadProfiles();
  if(page==='settings') { renderSettings(); await loadAudio(); }
}
async function loadHistory() {
  if(!$('history-date').value) return;
  const data=await api(`/api/history?date=${encodeURIComponent($('history-date').value)}`);
  $('history-summary').innerHTML=`<span><b>${data.scheduled}</b>Scheduled</span>`+countsHTML(data);
  $('history-rows').innerHTML=rowsHTML(data.occurrences);
}
function renderSettings() {
  if(!state) return;
  const s=state.settings;
  $('configuration').innerHTML=Object.entries({'Location':`${s.city}, ${s.country}`,'Timezone':s.timezone,'Aladhan method':s.method,'School':s.school===0?'Provider default (0)':'Hanafi (1)','Late-start grace':`${s.grace_seconds} seconds`,'Audio mode':s.audio_mode}).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  $('health-details').innerHTML=`<p>Database: ${esc(state.health.database)}<br>Scheduler: ${state.health.scheduler_alive?'Running':'Offline'}<br>Schedule coverage: ${state.health.schedule_days} days<br>Clock: ${esc(state.health.clock_sync)}</p>`+state.health.warnings.map(w=>`<p class="notice">${esc(w)}</p>`).join('');
}
async function loadAudio() { const data=await api('/api/audio'); $('audio-files').innerHTML=['normal','fajr'].map(k=>`<h4>${k==='fajr'?'Fajr Azan':'Normal Azan'}</h4><p>${data[k].map(f=>esc(f.filename)).join('<br>')||'No usable recordings'}</p>`).join(''); }
async function loadProfiles() {
  const profiles=await api('/api/ramadan');
  $('profiles').innerHTML=profiles.map(p=>`<article class="card profile-item"><div><strong>${esc(p.name)}</strong> <span class="badge">${p.active?'Active':'Draft / inactive'}</span><p>${esc(p.source)} · ${p.rows.length} dates${p.rows.length?` · ${esc(p.rows[0].date)} to ${esc(p.rows.at(-1).date)}`:''}</p></div><div class="actions"><button data-preview="${p.id}">Preview</button>${p.active?`<button data-deactivate="${p.id}">Deactivate</button>`:`<button data-edit="${p.id}">Edit</button><button data-delete="${p.id}">Delete</button>`}</div></article>`).join('')||'<p>No profiles yet. Create a draft below.</p>';
  return profiles;
}
function readDraft() { draft=[...$('draft-rows').querySelectorAll('tr')].map(tr=>Object.fromEntries([...tr.querySelectorAll('input')].map(i=>[i.dataset.key,i.value]))); return draft; }
function renderDraft() {
  $('draft-rows').innerHTML=draft.map((r,index)=>`<tr><td><input type="date" data-key="date" value="${esc(r.date)}" aria-label="Date row ${index+1}"></td><td><input type="time" data-key="fajr" value="${esc(r.fajr)}" aria-label="Fajr row ${index+1}"></td><td><input type="time" data-key="maghrib" value="${esc(r.maghrib)}" aria-label="Maghrib row ${index+1}"></td><td><input data-key="notes" value="${esc(r.notes)}" aria-label="Notes row ${index+1}" maxlength="500"></td><td><button data-remove="${index}" aria-label="Remove row ${index+1}">×</button></td></tr>`).join('');
}
async function showPreview(id) {
  message('Loading comparison with standard timings…');
  previewState=await api(`/api/ramadan/${id}/preview`);
  $('preview').hidden=false; $('confirm-preview').checked=false;
  $('preview-warnings').textContent=previewState.warnings.join(' · ')||'All rows validated. Check the differences below before confirming.';
  $('preview-table').innerHTML='<table><thead><tr><th>Date</th><th>Normal Fajr</th><th>Override</th><th>Δ min</th><th>Normal Maghrib</th><th>Override</th><th>Δ min</th></tr></thead><tbody>'+previewState.rows.map(r=>`<tr><td>${esc(r.date)}${r.error?'<br>Standard timing unavailable':''}</td><td>${esc(r.standard.Fajr||'Unknown')}</td><td>${esc(r.fajr||'Standard')}</td><td>${esc(r.differences.fajr??'—')}</td><td>${esc(r.standard.Maghrib||'Unknown')}</td><td>${esc(r.maghrib||'Standard')}</td><td>${esc(r.differences.maghrib??'—')}</td></tr>`).join('')+'</tbody></table>';
  $('preview').scrollIntoView({behavior:'smooth',block:'start'});
}
document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>perform(()=>openPage(b.dataset.page))));
document.querySelectorAll('[data-snooze]').forEach(b=>b.addEventListener('click',()=>perform(async()=>{await api('/api/snooze',{minutes:Number(b.dataset.snooze)});message(`Azan snoozed for ${b.dataset.snooze} minutes.`);} )));
$('snooze-custom').onclick=()=>perform(()=>api('/api/snooze',{until_time:$('snooze-time').value}));
$('resume').onclick=()=>perform(()=>api('/api/resume',{}));
$('stop').onclick=()=>perform(()=>api('/api/stop',{}));
$('prayers').addEventListener('click',e=>{const b=e.target.closest('[data-skip]');if(b) perform(()=>api(`/api/occurrences/${b.dataset.skip}/skip`,{}));});
$('prayers').addEventListener('change',e=>{if(e.target.dataset.prayer) perform(()=>api(`/api/prayers/${e.target.dataset.prayer}`,{enabled:e.target.checked}));});
$('volume').oninput=()=>{$('volume-label').textContent=`${$('volume').value}%`;};
$('volume').onchange=()=>perform(()=>api('/api/volume',{volume:Number($('volume').value)}));
for(const [id,delta] of [['volume-down',-5],['volume-up',5]]) $(id).onclick=()=>perform(()=>api('/api/volume',{volume:Math.min(100,Math.max(0,Number($('volume').value)+delta))}));
$('history-date').onchange=()=>perform(loadHistory);
$('save-token').onclick=()=>{token=$('control-token').value;sessionStorage.setItem('azan-token',token);$('control-token').value='';message('Control token saved for this tab.');};
for(const [id,collection] of [['test-normal-audio','normal'],['test-fajr-audio','fajr']]) $(id).onclick=()=>perform(async()=>{const result=await api('/api/audio/test',{collection});message(`Testing ${result.audio_file} at ${result.volume}%. Use Stop Azan to end playback.`);});
$('new-profile').onclick=()=>{editingId=null;draft=[{date:'',fajr:'',maghrib:'',notes:''}];$('profile-name').value='';$('profile-source').value='';$('editor-title').textContent='New draft';$('preview').hidden=true;renderDraft();$('profile-editor').scrollIntoView({behavior:'smooth'});};
$('add-row').onclick=()=>{readDraft();draft.push({date:'',fajr:'',maghrib:'',notes:''});renderDraft();};
$('draft-rows').onclick=e=>{const b=e.target.closest('[data-remove]');if(b){readDraft();draft.splice(Number(b.dataset.remove),1);renderDraft();}};
$('csv-file').onchange=()=>perform(async()=>{const f=$('csv-file').files[0];if(f){if(f.size>1024*1024)throw new Error('CSV limit is 1 MB');$('csv-text').value=await f.text();}});
$('parse-csv').onclick=()=>perform(async()=>{const result=await api('/api/ramadan/csv',{csv:$('csv-text').value,mapping:{date:$('map-date').value,fajr:$('map-fajr').value,maghrib:$('map-maghrib').value}});draft=result.rows;renderDraft();message(result.warnings.join(' · ')||'CSV loaded into the draft. Review and save to preview.');});
$('save-profile').onclick=()=>perform(async()=>{const data={name:$('profile-name').value,source:$('profile-source').value,rows:readDraft()};const result=await api(editingId?`/api/ramadan/${editingId}`:'/api/ramadan',data,editingId?'PUT':'POST');editingId=result.id;await loadProfiles();await showPreview(editingId);});
$('profiles').onclick=e=>perform(async()=>{
  const b=e.target.closest('button');if(!b)return;
  if(b.dataset.preview) await showPreview(Number(b.dataset.preview));
  if(b.dataset.deactivate){await api(`/api/ramadan/${b.dataset.deactivate}/activation`,{active:false});await loadProfiles();message('Profile deactivated. Future prayers use standard timings.');}
  if(b.dataset.delete && window.confirm('Delete this inactive Ramadan profile and its timetable?')){await api(`/api/ramadan/${b.dataset.delete}`,{confirmed:true},'DELETE');await loadProfiles();}
  if(b.dataset.edit){const p=(await loadProfiles()).find(p=>p.id===Number(b.dataset.edit));editingId=p.id;draft=p.rows;$('profile-name').value=p.name;$('profile-source').value=p.source;$('editor-title').textContent='Edit inactive profile';$('preview').hidden=true;renderDraft();$('profile-editor').scrollIntoView({behavior:'smooth'});}
});
$('activate-profile').onclick=()=>perform(async()=>{if(!$('confirm-preview').checked)throw new Error('Review the timetable and check the confirmation box first.');await api(`/api/ramadan/${previewState.profile.id}/activation`,{active:true,confirmed:true,revision:previewState.revision});$('preview').hidden=true;await loadProfiles();message('Ramadan profile activated. Future timings have been updated.');});
$('extract-ocr').onclick=()=>perform(async()=>{const file=$('ocr-file').files[0];if(!file)throw new Error('Choose a photo or PDF first.');if(file.size>8*1024*1024)throw new Error('Upload limit is 8 MB.');const form=new FormData();form.append('file',file);$('extract-ocr').disabled=true;message('Extracting timetable. This can take a minute.');try{const result=await api('/api/ramadan/ocr',form);ocrLines=result.lines;$('ocr-output').innerHTML=ocrLines.map(l=>`<p class="${l.confidence<85?'low-confidence':''}">${esc(l.text)} · confidence ${l.confidence}%</p>`).join('');message(result.warnings.join(' '));}finally{$('extract-ocr').disabled=false;}});
$('map-ocr').onclick=()=>perform(async()=>{const f=Number($('ocr-fajr-column').value)-1,m=Number($('ocr-maghrib-column').value)-1;if(f<0||m<0||f===m)throw new Error('Select two distinct time columns.');draft=ocrLines.filter(l=>l.date).map(l=>({date:l.date,fajr:l.times[f]?.padStart(5,'0')||'',maghrib:l.times[m]?.padStart(5,'0')||'',notes:`OCR confidence ${l.confidence}%; verify against source`}));if(!draft.length)throw new Error('No ISO Gregorian dates detected. Enter the dates and times manually using the extracted text.');renderDraft();message('OCR values copied to draft. Correct all dates and 24-hour times before saving.');});
renderDraft();refresh();setInterval(refresh,10000);setInterval(updateClock,1000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
