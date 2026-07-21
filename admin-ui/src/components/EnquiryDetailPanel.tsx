import { useEffect, useState } from 'react'
import { ExternalLink, Paperclip, X } from 'lucide-react'
import { format } from 'date-fns'
import { api } from '../api/client'
import type { Enquiry, EnquiryAttachment } from '../types/enquiry'

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

function pick(fields: Record<string, unknown>, key: string): string {
  return formatValue(key, fields[key])
}

function isImageAttachment(attachment: EnquiryAttachment): boolean {
  const mime = (attachment.mime_type || '').toLowerCase()
  if (mime.startsWith('image/')) return true
  const name = (attachment.file_name || attachment.file_url || '').toLowerCase()
  return /\.(jpe?g|png|gif|webp|bmp|svg)(\?|$)/i.test(name)
}

export function isViewableUrl(url: string): boolean {
  return (
    url.startsWith('http://')
    || url.startsWith('https://')
    || url.startsWith('/media/')
  )
}

function attachmentViewUrl(attachment: EnquiryAttachment): string {
  const preview = String(attachment.preview_url || '').trim()
  if (preview && isViewableUrl(preview)) return preview
  const url = String(attachment.file_url || '').trim()
  if (isViewableUrl(url)) return url
  return ''
}

function isWhatsAppRef(attachment: EnquiryAttachment): boolean {
  const url = String(attachment.file_url || '').trim()
  return url.startsWith('twilio:') || url.startsWith('whatsapp:')
}

function isTatvaCdnUrl(url: string): boolean {
  const u = url.trim().toLowerCase()
  return u.includes('cloudfront.net') && u.includes('/enquiries/')
}

function isSupabaseEnquiryFileUrl(url: string): boolean {
  const u = url.trim().toLowerCase()
  return u.includes('supabase.co/storage') && u.includes('enquiry-files')
}

function logicalAttachmentName(attachment: EnquiryAttachment): string {
  const raw = (attachment.file_name || attachment.file_url || '').trim().toLowerCase()
  const name = raw.includes('/') ? (raw.split('/').pop() || raw) : raw
  return name.replace(/_\d{10,}(\.[^./]+$)/, '$1')
}

function dedupeByLogicalName(attachments: EnquiryAttachment[]): EnquiryAttachment[] {
  const byKey = new Map<string, EnquiryAttachment>()
  const order: string[] = []
  for (const item of attachments) {
    const key = logicalAttachmentName(item) || String(item.file_url || '')
    if (!byKey.has(key)) {
      byKey.set(key, item)
      order.push(key)
      continue
    }
    const existing = byKey.get(key)!
    const existingUrl = String(existing.file_url || '')
    const nextUrl = String(item.file_url || '')
    if (isTatvaCdnUrl(nextUrl) && !isTatvaCdnUrl(existingUrl)) {
      byKey.set(key, item)
    }
  }
  return order.map(k => byKey.get(k)!)
}

/** Drop WhatsApp/Twilio and Supabase-cache duplicates when Tatva CDN links exist. */
function filterDisplayAttachments(attachments: EnquiryAttachment[]): EnquiryAttachment[] {
  const tatva = attachments.filter(a => isTatvaCdnUrl(String(a.file_url || a.preview_url || '')))
  if (tatva.length > 0) return dedupeByLogicalName(tatva)

  const http = attachments.filter(a => {
    const url = String(a.file_url || a.preview_url || '').trim()
    return url.startsWith('http://') || url.startsWith('https://')
  })
  if (http.length > 0) {
    const nonSupabase = http.filter(a => !isSupabaseEnquiryFileUrl(String(a.file_url || '')))
    return dedupeByLogicalName(nonSupabase.length > 0 ? nonSupabase : http)
  }

  const previews = attachments.filter(a => String(a.file_url || '').startsWith('/media/'))
  if (previews.length > 0) return dedupeByLogicalName(previews)

  return dedupeByLogicalName(attachments.filter(a => !isWhatsAppRef(a)))
}

function AttachmentPreviewModal({
  attachment,
  onClose,
}: {
  attachment: EnquiryAttachment
  onClose: () => void
}) {
  const url = attachmentViewUrl(attachment)
  const isImage = isImageAttachment(attachment)

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-4"
      onClick={onClose}
    >
      <div
        className="relative max-w-4xl w-full max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm text-theme-primary truncate pr-4">
            {attachment.file_name || 'Uploaded file'}
          </p>
          <button type="button" className="btn-ghost p-1" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="bg-slate-100 dark:bg-navy-900 rounded-lg overflow-hidden flex items-center justify-center min-h-[200px] max-h-[75vh]">
          {isImage && url ? (
            <img
              src={url}
              alt={attachment.file_name || 'Uploaded image'}
              className="max-h-[75vh] max-w-full object-contain"
            />
          ) : url ? (
            <div className="p-8 text-center space-y-3">
              <p className="text-slate-400 text-sm">Preview not available for this file type.</p>
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-1"
              >
                Open file <ExternalLink className="w-4 h-4" />
              </a>
            </div>
          ) : (
            <p className="text-slate-500 text-sm p-8 text-center max-w-md">
              This file was sent on WhatsApp and the preview link is not available yet.
              Redeploy the backend or wait for the file to sync to Tatva storage.
            </p>
          )}
        </div>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-indigo-400 hover:text-indigo-300 mt-2 inline-flex items-center gap-1 self-end"
          >
            Open in new tab <ExternalLink className="w-3 h-3" />
          </a>
        )}
      </div>
    </div>
  )
}

