import { useState } from 'react'
import { ExternalLink, Paperclip, X } from 'lucide-react'
import { format } from 'date-fns'
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

function isViewableUrl(url: string): boolean {
  return url.startsWith('http://') || url.startsWith('https://')
}

function AttachmentPreviewModal({
  attachment,
  onClose,
}: {
  attachment: EnquiryAttachment
  onClose: () => void
}) {
  const url = attachment.file_url || ''
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
          <p className="text-sm text-slate-200 truncate pr-4">
            {attachment.file_name || 'Uploaded file'}
          </p>
          <button type="button" className="btn-ghost p-1" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="bg-navy-900 rounded-lg overflow-hidden flex items-center justify-center min-h-[200px] max-h-[75vh]">
          {isImage && isViewableUrl(url) ? (
            <img
              src={url}
              alt={attachment.file_name || 'Uploaded image'}
              className="max-h-[75vh] max-w-full object-contain"
            />
          ) : isViewableUrl(url) ? (
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
            <p className="text-slate-500 text-sm p-8">WhatsApp upload — not viewable in browser.</p>
          )}
        </div>
        {isViewableUrl(url) && (
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

export function EnquiryFileList({ attachments }: { attachments: EnquiryAttachment[] }) {
  const [preview, setPreview] = useState<EnquiryAttachment | null>(null)

  if (attachments.length === 0) {
    return <p className="text-xs text-slate-500">No files for this enquiry.</p>
  }

  return (
    <>
      <ul className="space-y-1.5">
        {attachments.map((a, i) => {
          const url = a.file_url || ''
          const viewable = isViewableUrl(url)
          const isImage = isImageAttachment(a)
          return (
            <li key={`${url}-${i}`} className="flex items-center justify-between gap-2 text-sm">
              <button
                type="button"
                className="text-slate-300 truncate flex items-center gap-1.5 min-w-0 text-left hover:text-indigo-300"
                disabled={!viewable}
                onClick={() => viewable && setPreview(a)}
              >
                <Paperclip className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                {a.file_name || 'Uploaded file'}
              </button>
              {viewable ? (
                <button
                  type="button"
                  className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-0.5 shrink-0"
                  onClick={() => setPreview(a)}
                >
                  {isImage ? 'View image' : 'View'} <ExternalLink className="w-3 h-3" />
                </button>
              ) : (
                <span className="text-[10px] text-slate-600 shrink-0">WhatsApp upload</span>
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
  const attachments = enquiry.attachments || []
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
          <EnquiryFileList attachments={attachments} />
        </div>
      )}

      <p className="text-[10px] text-slate-600 pt-1 border-t border-slate-700/40">
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
