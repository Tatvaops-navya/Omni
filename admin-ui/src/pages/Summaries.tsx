import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { Download } from 'lucide-react'

export default function Summaries() {
  const [summaries, setSummaries] = useState<any[]>([])

  useEffect(() => { api.summaries().then(d => setSummaries(d.summaries || [])) }, [])

  const exportJSON = (s: any) => {
    const blob = new Blob([JSON.stringify(s, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url
    a.download = `summary_${s.session_id || 'export'}.json`; a.click()
  }

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="page-title">Project Summaries</h1>
        <p className="text-sm text-slate-500 mt-1">{summaries.length} generated</p>
      </div>

      {summaries.length === 0 ? (
        <div className="card text-center py-12 text-slate-500">
          Summaries will appear here when enquiries are completed.
        </div>
      ) : (
        <div className="space-y-4">
          {summaries.map((s, i) => (
            <div key={i} className="card border-indigo-500/20 space-y-4">
              {/* Header */}
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-semibold text-indigo-300">
                    {s.technical_specs || 'Project Summary'}
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">{s.session_id}</p>
                </div>
                <button onClick={() => exportJSON(s)} className="btn-ghost">
                  <Download className="w-3.5 h-3.5 mr-1" /> JSON
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {[
                  ['📌 Next Step', s.next_step],
                  ['📋 Overview', s.project_overview],
                  ['💰 Budget & Area', s.estimated_scope],
                  ['📅 Timeline', s.timeline],
                  ['🎨 Design Direction', s.design_direction],
                  ['✅ Execution Readiness', s.execution_readiness],
                ].map(([label, value]) => value && (
                  <div key={label as string} className="bg-slate-100 dark:bg-navy-900 rounded-lg p-3">
                    <p className="text-slate-500 mb-1">{label}</p>
                    <p className="text-slate-300">{value}</p>
                  </div>
                ))}
              </div>

              {s.scope_of_work?.length > 0 && (
                <div className="bg-slate-100 dark:bg-navy-900 rounded-lg p-3 text-xs">
                  <p className="text-slate-500 mb-2">🏗️ Scope of Work</p>
                  <div className="flex flex-wrap gap-1.5">
                    {s.scope_of_work.map((item: string, j: number) => (
                      <span key={j} className="badge bg-indigo-600/20 text-indigo-300">{item}</span>
                    ))}
                  </div>
                </div>
              )}

              {s.special_considerations && (
                <div className="bg-slate-100 dark:bg-navy-900 rounded-lg p-3 text-xs">
                  <p className="text-slate-500 mb-1">⭐ Special Considerations</p>
                  <p className="text-slate-300">{s.special_considerations}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
