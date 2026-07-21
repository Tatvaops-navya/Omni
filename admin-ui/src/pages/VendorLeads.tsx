import { useCallback, useEffect, useState } from 'react'
import {
  api,
  TatvaEmployee,
  tatvaEmployeeId,
  tatvaEmployeeLabel,
  VendorLeadItem,
} from '../api/client'
import { StaffCommentDisplay } from '../components/StaffCommentDisplay'
import { format } from 'date-fns'
import toast from 'react-hot-toast'

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

function vendorStatusBadge(status: string) {
  const normalized = status.toLowerCase()
  if (normalized === 'approved') {
    return 'badge capitalize bg-teal-600/20 text-teal-300'
  }
  if (normalized === 'rejected') {
    return 'badge capitalize bg-red-600/20 text-red-300'
  }
  if (normalized === 'pending') {
    return 'badge capitalize bg-amber-600/20 text-amber-300'
  }
  return 'badge capitalize bg-slate-600/20 text-slate-300'
}

function vendorStatus(row: VendorLeadItem): string {
  const value = pick(row, 'status', 'leadStatus', 'vendorStatus', 'approvalStatus')
  return value === '—' ? 'pending' : value
}

function formatVendorServices(row: VendorLeadItem): string {
  const services = row.services
  if (Array.isArray(services) && services.length > 0) {
    const names = services
      .map(item => {
        if (item && typeof item === 'object' && 'name' in item) {
          return String((item as { name?: string }).name || '').trim()
        }
        return String(item || '').trim()
      })
      .filter(Boolean)
    if (names.length > 0) return names.join(', ')
  }
  return pick(row, 'service', 'serviceCategory', 'serviceType', 'category')
}

function vendorLeadPocId(row: VendorLeadItem): string {
  const poc = row.poc
  if (typeof poc === 'string' && poc.trim()) return poc.trim()
  if (poc && typeof poc === 'object') {
    return String(poc._id || poc.id || '').trim()
  }
  const assignment = row.assignment
  const staffId = assignment?.staff_user_id || assignment?.presales_user_id || assignment?.rm_user_id || ''
  if (staffId.startsWith('tatva:')) return staffId.slice('tatva:'.length)
  return staffId
}

function vendorLeadPocName(row: VendorLeadItem): string {
  const poc = row.poc
  if (poc && typeof poc === 'object') {
    const name = String(poc.fullName || poc.name || '').trim()
    if (name) return name
  }
  const fromAssignment = String(row.assignment?.assignee_name || '').trim()
  if (fromAssignment) return fromAssignment
  return pick(row, 'assigneeName', 'assignee', 'assignedToName', 'assignedTo', 'rejectedByName', 'rejectedBy')
}

function vendorLeadTeamComment(row: VendorLeadItem): string {
  const assignment = row.assignment
  const fromNotes = String(assignment?.notes || '').trim()
  if (fromNotes) return fromNotes

  const log = assignment?.comment_log
  if (Array.isArray(log) && log.length > 0) {
    return log
      .map(entry => {
        const text = String(entry?.text || '').trim()
        if (!text) return ''
        const author = String(entry?.author_name || '').trim()
        return author ? `${author}: ${text}` : text
      })
      .filter(Boolean)
      .join('\n')
  }

  const fromRow = pick(
    row,
    'rejectionReason',
    'rejection_reason',
    'rejectReason',
    'reject_reason',
    'teamComment',
    'team_comment',
    'notes',
    'comment',
    'adminNotes',
  )
  return fromRow === '—' ? '' : fromRow
}

