import { AlertTriangle, Check, ChevronDown, Crown, ListChecks, Mail, StickyNote } from 'lucide-react'
import { useState } from 'react'
import { AGENTS, AGENT_ORDER } from '../meta'
import type { RunView, Seat } from '../runs'
import { reports as reportsOf } from '../runs'
import type { Draft, Note } from '../types'

export function Debrief({ run, seats }: { run: RunView | null; seats: Seat[] }) {
  const reports = reportsOf(run)
  const decision = run?.decision
  return (
    <div className="debrief">
      {decision ? (
        <section className="decision-card">
          <div className="decision-head">
            <span className="decision-icon"><Crown size={18} /></span>
            <div>
              <span className="eyebrow">The Boss’s call</span>
              <h3>{decision.decision}</h3>
            </div>
          </div>
          <p className="rationale">{decision.rationale}</p>
          {decision.human_actions_required.length > 0 && (
            <div className="for-you">
              <span className="eyebrow">For you, at the desk</span>
              <ol>{decision.human_actions_required.map((a, i) => <li key={i}>{a}</li>)}</ol>
            </div>
          )}
          {decision.next_steps.length > 0 && (
            <details className="next">
              <summary>Next steps ({decision.next_steps.length})</summary>
              <ul>{decision.next_steps.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </details>
          )}
        </section>
      ) : (
        <div className="empty-mini">The Boss’s decision appears here when the run finishes.</div>
      )}

      <h4 className="sub-head"><ListChecks size={15} /> What each agent did</h4>
      <div className="agent-grid">
        {AGENT_ORDER.filter((a) => a !== 'boss').map((key) => {
          const a = AGENTS[key]
          const seat = seats.find((s) => s.agent === key)
          const list = reports[key] ?? []
          return (
            <article
              key={key}
              className={`agent-card ${list.length ? '' : 'quiet'}`}
              style={{ ['--agent' as string]: a.color, ['--agent-soft' as string]: a.soft }}
            >
              <header>
                <span className="who-icon big"><a.Icon size={16} /></span>
                <div>
                  <b>{a.name}</b>
                  <span className="agent-card-meta">
                    {list.length ? `${seat?.toolCalls ?? 0} tool calls · ${list.length} report${list.length > 1 ? 's' : ''}` : seat?.state === 'working' ? 'working now…' : 'not called on this ticket'}
                  </span>
                </div>
              </header>
              {list.map((r, i) => (
                <div key={i} className="agent-report">
                  <p>{r.summary}</p>
                  {r.actions_taken.length > 0 && (
                    <ul className="did">{r.actions_taken.map((x, j) => <li key={j}><Check size={12} /> {x}</li>)}</ul>
                  )}
                  {r.blockers.length > 0 && (
                    <ul className="blockers">{r.blockers.map((x, j) => <li key={j}><AlertTriangle size={12} /> {x}</li>)}</ul>
                  )}
                  {r.facts.length > 0 && <Facts facts={r.facts} />}
                </div>
              ))}
            </article>
          )
        })}
      </div>
    </div>
  )
}

function Facts({ facts }: { facts: { statement: string; source_tool: string }[] }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="facts-box">
      <button className="link-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <ChevronDown size={13} className={open ? 'rot' : ''} /> {facts.length} facts, each with its source tool
      </button>
      {open && (
        <ul>
          {facts.map((f, i) => (
            <li key={i}>{f.statement} <span className="src">{f.source_tool}</span></li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function Drafts({ drafts, notes }: { drafts: Draft[]; notes: Note[] }) {
  return (
    <div className="drafts">
      {drafts.length === 0 && <div className="empty-mini"><Mail size={16} /> No drafts on this ticket yet.</div>}
      {drafts.map((d) => (
        <article key={d.id} className="letter">
          <span className="letter-stamp">Draft · not sent</span>
          <div className="letter-meta">
            <div><span>To</span>{d.recipient}</div>
            <div><span>Subject</span>{d.subject}</div>
            <div><span>Written by</span>{AGENTS[d.author as keyof typeof AGENTS]?.name ?? d.author} · draft #{d.id}</div>
          </div>
          <div className="letter-body">{d.body}</div>
        </article>
      ))}

      {notes.length > 0 && (
        <details className="notes">
          <summary><StickyNote size={14} /> Notes on file ({notes.length})</summary>
          <ol>
            {notes.map((n) => {
              const a = AGENTS[n.agent as keyof typeof AGENTS]
              return (
                <li key={n.id} style={{ ['--agent' as string]: a?.color ?? '#555' }}>
                  <b>{a?.name ?? n.agent}</b> {n.note}
                </li>
              )
            })}
          </ol>
        </details>
      )}
    </div>
  )
}
