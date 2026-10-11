import { ArrowRight, Ban, ChevronDown, CircleAlert, ClipboardCheck, Crown, Flag } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { AGENTS } from '../meta'
import { argsLine, clock } from '../format'
import type { FeedItem } from '../runs'
import type { AgentKey, ToolCall } from '../types'

function agentStyle(agent: AgentKey | null) {
  const a = AGENTS[agent ?? 'boss']
  return { ['--agent' as string]: a.color, ['--agent-soft' as string]: a.soft }
}

function Who({ agent, verb }: { agent: AgentKey | null; verb?: string }) {
  const a = AGENTS[agent ?? 'boss']
  return (
    <span className="who">
      <span className="who-icon"><a.Icon size={13} strokeWidth={2} /></span>
      <b>{a.name}</b>
      {verb && <span className="who-verb">{verb}</span>}
    </span>
  )
}

function Receipt({ call }: { call: ToolCall }) {
  if (call.tool === 'final_result') return <span className="receipt final"><ClipboardCheck size={12} /> files report</span>
  if (call.tool === 'delegate') {
    const to = AGENTS[(call.args.to_agent as AgentKey) ?? 'boss']
    return <span className="receipt handoff-receipt"><ArrowRight size={12} /> hands off to {to?.name}</span>
  }
  return (
    <span className="receipt" title={JSON.stringify(call.args, null, 1)}>
      <span className="receipt-tool">{call.tool}</span>
      {argsLine(call.args) && <span className="receipt-args">({argsLine(call.args)})</span>}
    </span>
  )
}

function Results({ results }: { results: { tool: string; result: string }[] }) {
  const [open, setOpen] = useState(false)
  if (!results.length) return null
  return (
    <div className="results">
      <button className="link-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <ChevronDown size={13} className={open ? 'rot' : ''} /> {open ? 'Hide' : 'Show'} what the MCP server returned ({results.length})
      </button>
      {open && (
        <div className="result-list">
          {results.map((r, i) => (
            <div key={i} className="result">
              <span className="receipt-tool">{r.tool}</span>
              <code>{r.result}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function LiveFloor({ items, running }: { items: FeedItem[]; running: boolean }) {
  const end = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLDivElement>(null)
  const count = items.length

  useEffect(() => {
    const el = box.current
    if (!el) return
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 220
    if (running || nearBottom) end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [count, running])

  return (
    <div className="floor" ref={box} aria-live="polite" aria-label="Live agent activity">
      {items.map((it) => {
        const e = it.e
        const indent = { marginLeft: `${Math.min(e.depth, 3) * 22}px` }
        switch (it.kind) {
          case 'start':
            return (
              <div key={e.event_id} className="floor-start">
                <Flag size={14} /> Ticket picked up · {clock(e.logged_at)}
              </div>
            )
          case 'pickup':
            return (
              <div key={e.event_id} className="floor-pickup" style={{ ...indent, ...agentStyle(e.agent) }}>
                <Who agent={e.agent} verb="picks up the task" />
              </div>
            )
          case 'think':
            return (
              <article key={e.event_id} className="bubble" style={{ ...indent, ...agentStyle(e.agent) }}>
                <header>
                  <Who agent={e.agent} verb={AGENTS[e.agent ?? 'boss'].voice} />
                  <time>{clock(e.logged_at)}</time>
                </header>
                {e.said && <p className="said">{e.said}</p>}
                <div className="receipts">{it.calls.map((c, i) => <Receipt key={i} call={c} />)}</div>
                <Results results={it.results} />
              </article>
            )
          case 'handoff': {
            const to = AGENTS[it.to] ?? AGENTS.boss
            return (
              <div key={e.event_id} className="handoff" style={indent}>
                <div className="handoff-line">
                  <Who agent={e.agent} />
                  <span className="handoff-arrow"><ArrowRight size={14} /></span>
                  <span className="who" style={agentStyle(it.to)}>
                    <span className="who-icon"><to.Icon size={13} /></span><b>{to.name}</b>
                  </span>
                </div>
                <blockquote>{it.task}</blockquote>
              </div>
            )
          }
          case 'refused':
            return (
              <div key={e.event_id} className="floor-note warn" style={indent}>
                <Ban size={13} /> {e.said}
              </div>
            )
          case 'report':
            return (
              <div key={e.event_id} className="report-filed" style={{ ...indent, ...agentStyle(e.agent) }}>
                <ClipboardCheck size={14} />
                <div>
                  <Who agent={e.agent} verb="files a report" />
                  <p>{it.report.summary}</p>
                </div>
              </div>
            )
          case 'decision':
            return (
              <div key={e.event_id} className="floor-decision">
                <Crown size={16} />
                <div>
                  <span className="eyebrow">The Boss’s call · {clock(e.logged_at)}</span>
                  <p>{it.decision.decision}</p>
                </div>
              </div>
            )
          case 'error':
            return (
              <div key={e.event_id} className="floor-note bad" style={indent}>
                <CircleAlert size={13} /> {e.said ?? e.event}
              </div>
            )
        }
      })}
      {running && (
        <div className="floor-working">
          <span className="typing"><i /><i /><i /></span> the team is working…
        </div>
      )}
      <div ref={end} />
    </div>
  )
}
