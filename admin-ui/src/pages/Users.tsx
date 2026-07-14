import { useCallback, useEffect, useRef, useState } from 'react'
import { api, TatvaUserItem } from '../api/client'
import MeetScheduleModal from '../components/MeetScheduleModal'
import clsx from 'clsx'
import { format } from 'date-fns'
import { Video } from 'lucide-react'

const COLUMN_COUNT = 13
const PAGE_SIZE = 20

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

function UtmCell({ value }: { value: string | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="text-slate-500">null</span>
  }
  return <span className="text-slate-400">{value}</span>
}

export default function Users() {
  const [users, setUsers] = useState<TatvaUserItem[]>([])
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [meetUser, setMeetUser] = useState<TatvaUserItem | null>(null)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const loadingRef = useRef(false)
  const pageRef = useRef(1)
  const hasMoreRef = useRef(true)

  const loadPage = useCallback(async (pageNum: number, mode: 'replace' | 'append') => {
    if (loadingRef.current) return
    loadingRef.current = true
    if (mode === 'replace') {
      setLoading(true)
      setError('')
    } else {
      setLoadingMore(true)
    }
    try {
      const data = await api.users({ page: pageNum, limit: PAGE_SIZE })
      if (!data.success && data.message && mode === 'replace') {
        setError(data.message)
      }
      const nextUsers = data.data?.users || []
      const nextTotal = data.data?.total ?? 0
      const nextTotalPages = data.data?.totalPages ?? 1
      const more = pageNum < nextTotalPages && nextUsers.length > 0
      setTotal(nextTotal)
      setHasMore(more)
      pageRef.current = pageNum
      hasMoreRef.current = more
      if (mode === 'append') {
        setUsers(prev => {
          const seen = new Set(prev.map(row => row._id))
          return [...prev, ...nextUsers.filter(row => !seen.has(row._id))]
        })
      } else {
        setUsers(nextUsers)
      }
    } catch {
      if (mode === 'replace') {
        setError('Failed to load users.')
        setUsers([])
        setHasMore(false)
        hasMoreRef.current = false
      }
    } finally {
      loadingRef.current = false
      setLoading(false)
      setLoadingMore(false)
    }
  }, [])

  useEffect(() => {
    loadPage(1, 'replace')
  }, [loadPage])

  useEffect(() => {
    const id = window.setInterval(() => {
      if (pageRef.current === 1 && !loadingRef.current) {
        loadPage(1, 'replace')
      }
    }, 30000)
    return () => window.clearInterval(id)
  }, [loadPage])

  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return undefined
    const observer = new IntersectionObserver(
      entries => {
        const entry = entries[0]
        if (!entry?.isIntersecting) return
        if (!hasMoreRef.current || loadingRef.current) return
        loadPage(pageRef.current + 1, 'append')
      },
      { root: null, rootMargin: '200px', threshold: 0 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [loadPage, users.length, hasMore])

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
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Medium</th>
                <th className="px-4 py-3 font-medium">Campaign</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Flag</th>
                <th className="px-4 py-3 font-medium">Email verified</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Created</th>
                <th className="px-4 py-3 font-medium">Meet</th>
              </tr>
            </thead>
            <tbody>
              {loading && users.length === 0 ? (
                <tr>
                  <td colSpan={COLUMN_COUNT} className="px-4 py-12 text-center text-slate-500">
                    Loading users...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={COLUMN_COUNT} className="px-4 py-12 text-center text-slate-500">
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
                    <td className="px-4 py-3 whitespace-nowrap">
                      <UtmCell value={row.utm_source} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <UtmCell value={row.utm_medium} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <UtmCell value={row.utm_campaign} />
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
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium text-indigo-300 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/30 transition-colors"
                        title="View meet schedules"
                        onClick={() => setMeetUser(row)}
                      >
                        <Video className="w-3.5 h-3.5" />
                        Meet
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div ref={sentinelRef} className="px-4 py-3 border-t border-slate-700/50 text-center">
          {loadingMore ? (
            <span className="text-xs text-slate-500">Loading more...</span>
          ) : hasMore ? (
            <span className="text-xs text-slate-600">Scroll for more</span>
          ) : users.length > 0 ? (
            <span className="text-xs text-slate-600">
              Showing {users.length} of {total}
            </span>
          ) : null}
        </div>
      </div>

      {meetUser && (
        <MeetScheduleModal user={meetUser} onClose={() => setMeetUser(null)} />
      )}
    </div>
  )
}
