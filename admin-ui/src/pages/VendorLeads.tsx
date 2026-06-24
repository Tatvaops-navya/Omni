import { useCallback, useEffect, useState } from 'react'
import { api, VendorLeadItem } from '../api/client'
import clsx from 'clsx'
import { format } from 'date-fns'

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

export default function VendorLeads() {
  const [items, setItems] = useState<VendorLeadItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [limit] = useState(20)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.vendorLeads({
        page,
        limit,
        ...(statusFilter ? { status: statusFilter } : {}),
      })
      if (!data.success && data.message) {
        setError(data.message)
      }
      setItems(data.data?.items || [])
      setTotal(data.data?.total ?? 0)
      setTotalPages(data.data?.totalPages ?? 1)
    } catch {
      setError('Failed to load vendor leads.')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page, limit, statusFilter])

  useEffect(() => {
    setPage(1)
  }, [statusFilter])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-200">Vendor Leads</h1>
          <p className="text-sm text-slate-500 mt-1">
            {total} record{total !== 1 ? 's' : ''} from Tatva · refreshes every 30s
          </p>
        </div>
        <select
          className="input w-40"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="">All statuses</option>
        </select>
      </div>

      {error && (
        <div className="card text-red-400 text-sm">{error}</div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-slate-700/50 text-xs text-slate-500 uppercase tracking-wide">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Company</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Location</th>
                <th className="px-4 py-3 font-medium">Service</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                    Loading vendor leads...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                    No vendor leads found.
                  </td>
                </tr>
              ) : (
                items.map(row => {
                  const name = pick(row, 'name', 'fullName', 'contactName', 'vendorName')
                  const company = pick(row, 'companyName', 'businessName', 'company', 'vendorName')
                  const phone = pick(row, 'phoneNumber', 'phone', 'mobile')
                  const email = pick(row, 'email')
                  const location = pick(row, 'location', 'city', 'address')
                  const service = pick(row, 'service', 'serviceCategory', 'serviceType', 'category')
                  const status = pick(row, 'status', 'leadStatus')
                  const created = pick(row, 'createdAt', 'created_at')
                  const rowKey = String(row._id || row.id || `${phone}-${created}`)

                  return (
                    <tr
                      key={rowKey}
                      className="border-b border-slate-700/30 hover:bg-navy-700/30"
                    >
                      <td className="px-4 py-3 text-slate-200 whitespace-nowrap">{name}</td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{company}</td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">{phone}</td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{email}</td>
                      <td className="px-4 py-3 text-slate-400 max-w-[160px] truncate" title={location}>
                        {location}
                      </td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{service}</td>
                      <td className="px-4 py-3">
                        {status !== '—' ? (
                          <span className="badge capitalize bg-indigo-600/20 text-indigo-300">
                            {status}
                          </span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">
                        {formatDate(created !== '—' ? created : undefined)}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
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
