import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import clsx from 'clsx'
import { format } from 'date-fns'
import toast from 'react-hot-toast'

type MyLeadRow = {
  external_id: string
  status: string
  snapshot: Record<string, unknown>
  assigned_at?: string
  notes?: string
}

function snap(row: MyLeadRow, key: string): string {
  const v = row.snapshot?.[key]
  return v != null && String(v).trim() ? String(v) : '—'
}

function formatDate(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy, HH:mm')
  } catch {
    return iso
  }
}

export default function MyLeads() {
  const [items, setItems] = useState<MyLeadRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.myLeads({ page, limit: 20 })
      setItems(data.data?.items || [])
      setTotal(data.data?.total ?? 0)
      setTotalPages(data.data?.totalPages ?? 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load leads')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  const handleComplete = async (externalId: string) => {
    try {
      await api.completeMyLead(externalId)
      toast.success('Marked as completed')
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not update lead')
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-200">My Leads</h1>
        <p className="text-sm text-slate-500 mt-1">{total} assigned lead{total !== 1 ? 's' : ''}</p>
      </div>

      {error && <div className="card text-red-400 text-sm">{error}</div>}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-slate-700/50 text-xs text-slate-500 uppercase tracking-wide">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Flag</th>
                <th className="px-4 py-3 font-medium">Location</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Assigned</th>
                <th className="px-4 py-3 font-medium">Action</th>
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">Loading...</td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-12 text-center text-slate-500">No leads assigned yet.</td>
                </tr>
              ) : (
                items.map(row => (
                  <tr key={row.external_id} className="border-b border-slate-700/30 hover:bg-navy-700/30">
                    <td className="px-4 py-3 text-slate-200">{snap(row, 'name')}</td>
                    <td className="px-4 py-3 text-slate-300">{snap(row, 'phoneNumber')}</td>
                    <td className="px-4 py-3">
                      <span className={clsx(
                        'badge uppercase',
                        snap(row, 'flag') === 'high' ? 'bg-teal-600/20 text-teal-300' : 'bg-amber-600/20 text-amber-300',
                      )}>
                        {snap(row, 'flag')}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400 max-w-[160px] truncate">{snap(row, 'location')}</td>
                    <td className="px-4 py-3 capitalize text-slate-400">{row.status.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">{formatDate(row.assigned_at)}</td>
                    <td className="px-4 py-3">
                      {row.status !== 'presales_completed' && (
                        <button
                          type="button"
                          className="btn-ghost text-teal-400 text-xs"
                          onClick={() => handleComplete(row.external_id)}
                        >
                          Mark complete
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
          <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <button type="button" className="btn-ghost disabled:opacity-40" disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}>Previous</button>
            <button type="button" className="btn-ghost disabled:opacity-40" disabled={page >= totalPages || loading} onClick={() => setPage(p => p + 1)}>Next</button>
          </div>
        </div>
      </div>
    </div>
  )
}
