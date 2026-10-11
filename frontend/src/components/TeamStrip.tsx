import { Check, Minus } from 'lucide-react'
import { AGENTS } from '../meta'
import type { Seat } from '../runs'

const STATE_LABEL = { idle: 'At their desk', working: 'Working…', done: 'Done', skipped: 'Not needed' } as const

export function TeamStrip({ seats }: { seats: Seat[] }) {
  return (
    <div className="team" role="list" aria-label="Agent team">
      {seats.map((s) => {
        const a = AGENTS[s.agent]
        return (
          <div
            key={s.agent}
            role="listitem"
            className={`seat seat-${s.state}`}
            style={{ ['--agent' as string]: a.color, ['--agent-soft' as string]: a.soft }}
            title={s.lastSaid ?? a.role}
          >
            <div className="avatar">
              <a.Icon size={20} strokeWidth={1.9} />
              {s.state === 'done' && <span className="avatar-badge"><Check size={11} strokeWidth={3} /></span>}
              {s.state === 'skipped' && <span className="avatar-badge muted"><Minus size={11} strokeWidth={3} /></span>}
            </div>
            <div className="seat-name">{a.name}</div>
            <div className="seat-role">{a.role}</div>
            <div className="seat-state">
              {s.state === 'working' ? (
                <span className="typing" aria-label="working"><i /><i /><i /></span>
              ) : (
                STATE_LABEL[s.state]
              )}
              {s.toolCalls > 0 && <span className="seat-tools">{s.toolCalls} tool{s.toolCalls === 1 ? '' : 's'}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}
