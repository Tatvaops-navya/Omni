import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { formatDistanceToNow } from 'date-fns'
import { MessageSquare, Mic, ChevronRight } from 'lucide-react'
import clsx from 'clsx'

const STAGE_COLORS: Record<string, string> = {
  ROUTING: 'bg-amber-600/30 text-amber-300',
  DISCOVERY: 'bg-slate-600 text-slate-300',
  DETAIL_COLLECTION: 'bg-indigo-600/30 text-indigo-300',
  CONFIRMATION: 'bg-teal-600/30 text-teal-300',
  SUMMARY_GENERATED: 'bg-green-600/30 text-green-300',
}

export default function Sessions() {
  const [sessions, setSessions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    api.sessions().then(d => { setSessions(d.sessions); setLoading(false) })
    const id = setInterval(() => api.sessions().then(d => setSessions(d.sessions)), 10000)
    return () => clearInterval(id)
  }, [])

  if (loading) return <div className="p-6 text-slate-500">Loading sessions...</div>

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="page-title">Sessions</h1>
          <p className="text-sm text-slate-500 mt-1">{sessions.length} total · refreshes every 10s</p>
        </div>
      </div>

      {sessions.length === 0 ? (
        <div className="card text-center py-12 text-slate-500">
          No active sessions yet. Waiting for conversations...
        </div>
      ) : (
        <div className="space-y-2">
          {sessions.map(s => (
            <div
              key={s.session_id}
              onClick={() => navigate(`/krsna/sessions/${s.session_id}`)}
              className="card flex items-center gap-4 cursor-pointer hover:border-indigo-500/40 transition-colors"
            >
              {/* Channel icon */}
              <div className={clsx(
                'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0',
                s.channel === 'voice' ? 'bg-teal-600/20' : 'bg-indigo-600/20'
              )}>
                {s.channel === 'voice'
                  ? <Mic className="w-4 h-4 text-teal-400" />
                  : <MessageSquare className="w-4 h-4 text-indigo-400" />
                }
              </div>

              {/* Main info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-theme-primary truncate">
                    {s.phone_number}
                  </span>
                  <span className={clsx('badge', STAGE_COLORS[s.conversation_stage] ?? '')}>
                    {s.conversation_stage}
                  </span>
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                  {s.active_consultant && <span>{s.active_consultant}</span>}
                  {s.service_category && <span>· {s.service_category}</span>}
                  {s.lead_tier && <span>· {s.lead_tier}</span>}
                  <span>· {s.fields_collected} fields</span>
                  <span>·</span>
                  <span>{s.turn_count} turns</span>
                  <span>·</span>
                  <span>{formatDistanceToNow(new Date(s.last_active), { addSuffix: true })}</span>
                </div>
              </div>

              {/* Field completion bar */}
              <div className="w-24 flex-shrink-0 hidden sm:block">
                <div className="h-1 bg-navy-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all"
                    style={{ width: `${s.field_completion_pct}%` }}
                  />
                </div>
                <p className="text-xs text-slate-600 text-right mt-0.5">{s.field_completion_pct}%</p>
              </div>

              <ChevronRight className="w-4 h-4 text-slate-600 flex-shrink-0" />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
