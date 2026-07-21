import { useEffect, useState } from 'react'
import { api, createSSEStream } from '../api/client'
import { CheckCircle, XCircle, AlertCircle, Activity } from 'lucide-react'
import clsx from 'clsx'

const SERVICE_PASTELS = [
  'pastel-mint',
  'pastel-lilac',
  'pastel-peach',
  'pastel-sky',
  'pastel-butter',
  'pastel-violet',
] as const

function StatusBadge({ status }: { status: string }) {
  const ok = status === 'ok' || status === 'configured'
  const warn = status === 'not_configured'
  return (
    <div
      className={clsx(
        'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold shrink-0',
        ok ? 'badge-success' : warn ? 'badge-warning' : 'badge-danger',
      )}
    >
      {ok ? <CheckCircle className="w-3.5 h-3.5" /> :
        warn ? <AlertCircle className="w-3.5 h-3.5" /> :
          <XCircle className="w-3.5 h-3.5" />}
      {status}
    </div>
  )
}

export default function SystemHealth() {
  const [health, setHealth] = useState<any>(null)
  const [liveEvents, setLiveEvents] = useState<any[]>([])
  const [esStatus, setEsStatus] = useState('connecting')

  useEffect(() => {
    api.health().then(setHealth)
    const id = setInterval(() => api.health().then(setHealth), 30000)

    const es = createSSEStream((data: any) => {
      if (data.event !== 'connected') {
        setLiveEvents(prev => [data, ...prev].slice(0, 50))
      }
      setEsStatus('connected')
    })
    es.onerror = () => setEsStatus('error')

    return () => { clearInterval(id); es.close() }
  }, [])

  const services = health?.services || {}
  const isHealthy = health?.overall === 'healthy'
  const serviceEntries = Object.entries(services)

  return (
    <div className="p-6 space-y-6 max-w-[1200px]">
      <div>
        <h1 className="page-title">System Health</h1>
        <p className="text-sm text-theme-muted mt-1">
          Overall:{' '}
          <span className={clsx(
            'font-medium capitalize',
            isHealthy ? 'text-[var(--success)]' : 'text-[var(--warning)]',
          )}>
            {health?.overall || 'checking...'}
          </span>
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {serviceEntries.map(([name, info]: [string, any], i) => {
          const pastel = SERVICE_PASTELS[i % SERVICE_PASTELS.length]
          return (
            <div
              key={name}
              className={clsx(
                'stat-card pastel flex items-center justify-between gap-3 !p-4',
                pastel,
              )}
            >
              <div className="min-w-0">
                <p className="stat-label text-sm font-semibold capitalize truncate">{name}</p>
                {info.model && (
                  <p className="text-xs text-theme-muted mt-0.5 truncate">{info.model}</p>
                )}
                {info.error && (
                  <p className="text-xs text-[var(--danger)] mt-1 truncate max-w-[200px]">{info.error}</p>
                )}
              </div>
              <StatusBadge status={info.status} />
            </div>
          )
        })}
      </div>

      <div className="chart-card">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-[var(--divider)]">
          <div className="flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-[var(--accent-soft)]">
              <Activity className="w-4 h-4 text-[var(--accent)]" />
            </span>
            <h3 className="text-sm font-semibold text-theme-primary">Live Monitor</h3>
          </div>
          <span className={clsx(
            'badge',
            esStatus === 'connected' ? 'badge-success' : esStatus === 'error' ? 'badge-danger' : 'badge-warning',
          )}>
            ● {esStatus}
          </span>
        </div>

        <div
          className="rounded-xl p-3 space-y-1.5 max-h-72 overflow-y-auto font-mono text-xs"
          style={{ background: 'var(--surface-sunken)' }}
        >
          {liveEvents.length === 0 ? (
            <p className="text-theme-muted py-8 text-center">Waiting for events...</p>
          ) : (
            liveEvents.map((ev, i) => (
              <div
                key={i}
                className="flex gap-3 px-2 py-1.5 rounded-lg hover:bg-[var(--surface)] transition-colors"
              >
                <span className="text-theme-muted flex-shrink-0 tabular-nums">
                  {new Date(ev.timestamp).toLocaleTimeString()}
                </span>
                <span className="text-[var(--accent)] flex-shrink-0 font-medium">{ev.event}</span>
                <span className="text-theme-secondary truncate">{ev.session_id}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
