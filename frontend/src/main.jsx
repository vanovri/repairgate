import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

function download(report) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type: 'application/json'}));
  const a = document.createElement('a');
  a.href = url; a.download = `repairgate-${report.case.id}-report.json`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function App() {
  const [catalog, setCatalog] = useState([]), [caseId, setCaseId] = useState('bill-splitter');
  const [report, setReport] = useState(null), [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [guide, setGuide] = useState(false);
  const selected = report?.case || catalog.find(item => item.id === caseId);
  const attempt = report?.attempts[active];
  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/cases', {signal: controller.signal}).then(response => {
      if (!response.ok) throw Error('Could not load the bundled cases. Check the local server and reload.');
      return response.json();
    }).then(setCatalog).catch(error => {if (error.name !== 'AbortError') setError(error.message);});
    return () => controller.abort();
  }, []);
  async function run() {
    setBusy(true); setError(''); setReport(null);
    try {
      const response = await fetch(`/api/demo?case_id=${encodeURIComponent(caseId)}`, {method: 'POST'});
      if (!response.ok) throw Error('Verification unavailable. Check the local server and try again.');
      const result = await response.json();
      setReport(result); setActive(result.attempts.length - 1);
    } catch (error) {setError(error.message);} finally {setBusy(false);}
  }
  function changeCase(event) {
    setCaseId(event.target.value); setReport(null); setActive(0); setError('');
  }
  return <>
    <a className="skip" href="#workspace">Skip to workspace</a>
    <header><a className="brand" href="/">RG<span>RepairGate</span></a><span className="version">LOCAL / v0.2</span><button className="quiet" onClick={() => setGuide(!guide)} aria-expanded={guide}>CLI guide</button></header>
    <main id="workspace">
      <section className="intro">
        <div><p className="eyebrow">REGRESSION LAB</p><h1>Passing the example <br/>is only the start.</h1><p className="lede">Replay three synthetic cases. Inspect which repairs pass the examples, which fail independent checks, and why.</p></div>
        <div className="runbox">
          <span className="tag">Recorded proposals · actual test runs</span>
          <label className="case-label" htmlFor="case">Regression case</label>
          <select id="case" value={caseId} onChange={changeCase} disabled={busy || !catalog.length}>{catalog.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select>
          <p>{selected?.summary || 'Loading bundled cases…'}</p>
          <button className="primary" onClick={run} disabled={busy || !selected}>{busy ? 'Verifying candidates…' : report ? 'Run verification again' : 'Run verification'}</button>
          <span className="small">Each candidate starts from the original. No live model required.</span>
        </div>
      </section>
      {guide && <section className="guide"><h2>Replay all cases or use your own trusted repository</h2><pre>{'repairgate lab --output regression-lab-report.json\nrepairgate demo --case sample-window\n\nrepairgate repair ./my-project --holdout ../holdout-tests\n  --task "Fix the rounding bug" --ollama qwen2.5:7b\n  --trust-local-code --output repair-report.json'}</pre><p>The web demo runs only bundled fixtures. The CLI accepts trusted pure-function repositories with src/, tests/__init__.py and stdlib-only tests. Imports and attributes are blocked. Disposable copies protect originals; they are not a security sandbox. Review accepted replacements before applying them.</p></section>}
      <div role="status" className="statusbar">{busy ? 'Running visible tests, independent checks and file integrity checks…' : report ? `Run outcome: ${report.status.toUpperCase()} · Original unchanged: ${report.original_unchanged ? 'yes' : 'no'}` : selected ? `Ready. ${selected.example} should return ${selected.expected}.` : 'Loading cases…'}</div>
      {error && <p role="alert" className="error">{error}</p>}
      <section className="workspace">
        <aside>
          <div className="paneltitle"><h2>Verification path</h2><span>{report ? `0${active + 1}` : '01'} / 03</span></div>
          <div className="baseline"><p className="eyebrow">BASELINE</p><strong>{report ? 'Failure reproduced' : selected?.title}</strong><p>{selected?.example}</p><code>Expected {selected?.expected}<br/>Actual {selected?.actual}</code></div>
          <ol className="steps">{selected?.proposal_names.map((name, index) => <li key={name}><button disabled={!report} aria-pressed={active === index && !!report} onClick={() => setActive(index)}><span className="stepnumber">0{index + 1}</span><span>{name}<small>{report ? report.attempts[index]?.status : 'Awaiting verification'}</small></span></button></li>)}</ol>
          <div className="invariant"><span className="eyebrow">PUBLIC INDEPENDENT CHECKS</span><p>{selected?.contract}</p><span className="small">{selected?.coverage}. These fixtures are public, not a sealed benchmark.</span></div>
        </aside>
        <article>
          <div className="paneltitle"><h2>{attempt ? `Proposal ${attempt.number} / decision` : `${selected?.source_path || 'Source'} / starting code`}</h2><span className={attempt?.status === 'accepted' ? 'good' : 'tag'}>{attempt?.status || 'unverified'}</span></div>
          <p className="decision">{attempt?.reason || 'A hardcoded repair can pass the visible examples. Independent checks cover more inputs and invariants.'}</p>
          <pre className="code" aria-label={attempt ? 'Proposed code diff' : 'Starting code'}>{attempt?.diff || selected?.starting_code}</pre>
          <div className="checks">{['visible', 'holdout'].map(key => <div key={key}><span>{key === 'visible' ? 'Visible tests' : 'Independent checks'}</span><strong>{attempt?.[key] ? `${attempt[key].passed ? 'PASS' : 'FAIL'} · ${attempt[key].tests} tests` : attempt ? 'BLOCKED' : 'Pending'}</strong></div>)}<div><span>File integrity</span><strong>{attempt?.integrity_passed === true ? 'PASS' : attempt?.integrity_passed === false ? 'FAIL' : attempt ? 'BLOCKED' : 'Pending'}</strong></div></div>
          {attempt?.starting_source_digest && <section className="audit" aria-label="Replay evidence"><div><span>Same starting source</span><strong>{attempt.starting_source_digest === report.source_digest ? 'MATCH' : 'MISMATCH'}</strong></div><div><span>Protected test files</span><strong>{attempt.protected_tests_unchanged ? 'UNCHANGED' : 'CHANGED'}</strong></div><details><summary>SHA256 evidence</summary><p>Starting source</p><code>{attempt.starting_source_digest}</code><p>Protected tests before / after</p><code>{attempt.protected_tests_before_digest}<br/>{attempt.protected_tests_after_digest}</code><p>Proposal</p><code>{attempt.proposal_digest}</code></details></section>}
          {attempt?.visible && <details><summary>Test output</summary><pre>{attempt.visible.log}{'\nINDEPENDENT CHECKS\n'}{attempt.holdout.log}</pre></details>}
          {report && <div className="export"><button onClick={() => download(report)}>Export audit report</button><p>Code diff, gate decisions, test output and SHA256 evidence for this run.</p></div>}
        </article>
      </section>
      <footer><span>Synthetic fixtures. Verification is bounded by test coverage.</span><span>Proposals are recorded. Decisions are computed.</span></footer>
    </main>
  </>;
}
createRoot(document.getElementById('root')).render(<App/>);