export function EnquiryFileList({
  attachments: initialAttachments,
  sessionId,
}: {
  attachments: EnquiryAttachment[]
  sessionId?: string
}) {
  const [preview, setPreview] = useState<EnquiryAttachment | null>(null)
  const [attachments, setAttachments] = useState(() => filterDisplayAttachments(initialAttachments))

  useEffect(() => {
    setAttachments(filterDisplayAttachments(initialAttachments))
  }, [initialAttachments])

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    const resolve = async () => {
      try {
        const refreshed = await api.refreshEnquiryAttachments(sessionId)
        if (!cancelled && refreshed.attachments?.length) {
          setAttachments(filterDisplayAttachments(refreshed.attachments))
          return
        }
      } catch {
        // fall through to GET
      }
      try {
        const resolved = await api.enquiryAttachments(sessionId)
        if (!cancelled && resolved.attachments?.length) {
          setAttachments(filterDisplayAttachments(resolved.attachments))
        }
      } catch {
        // keep initial list
      }
    }
    void resolve()
    return () => { cancelled = true }
  }, [sessionId])

  if (attachments.length === 0) {
    return <p className="text-xs text-slate-500">No files for this enquiry.</p>
  }

  return (
    <>
      <ul className="space-y-1.5">
        {attachments.map((a, i) => {
          const url = attachmentViewUrl(a)
          const isImage = isImageAttachment(a)
          return (
            <li key={`${a.file_name}-${url}-${i}`} className="flex items-center justify-between gap-2 text-sm">
              <button
                type="button"
                className="text-theme-secondary truncate flex items-center gap-1.5 min-w-0 text-left hover:text-indigo-300 disabled:cursor-default disabled:hover:text-slate-700 dark:hover:text-slate-300"
                disabled={!url}
                onClick={() => url && setPreview(a)}
              >
                <Paperclip className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                {a.file_name || 'Uploaded file'}
              </button>
              {url ? (
                <button
                  type="button"
                  className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-0.5 shrink-0"
                  onClick={() => setPreview(a)}
                >
                  {isImage ? 'View image' : 'Open'} <ExternalLink className="w-3 h-3" />
                </button>
              ) : (
                <span
                  className="text-[10px] text-slate-500 shrink-0 max-w-[120px] text-right leading-tight"
                  title="Preview link is not available for this file"
                >
                  No link
                </span>
              )}
            </li>
          )
        })}
      </ul>
      {preview && (
        <AttachmentPreviewModal attachment={preview} onClose={() => setPreview(null)} />
      )}
    </>
  )
}

export function EnquiryDetailPanel({
  enquiry,
  showFiles = true,
}: {
  enquiry: Enquiry
  showFiles?: boolean
}) {
  const fields = enquiry.extracted_fields || {}
  const requirements = enquiry.requirements_summary || []
  const attachments = filterDisplayAttachments(enquiry.attachments || [])
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
    <div className="bg-slate-100 dark:bg-navy-900/60 rounded-lg p-4 space-y-3 text-sm">
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
        <div className="border-t border-slate-200/80 dark:border-slate-700/40 pt-3">
          <p className="text-xs text-slate-500 mb-2">Requirements</p>
          <ul className="space-y-1.5">
            {requirements.map((item, idx) => (
              <li key={`${item.label}-${idx}`} className="text-theme-secondary leading-snug">
                <span className="text-slate-400">{shortLabel(item.label)}:</span>{' '}
                {item.value}
              </li>
            ))}
          </ul>
        </div>
      )}

      {showFiles && attachments.length > 0 && (
        <div className="border-t border-slate-200/80 dark:border-slate-700/40 pt-3">
          <p className="text-xs text-slate-500 mb-2">
            Uploaded files ({attachments.length})
          </p>
          <EnquiryFileList
            attachments={attachments}
            sessionId={enquiry.session_id}
          />
        </div>
      )}

      <p className="text-[10px] text-slate-600 pt-1 border-t border-slate-200/80 dark:border-slate-700/40">
        {[enquiry.channel, formatWhen(enquiry.last_active)].filter(Boolean).join(' · ')}
      </p>
    </div>
  )
}

export function enquiryStatusBadge(status?: string) {
  const value = (status || 'in_progress').toLowerCase()
  if (value === 'completed') {
    return { label: 'Completed', className: 'bg-teal-500/15 text-teal-300 border-teal-500/30' }
  }
  if (value === 'declined') {
    return { label: 'Declined', className: 'bg-amber-500/15 text-amber-300 border-amber-500/30' }
  }
  return { label: 'In progress', className: 'bg-slate-600/30 text-slate-300 border-slate-500/30' }
}
