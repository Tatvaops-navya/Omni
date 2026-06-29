import { useEffect, useState } from 'react'
import { X, Loader2 } from 'lucide-react'
import { api, canViewEnquiryAttachments } from '../api/client'
import type { Enquiry } from '../types/enquiry'
import { findEnquiryByPhone } from '../utils/phone'
import { EnquiryDetailPanel, enquiryStatusBadge } from './EnquiryDetailPanel'

function formatValue(field: string, value: unknown): string {
  if (value == null || value === '') return ''
  const raw = String(value).trim()
  if (raw.includes('_') && raw === raw.toLowerCase() && !raw.includes('@')) {
    return raw.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  }
  return raw
}

function pick(fields: Record<string, unknown>, key: string): string {
  return formatValue(key, fields[key])
}

export default function EnquiryViewModal({
  leadName,
  phone,
  onClose,
}: {
  leadName?: string
  phone?: string
  onClose: () => void
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [enquiry, setEnquiry] = useState<Enquiry | null>(null)
  const showFiles = canViewEnquiryAttachments()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    setEnquiry(null)
    api.enquiries()
      .then(data => {
        if (cancelled) return
        const match = findEnquiryByPhone(data.enquiries || [], phone)
        if (!match) {
          setError('No enquiry found for this lead yet.')
          return
        }
        setEnquiry(match)
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load enquiry.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [phone])

  const fields = enquiry?.extracted_fields || {}
  const badge = enquiry ? enquiryStatusBadge(enquiry.status || String(fields._enquiry_status || '')) : null
  const displayName = pick(fields, 'client_name') || leadName || 'Lead enquiry'
  const service = enquiry
    ? formatValue('service_category', enquiry.service_category || fields.service_category)
    : ''

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-lg font-semibold text-slate-200">{displayName}</h2>
              {badge && (
                <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full border ${badge.className}`}>
                  {badge.label}
                </span>
              )}
              {service && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                  {service}
                </span>
              )}
            </div>
            {phone && <p className="text-xs text-slate-500 mt-1">{phone}</p>}
          </div>
          <button type="button" className="btn-ghost p-1 shrink-0" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading enquiry…
          </div>
        ) : error ? (
          <div className="text-center py-12 text-slate-500 text-sm">{error}</div>
        ) : enquiry ? (
          <EnquiryDetailPanel enquiry={enquiry} showFiles={showFiles} />
        ) : null}
      </div>
    </div>
  )
}
