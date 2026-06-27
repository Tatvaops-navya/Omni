import { useEffect, useState } from 'react'
import { api, canViewEnquiryAttachments, isPresalesUser, isRmUser } from '../api/client'
import { Paperclip, ExternalLink } from 'lucide-react'
import { format } from 'date-fns'

type Attachment = {
  file_name: string
  file_url: string
  mime_type?: string
}

type Enquiry = {
  session_id?: string
  phone_number?: string
  channel?: string
  service_category?: string | null
  extracted_fields?: Record<string, unknown>
  completion_pct?: number
  attachment_count?: number
  attachments?: Attachment[]
  created_at?: string
  last_active?: string
  status?: string
  requirements_summary?: { label: string; value: string }[]
}

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

function shortLabel(label: string): string {
  const text = label.trim()
  if (text.length <= 42) return text
  const cut = text.split(/[.—–\-!?]/)[0]?.trim()
  if (cut && cut.length >= 8 && cut.length <= 42) return cut
  return `${text.slice(0, 40)}…`
}

function statusBadge(status?: string) {
  const value = (status || 'in_progress').toLowerCase()
  if (value === 'completed') {
    return { label: 'Completed', className: 'bg-teal-500/15 text-teal-300 border-teal-500/30' }
  }
  if (value === 'declined') {
    return { label: 'Declined', className: 'bg-amber-500/15 text-amber-300 border-amber-500/30' }
  }
  return { label: 'In progress', className: 'bg-slate-600/30 text-slate-300 border-slate-500/30' }
}

function isDeclined(fields: Record<string, unknown>, status?: string): boolean {
  if (status === 'declined') return true
  const v = String(fields.willing_to_create_project || '').trim().toLowerCase()
  return v === 'no' || v === 'n'
}

function pick(fields: Record<string, unknown>, key: string): string {
  return formatValue(key, fields[key])
}

function BriefSummary({
  enquiry,
  fields,
  requirements,
  attachments,
  showFiles,
}: {
  enquiry: Enquiry
  fields: Record<string, unknown>
  requirements: { label: string; value: string }[]
  attachments: Attachment[]
  showFiles: boolean
}) {
  const name = pick(fields, 'client_name') || 'Unknown'
  const phone = formatPhone(enquiry.phone_number) || pick(fields, 'phone_number')
  const email = pick(fields, 'email')
  const city = pick(fields, 'city')
  const location = pick(fields, 'property_location')
  const contactTime = pick(fields, 'preferred_contact_time')
  const service = formatValue(
    'service_category',
    enquiry.service_category || fields.service_category,
  )
  const specialist = pick(fields, 'assigned_consultant') || pick(fields, 'active_consultant')
  const createProject = pick(fields, 'willing_to_create_project')

  const locationLine = [city, location].filter(Boolean).join(', ')

  return (
    <div className="bg-navy-900/60 rounded-lg p-4 space-y-3 text-sm">
      <div className="space-y-1 text-slate-300">
        <p>
          <span className="text-slate-500">Lead:</span>{' '}
          {[name, phone, email].filter(Boolean).join(' · ')}
        </p>
        {locationLine && (
          <p>
            <span className="text-slate-500">Property:</span> {locationLine}
            {contactTime ? ` · prefers ${contactTime.toLowerCase()} calls` : ''}
          </p>
        )}
        {(service || specialist || createProject) && (
          <p>
            <span className="text-slate-500">Project:</span>{' '}
            {[service, specialist && `Specialist: ${specialist}`, createProject && `Ready: ${createProject}`]
              .filter(Boolean)
              .join(' · ')}
          </p>
        )}
      </div>

      {requirements.length > 0 && (
        <div className="border-t border-slate-700/40 pt-3">
          <p className="text-xs text-slate-500 mb-2">Requirements</p>
          <ul className="space-y-1.5">
            {requirements.map((item, idx) => (
              <li key={`${item.label}-${idx}`} className="text-slate-300 leading-snug">
                <span className="text-slate-400">{shortLabel(item.label)}:</span>{' '}
                {item.value}
              </li>
            ))}
          </ul>
        </div>
      )}

      {showFiles && (
        <div className="border-t border-slate-700/40 pt-3">
          <p className="text-xs text-slate-500 mb-2">
            Uploaded files{attachments.length > 0 ? ` (${attachments.length})` : ''}
          </p>
          <FileList attachments={attachments} />
        </div>
      )}

      <p className="text-[10px] text-slate-600 pt-1 border-t border-slate-700/40">
        {[enquiry.channel, formatWhen(enquiry.last_active)].filter(Boolean).join(' · ')}
      </p>
    </div>
  )
}

function FileList({ attachments }: { attachments: Attachment[] }) {
  if (attachments.length === 0) {
    return <p className="text-xs text-slate-500">No files for this enquiry.</p>
  }
  return (
    <ul className="space-y-1.5">
      {attachments.map((a, i) => {
        const url = a.file_url || ''
        const viewable = url.startsWith('http://') || url.startsWith('https://')
        return (
          <li key={`${url}-${i}`} className="flex items-center justify-between gap-2 text-sm">
            <span className="text-slate-300 truncate flex items-center gap-1.5 min-w-0">
              <Paperclip className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
              {a.file_name || 'Uploaded file'}
            </span>
            {viewable ? (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-0.5 shrink-0"
              >
                View <ExternalLink className="w-3 h-3" />
              </a>
            ) : (
              <span className="text-[10px] text-slate-600 shrink-0">WhatsApp upload</span>
            )}
          </li>
        )
      })}
    </ul>
  )
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
        <h1 className="text-xl font-semibold text-slate-200">Enquiries</h1>
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
            const badge = statusBadge(e.status || String(fields._enquiry_status || ''))
            const requirements = e.requirements_summary || []
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
                  <div className="mt-3 pt-3 border-t border-slate-700/50">
                    <BriefSummary
                      enquiry={e}
                      fields={fields}
                      requirements={requirements}
                      attachments={attachments}
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
