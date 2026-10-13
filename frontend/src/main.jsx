import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const initial = `def split_cents(total, people):\n    return [round(total / people)] * people`;
function download(report) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));
  const a = document.createElement('a'); a.href=url; a.download='repairgate-report.json'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function App(){
  const [report,setReport]=useState(null), [active,setActive]=useState(0), [busy,setBusy]=useState(false), [error,setError]=useState(''), [guide,setGuide]=useState(false);
  const attempt=report?.attempts[active];
  async function run(){
    setBusy(true); setError(''); setReport(null);
    try{const r=await fetch('/api/demo',{method:'POST'}); if(!r.ok)throw Error('Verification unavailable. Check the local server and try again.'); setReport(await r.json()); setActive(2);}
    catch(e){setError(e.message);} finally{setBusy(false);}
  }
  return <><a className="skip" href="#workspace">Skip to workspace</a><header><a className="brand" href="/">RG<span>RepairGate</span></a><span className="version">LOCAL / v0.1</span><button className="quiet" onClick={()=>setGuide(!guide)} aria-expanded={guide}>CLI guide</button></header>
    <main id="workspace"><section className="intro"><div><p className="eyebrow">SELF-CORRECTING CODE ASSISTANT</p><h1>A patch needs<br/>more than a promise.</h1><p className="lede">Keep tests protected. Catch overfitting. Accept a repair only after the checks pass.</p></div><div className="runbox"><span className="tag">Recorded proposal demo</span><p>Three proposed repairs. One independent gate.<br/>Run the actual tests in disposable copies.</p><button className="primary" onClick={run} disabled={busy}>{busy?'Verifying candidates…':report?'Run verification again':'Run verification'}</button><span className="small">Original source stays untouched.</span></div></section>
    {guide&&<section className="guide"><h2>Use your own trusted pure-function repository</h2><p>The CLI supports local Ollama or recorded replacement proposals. The web demo only executes the bundled fixture.</p><pre>repairgate repair ./my-project --holdout ../holdout-tests\n  --task "Fix the rounding bug" --ollama qwen2.5:7b\n  --trust-local-code --output repair-report.json</pre><p>Requires src/, tests/__init__.py, stdlib-only tests, and external holdout tests. This version permits pure functions with an explicit call allowlist. Imports and attributes are blocked. Repository code runs locally. Disposable copies protect originals; they are not a security sandbox. Review accepted replacements before applying them.</p></section>}
    <div role="status" className="statusbar">{busy?'Running visible tests, holdout tests and file integrity checks…':report?`Decision: ${report.status.toUpperCase()} · Original unchanged: ${report.original_unchanged?'yes':'no'}`:'Ready. The starting function loses a cent when splitting 100 between three people.'}</div>
    {error&&<p role="alert" className="error">{error}</p>}
    <section className="workspace"><aside><div className="paneltitle"><h2>Verification path</h2><span>{report?`0${active+1}`:'01'} / 03</span></div><div className="baseline"><p className="eyebrow">BASELINE</p><strong>{report?'Failure reproduced':'Rounding regression'}</strong><p>100 cents ÷ 3 people</p><code>Expected [34, 33, 33]<br/>Actual [33, 33, 33]</code></div>
    <ol className="steps">{['Modify the tests','Hardcode the example','Repair the algorithm'].map((name,i)=><li key={name}><button disabled={!report} aria-pressed={active===i&&!!report} onClick={()=>setActive(i)}><span className="stepnumber">0{i+1}</span><span>{name}<small>{report?report.attempts[i]?.status:'Awaiting verification'}</small></span></button></li>)}</ol>
    <div className="invariant"><span className="eyebrow">HOLDOUT CONTRACT</span><p>Every cent conserved.<br/>Shares differ by at most one.<br/>Invalid inputs rejected.</p><span className="small">35 unseen input combinations + invalid inputs</span></div></aside>
    <article><div className="paneltitle"><h2>{attempt?`Proposal ${attempt.number} / decision`:'src/money.py / starting code'}</h2><span className={attempt?.status==='accepted'?'good':'tag'}>{attempt?.status||'unverified'}</span></div><p className="decision">{attempt?.reason||'The visible test detects the loss. Holdout checks guard against fixes that only match the example.'}</p>
    <pre className="code" aria-label={attempt?'Proposed code diff':'Starting code'}>{attempt?.diff||initial}</pre>
    <div className="checks">{['visible','holdout'].map(key=><div key={key}><span>{key==='visible'?'Visible tests':'Holdout tests'}</span><strong>{attempt?.[key]?`${attempt[key].passed?'PASS':'FAIL'} · ${attempt[key].tests} tests`:attempt?'BLOCKED':'Pending'}</strong></div>)}<div><span>File integrity</span><strong>{attempt?.integrity_passed===true?'PASS':attempt?'BLOCKED':'Pending'}</strong></div></div>
    {attempt?.visible&&<details><summary>Test output</summary><pre>{attempt.visible.log}{'\nHOLDOUT\n'}{attempt.holdout.log}</pre></details>}
    {report&&<div className="export"><button onClick={()=>download(report)}>Export audit report</button><p>Includes code diff, gate decisions, test output and source digests.</p></div>}
    </article></section><footer><span>Verification is bounded by the tests you provide.</span><span>AI proposes. The gate checks.</span></footer></main></>;
}
createRoot(document.getElementById('root')).render(<App/>);
