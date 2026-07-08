import { useCallback, useEffect, useState } from 'react'
import {
  api,
  PresalesItem,
  TatvaEmployee,
  VendorLeadItem,
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
  const staffId = assignment?.staff_user_id || assignment?.presales_user_id || assignment?.rm_user_id || ''
  if (staffId.startsWith('tatva:')) return staffId.slice('tatva:'.length)
  return staffId
}

function RmAssignPlaceholder() {
  return (
    <select
      className="input text-xs py-1.5 min-w-[160px] opacity-60 cursor-not-allowed"
      disabled
      title="RM assignment API coming soon"
    >
      <option value="">Assign RM...</option>
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

function vendorRowId(vendor: VendorLeadItem): string {
  return String(vendor._id || vendor.id || '').trim()
}

function vendorDisplayName(vendor: VendorLeadItem): string {
  const name = String(
    vendor.fullName || vendor.name || vendor.contactName || vendor.vendorName || '',
  ).trim()
  const company = String(
    vendor.companyName || vendor.businessName || vendor.company || '',
  ).trim()
  if (name && company && name.toLowerCase() !== company.toLowerCase()) {
    return `${name} (${company})`
  }
  return name || company || 'Vendor'
}

function isApprovedVendor(vendor: VendorLeadItem): boolean {
  const status = String(
    vendor.status || vendor.leadStatus || vendor.approvalStatus || 'approved',
  ).trim().toLowerCase()
  return status === 'approved' || status === 'verified'
}

function rowVendorName(row: PresalesItem): string {
  return String(row.vendor_assignment?.vendor_name || '').trim() || '—'
}

function assignedVendorId(row: PresalesItem): string {
  return String(row.vendor_assignment?.vendor_id || '').trim()
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
    return <span className="text-xs text-slate-600">—</span>
  }
  return (
    <select
      className="input text-xs py-1.5 min-w-[160px]"
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

function VendorAssignDropdown({
  row,
  vendors,
  assigningId,
  crmConfigured,
  onAssign,
}: {
  row: PresalesItem
  vendors: VendorLeadItem[]
  assigningId: string | null
  crmConfigured: boolean
  onAssign: (row: PresalesItem, vendorId: string) => void
}) {
  const currentVendor = assignedVendorId(row)
  if (vendors.length === 0) {
    return <span className="text-xs text-slate-600">—</span>
  }
  return (
    <select
      className="input text-xs py-1.5 min-w-[160px]"
      value={currentVendor}
      disabled={assigningId === row._id || !crmConfigured}
      title={crmConfigured ? undefined : 'Configure Supabase CRM to save assignments'}
      onChange={e => onAssign(row, e.target.value)}
    >
      <option value="">Assign vendor...</option>
      {vendors.map(vendor => {
        const id = vendorRowId(vendor)
        if (!id) return null
        return (
          <option key={id} value={id}>
            {vendorDisplayName(vendor)}
          </option>
        )
      })}
    </select>
  )
}

export default function Presales() {
  const [items, setItems] = useState<PresalesItem[]>([])
  const [employees, setEmployees] = useState<TatvaEmployee[]>([])
  const [vendors, setVendors] = useState<VendorLeadItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [flagFilter, setFlagFilter] = useState('high')
  const [crmConfigured, setCrmConfigured] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [assigningId, setAssigningId] = useState<string | null>(null)
  const [assigningVendorId, setAssigningVendorId] = useState<string | null>(null)
  const [viewLead, setViewLead] = useState<{ name?: string; phone?: string } | null>(null)
  const columnCount = 13

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
      const data = await api.tatvaEmployees('sales', { page: 1, limit: 50 })
      setEmployees(data.employees || [])
    } catch (e) {
      setEmployees([])
      console.warn('Failed to load Tatva employees:', e)
    }
  }, [])

  const loadVendors = useCallback(async () => {
    try {
      const data = await api.vendors({ page: 1, limit: 200 })
      const approved = (data.data?.items || []).filter(isApprovedVendor)
      setVendors(approved)
    } catch (e) {
      setVendors([])
      console.warn('Failed to load approved vendors:', e)
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
    loadVendors()
    loadCrmStatus()
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load, loadEmployees, loadVendors, loadCrmStatus])

  useEffect(() => {
    setPage(1)
  }, [flagFilter])

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
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Assignment failed')
    } finally {
      setAssigningId(null)
    }
  }

  const handleAssignVendor = async (row: PresalesItem, vendorId: string) => {
    if (!vendorId) return
    if (!crmConfigured) {
      toast.error('Configure Supabase CRM to save assignments')
      return
    }
    const vendor = vendors.find(v => vendorRowId(v) === vendorId)
    setAssigningVendorId(row._id)
    try {
      await api.assignPresalesVendor(row._id, {
        vendor_id: vendorId,
        vendor_name: vendor ? vendorDisplayName(vendor) : '',
        vendor_company: String(vendor?.companyName || vendor?.businessName || '').trim(),
        vendor_phone: String(vendor?.phoneNumber || vendor?.phone || '').trim(),
        snapshot: { ...row },
      })
      toast.success('Vendor assigned')
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Vendor assignment failed')
    } finally {
      setAssigningVendorId(null)
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
            {vendors.length > 0 ? ` · ${vendors.length} approved vendor${vendors.length !== 1 ? 's' : ''}` : ''}
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
                <th className="px-4 py-3 font-medium whitespace-nowrap">Assignee</th>
                <th className="px-4 py-3 font-medium">Track</th>
                <th className="px-4 py-3 font-medium">Assign sales</th>
                <th className="px-4 py-3 font-medium">Assign RM</th>
                <th className="px-4 py-3 font-medium whitespace-nowrap">Vendor</th>
                <th className="px-4 py-3 font-medium">Assign vendor</th>
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
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                        {rowAssigneeName(row, employees)}
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
                        <RmAssignPlaceholder />
                      </td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap max-w-[180px] truncate">
                        {rowVendorName(row)}
                      </td>
                      <td className="px-4 py-3">
                        <VendorAssignDropdown
                          row={row}
                          vendors={vendors}
                          assigningId={assigningVendorId}
                          crmConfigured={crmConfigured}
                          onAssign={handleAssignVendor}
                        />
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
