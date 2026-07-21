import { useCallback, useEffect, useRef, useState } from 'react'
import {
  api,
  PresalesItem,
  TatvaEmployee,
  tatvaEmployeeId,
  tatvaEmployeeLabel,
  tatvaEmployeeName,
  tatvaEmployeeDepartmentName,
  tatvaEmployeeRoleName,
} from '../api/client'
import EnquiryViewModal from '../components/EnquiryViewModal'
import LeadProgressButton from '../components/LeadProgressButton'
import clsx from 'clsx'
import { format } from 'date-fns'
import { Eye } from 'lucide-react'
import toast from 'react-hot-toast'
import { extractCommentLog } from '../utils/commentLog'
import { extractCustomProgressStages } from '../utils/customProgressStages'
import type { CustomProgressStage } from '../types/leadProgress'

const PAGE_SIZE = 20
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

function assignedEmployeeId(row: PresalesItem): string {
  const poc = row.poc
  if (typeof poc === 'string' && poc.trim()) return poc.trim()
  if (poc && typeof poc === 'object') {
    const id = String(poc._id || poc.id || '').trim()
    if (id) return id
  }
  const assigned = row.assignedTo
  if (assigned && typeof assigned === 'object') {
    const id = String(assigned._id || assigned.id || '').trim()
    if (id) return id
  }
  const assignment = row.assignment
  const staffId = assignment?.presales_user_id || ''
  if (staffId.startsWith('tatva:')) return staffId.slice('tatva:'.length)
  return staffId
}

function assignedRmId(row: PresalesItem): string {
  const record = row as PresalesItem & Record<string, unknown>
  for (const key of ['rm', 'rmId', 'rm_id', 'relationshipManager']) {
    const raw = record[key]
    if (raw && typeof raw === 'object') {
      const obj = raw as Record<string, unknown>
      const id = String(obj._id || obj.id || '').trim()
      if (id) return id
    }
    if (typeof raw === 'string' && raw.trim()) return raw.trim()
  }
  const rid = String(row.assignment?.rm_user_id || '').trim()
  if (rid.startsWith('tatva:')) return rid.slice('tatva:'.length)
  return rid
}

