import React, { useEffect, useRef } from 'react'
import { Icon } from './icons.jsx'

const verdictLabels = {
  green: 'Credible based on available evidence',
  yellow: 'Not enough or mixed evidence',
  red: 'Material red flags found',
}

function Citation({source, quote}) {
  if (!source) return null
  let url
  try { url = new URL(source.url) } catch { return null }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return null
  return <div className="citation">
    {quote && <blockquote>“{quote}”</blockquote>}
    <a href={url.href} target="_blank" rel="noopener noreferrer">{source.title || url.hostname}<Icon name="external" /></a>
  </div>
}

export function Report({report, fixture, retry}) {
  const title = useRef(null)
  useEffect(() => { title.current?.focus() }, [report])
  const sources = new Map(report.sources.map(source => [source.id, source]))
  return <section className="report" aria-labelledby="report-title">
    <div className="report-top">
      <div>
        <span className="section-label">{fixture ? 'Synthetic fixture assessment' : 'Assessment'}</span>
        <h2 id="report-title" tabIndex="-1" ref={title}>{report.productName || 'Investigation result'}</h2>
        <span className="report-url">{report.inputUrl}</span>
      </div>
      {report.score !== null && <div className="score"><span className="section-label">Evidence score</span><strong>{report.score}<small> / 100</small></strong></div>}
    </div>
    <div className={'badge ' + (report.verdict || 'yellow')}><Icon name={report.verdict === 'green' ? 'check' : 'alert'} />{verdictLabels[report.verdict] || 'Investigation incomplete'}</div>
    <p className="interpretation">{report.interpretation}</p>
    {report.score !== null && <p className="score-note">Only confirmed checks earn points.</p>}
    <div className="findings">
      {report.checks.map(check => <article className="finding" key={check.id}>
        <div className="finding-title"><Icon name={check.id} /><h3>{check.label}</h3><span className="points">{check.points} / {check.maxPoints}</span></div>
        <div className="finding-body"><span className={'status ' + check.status}>{check.status}</span><p>{check.summary}</p>
          {check.evidence.map(({sourceId,quote}, i) => <Citation key={sourceId + '-' + i} source={sources.get(sourceId)} quote={quote}/>)}
        </div>
      </article>)}
    </div>
    {report.limitations.length > 0 && <div className="unknowns"><h3>Unknowns and limitations</h3><ul>{report.limitations.map((item,i) => <li key={i}>{item}</li>)}</ul></div>}
    {report.score === null && <button className="retry" onClick={retry}>Retry</button>}
  </section>
}
