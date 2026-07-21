import { useCallback, useEffect, useState } from 'react'
import { api, VendorLeadItem } from '../api/client'
import { format } from 'date-fns'
import { ExternalLink } from 'lucide-react'

const TATVA_VENDOR_PROFILE_BASE = 'https://devops.withtatva.ai/vendor'

function vendorProfileUrl(vendorId: string): string {
  return `${TATVA_VENDOR_PROFILE_BASE}/${encodeURIComponent(vendorId)}`
}

function pick(row: VendorLeadItem, ...keys: string[]): string {
  for (const key of keys) {
    const value = row[key]
    if (value != null && String(value).trim() !== '') {
      return String(value).trim()
    }
  }
  return '—'
}

function formatDate(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy, HH:mm')
  } catch {
    return iso
  }
}

function formatVendorServices(row: VendorLeadItem): string {
  const services = row.services
  if (Array.isArray(services) && services.length > 0) {
    const names = services
      .map(item => {
        if (!item || typeof item !== 'object') return ''
        const rec = item as Record<string, unknown>
        const serviceId = rec.serviceId
        if (serviceId && typeof serviceId === 'object' && !Array.isArray(serviceId)) {
          const name = String((serviceId as { name?: string }).name || '').trim()
          if (name) return name
        }
        if ('name' in rec) return String(rec.name || '').trim()
        return ''
      })
      .filter(Boolean)
    if (names.length > 0) return names.join(', ')
  }
  return pick(row, 'service', 'serviceCategory', 'serviceType', 'category')
}

export default function Vendors() {
  const [items, setItems] = useState<VendorLeadItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [limit] = useState(100)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.vendors({ page, limit })
      if (!data.success && data.message) {
        setError(data.message)
      }
      setItems(data.data?.items || [])
      setTotal(data.data?.total ?? 0)
      setTotalPages(data.data?.totalPages ?? 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load approved vendors.')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page, limit])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  const rowId = (row: VendorLeadItem) => String(row._id || row.id || '')

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="page-title">Vendors</h1>
        <p className="text-sm text-slate-500 mt-1">
          {total} approved vendor{total !== 1 ? 's' : ''} from Tatva
        </p>
      </div>

      {error && (
        <div className="card text-red-400 text-sm">{error}</div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table w-full text-sm text-left">
            <thead>
              <tr className="">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Company</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Location</th>
                <th className="px-4 py-3 font-medium">Service</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Approved</th>
                <th className="px-4 py-3 font-medium">Profile</th>
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                    Loading approved vendors...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                    No approved vendors found.
                  </td>
                </tr>
              ) : (
                items.map(row => {
                  const name = pick(row, 'fullName', 'name', 'primaryContactPerson', 'contactName', 'vendorName', 'designation')
                  const company = pick(row, 'companyName', 'businessName', 'company', 'vendorName')
                  const phone = pick(row, 'phoneNumber', 'phone', 'mobile')
                  const email = pick(row, 'email')
                  const location = pick(row, 'businessAddress', 'location', 'city', 'address')
                  const service = formatVendorServices(row)
                  const created = pick(row, 'createdAt', 'created_at', 'updatedAt', 'updated_at')
                  const rowKey = rowId(row) || `${phone}-${created}`
                  const vendorId = rowId(row)
                  const profileUrl = vendorId ? vendorProfileUrl(vendorId) : ''

                  return (
                    <tr
                      key={rowKey}
                      className=""
                    >
                      <td className="px-4 py-3 text-theme-primary whitespace-nowrap">{name}</td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{company}</td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">{phone}</td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{email}</td>
                      <td className="px-4 py-3 text-slate-400 align-top min-w-[220px] whitespace-normal break-words">
                        {location}
                      </td>
                      <td className="px-4 py-3 text-slate-400 align-top min-w-[200px] whitespace-normal break-words">
                        {service}
                      </td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">
                        {formatDate(created !== '—' ? created : undefined)}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {profileUrl ? (
                          <a
                            href={profileUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-indigo-400 hover:text-indigo-300 text-xs inline-flex items-center gap-1"
                          >
                            View <ExternalLink className="w-3 h-3 shrink-0" />
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="table-footer flex items-center justify-between">
          <span className="text-xs text-slate-500">
            Page {page} of {totalPages} · {total} total
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-ghost disabled:opacity-40"
              disabled={page <= 1 || loading}
              onClick={() => setPage(p => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className="btn-ghost disabled:opacity-40"
              disabled={page >= totalPages || loading}
              onClick={() => setPage(p => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
