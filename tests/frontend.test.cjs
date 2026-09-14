const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM} = require('jsdom');

const html = fs.readFileSync('app/static/index.html','utf8');
const script = fs.readFileSync('app/static/app.js','utf8');
const settle = () => new Promise(resolve=>setTimeout(resolve,20));
function fixture() {
  return {now:'2027-03-05T10:00:00Z',date:'2027-03-05',scheduled:5,playing:null,
    settings:{timezone:'Asia/Kolkata',city:'Hyderabad',country:'India',method:1,school:0,
      grace_seconds:90,audio_mode:'console',volume:70,snooze_until:null,
      enabled:{Fajr:true,Dhuhr:true,Asr:true,Maghrib:true,Isha:true}},
    health:{ok:false,scheduler_alive:true,database:'ok',schedule_days:35,warnings:['Console simulation'],clock_sync:'Unknown'},
    counts:{PLAYED:2,PENDING:3},
    next:{id:3,prayer:'Asr',scheduled_at:'2027-03-05T11:09:00Z',date:'2027-03-05',timing_source:'Standard calculation'},
    occurrences:[{id:3,prayer:'Asr',scheduled_at:'2027-03-05T11:09:00Z',status:'PENDING',timing_source:'Standard calculation'}]};
}
async function page() {
  const dom = new JSDOM(html,{url:'http://localhost:8080',runScripts:'outside-only',pretendToBeVisual:true});
  const state=fixture(), calls=[];
  dom.window.HTMLElement.prototype.scrollIntoView=function(){};
  dom.window.fetch=async(path,options={})=>{
    const data=options.body?JSON.parse(options.body):undefined;
    calls.push({path,options,data});
    let result={ok:true};
    if(path==='/api/status')result=state;
    else if(path==='/api/volume')state.settings.volume=data.volume;
    else if(path==='/api/snooze')state.settings.snooze_until='2027-03-05T11:00:00Z';
    else if(path==='/api/resume')state.settings.snooze_until=null;
    else if(path==='/api/stop')state.playing=null;
    else if(path.startsWith('/api/history'))result={date:'2027-03-05',scheduled:5,counts:state.counts,occurrences:state.occurrences};
    else if(path==='/api/ramadan')result=[];
    else if(path==='/api/audio')result={normal:[{filename:'azan_1.wav'}],fajr:[{filename:'fajr_1.wav'}],warnings:[]};
    else if(path==='/api/ramadan/csv')result={rows:[{date:'2027-03-05',fajr:'05:21',maghrib:'18:34'}],warnings:[]};
    return {ok:true,json:async()=>JSON.parse(JSON.stringify(result))};
  };
  dom.window.eval(script);
  await settle();
  return {dom,document:dom.window.document,state,calls};
}

test('dashboard renders server timezone, precise statuses and live countdown',async()=>{
  const {dom,document:d}=await page();
  try {
    assert.equal(d.getElementById('next-prayer').textContent,'Asr');
    assert.match(d.getElementById('next-time').textContent,/4:39|04:39|16:39/);
    assert.equal(d.getElementById('countdown').textContent,'01:09:00');
    assert.equal(d.getElementById('played-summary').textContent,'2 of 5 Azans played today');
    assert.match(d.getElementById('summary').textContent,/0Suppressed/);
    assert.equal(d.getElementById('timezone').textContent,'Asia/Kolkata');
  } finally {dom.window.close();}
});
test('meeting snooze, resume and stop issue control calls and update banners',async()=>{
  const {dom,document:d,state,calls}=await page();
  try {
    d.querySelector('[data-snooze="60"]').click();await settle();
    assert.equal(calls.find(c=>c.path==='/api/snooze').data.minutes,60);
    assert.equal(d.getElementById('snooze-banner').hidden,false);
    d.getElementById('resume').click();await settle();
    assert.equal(d.getElementById('snooze-banner').hidden,true);
    state.playing=3;d.dispatchEvent(new dom.window.Event('visibilitychange'));await settle();
    assert.equal(d.getElementById('playing-banner').hidden,false);
    d.getElementById('stop').click();await settle();
    assert.equal(d.getElementById('playing-banner').hidden,true);
    assert.equal(calls.find(c=>c.path==='/api/stop').options.headers['X-Azan-Control'],'1');
  } finally {dom.window.close();}
});
test('volume, prayer toggle and occurrence skip send distinct requests',async()=>{
  const {dom,document:d,calls}=await page();
  try {
    d.getElementById('volume').value=25;
    d.getElementById('volume').dispatchEvent(new dom.window.Event('change'));await settle();
    assert.equal(calls.find(c=>c.path==='/api/volume').data.volume,25);
    const toggle=d.querySelector('[data-prayer="Asr"]');toggle.checked=false;
    toggle.dispatchEvent(new dom.window.Event('change',{bubbles:true}));await settle();
    assert.equal(calls.find(c=>c.path==='/api/prayers/Asr').data.enabled,false);
    d.querySelector('[data-skip="3"]').click();await settle();
    assert.ok(calls.some(c=>c.path==='/api/occurrences/3/skip'));
  } finally {dom.window.close();}
});
test('history and settings display actual endpoint data',async()=>{
  const {dom,document:d}=await page();
  try {
    d.querySelector('[data-page="history"]').click();await settle();
    assert.equal(d.getElementById('page-history').hidden,false);
    assert.match(d.getElementById('history-rows').textContent,/Asr/);
    d.querySelector('[data-page="settings"]').click();await settle();
    assert.match(d.getElementById('configuration').textContent,/Hyderabad/);
    assert.match(d.getElementById('audio-files').textContent,/fajr_1.wav/);
  } finally {dom.window.close();}
});
test('CSV mapping only loads editable draft; no activation request',async()=>{
  const {dom,document:d,calls}=await page();
  try {
    d.getElementById('csv-text').value='date,fajr,maghrib\n2027-03-05,05:21,18:34';
    d.getElementById('parse-csv').click();await settle();
    assert.equal(d.querySelector('[data-key="maghrib"]').value,'18:34');
    assert.deepEqual(calls.find(c=>c.path==='/api/ramadan/csv').data.mapping,{date:'date',fajr:'fajr',maghrib:'maghrib'});
    assert.ok(!calls.some(c=>c.path.includes('/activation')));
  } finally {dom.window.close();}
});
test('server failure is visible and unsafe text renders as text',async()=>{
  const {dom,document:d,state}=await page();
  try {
    state.occurrences[0].timing_source='<img src=x onerror=alert(1)>';
    d.dispatchEvent(new dom.window.Event('visibilitychange'));await settle();
    assert.equal(d.querySelectorAll('#prayers img').length,0);
    assert.match(d.getElementById('prayers').textContent,/<img/);
    dom.window.fetch=async()=>{throw new Error('Network unavailable');};
    d.getElementById('stop').click();await settle();
    assert.equal(d.getElementById('error').hidden,false);
    assert.match(d.getElementById('error').textContent,/Network unavailable/);
  } finally {dom.window.close();}
});
