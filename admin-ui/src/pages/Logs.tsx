import { useEffect, useState } from 'react'
import { api } from '../api/client'
import clsx from 'clsx'

const EVENT_COLORS: Record<string, string> = {
  SESSION_START:       'text-teal-400',
  USER_MESSAGE:        'text-green-400',
  GEMINI_RESPONSE:     'text-blue-400',
  EXTRACTED_FIELDS:    'text-yellow-400',
  NEXT_FIELD_DECISION: 'text-purple-400',
  STAGE_TRANSITION:    'text-cyan-400',
  SUMMARY_GENERATED:   'text-green-300',
  GUARDRAIL_TRIGGERED: 'text-amber-400',
  API_ERROR:           'text-red-400',
}

const ALL_EVENTS = Object.keys(EVENT_COLORS)

export default function Logs() {
  const [logs, setLogs] = useState<any[]>([])
  const [sessionFilter, setSessionFilter] = useState('')
  const [eventFilter, setEventFilter] = useState('')

  const load = () =>
    api.logs({ session_id: sessionFilter || undefined, event: eventFilter || undefined }).then(d => setLogs(d.logs || []))

  useEffect(() => { load(); const i = setInterval(load, 6000); return () => clearInterval(i) }, [sessionFilter, eventFilter])

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="page-title">Logs</h1>
        <p className="text-sm text-slate-500 mt-1">{logs.length} entries · refreshes every 6s</p>
      </div>

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <input
          className="input w-56"
          placeholder="Filter by session ID..."
          value={sessionFilter}
          onChange={e => setSessionFilter(e.target.value)}
        />
        <select
          className="input w-48"
          value={eventFilter}
          onChange={e => setEventFilter(e.target.value)}
        >
          <option value="">All events</option>
          {ALL_EVENTS.map(e => <option key={e} value={e}>{e}</option>)}
        </select>
      </div>

      {/* Log feed */}
      <div className="card p-0 overflow-hidden">
        <div className="overflow-y-auto max-h-[60vh] font-mono text-xs">
          {logs.length === 0 ? (
            <div className="p-6 text-center text-slate-500">No logs yet.</div>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="px-4 py-2  flex gap-3">
                <span className="text-slate-600 flex-shrink-0 w-20">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span className={clsx('flex-shrink-0 w-36', EVENT_COLORS[log.event] ?? 'text-slate-400')}>
                  {log.event}
                </span>
                <span className="text-slate-500 flex-shrink-0 w-32 truncate">
                  {log.session_id}
                </span>
                <span className="text-slate-400 truncate">
                  {JSON.stringify(
                    Object.fromEntries(
                      Object.entries(log).filter(([k]) => !['event','session_id','timestamp'].includes(k))
                    )
                  )}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
