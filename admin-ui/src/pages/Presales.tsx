import { useCallback, useEffect, useState } from 'react'
import {
  api,
  PresalesItem,
  TatvaEmployee,
  tatvaEmployeeDepartmentName,
  tatvaEmployeeId,
  tatvaEmployeeLabel,
  tatvaEmployeeName,
  tatvaEmployeeRoleName,
} from '../api/client'
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

function assignedEmployeeId(assignment: PresalesItem['assignment']): string {
  const staffId = assignment?.staff_user_id || assignment?.presales_user_id || assignment?.rm_user_id || ''
  if (staffId.startsWith('tatva:')) return staffId.slice('tatva:'.length)
  return staffId
}

function presalesProjectId(row: PresalesItem): string {
  const value = String(row.projectId || row.project_id || '').trim()
  return value || '—'
}

function presalesAssignee(row: PresalesItem): string {
  const assigned = row.assignedTo
  if (assigned && typeof assigned === 'object') {
    const name = String(assigned.fullName || assigned.name || '').trim()
    if (name) return name
  }
  const direct = String(
    row.assigneeName
    || row.assignee
    || (typeof assigned === 'string' ? assigned : '')
    || row.assignment?.assignee_name
    || '',
  ).trim()
  return direct || '—'
}

function rowAssigneeName(row: PresalesItem): string {
  const crm = String(row.assignment?.assignee_name || '').trim()
  if (crm) return crm
  if (row.flag === 'high') return presalesAssignee(row)
  return '—'
}

function AssignDropdown({
  row,
  employees,
  assigningId,
  crmConfigured,
  onAssign,
}: {
  row: PresalesItem
  employees: TatvaEmployee[]
  assigningId: string | null
  crmConfigured: boolean
  onAssign: (row: PresalesItem, employeeId: string) => void
}) {
  const currentAssignee = assignedEmployeeId(row.assignment)
  if (employees.length === 0) {
    return <span className="text-xs text-slate-600">—</span>
  }
  return (
    <select
      className="input text-xs py-1.5 min-w-[160px]"
      value={currentAssignee}
      disabled={assigningId === row._id || !crmConfigured}
      title={crmConfigured ? undefined : 'Configure Supabase CRM to save assignments'}
      onChange={e => onAssign(row, e.target.value)}
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
  )
}

export default function Presales() {
  const [items, setItems] = useState<PresalesItem[]>([])
  const [employees, setEmployees] = useState<TatvaEmployee[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [flagFilter, setFlagFilter] = useState('high')
  const [crmConfigured, setCrmConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [assigningId, setAssigningId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [viewLead, setViewLead] = useState<{ name?: string; phone?: string } | null>(null)
  const isHighIntentView = flagFilter === 'high'
  const columnCount = isHighIntentView ? 12 : 11

  const loadEmployees = useCallback(async () => {
    try {
      const data = await api.tatvaEmployees('sales', { page: 1, limit: 50 })
      setEmployees(data.employees || [])
    } catch (e) {
      setEmployees([])
      console.warn('Failed to load Tatva employees:', e)
    }
  }, [])

  const loadCrmStatus = useCallback(async () => {
    try {
      const data = await api.crmUsers()
      setCrmConfigured(!!data.configured)
    } catch {
      setCrmConfigured(false)
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
      if (typeof data.crm_configured === 'boolean') {
        setCrmConfigured(data.crm_configured)
      }
    } catch {
      setError('Failed to load presales records.')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page, flagFilter])

  useEffect(() => {
    loadEmployees()
    loadCrmStatus()
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load, loadEmployees, loadCrmStatus])

  useEffect(() => {
    setPage(1)
  }, [flagFilter])

  const handleAssign = async (row: PresalesItem, employeeId: string) => {
    if (!employeeId) return
    if (!crmConfigured) {
      toast.error('Configure Supabase CRM to save assignments')
      return
    }
    const employee = employees.find(emp => tatvaEmployeeId(emp) === employeeId)
    setAssigningId(row._id)
    try {
      await api.assignEmployeeLead(row._id, {
        employee_id: employeeId,
        employee_name: employee ? tatvaEmployeeName(employee) : '',
        employee_email: String(employee?.email || ''),
        employee_department: employee ? tatvaEmployeeDepartmentName(employee) : '',
        employee_role: employee ? tatvaEmployeeRoleName(employee) : '',
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
            {employees.length > 0 ? ` · ${employees.length} sales team member${employees.length !== 1 ? 's' : ''}` : ''}
            {crmConfigured ? ' · assignment enabled' : ' · configure Supabase to save assignments'}
          </p>
        </div>
        <select
          className="input w-40"
          value={flagFilter}
          onChange={e => setFlagFilter(e.target.value)}
        >
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
                <th className="px-4 py-3 font-medium min-w-[180px]">Location</th>
                <th className="px-4 py-3 font-medium min-w-[280px]">Property location</th>
                {isHighIntentView && (
                  <th className="px-4 py-3 font-medium whitespace-nowrap">Project ID</th>
                )}
                <th className="px-4 py-3 font-medium whitespace-nowrap">Assignee</th>
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
                  <td colSpan={columnCount} className="px-4 py-12 text-center text-slate-500">
                    Loading presales records...
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={columnCount} className="px-4 py-12 text-center text-slate-500">
                    No presales records found.
                  </td>
                </tr>
              ) : (
                items.map(row => {
                  const assignment = row.assignment
                  const isLowIntent = row.flag === 'low'
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
                      <td className="px-4 py-3 text-slate-400 min-w-[180px] max-w-[220px] whitespace-normal break-words align-top">
                        {row.location || '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-400 min-w-[280px] max-w-[360px] whitespace-normal break-words align-top">
                        {row.propertyLocation || '—'}
                      </td>
                      {isHighIntentView && (
                        <td className="px-4 py-3 text-slate-300 whitespace-nowrap font-mono text-xs">
                          {presalesProjectId(row)}
                        </td>
                      )}
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                        {rowAssigneeName(row)}
                      </td>
                      <td className="px-4 py-3 text-slate-400 capitalize text-xs">
                        {statusLabel(assignment?.status)}
                      </td>
                      <td className="px-4 py-3 align-top">
                        <StaffCommentDisplay text={assignment?.notes} />
                      </td>
                      <td className="px-4 py-3">
                        <AssignDropdown
                          row={row}
                          employees={employees}
                          assigningId={assigningId}
                          crmConfigured={crmConfigured}
                          onAssign={handleAssign}
                        />
                      </td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">
                        {formatDate(row.createdAt)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          {!isLowIntent && (
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
                          )}
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
