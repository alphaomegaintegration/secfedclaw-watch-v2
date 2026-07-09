"""Static assets for the SECFEDCLAW dashboard — the inline CSS design
system and the offline JS (tabs, filters, runs polling, labeling,
retrain, entity/queue navigation). Extracted verbatim from dashboard_v2
to shrink that module; imported back as CSS / JS. No behavior change.
"""
CSS = """
/* USWDS + SEC.gov design system — Public Sans typography, federal navy header */
:root{
  /* USWDS color tokens (light theme) */
  --bg:#ffffff; --panel:#f0f0f0; --panel-2:#e8f0f8; --line:#dfe1e2; --line-2:#a9aeb1;
  --ink:#1b1b1b; --muted:#555f6b; --faint:#71767a;
  --brand:#005ea2; --brand-dark:#1a4480; --brand-light:#d9e8f6;
  --accent:#c9a227; --accent-bg:#faf3d1;
  /* USWDS semantic status colors */
  --ok:#00a91c; --ok-bg:#ecf3ec; --crit:#b50909; --crit-bg:#fff3ee;
  --high:#c05600; --high-bg:#fef0e8; --med:#276130; --med-bg:#edf5ee; --low:#555f6b; --low-bg:#f0f0f0;
  /* SEC.gov header navy */
  --header-bg:#17375e; --header-ink:#ffffff;
  --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px;
  --radius:4px; --shadow:0 1px 3px rgba(0,0,0,.12);
  /* Public Sans (USWDS default) → Source Sans Pro → system */
  --f:"Public Sans","Source Sans Pro",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
*{box-sizing:border-box} html{scroll-behavior:smooth;color-scheme:light}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 var(--f);-webkit-font-smoothing:antialiased}
a{color:var(--brand);text-decoration:none} a:hover{text-decoration:underline}
a:focus-visible{outline:3px solid var(--brand);outline-offset:2px;border-radius:2px}

/* === GOVERNMENT BANNER (USWDS usa-banner pattern) === */
.govbanner{background:#f0f0f0;border-bottom:1px solid #dfe1e2;padding:6px var(--s5);font-size:12px;color:#555f6b}
.govbanner-inner{max-width:1180px;margin:0 auto;display:flex;align-items:center;gap:6px}
.govbanner span{font-weight:600}

/* === HEADER (SEC.gov navy) === */
.topbar{background:var(--header-bg);border-bottom:4px solid var(--accent);padding:var(--s4) var(--s5);position:sticky;top:0;z-index:10}
.brand-row{display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap}
.brand{font-weight:800;letter-spacing:.3px;font-size:20px;color:var(--header-ink);text-transform:uppercase}
.brand .v{color:#d9e8f6;font-weight:400;font-size:13px;text-transform:none;letter-spacing:0}
.subtitle{color:rgba(255,255,255,.75);font-size:13px;font-weight:400}
.meta{margin-left:auto;color:rgba(255,255,255,.6);font-size:12px}
.boundary{margin-top:var(--s3);background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);color:#ffe8b0;border-radius:var(--radius);padding:var(--s2) var(--s3);font-size:12.5px}

/* === SIDEBAR NAV (drawer/cabinet) === */
:root{--sidebar-w:220px;--sidebar-collapsed:48px}
.sidebar{position:fixed;left:0;top:0;bottom:0;width:var(--sidebar-w);background:var(--header-bg);border-right:3px solid var(--accent);z-index:20;display:flex;flex-direction:column;transition:width .2s ease;overflow:hidden}
.sidebar.collapsed{width:var(--sidebar-collapsed)}
.sidebar-header{display:flex;align-items:center;justify-content:flex-end;padding:var(--s3) var(--s2);border-bottom:1px solid rgba(255,255,255,.15);min-height:52px;flex-shrink:0}
.sidebar-toggle{background:none;border:none;cursor:pointer;color:rgba(255,255,255,.8);padding:7px;border-radius:var(--radius);line-height:1;font-size:18px;min-width:44px;min-height:44px;text-align:center;transition:background .1s;display:flex;align-items:center;justify-content:center}
.sidebar-toggle:hover{background:rgba(255,255,255,.12);color:#fff}
.sidebar-toggle:focus-visible{outline:3px solid rgba(255,255,255,.6);outline-offset:2px}
.tabs{display:flex;flex-direction:column;gap:2px;padding:var(--s2);overflow-y:auto;flex:1}
.nav-section{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:rgba(255,255,255,.45);padding:9px var(--s3) 4px;margin-top:var(--s2)}
.nav-section:first-child{margin-top:0}
.sidebar.collapsed .nav-section{display:none}
.tab{padding:9px var(--s3);background:transparent;border:1px solid transparent;border-radius:var(--radius);cursor:pointer;font-family:inherit;font-weight:600;font-size:13.5px;line-height:1.2;color:rgba(255,255,255,.7);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:background .1s,color .1s;text-align:left;width:100%;display:block}
.tab:hover{color:#fff;background:rgba(255,255,255,.1)}
.tab:focus-visible{outline:2px solid #fff;outline-offset:1px}
.tab.active{background:rgba(255,255,255,.18);color:#fff;border-color:rgba(255,255,255,.25)}
.sidebar.collapsed .tab{padding:9px;text-align:center;font-size:0;overflow:visible}
.sidebar.collapsed .tab::before{font-size:13px;display:block;font-weight:700;color:rgba(255,255,255,.8);line-height:1.6}
.sidebar.collapsed .tab[data-id="overview"]::before{content:"O"}
.sidebar.collapsed .tab[data-id="packages"]::before{content:"P"}
.sidebar.collapsed .tab[data-id="network"]::before{content:"N"}
.sidebar.collapsed .tab[data-id="entities"]::before{content:"E"}
.sidebar.collapsed .tab[data-id="howitworks"]::before{content:"?"}
.sidebar.collapsed .tab[data-id="agents"]::before{content:"A"}
.sidebar.collapsed .tab[data-id="learning"]::before{content:"L"}
.sidebar.collapsed .tab[data-id="status"]::before{content:"S"}
.sidebar.collapsed .tab[data-id="runs"]::before{content:"▶"}
.sidebar.collapsed .tab[data-id="llm"]::before{content:"$"}
.sidebar.collapsed .tab[data-id="methodology"]::before{content:"M"}
.sidebar.collapsed .tab[data-id="cases"]::before{content:"⚖"}
.sidebar.collapsed .tab[data-id="backtest"]::before{content:"B"}
.panel{display:none;animation:f .15s ease} .panel.active{display:block} @keyframes f{from{opacity:.5}to{opacity:1}}

/* === LAYOUT (content shifts right for sidebar) === */
.page-shell{margin-left:var(--sidebar-w);transition:margin-left .2s ease}
.page-shell.nav-collapsed{margin-left:var(--sidebar-collapsed)}
.wrap{max-width:1180px;margin:0 auto;padding:var(--s5)}
@media(max-width:760px){.sidebar{width:var(--sidebar-collapsed)}.page-shell{margin-left:var(--sidebar-collapsed)}}
.intro{color:var(--muted);max-width:80ch;margin:0 0 var(--s4);font-size:16px;line-height:1.65}

/* === TYPOGRAPHY === */
h2{font-size:22px;font-weight:700;margin:0 0 var(--s4);color:var(--ink)}
h3{font-size:17px;font-weight:700;margin:0 0 var(--s3);color:var(--ink)}

/* === CARDS === */
.card{background:var(--bg);border:1px solid var(--line);border-radius:var(--radius);padding:var(--s4);margin-bottom:var(--s4);box-shadow:var(--shadow)}

/* === TABLES (USWDS usa-table pattern) === */
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line);vertical-align:middle}
thead th{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.5px;font-weight:700;background:var(--panel);border-bottom:2px solid var(--line-2)}
tbody tr:hover{background:#f5f7fb}
.num{text-align:right;font-variant-numeric:tabular-nums} .muted{color:var(--muted)} .faint{color:var(--faint)} .small{font-size:13px}
.tk{white-space:nowrap}
.reflinks{display:inline-flex;gap:6px;margin-left:8px}
.reflinks a{font-size:10.5px;font-weight:700;color:var(--brand);border:1px solid var(--line-2);border-radius:3px;padding:1px 5px;background:var(--bg)}
.reflinks a:hover{background:var(--brand);color:#fff;border-color:var(--brand);text-decoration:none}

/* === PRIORITY PILLS (USWDS semantic + accessible on white) === */
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:700;letter-spacing:.2px}
.pill.crit{background:var(--crit-bg);color:var(--crit);border:1px solid #e59393}
.pill.high{background:var(--high-bg);color:var(--high);border:1px solid #f0ab70}
.pill.med{background:var(--med-bg);color:var(--med);border:1px solid #86c387}
.pill.low{background:var(--low-bg);color:var(--low);border:1px solid var(--line-2)}

/* === INFO TOOLTIP === */
.info{display:inline-block;width:17px;height:17px;line-height:17px;text-align:center;border-radius:50%;background:var(--brand);color:#fff;font-size:10px;font-weight:700;cursor:help;margin-left:4px;position:relative;vertical-align:middle}
.info .tooltip{display:none;position:absolute;bottom:calc(100% + 8px);left:50%;transform:translateX(-50%);background:#fff;color:var(--ink);border:1px solid var(--line-2);box-shadow:0 4px 12px rgba(0,0,0,.15);border-radius:var(--radius);padding:10px 14px;font-size:13px;font-weight:400;line-height:1.5;width:320px;max-width:90vw;white-space:normal;text-align:left;z-index:100;pointer-events:none}
.info .tooltip::after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:var(--line-2)}
.info:hover .tooltip,.info:focus-visible .tooltip{display:block}

/* === SCORE BARS === */
.bar{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:3px;height:18px;min-width:130px;overflow:hidden}
.bar-fill{position:absolute;inset:0 auto 0 0;background:linear-gradient(90deg,#00571a,#00a91c)}
.bar-fill.anom{background:linear-gradient(90deg,#7a2700,#c05600)}
.bar-num{position:relative;padding-left:8px;font-size:11.5px;line-height:18px;color:#fff;font-weight:700;text-shadow:0 0 3px rgba(0,0,0,.5)}

/* === KPI TILES === */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:var(--s3);margin-bottom:var(--s4)}
.kpi{background:var(--bg);border:1px solid var(--line);border-top:3px solid var(--brand);border-radius:var(--radius);padding:var(--s3) var(--s4);box-shadow:var(--shadow)}
.kpi-num{font-size:24px;font-weight:700;color:var(--brand)}
.kpi-num.kpi-text{font-size:15px;font-weight:600;color:var(--muted);letter-spacing:.2px}
.kpi-lbl{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600;margin-top:2px}
.kpi-sub{font-size:11px;color:var(--faint);margin-top:2px}

/* === FILTER BUTTONS === */
.filters{margin:0 0 var(--s3);display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.filters button{background:var(--bg);border:1px solid var(--line-2);color:var(--muted);border-radius:3px;padding:7px 14px;cursor:pointer;font-weight:600;font-size:13px;transition:all .1s;min-height:32px}
.filters button:hover{border-color:var(--brand);color:var(--brand);background:var(--brand-light)}
.mini td,.mini th{padding:5px 8px;font-size:12.5px}

/* === CONFUSION MATRIX === */
.cm .tp{color:#00571a;font-weight:700}.cm .tn{color:#005ea2;font-weight:700}.cm .fp{color:#c05600;font-weight:700}.cm .fn{color:#b50909;font-weight:700}

/* === GRID LAYOUTS === */
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:var(--s4)} @media(max-width:760px){.grid2{grid-template-columns:1fr}}

/* === PACKAGE CARDS === */
.pkg-head{display:flex;align-items:center;gap:var(--s3);flex-wrap:wrap;margin-bottom:var(--s2)}
/* collapsible package card: summary is the click target, custom caret */
details.pkg>summary{cursor:pointer;list-style:none;margin:0 0 var(--s2);align-items:baseline}
details.pkg>summary::-webkit-details-marker{display:none}
details.pkg>summary::before{content:"\25B8";color:var(--faint);font-size:11px;margin-right:6px;display:inline-block;transition:transform .12s}
details.pkg[open]>summary::before{transform:rotate(90deg)}
details.pkg>summary:hover{color:var(--brand)}
.pkg-sum{font-weight:400;margin-left:auto;font-size:12px}
/* drill-down: nested evidence the examiner opens */
.dd-wrap{margin-top:var(--s2);border-top:1px solid var(--line);padding-top:var(--s2);display:flex;flex-direction:column;gap:4px}
details.dd>summary{cursor:pointer;font-size:12.5px;font-weight:600;color:var(--muted);padding:4px 0;list-style:none}
details.dd>summary::-webkit-details-marker{display:none}
details.dd>summary::before{content:"\25B8";color:var(--faint);font-size:10px;margin-right:6px;transition:transform .12s;display:inline-block}
details.dd[open]>summary::before{transform:rotate(90deg)}
details.dd>summary:hover{color:var(--brand)}
.dd-n{color:var(--faint);font-weight:400}
.dd-list{margin:2px 0 6px 20px;color:var(--muted)}.dd-list li{margin:2px 0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--faint)}
/* examiner label actions */
.lbl-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:var(--s2);padding-top:var(--s2);border-top:1px solid var(--line)}
.lbl-cap{font-size:12px;font-weight:600;color:var(--muted)}
.lbl-btn{font:inherit;font-size:12px;padding:4px 10px;border:1px solid var(--line-2);border-radius:var(--radius);background:var(--bg);color:var(--brand);cursor:pointer;transition:background .1s}
.lbl-btn:hover{background:var(--brand-light)}
.lbl-btn:disabled{opacity:.5;cursor:default;background:var(--panel)}
.lbl-status{margin-left:4px}
.lbl-note{font:inherit;font-size:12px;padding:3px 8px;border:1px solid var(--line-2);border-radius:var(--radius);background:var(--bg);color:var(--ink);min-width:160px}
.lbl-prior{font-size:11.5px;font-weight:700;color:var(--ok);background:rgba(0,128,0,.08);border-radius:3px;padding:2px 7px}
.pkg-ts{margin-left:auto;font-size:11.5px;color:var(--faint);white-space:nowrap}
.pkg-ts.stale{color:#b45309;font-weight:600}
.tk-link{font:inherit;font-weight:700;color:var(--brand);background:none;border:none;padding:0;cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.tk-link:hover{color:var(--ink)}
.pkg.flash{animation:pkgflash 1.4s ease-out}
@keyframes pkgflash{0%{box-shadow:0 0 0 3px var(--med)}100%{box-shadow:0 0 0 0 transparent}}
.warn{color:var(--high);font-weight:600}.adv{color:var(--brand)}.model{color:#6b48a8}.enf{color:#8b2d5e}.promo{color:var(--crit);font-weight:600}
.si{color:#0a6b54}.si-list{margin:2px 0 6px 18px;color:var(--muted)}
.expl{background:var(--brand-light);border-radius:var(--radius);padding:8px 10px;color:var(--ink);border:1px solid rgba(0,94,162,.15)}
.rationale{color:var(--muted);border-top:1px dashed var(--line);padding-top:var(--s2);margin-top:var(--s2)}

/* === STATUS DOTS === */
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:middle}
.dot.ok{background:var(--ok)}.dot.warn-d{background:#e5a000}.dot.bad{background:#d54309}.dot.idle{background:var(--low)}
.agent-state{font-size:12px;font-weight:700;margin:2px 0 6px}

/* === PIPELINE STAGES === */
.pipeline{display:flex;align-items:stretch;gap:var(--s2);flex-wrap:wrap;margin-bottom:var(--s4)}
.stage{flex:1;min-width:200px;background:var(--bg);border:1px solid var(--line);border-top:3px solid var(--brand);border-radius:var(--radius);padding:var(--s4);position:relative}
.stage-num{font-size:11px;font-weight:800;color:var(--brand);letter-spacing:1px;text-transform:uppercase}
.stage .tag{display:inline-block;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:#6b3600;background:var(--high-bg);border:1px solid #f0ab70;border-radius:3px;padding:1px 7px;margin-bottom:var(--s2)}
.stage .out{color:var(--muted);border-top:1px dashed var(--line);padding-top:var(--s2);margin-top:var(--s2)}
.arrow{display:flex;align-items:center;color:var(--brand);font-size:22px;font-weight:700}
@media(max-width:760px){.arrow{display:none}.stage{min-width:100%}}

/* === BANDS & CASES === */
.bands{display:flex;gap:var(--s2);flex-wrap:wrap;margin-bottom:var(--s2)}
.cases{display:grid;grid-template-columns:1fr 1fr;gap:var(--s4)} @media(max-width:760px){.cases{grid-template-columns:1fr}}
.case-head{display:flex;justify-content:space-between;align-items:baseline;gap:var(--s2)}
.case .src{font-size:11px;font-weight:700;color:var(--brand);white-space:nowrap}
.case .thr{color:var(--med);font-weight:600}.case .train{color:#6b48a8;font-weight:600}
.worked{border-top-color:var(--med)!important}

/* === RUNS (live control plane) === */
.runctl{display:flex;gap:var(--s2);align-items:center;flex-wrap:wrap;margin-bottom:var(--s2)}
.runctl input[type=text]{flex:1;min-width:220px;padding:8px;border:1px solid var(--line);border-radius:var(--radius);font:inherit}
.runlive{display:flex;align-items:center;gap:5px;font-size:13px;color:var(--muted);white-space:nowrap}
.runmsg{font-size:13px;color:var(--muted);min-height:18px}
.runmeta{font-size:13px;margin-bottom:var(--s2);color:var(--muted)}
.runtable{width:100%;border-collapse:collapse;font-size:13px}
.runtable th,.runtable td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
.runtable th{color:var(--muted);font-weight:600}
.run-pill{display:inline-block;padding:1px 9px;border-radius:10px;font-size:12px;font-weight:700;color:#fff}
.run-pill.ok{background:var(--ok)}.run-pill.err{background:var(--crit)}
.run-pill.run{background:var(--med)}.run-pill.na{background:var(--faint)}
.run-err{color:var(--crit);font-size:12px}

/* === FOOTER === */
.footer{color:var(--faint);font-size:12px;text-align:center;padding:var(--s5) 0;border-top:1px solid var(--line);margin-top:var(--s4)}
"""

