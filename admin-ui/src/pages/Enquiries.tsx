import { useEffect, useState } from 'react'
import { api } from '../api/client'

const COMPACT_FIELDS = [
  'client_name',
  'city',
  'property_location',
  'preferred_contact_time',
  'willing_to_create_project',
  'property_type',
  'configuration',
] as const

function formatFieldLabel(field: string): string {
  return field.replace(/_/g, ' ')
}

function formatFieldValue(field: string, value: unknown): string {
  if (value == null || value === '') return '—'
  if (field === 'willing_to_create_project') {
    const v = String(value).trim().toLowerCase()
    if (v === 'no' || v === 'n') return 'No'
    if (v === 'yes' || v === 'y') return 'Yes'
  }
  return String(value)
}

function isProjectDeclined(fields: Record<string, unknown>): boolean {
  const v = String(fields.willing_to_create_project || '').trim().toLowerCase()
  return v === 'no' || v === 'n'
}

export default function Enquiries() {
  const [enquiries, setEnquiries] = useState<any[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => { api.enquiries().then(d => setEnquiries(d.enquiries || [])) }, [])

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-200">Enquiries</h1>
        <p className="text-sm text-slate-500 mt-1">{enquiries.length} collected</p>
      </div>

      {enquiries.length === 0 ? (
        <div className="card text-center py-12 text-slate-500">No enquiries yet.</div>
      ) : (
        <div className="space-y-2">
          {enquiries.map((e, i) => {
            const key = e.id || e.session_id || String(i)
            const fields = e.extracted_fields || e
            const declined = isProjectDeclined(fields)
            const visibleFields = COMPACT_FIELDS.filter(
              f => fields[f] != null && fields[f] !== '' || COMPACT_FIELDS.indexOf(f) < 5
            ).slice(0, 4)

            return (
              <div key={key} className="card">
                <div
                  className="flex items-center justify-between cursor-pointer"
                  onClick={() => setExpanded(expanded === key ? null : key)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      {declined && (
                        <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                          Not ready for project
                        </span>
                      )}
                      {e.phone_number && (
                        <span className="text-[10px] text-slate-600 truncate">{e.phone_number}</span>
                      )}
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-1">
                      {visibleFields.map(f => (
                        <div key={f}>
                          <p className="text-[10px] text-slate-600">{formatFieldLabel(f)}</p>
                          <p className="text-xs text-slate-300">{formatFieldValue(f, fields[f])}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                  <span className="text-slate-500 text-xs ml-4 shrink-0">{expanded === key ? '▲' : '▼'}</span>
                </div>
                {expanded === key && (
                  <div className="mt-4 pt-4 border-t border-slate-700/50">
                    <pre className="text-xs text-slate-400 overflow-x-auto whitespace-pre-wrap bg-navy-900 rounded-lg p-3">
                      {JSON.stringify(fields, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