function RmAssignDropdown({
  row,
  employees,
  assigningId,
  onAssign,
}: {
  row: PresalesItem
  employees: TatvaEmployee[]
  assigningId: string | null
  onAssign: (row: PresalesItem, employeeId: string) => void
}) {
  const currentRm = assignedRmId(row)
  if (employees.length === 0) {
    return <span className="text-xs text-theme-muted">—</span>
  }
  return (
    <select
      className={clsx(
        'input text-xs py-1.5 min-w-[160px]',
        currentRm ? 'input-assigned' : 'input-unassigned',
      )}
      value={currentRm}
      disabled={assigningId === row._id}
      onChange={e => onAssign(row, e.target.value)}
    >
      <option value="">Assign RM...</option>
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

function employeeNameById(employeeId: string, employees: TatvaEmployee[]): string {
  if (!employeeId) return ''
  const emp = employees.find(e => tatvaEmployeeId(e) === employeeId)
  return emp ? tatvaEmployeeName(emp) : ''
}

function presalesAssignee(row: PresalesItem, employees: TatvaEmployee[] = []): string {
  const poc = row.poc
  if (poc && typeof poc === 'object') {
    const name = String(poc.fullName || poc.name || '').trim()
    if (name) return name
  }

  const empId = assignedEmployeeId(row)
  const fromEmployees = employeeNameById(empId, employees)
  if (fromEmployees) return fromEmployees

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

function rowAssigneeName(row: PresalesItem, employees: TatvaEmployee[] = []): string {
  const crm = String(row.assignment?.assignee_name || '').trim()
  if (crm) return crm
  return presalesAssignee(row, employees)
}

function rowVendorName(row: PresalesItem): string {
  return String(row.vendor_assignment?.vendor_name || '').trim() || '—'
}

function nestedMarketing(row: PresalesItem): Record<string, unknown> | null {
  const record = row as Record<string, unknown>
  for (const key of ['utm', 'marketing']) {
    const nested = record[key]
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      return nested as Record<string, unknown>
    }
  }
  return null
}

function displayAttr(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>
    const name = String(obj.fullName || obj.name || obj.email || '').trim()
    return name || '—'
  }
  const text = String(value).trim()
  return text || '—'
}

function rowSource(_row: PresalesItem): string {
  // Temporary placeholder until Tatva source API is wired
  return 'Whatsapp'
}

function rowMedium(row: PresalesItem): string {
  const nested = nestedMarketing(row)
  return displayAttr(
    row.utm_medium || row.utmMedium || row.medium || nested?.utm_medium || nested?.utmMedium || nested?.medium,
  )
}

function rowCampaign(row: PresalesItem): string {
  const nested = nestedMarketing(row)
  return displayAttr(
    row.utm_campaign
    || row.utmCampaign
    || row.campaign
    || nested?.utm_campaign
    || nested?.utmCampaign
    || nested?.campaign,
  )
}

function rowCampaignOwner(row: PresalesItem): string {
  const record = row as Record<string, unknown>
  const nested = nestedMarketing(row)
  for (const key of [
    'campaignOwner',
    'campaign_owner',
    'campaignOwnerName',
    'campaign_owner_name',
    'campaignOwnerId',
  ]) {
    const value = record[key] ?? nested?.[key]
    const label = displayAttr(value)
    if (label !== '—') return label
  }
  return '—'
}

function AssignDropdown({
  row,
  employees,
  assigningId,
  onAssign,
}: {
  row: PresalesItem
  employees: TatvaEmployee[]
  assigningId: string | null
  onAssign: (row: PresalesItem, employeeId: string) => void
}) {
  const currentAssignee = assignedEmployeeId(row)
  if (employees.length === 0) {
    return <span className="text-xs text-theme-muted">—</span>
  }
  return (
    <select
      className={clsx(
        'input text-xs py-1.5 min-w-[160px]',
        currentAssignee ? 'input-assigned' : 'input-unassigned',
      )}
      value={currentAssignee}
      disabled={assigningId === row._id}
      onChange={e => onAssign(row, e.target.value)}
    >
      <option value="">Assign sales...</option>
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
  const [rmEmployees, setRmEmployees] = useState<TatvaEmployee[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [flagFilter, setFlagFilter] = useState('high')
  const [crmConfigured, setCrmConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [assigningId, setAssigningId] = useState<string | null>(null)
  const [assigningRmId, setAssigningRmId] = useState<string | null>(null)
  const [viewLead, setViewLead] = useState<{ name?: string; phone?: string } | null>(null)
  const columnCount = 15
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const loadingRef = useRef(false)
  const pageRef = useRef(1)
  const hasMoreRef = useRef(true)

  const handleProgressStagesChange = useCallback((externalId: string, stages: CustomProgressStage[]) => {
    setItems(prev => prev.map(row => (
      row._id === externalId
        ? {
          ...row,
          assignment: {
            ...(row.assignment || {}),
            custom_progress_stages: stages,
          },
        }
        : row
    )))
  }, [])

  const loadEmployees = useCallback(async () => {
    try {
      const [salesRes, rmRes] = await Promise.all([
        api.tatvaEmployees('sales', { page: 1, limit: 50 }),
        api.tatvaEmployees('rm', { page: 1, limit: 50 }),
      ])
      setEmployees(salesRes.employees || [])
      setRmEmployees(rmRes.employees || [])
    } catch (e) {
      setEmployees([])
      setRmEmployees([])
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
      const data = await api.presales({
        page: pageNum,
        limit: PAGE_SIZE,
        flag: flagFilter || undefined,
      })
      if (!data.success && data.message && mode === 'replace') {
        setError(data.message)
      }
      const nextItems = data.data?.items || []
      const nextTotal = data.data?.total ?? 0
      const nextTotalPages = data.data?.totalPages ?? 1
      const more = pageNum < nextTotalPages && nextItems.length > 0
      setTotal(nextTotal)
      setPage(pageNum)
      setHasMore(more)
      pageRef.current = pageNum
      hasMoreRef.current = more
      if (typeof data.crm_configured === 'boolean') {
        setCrmConfigured(data.crm_configured)
      }
      if (mode === 'append') {
        setItems(prev => {
          const seen = new Set(prev.map(row => row._id))
          return [...prev, ...nextItems.filter(row => !seen.has(row._id))]
        })
      } else {
        setItems(nextItems)
      }
    } catch {
      if (mode === 'replace') {
        setError('Failed to load presales records.')
        setItems([])
        setHasMore(false)
        hasMoreRef.current = false
      }
    } finally {
      loadingRef.current = false
      setLoading(false)
      setLoadingMore(false)
    }
  }, [flagFilter])

  useEffect(() => {
    loadEmployees()
    loadCrmStatus()
  }, [loadEmployees, loadCrmStatus])

  useEffect(() => {
    pageRef.current = 1
    hasMoreRef.current = true
    setPage(1)
    setHasMore(true)
    loadPage(1, 'replace')
  }, [flagFilter, loadPage])

  useEffect(() => {
    const id = window.setInterval(() => {
      // Soft refresh first page only when user hasn't scrolled further.
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
  }, [loadPage, items.length, hasMore])

  const handleAssign = async (row: PresalesItem, employeeId: string) => {
    if (!employeeId) return
    const emp = employees.find(e => tatvaEmployeeId(e) === employeeId)
    const empName = emp ? tatvaEmployeeName(emp) : ''
    setAssigningId(row._id)
    try {
      await api.assignPresalesPoc(row._id, employeeId)
      if (crmConfigured && emp) {
        try {
          await api.assignEmployeeLead(row._id, {
            employee_id: employeeId,
            employee_name: empName,
            employee_email: String(emp.email || '').trim(),
            employee_department: tatvaEmployeeDepartmentName(emp),
            employee_role: tatvaEmployeeRoleName(emp),
            snapshot: { ...row },
          })
        } catch {
          // Tatva POC is saved; CRM mirror is best-effort
        }
      }
      setItems(prev => prev.map(item => {
        if (item._id !== row._id) return item
        return {
          ...item,
          poc: emp
            ? { _id: employeeId, id: employeeId, fullName: empName, name: empName }
            : employeeId,
          assignment: {
            ...(item.assignment || {}),
            assignee_name: empName || item.assignment?.assignee_name,
          },
        }
      }))
      toast.success('Sales POC assigned')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Assignment failed')
    } finally {
      setAssigningId(null)
    }
  }

  const handleAssignRm = async (row: PresalesItem, employeeId: string) => {
    if (!employeeId) return
    const emp = rmEmployees.find(e => tatvaEmployeeId(e) === employeeId)
    const empName = emp ? tatvaEmployeeName(emp) : ''
    setAssigningRmId(row._id)
    try {
      await api.assignPresalesRm(row._id, employeeId)
      setItems(prev => prev.map(item => {
        if (item._id !== row._id) return item
        return {
          ...item,
          rm: emp
            ? { _id: employeeId, id: employeeId, fullName: empName, name: empName }
            : employeeId,
          assignment: {
            ...(item.assignment || {}),
            rm_user_id: `tatva:${employeeId}`,
            rm_name: empName || item.assignment?.rm_name,
          },
        }
      }))
      toast.success('RM assigned')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'RM assignment failed')
    } finally {
      setAssigningRmId(null)
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title">Pre-sales</h1>
          <p className="text-sm text-slate-500 mt-1">
            {total} record{total !== 1 ? 's' : ''} from Tatva
            {employees.length > 0 ? ` · ${employees.length} sales team member${employees.length !== 1 ? 's' : ''}` : ''}
            {rmEmployees.length > 0 ? ` · ${rmEmployees.length} RM${rmEmployees.length !== 1 ? 's' : ''}` : ''}
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
          <table className="data-table w-full text-sm text-left">
            <thead>
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Flag</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Source</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Medium</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Campaign</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Campaign Owner</th>
                <th className="px-4 py-3 font-medium min-w-[180px]">Location</th>
                <th className="px-4 py-3 font-medium min-w-[280px]">Property location</th>
                <th className="px-4 py-3 font-medium">Track</th>
                <th className="px-4 py-3 font-medium">Assign sales</th>
                <th className="px-4 py-3 font-medium">Assign RM</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Vendor</th>
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
                    <tr key={row._id}>
                      <td className="px-4 py-3 text-theme-primary whitespace-nowrap">
                        {displayName(row.name)}
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">
                        {row.phoneNumber || '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={clsx(
                            'badge uppercase',
                            row.flag === 'high' ? 'badge-danger' : 'badge-warning',
                          )}
                        >
                          {row.flag || '—'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap max-w-[140px] truncate" title={rowSource(row)}>
                        {rowSource(row)}
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap max-w-[140px] truncate" title={rowMedium(row)}>
                        {rowMedium(row)}
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap max-w-[160px] truncate" title={rowCampaign(row)}>
                        {rowCampaign(row)}
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap max-w-[160px] truncate" title={rowCampaignOwner(row)}>
                        {rowCampaignOwner(row)}
                      </td>
                      <td className="px-4 py-3 text-slate-400 min-w-[180px] max-w-[220px] whitespace-normal break-words align-top">
                        {row.location || '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-400 min-w-[280px] max-w-[360px] whitespace-normal break-words align-top">
                        {row.propertyLocation || '—'}
                      </td>
                      <td className="px-4 py-3">
                        <LeadProgressButton
                          leadName={displayName(row.name) !== '—' ? displayName(row.name) : row.phoneNumber || 'Lead'}
                          externalId={row._id}
                          leadType="user"
                          status={assignment?.status}
                          assignedAt={assignment?.assigned_at}
                          completedAt={assignment?.presales_completed_at}
                          createdAt={row.createdAt}
                          assigneeName={rowAssigneeName(row, employees)}
                          commentLog={extractCommentLog(assignment as Record<string, unknown> | undefined)}
                          commentCount={extractCommentLog(assignment as Record<string, unknown> | undefined).length}
                          customStages={extractCustomProgressStages(assignment as Record<string, unknown> | undefined)}
                          onStagesChange={stages => handleProgressStagesChange(row._id, stages)}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <AssignDropdown
                          row={row}
                          employees={employees}
                          assigningId={assigningId}
                          onAssign={handleAssign}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <RmAssignDropdown
                          row={row}
                          employees={rmEmployees}
                          assigningId={assigningRmId}
                          onAssign={handleAssignRm}
                        />
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap max-w-[180px] truncate">
                        {rowVendorName(row)}
                      </td>
                      <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">
                        {formatDate(row.createdAt)}
                      </td>
                      <td className="px-4 py-3">
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
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        <div ref={sentinelRef} className="table-footer">
          {loadingMore ? (
            <span className="text-xs text-slate-500">Loading more...</span>
          ) : hasMore ? (
            <span className="text-xs text-slate-600">Scroll for more</span>
          ) : items.length > 0 ? (
            <span className="text-xs text-slate-600">
              Showing {items.length} of {total}
            </span>
          ) : null}
        </div>
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
