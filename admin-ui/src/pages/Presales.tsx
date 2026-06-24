import { useCallback, useEffect, useState } from 'react'
import { api, PresalesItem } from '../api/client'
import clsx from 'clsx'
import { format } from 'date-fns'

const PLACEHOLDER_NAMES = new Set(['__returning_user__', 'registered user'])

function displayName(name: string | undefined): string {
  const value = (name || '').trim()
  if (!value || PLACEHOLDER_NAMES.has(value.toLowerCase())) return '—'
  return value
}

function formatDate(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy, HH:mm')
  } catch {
    return iso
  }
}

export default function Presales() {
  const [items, setItems] = useState<PresalesItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [flagFilter, setFlagFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.presales({
        page,
        limit: 20,
        flag: flagFilter || undefined,
      })
      if (!data.success && data.message) {
        setError(data.message)
      }
      setItems(data.data?.items || [])
      setTotal(data.data?.total ?? 0)
      setTotalPages(data.data?.totalPages ?? 1)
    } catch {
      setError('Failed to load presales records.')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page, flagFilter])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  useEffect(() => {
    setPage(1)
  }, [flagFilter])

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-200">Pre-sales</h1>
          <p className="text-sm text-slate-500 mt-1">
            {total} record{total !== 1 ? 's' : ''} from Tatva · refreshes every 30s
          </p>
        </div>
        <select
          className="input w-40"
          value={flagFilter}
          onChange={e => setFlagFilter(e.target.value)}
        >
          <option value="">All flags</option>
          <option value="high">High intent</option>
          <option value="low">Low intent</option>
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
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Flag</th>
                <th className="px-4 py-3 font-medium">Location</th>
                <th className="px-4 py-3 font-medium min-w-[200px]">Property</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    Loading presales records...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                    No presales records found.
                  </td>
                </tr>
              ) : (
                items.map(row => (
                  <tr
                    key={row._id}
                    className="border-b border-slate-700/30 hover:bg-navy-700/30"
                  >
                    <td className="px-4 py-3 text-slate-200 whitespace-nowrap">
                      {displayName(row.name)}
                    </td>
                    <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                      {row.phoneNumber || '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                      {row.email || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={clsx(
                          'badge uppercase',
                          row.flag === 'high'
                            ? 'bg-teal-600/20 text-teal-300'
                            : 'bg-amber-600/20 text-amber-300',
                        )}
                      >
                        {row.flag || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400 max-w-[160px] truncate" title={row.location}>
                      {row.location || '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-400 max-w-[240px] truncate" title={row.propertyLocation}>
                      {row.propertyLocation || '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">
                      {formatDate(row.createdAt)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
            <span className="text-xs text-slate-500">
              Page {page} of {totalPages}
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
        )}
      </div>
    </div>
  )
}
