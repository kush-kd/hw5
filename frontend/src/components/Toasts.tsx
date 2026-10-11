import { CircleAlert, CircleCheck, Info } from 'lucide-react'

export interface Toast { id: number; tone: 'ok' | 'bad' | 'info'; title: string; body?: string }

export function Toasts({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: number) => void }) {
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map((t) => (
        <button key={t.id} className={`toast ${t.tone}`} onClick={() => dismiss(t.id)}>
          {t.tone === 'ok' ? <CircleCheck size={16} /> : t.tone === 'bad' ? <CircleAlert size={16} /> : <Info size={16} />}
          <div>
            <b>{t.title}</b>
            {t.body && <span>{t.body}</span>}
          </div>
        </button>
      ))}
    </div>
  )
}
