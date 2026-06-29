import { useCallback, useEffect, useState } from 'react'
import { api, CrmUser, PresalesItem } from '../api/client'
import { StaffCommentDisplay } from '../components/StaffCommentDisplay'
import EnquiryViewModal from '../components/EnquiryViewModal'
import clsx from 'clsx'
import { format } from 'date-fns'
import { Eye, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'

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

function statusLabel(status: string | undefined): string {
  return (status || 'unassigned').replace(/_/g, ' ')
}

export default function Presales() {
  const [items, setItems] = useState<PresalesItem[]>([])
  const [team, setTeam] = useState<CrmUser[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [flagFilter, setFlagFilter] = useState('')
  const [crmConfigured, setCrmConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [assigningId, setAssigningId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [viewLead, setViewLead] = useState<{ name?: string; phone?: string } | null>(null)

  const loadTeam = useCallback(async () => {
    try {
      const [presales, rm] = await Promise.all([
        api.crmUsers('presales'),
        api.crmUsers('rm'),
      ])
      setTeam([...(presales.users || []), ...(rm.users || [])])
    } catch {
      setTeam([])
    }
  }, [])

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
      setCrmConfigured(!!data.crm_configured)
    } catch {
      setError('Failed to load presales records.')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page, flagFilter])

  useEffect(() => {
    loadTeam()
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load, loadTeam])

  useEffect(() => {
    setPage(1)
  }, [flagFilter])

  const handleAssign = async (row: PresalesItem, staffUserId: string) => {
    if (!staffUserId) return
    setAssigningId(row._id)
    try {
      await api.assignUserLead(row._id, {
        staff_user_id: staffUserId,
        snapshot: { ...row },
      })
      toast.success('Lead assigned')
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Assignment failed')
    } finally {
      setAssigningId(null)
    }
  }

  const handleDelete = async (row: PresalesItem) => {
    const label = displayName(row.name) !== '—' ? displayName(row.name) : row.phoneNumber || 'this lead'
    if (!window.confirm(`Delete presales record for ${label}? This cannot be undone.`)) {
      return
    }
    setDeletingId(row._id)
    try {
      await api.deletePresales(row._id)
      toast.success('Presales record deleted')
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-200">Pre-sales</h1>
          <p className="text-sm text-slate-500 mt-1">
            {total} record{total !== 1 ? 's' : ''} from Tatva
            {crmConfigured ? ' · assignment enabled' : ' · configure Supabase for assignment'}
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
                <th className="px-4 py-3 font-medium">Assignee</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Team comment</th>
                <th className="px-4 py-3 font-medium">Assign</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Created</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-4 py-12 text-center text-slate-500">
                    Loading presales records...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-4 py-12 text-center text-slate-500">
                    No presales records found.
                  </td>
                </tr>
              ) : (
                items.map(row => {
                  const assignment = row.assignment
                  const currentAssignee = assignment?.staff_user_id || assignment?.presales_user_id || assignment?.rm_user_id || ''
                  return (
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
                      <td className="px-4 py-3 text-slate-400 max-w-[140px] truncate" title={row.location}>
                        {row.location || '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                        {assignment?.assignee_name || '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-400 capitalize text-xs">
                        {statusLabel(assignment?.status)}
                      </td>
                      <td className="px-4 py-3 align-top">
                        <StaffCommentDisplay text={assignment?.notes} />
                      </td>
                      <td className="px-4 py-3">
                        {crmConfigured && team.length > 0 ? (
                          <select
                            className="input text-xs py-1.5 min-w-[120px]"
                            value={currentAssignee}
                            disabled={assigningId === row._id}
                            onChange={e => handleAssign(row, e.target.value)}
                          >
                            <option value="">Assign to...</option>
                            {team.map(u => (
                              <option key={u.id || ''} value={u.id || ''}>
                                {u.name} ({u.role})
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="text-xs text-slate-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">
                        {formatDate(row.createdAt)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            className="p-1.5 rounded-md text-slate-400 hover:text-indigo-300 hover:bg-indigo-500/10 transition-colors"
                            title="View enquiry"
                            onClick={() => setViewLead({
                              name: row.name,
                              phone: row.phoneNumber,
                            })}
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            className="p-1.5 rounded-md text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-40"
                            title="Delete presales record"
                            disabled={deletingId === row._id}
                            onClick={() => handleDelete(row)}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-slate-700/50">
            <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
            <div className="flex gap-2">
              <button type="button" className="btn-ghost disabled:opacity-40" disabled={page <= 1 || loading} onClick={() => setPage(p => Math.max(1, p - 1))}>Previous</button>
              <button type="button" className="btn-ghost disabled:opacity-40" disabled={page >= totalPages || loading} onClick={() => setPage(p => p + 1)}>Next</button>
            </div>
          </div>
        )}
      </div>

      {viewLead && (
        <EnquiryViewModal
          leadName={viewLead.name}
          phone={viewLead.phone}
          onClose={() => setViewLead(null)}
        />
      )}
    </div>
  )
}
