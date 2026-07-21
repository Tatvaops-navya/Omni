import { useEffect, useState } from 'react'
import { api, canViewEnquiryAttachments, isPresalesUser, isRmUser } from '../api/client'
import { Paperclip } from 'lucide-react'
import { format } from 'date-fns'
import type { Enquiry } from '../types/enquiry'
import { EnquiryDetailPanel, enquiryStatusBadge } from '../components/EnquiryDetailPanel'

function formatValue(field: string, value: unknown): string {
  if (value == null || value === '') return ''
  if (field === 'willing_to_create_project') {
    const v = String(value).trim().toLowerCase()
    if (v === 'no' || v === 'n') return 'No'
    if (v === 'yes' || v === 'y') return 'Yes'
  }
  if (field === 'preferred_contact_time') {
    return String(value).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }
  const raw = String(value).trim()
  if (raw.includes('_') && raw === raw.toLowerCase() && !raw.includes('@')) {
    return raw.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }
  return raw
}

function formatPhone(phone?: string): string {
  if (!phone) return ''
  return phone.replace(/^whatsapp:/i, '')
}

function formatWhen(iso?: string): string {
  if (!iso) return ''
  try {
    return format(new Date(iso), 'dd MMM yyyy, HH:mm')
  } catch {
    return iso
  }
}

function pick(fields: Record<string, unknown>, key: string): string {
  return formatValue(key, fields[key])
}

function isDeclined(fields: Record<string, unknown>, status?: string): boolean {
  if (status === 'declined') return true
  const v = String(fields.willing_to_create_project || '').trim().toLowerCase()
  return v === 'no' || v === 'n'
}

export default function Enquiries() {
  const [enquiries, setEnquiries] = useState<Enquiry[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [scopedToAssignments, setScopedToAssignments] = useState(false)
  const showAttachments = canViewEnquiryAttachments()
  const isTeamMember = isPresalesUser() || isRmUser()

  useEffect(() => {
    const load = () => {
      setLoading(true)
      setError('')
      api.enquiries()
        .then(d => {
          setEnquiries(d.enquiries || [])
          setScopedToAssignments(!!d.scoped_to_assignments)
        })
        .catch(() => {
          setError('Failed to load enquiries.')
          setEnquiries([])
        })
        .finally(() => setLoading(false))
    }
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="page-title">Enquiries</h1>
        <p className="text-sm text-slate-500 mt-1">
          {enquiries.length} {scopedToAssignments || isTeamMember ? 'assigned ' : ''}lead{enquiries.length !== 1 ? 's' : ''}
        </p>
      </div>

      {error && <div className="card text-red-400 text-sm">{error}</div>}

      {loading ? (
        <div className="card text-center py-12 text-slate-500">Loading…</div>
      ) : enquiries.length === 0 ? (
        <div className="card text-center py-12 text-slate-500">
          {scopedToAssignments || isTeamMember
            ? 'No enquiries assigned to you yet.'
            : 'No enquiries yet.'}
        </div>
      ) : (
        <div className="space-y-2">
          {enquiries.map((e, i) => {
            const key = e.session_id || String(i)
            const fields = e.extracted_fields || {}
            const name = pick(fields, 'client_name') || 'Unknown'
            const isOpen = expanded === key
            const attachments = e.attachments || []
            const fileCount = e.attachment_count ?? attachments.length
            const badge = enquiryStatusBadge(e.status || String(fields._enquiry_status || ''))
            const service = formatValue('service_category', e.service_category || fields.service_category)
            const location = [pick(fields, 'city'), pick(fields, 'property_location')].filter(Boolean).join(', ')

            return (
              <div key={key} className="card">
                <div
                  className="flex items-center justify-between cursor-pointer gap-3"
                  onClick={() => setExpanded(isOpen ? null : key)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-sm font-medium text-slate-200">{name}</p>
                      <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full border ${badge.className}`}>
                        {badge.label}
                      </span>
                      {service && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                          {service}
                        </span>
                      )}
                      {isDeclined(fields, e.status) && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">
                          Exploring only
                        </span>
                      )}
                      {showAttachments && fileCount > 0 && (
                        <span className="text-[10px] text-slate-500 flex items-center gap-1">
                          <Paperclip className="w-3 h-3" /> {fileCount}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 mt-1 truncate">
                      {[location, formatPhone(e.phone_number), formatWhen(e.last_active)].filter(Boolean).join(' · ')}
                    </p>
                  </div>
                  <span className="text-slate-500 text-xs shrink-0">{isOpen ? '▲' : '▼'}</span>
                </div>

                {isOpen && (
                  <div className="mt-3 pt-3 border-t border-slate-200/80 dark:border-slate-700/50">
                    <EnquiryDetailPanel
                      enquiry={e}
                      showFiles={showAttachments}
                    />
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