export default function VendorLeads() {
  const [items, setItems] = useState<VendorLeadItem[]>([])
  const [employees, setEmployees] = useState<TatvaEmployee[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [limit] = useState(20)
  const [statusFilter, setStatusFilter] = useState('pending')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [assigningId, setAssigningId] = useState<string | null>(null)

  const loadEmployees = useCallback(async () => {
    try {
      const data = await api.tatvaEmployees('sales', { page: 1, limit: 50 })
      setEmployees(data.employees || [])
    } catch {
      setEmployees([])
    }
  }, [])

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
    loadEmployees()
  }, [loadEmployees])

  useEffect(() => {
    setPage(1)
  }, [statusFilter])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  const rowId = (row: VendorLeadItem) => String(row._id || row.id || '')

  const handleAssign = async (row: VendorLeadItem, pocId: string) => {
    const vendorLeadId = rowId(row)
    if (!pocId || !vendorLeadId) return
    setAssigningId(vendorLeadId)
    try {
      await api.assignVendorLeadPoc(vendorLeadId, pocId)
      toast.success('Sales POC assigned')
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Assignment failed')
    } finally {
      setAssigningId(null)
    }
  }

  const isRejectedView = statusFilter === 'rejected'
  const columnCount = isRejectedView ? 10 : 11

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Vendor Leads</h1>
          <p className="text-sm text-slate-500 mt-1">
            {total} record{total !== 1 ? 's' : ''} from Tatva
            {isRejectedView
              ? ' · read-only assignee and rejection notes'
              : ' · sales assignment via Tatva POC'}
          </p>
        </div>
        <select
          className="input w-40"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
        >
          <option value="pending">Pending</option>
          <option value="rejected">Rejected</option>
        </select>
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
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Assignee</th>
                <th className="px-4 py-3 font-medium">
                  {isRejectedView ? 'Rejection reason' : 'Team comment'}
                </th>
                {!isRejectedView && (
                  <th className="px-4 py-3 font-medium">Assign</th>
                )}
                <th className="px-4 py-3 font-medium whitespace-nowrap">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr>
                  <td colSpan={columnCount} className="px-4 py-12 text-center text-slate-500">
                    Loading vendor leads...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={columnCount} className="px-4 py-12 text-center text-slate-500">
                    No vendor leads found.
                  </td>
                </tr>
              ) : (
                items.map(row => {
                  const name = pick(row, 'name', 'fullName', 'contactName', 'vendorName', 'designation')
                  const company = pick(row, 'companyName', 'businessName', 'company', 'vendorName')
                  const phone = pick(row, 'phoneNumber', 'phone', 'mobile')
                  const email = pick(row, 'email')
                  const location = pick(row, 'businessAddress', 'location', 'city', 'address')
                  const service = formatVendorServices(row)
                  const leadStatus = vendorStatus(row)
                  const created = pick(row, 'createdAt', 'created_at')
                  const rowKey = rowId(row) || `${phone}-${created}`
                  const assignment = row.assignment
                  const assignee = vendorLeadPocName(row)
                  const teamComment = vendorLeadTeamComment(row)
                  const currentPoc = vendorLeadPocId(row)

                  return (
                    <tr
                      key={rowKey}
                      className=""
                    >
                      <td className="px-4 py-3 text-theme-primary whitespace-nowrap">{name}</td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{company}</td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">{phone}</td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{email}</td>
                      <td className="px-4 py-3 text-slate-400 max-w-[160px] truncate" title={location}>
                        {location}
                      </td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{service}</td>
                      <td className="px-4 py-3">
                        <span className={vendorStatusBadge(leadStatus)}>{leadStatus}</span>
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">
                        {assignee}
                      </td>
                      <td className="px-4 py-3 align-top min-w-[200px]">
                        <StaffCommentDisplay text={teamComment} />
                      </td>
                      {!isRejectedView && (
                        <td className="px-4 py-3">
                          {employees.length > 0 ? (
                            <select
                              className="input text-xs py-1.5 min-w-[160px]"
                              value={currentPoc}
                              disabled={assigningId === rowKey}
                              onChange={e => handleAssign(row, e.target.value)}
                            >
                              <option value="">Assign to...</option>
                              {employees.map(emp => {
                                const id = tatvaEmployeeId(emp)
                                if (!id) return null
                                return (
                                  <option key={id} value={id}>
                                    {tatvaEmployeeLabel(emp)}
                                  </option>
                                )
                              })}
                            </select>
                          ) : (
                            <span className="text-xs text-slate-600">—</span>
                          )}
                        </td>
                      )}
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
