import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { ArrowLeft, RotateCcw, FileText, X, CheckCircle, Circle } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const REQUIRED = ['client_name','property_type','city','service_type',
                  'area_sqft','configuration','rooms_to_design','budget_range','timeline']

export default function SessionDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [session, setSession] = useState<any>(null)
  const [activeTrace, setActiveTrace] = useState<number>(0)

  const load = () => id && api.session(id).then(setSession)

  useEffect(() => { load(); const i = setInterval(load, 8000); return () => clearInterval(i) }, [id])

  if (!session) return <div className="p-6 text-slate-500">Loading...</div>

  const lastTrace = session.thinking_traces?.[session.thinking_traces.length - 1]

  const handleReset = async () => {
    await api.resetSession(id!); toast.success('Session reset'); navigate('/krsna/sessions')
  }
  const handleForceSummary = async () => {
    await api.forceSummary(id!); toast.success('Summary generated!'); load()
  }
  const handleClose = async () => {
    await api.closeSession(id!); toast.success('Session closed'); load()
  }

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/krsna/sessions')} className="btn-ghost">
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-theme-primary">{session.phone_number}</h1>
          <p className="text-xs text-slate-500">{session.channel} · {session.conversation_stage}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleForceSummary} className="btn-ghost text-teal-400 hover:text-teal-300">
            <FileText className="w-4 h-4" /> Force Summary
          </button>
          <button onClick={handleReset} className="btn-ghost text-amber-400 hover:text-amber-300">
            <RotateCcw className="w-4 h-4" /> Reset
          </button>
          <button onClick={handleClose} className="btn-ghost text-red-400 hover:text-red-300">
            <X className="w-4 h-4" /> Close
          </button>
        </div>
      </div>

      {/* Main split pane */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* LEFT — Conversation */}
        <div className="lg:col-span-3 card flex flex-col" style={{ maxHeight: '72vh' }}>
          <h3 className="text-sm font-medium text-slate-400 mb-3 flex-shrink-0">Conversation</h3>
          <div className="flex-1 overflow-y-auto space-y-3 pr-1">
            {session.conversation_history.map((msg: any, i: number) => (
              <div key={i} className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div className={clsx(
                  'max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm',
                  msg.role === 'user'
                    ? 'bg-indigo-600/30 text-slate-200 rounded-br-sm'
                    : 'bg-navy-700 text-slate-300 rounded-bl-sm'
                )}>
                  <p className="text-[10px] font-medium mb-1 opacity-60">
                    {msg.role === 'user' ? 'Client' : '🪷 Aadhya'}
                  </p>
                  {msg.content}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT — AI State */}
        <div className="lg:col-span-2 space-y-4">
          {/* Fields */}
          <div className="card">
            <h3 className="text-sm font-medium text-slate-400 mb-3">
              Extracted Fields
              <span className="ml-2 text-indigo-400 font-bold">{session.field_completion_pct}%</span>
            </h3>
            <div className="space-y-1.5">
              {REQUIRED.map(field => {
                const val = session.extracted_fields[field]
                const done = session.completed_fields.includes(field)
                return (
                  <div key={field} className="flex items-center gap-2 text-xs">
                    {done
                      ? <CheckCircle className="w-3.5 h-3.5 text-teal-400 flex-shrink-0" />
                      : <Circle className="w-3.5 h-3.5 text-slate-600 flex-shrink-0" />
                    }
                    <span className={clsx('font-medium', done ? 'text-slate-300' : 'text-slate-600')}>
                      {field}
                    </span>
                    {val && <span className="text-teal-400 truncate">{String(val)}</span>}
                  </div>
                )
              })}
            </div>
          </div>

          {/* AI Thinking trace */}
          {lastTrace && (
            <div className="card">
              <h3 className="text-sm font-medium text-slate-400 mb-3">AI Thinking Trace</h3>
              <div className="space-y-2 text-xs">
                <div>
                  <span className="text-slate-500">Next Target</span>
                  <p className="text-indigo-300 font-semibold mt-0.5">
                    → {lastTrace.next_field_target || 'confirmation'}
                  </p>
                </div>
                {Object.keys(lastTrace.detected_fields || {}).length > 0 && (
                  <div>
                    <span className="text-slate-500">Detected this turn</span>
                    <div className="mt-1 space-y-0.5">
                      {Object.entries(lastTrace.detected_fields).map(([k, v]) => (
                        <div key={k} className="text-teal-300">
                          {k}: {String(v)}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div>
                  <span className="text-slate-500">Stage</span>
                  <p className="text-theme-secondary mt-0.5">{lastTrace.stage_after}</p>
                </div>
                {lastTrace.guardrail_triggered && (
                  <div className="text-amber-400">⚠ Guardrail triggered</div>
                )}
              </div>
            </div>
          )}

          {/* Summary */}
          {session.summary_generated && session.summary && (
            <div className="card border-teal-500/30">
              <h3 className="text-sm font-medium text-teal-400 mb-2">✅ Summary Generated</h3>
              <p className="text-xs text-slate-400">{session.summary.project_overview}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
