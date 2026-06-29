import { useCallback, useEffect, useState } from 'react'
import { api, TatvaUserItem } from '../api/client'
import clsx from 'clsx'
import { format } from 'date-fns'

function formatDate(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy, HH:mm')
  } catch {
    return iso
  }
}

function displayName(user: TatvaUserItem): string {
  return user.fullName || user.userName || '—'
}

export default function Users() {
  const [users, setUsers] = useState<TatvaUserItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [limit] = useState(10)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.users({ page, limit })
      if (!data.success && data.message) {
        setError(data.message)
      }
      setUsers(data.data?.users || [])
      setTotal(data.data?.total ?? 0)
      setTotalPages(data.data?.totalPages ?? 1)
    } catch {
      setError('Failed to load users.')
      setUsers([])
    } finally {
      setLoading(false)
    }
  }, [page, limit])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-200">Users</h1>
        <p className="text-sm text-slate-500 mt-1">
          {total} registered user{total !== 1 ? 's' : ''} from Tatva · refreshes every 30s
        </p>
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
                <th className="px-4 py-3 font-medium">Username</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Flag</th>
                <th className="px-4 py-3 font-medium">Email verified</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading && users.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-slate-500">
                    Loading users...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-slate-500">
                    No users found.
                  </td>
                </tr>
              ) : (
                users.map(row => (
                  <tr
                    key={row._id}
                    className="border-b border-slate-700/30 hover:bg-navy-700/30"
                  >
                    <td className="px-4 py-3 text-slate-200 whitespace-nowrap">
                      {displayName(row)}
                    </td>
                    <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                      {row.userName || '—'}
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
                          'badge capitalize',
                          row.status === 'active'
                            ? 'bg-teal-600/20 text-teal-300'
                            : 'bg-slate-600/30 text-slate-400',
                        )}
                      >
                        {row.status || '—'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-400 capitalize">
                      {row.role || '—'}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {row.flag || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={clsx(
                          'badge',
                          row.isEmailVerified
                            ? 'bg-teal-600/20 text-teal-300'
                            : 'bg-slate-600/30 text-slate-500',
                        )}
                      >
                        {row.isEmailVerified ? 'Yes' : 'No'}
                      </span>
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