JS = r"""
function show(id,el){document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
document.querySelectorAll('.tab').forEach(t=>{t.classList.remove('active');t.setAttribute('aria-selected','false');});
document.getElementById(id).classList.add('active');
if(!el)el=document.querySelector('.tab[data-id="'+id+'"]');
if(el){el.classList.add('active');el.setAttribute('aria-selected','true');}
if(history.replaceState)history.replaceState(null,'','#'+id);
if(id==='runs')loadRuns(true);}
// Jump from the queue straight to a ticker's evidence card (open + scroll + flash).
function gotoPkg(tk){show('packages');var c=document.getElementById('pkg-'+tk);
if(c){c.open=true;c.scrollIntoView({behavior:'smooth',block:'start'});
c.classList.add('flash');setTimeout(function(){c.classList.remove('flash');},1400);}}
function filt(p){document.querySelectorAll('#overview [data-priority]').forEach(r=>{
r.style.display=(p==='ALL'||r.getAttribute('data-priority')===p)?'':'none';});}
function toggleNav(){
  var s=document.getElementById('sidebar'),ps=document.getElementById('pageShell');
  var c=s.classList.toggle('collapsed');
  ps.classList.toggle('nav-collapsed',c);
  document.getElementById('navToggle').textContent=c?'☰':'✕';
  try{localStorage.setItem('navCollapsed',c?'1':'0');}catch(e){}
}
window.addEventListener('DOMContentLoaded',function(){
  // Style non-numeric KPI values (e.g. "live", "abstaining", "—") at smaller text size
  document.querySelectorAll('.kpi-num').forEach(function(el){
    if(!/^[\d.,+\-$%\/]+$/.test(el.textContent.trim()))el.classList.add('kpi-text');
  });
  var h=location.hash.slice(1);
  if(h){var t=document.querySelector('.tab[data-id="'+h+'"]');if(t)t.click();}
  try{if(localStorage.getItem('navCollapsed')==='1'){
    document.getElementById('sidebar').classList.add('collapsed');
    document.getElementById('pageShell').classList.add('nav-collapsed');
    document.getElementById('navToggle').textContent='☰';
  }}catch(e){}
});

// === Runs: live status polling + re-run control (talks to the LOCAL serve.py) ===
function _tok(){try{return new URLSearchParams(location.search).get('token')||'';}catch(e){return '';}}
function _u(p){var t=_tok();return p+(t?('?token='+encodeURIComponent(t)):'');}
function _pill(s){var c={done:'ok',error:'err',in_progress:'run'}[s]||'na';return '<span class="run-pill '+c+'">'+(s||'pending')+'</span>';}
function _esc(s){return String(s==null?'':s).replace(/[&<>]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
var _lastManifest=null,_runFails=0,_runPollStop=false;
function _failedTickers(){var t=(_lastManifest&&_lastManifest.tickers)||{};
  return Object.keys(t).filter(function(k){return (t[k]||{}).status==='error';});}
function loadRuns(force){
  var panel=document.getElementById('runs');
  if(!panel||!panel.classList.contains('active'))return;
  if(force){_runFails=0;_runPollStop=false;}   // manual open/retry resets backoff
  if(_runPollStop)return;                        // paused after repeated failures
  fetch(_u('/run_manifest.json'),{cache:'no-store'}).then(function(r){
    if(!r.ok)throw new Error('HTTP '+r.status);return r.json();
  }).then(function(m){
    _runFails=0;_lastManifest=m;
    var tickers=m.tickers||{};var uni=m.universe||Object.keys(tickers);
    var running=!m.finished_utc;
    document.getElementById('runsMeta').innerHTML='Run <b>'+_esc(m.run_id||'—')+'</b> · mode '+_esc(m.mode||'?')+' · '+
      (running?'<span class="run-pill run">in progress</span>':'finished '+_esc(m.finished_utc||''))+
      ' · '+Object.keys(tickers).length+'/'+(uni.length||Object.keys(tickers).length)+' tickers';
    document.getElementById('runsBody').innerHTML=uni.map(function(t){
      var i=tickers[t]||{};
      return '<tr><td><b>'+_esc(t)+'</b></td><td>'+_pill(i.status)+'</td><td>'+_esc(i.priority||'')+
        '</td><td>'+_esc(i.watch_score!=null?i.watch_score:'')+'</td><td>'+_esc(i.ms!=null?i.ms:'')+
        '</td><td>'+_esc(i.mode||(m.mode||''))+(i.error?(' <span class="run-err">'+_esc(i.error)+'</span>'):'')+'</td></tr>';
    }).join('');
    if(running)setTimeout(loadRuns,2000);
  }).catch(function(e){
    _runFails++;if(_runFails>=3)_runPollStop=true;  // back off after repeated errors
    document.getElementById('runsMeta').innerHTML='<span style="color:var(--faint)">No run yet, or live status needs the local server: <code>python3 serve.py</code> ('+_esc(e.message||e)+')'+(_runPollStop?' — polling paused after repeated errors; switch to this tab to retry.':'')+'</span>';
    document.getElementById('runsBody').innerHTML='';
  });
}
function rerun(failed){
  var msg=document.getElementById('runsMsg');
  var body={live:document.getElementById('runLive').checked};
  if(failed){
    // Don't fire a request that 400s when nothing failed (avoids a console error).
    if(_lastManifest&&_failedTickers().length===0){
      msg.textContent='Nothing failed in the last run — nothing to re-run.';return;}
    body.failed=true;
  }
  else{
    var raw=(document.getElementById('runTickers').value||'').trim();
    if(!raw){msg.textContent='Enter at least one ticker.';return;}
    body.tickers=raw.split(/[\s,]+/).filter(Boolean);
  }
  msg.textContent='Starting…';
  fetch(_u('/api/rerun'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
   .then(function(r){return r.text().then(function(t){return {ok:r.ok,status:r.status,t:t};});})
   .then(function(r){
     if(r.ok){var j={};try{j=JSON.parse(r.t);}catch(e){}
       msg.textContent='Started run '+(j.run_id||'')+' ('+(j.mode||'')+': '+((j.universe||[]).join(', '))+')';
       setTimeout(function(){loadRuns(true);},400);
     }else{msg.textContent='Could not start run ('+r.status+'): '+r.t.replace(/^\d+\s*/,'').replace(/^Bad Request:\s*/,'');}
   }).catch(function(e){msg.textContent='Request failed: '+(e.message||e)+' — is serve.py running?';});
}
// Examiner labels a package (closes the human-in-the-loop feedback). POSTs to
// serve.py; degrades gracefully when the dashboard is opened as a file:// (no server).
function label(file,lbl,btn){
  var row=btn.closest('.lbl-actions'); var st=row.querySelector('.lbl-status');
  var ni=row.querySelector('.lbl-note'); var note=ni?(ni.value||'').trim():'';
  st.textContent='saving…';
  fetch(_u('/api/label'),{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({package:file,label:lbl,note:note})})
   .then(function(r){return r.text().then(function(t){return {ok:r.ok,status:r.status,t:t};});})
   .then(function(r){
     if(r.ok){var j={};try{j=JSON.parse(r.t);}catch(e){}
       st.textContent='✓ labeled '+(j.label||lbl)+' (ledger: '+(j.n_labels||'?')+') — retrain on the Learning tab';
       row.querySelectorAll('.lbl-btn').forEach(function(b){b.disabled=true;});
       if(ni)ni.disabled=true;
     }else{st.textContent='✗ '+r.t.replace(/\n/g,' ').replace(/^\d+\s*/,'').slice(0,90);}
   }).catch(function(e){st.textContent='✗ needs serve.py running (python3 serve.py)';});
}
// Retrain the model on the current ledger labels (completes label->learn->advise).
function retrain(btn){
  var st=btn.parentNode.querySelector('.lbl-status'); btn.disabled=true; st.textContent='retraining… (runs train_model.py)';
  fetch(_u('/api/retrain'),{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})
   .then(function(r){return r.text().then(function(t){return {ok:r.ok,status:r.status,t:t};});})
   .then(function(r){ btn.disabled=false;
     if(r.ok){var j={};try{j=JSON.parse(r.t);}catch(e){}
       st.textContent = j.abstain ? ('model abstains — '+(j.reason||'need more labels'))
         : ('✓ retrained · AUC '+(j.cv_auc||'?')+' · n='+(j.n_total||'?')+' ('+(j.n_real_labels||0)+' real)');
     }else{st.textContent='✗ '+r.t.replace(/\n/g,' ').replace(/^\d+\s*/,'').slice(0,90);}
   }).catch(function(e){btn.disabled=false;st.textContent='✗ needs serve.py running (python3 serve.py)';});
}
setInterval(loadRuns,4000);
"""
