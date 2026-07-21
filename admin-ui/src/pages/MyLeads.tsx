import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  resolveLoggedInTatvaEmployeeId,
  resolveMeetSlotId,
  TATVA_MY_USER_LEADS_POC_ID,
  TATVA_MY_VENDOR_LEADS_POC_ID,
  type PresalesItem,
  type VendorLeadItem,
} from '../api/client'
import type { MeetLinkRecord, MeetSlot } from '../types/meet'
import clsx from 'clsx'
import { format } from 'date-fns'
import { ExternalLink, MessageSquare } from 'lucide-react'
import toast from 'react-hot-toast'
import CommentLogModal, { type LeadCommentLogEntry } from '../components/CommentLogModal'
import LeadProgressButton from '../components/LeadProgressButton'
import { extractCommentLog } from '../utils/commentLog'
import { extractCustomProgressStages } from '../utils/customProgressStages'
import type { CustomProgressStage } from '../types/leadProgress'

type LeadTab = 'user' | 'vendor' | 'meet'

type MyLeadRow = {
  external_id: string
  status: string
  snapshot: Record<string, unknown>
  assigned_at?: string
  presales_completed_at?: string
  notes?: string
  comment_log?: LeadCommentLogEntry[]
  custom_progress_stages?: CustomProgressStage[]
}

function snap(row: MyLeadRow, ...keys: string[]): string {
  const snapshot = row.snapshot || {}
  for (const key of keys) {
    const v = snapshot[key]
    if (v != null && String(v).trim()) return String(v)
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

function formatSlotWhen(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy, hh:mm a')
  } catch {
    return iso
  }
}

function slotStatusClass(status: string | undefined): string {
  const value = (status || 'pending').toLowerCase()
  if (value === 'scheduled' || value === 'confirmed') {
    return 'bg-teal-600/20 text-teal-300'
  }
  if (value === 'cancelled' || value === 'canceled') {
    return 'bg-red-600/20 text-red-300'
  }
  return 'bg-amber-600/20 text-amber-300'
}

function meetCustomerName(record: MeetLinkRecord): string {
  const user = record.userId
  if (!user) return '—'
  return user.fullName || user.userName || user.phoneNumber || '—'
}

function vendorLeadToMyLeadRow(lead: VendorLeadItem): MyLeadRow {
  const externalId = String(lead._id || lead.id || '').trim()
  const assignment = lead.assignment as Record<string, unknown> | undefined
  const commentLog = extractCommentLog(assignment)
  const notes = String(lead.assignment?.notes || '').trim()
  return {
    external_id: externalId,
    status: String(lead.assignment?.status || lead.status || lead.leadStatus || 'assigned'),
    snapshot: { ...lead },
    assigned_at: String(
      lead.assignment?.assigned_at || lead.createdAt || lead.created_at || lead.updatedAt || '',
    ),
    presales_completed_at: lead.assignment?.presales_completed_at ?? undefined,
    notes: notes || undefined,
    comment_log: commentLog,
    custom_progress_stages: extractCustomProgressStages(assignment),
  }
}

function presalesLeadToMyLeadRow(lead: PresalesItem): MyLeadRow {
  const externalId = String(lead._id || '').trim()
  const assignment = lead.assignment as Record<string, unknown> | undefined
  const commentLog = extractCommentLog(assignment)
  const notes = String(lead.assignment?.notes || '').trim()
  return {
    external_id: externalId,
    status: String(assignment?.status || 'assigned'),
    snapshot: { ...lead },
    assigned_at: String(
      assignment?.assigned_at || lead.createdAt || lead.updatedAt || '',
    ),
    presales_completed_at: assignment?.presales_completed_at as string | undefined,
    notes: notes || undefined,
    comment_log: commentLog,
    custom_progress_stages: extractCustomProgressStages(assignment),
  }
}

function vendorLeadApprovalStatus(row: MyLeadRow): string {
  const snapshot = row.snapshot || {}
  const value = String(
    snapshot.status || snapshot.leadStatus || snapshot.approvalStatus || snapshot.vendorStatus || row.status || 'pending',
  ).trim().toLowerCase()
  return value || 'pending'
}

function canReviewVendorLead(status: string): boolean {
  return status !== 'approved' && status !== 'rejected'
}

function leadActionButtonClass(tone: 'approve' | 'reject' | 'complete'): string {
  const base = 'text-xs font-medium rounded-md px-2 py-1 transition-colors disabled:opacity-50 disabled:pointer-events-none'
  if (tone === 'reject') {
    return `${base} text-red-400 hover:text-red-300 hover:bg-red-500/10`
  }
  return `${base} text-teal-400 hover:text-teal-300 hover:bg-teal-500/10`
}

export default function MyLeads() {
  const [tab, setTab] = useState<LeadTab>('user')
  const [items, setItems] = useState<MyLeadRow[]>([])
  const [meetRecords, setMeetRecords] = useState<MeetLinkRecord[]>([])
  const [busySlotId, setBusySlotId] = useState<string | null>(null)
  const [busyVendorLeadId, setBusyVendorLeadId] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [logModal, setLogModal] = useState<{
    externalId: string
    leadName: string
    leadType: 'user' | 'vendor'
    entries: LeadCommentLogEntry[]
  } | null>(null)

  const handleCommentSaved = useCallback((externalId: string, log: LeadCommentLogEntry[]) => {
    setItems(prev => prev.map(row => (
      row.external_id === externalId
        ? { ...row, comment_log: log, notes: log[log.length - 1]?.text }
        : row
    )))
    setLogModal(prev => (
      prev && prev.externalId === externalId
        ? { ...prev, entries: log }
        : prev
    ))
  }, [])

  const handleProgressStagesChange = useCallback((externalId: string, stages: CustomProgressStage[]) => {
    setItems(prev => prev.map(row => (
      row.external_id === externalId
        ? { ...row, custom_progress_stages: stages }
        : row
    )))
  }, [])

  const leadDisplayName = useCallback((row: MyLeadRow) => {
    if (tab === 'vendor') {
      return snap(row, 'name', 'fullName', 'contactName', 'vendorName')
    }
    return snap(row, 'name')
  }, [tab])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (tab === 'meet') {
        const data = await api.meetLinks({ page, limit: 20 })
        if (!data.success && data.message) {
          setError(data.message)
        }
        setMeetRecords(data.data || [])
        setTotal(data.pagination?.total ?? (data.data || []).length)
        setTotalPages(data.pagination?.totalPages ?? 1)
        setItems([])
      } else if (tab === 'vendor') {
        const data = await api.vendorLeadsByPoc(TATVA_MY_VENDOR_LEADS_POC_ID, { page, limit: 20 })
        if (!data.success && data.message) {
          setError(data.message)
        }
        const rows = (data.data?.items || []).map(vendorLeadToMyLeadRow)
        setItems(rows)
        setTotal(data.data?.total ?? rows.length)
        setTotalPages(data.data?.totalPages ?? 1)
        setMeetRecords([])
      } else {
        const pocId = resolveLoggedInTatvaEmployeeId() || TATVA_MY_USER_LEADS_POC_ID
        const data = await api.presalesByPoc(pocId, { page, limit: 20 })
        if (!data.success && data.message) {
          setError(data.message)
        }
        const rows = (data.data?.items || []).map(presalesLeadToMyLeadRow)
        setItems(rows)
        setTotal(data.data?.total ?? rows.length)
        setTotalPages(data.data?.totalPages ?? 1)
        setMeetRecords([])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
      setItems([])
      setMeetRecords([])
    } finally {
      setLoading(false)
    }
  }, [page, tab])

  useEffect(() => {
    setPage(1)
  }, [tab])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  const handleComplete = async (externalId: string) => {
    try {
      await api.completeMyLead(externalId, undefined, tab === 'vendor' ? 'vendor' : 'user')
      toast.success('Marked as completed')
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not update lead')
    }
  }

  const handleVendorReview = async (externalId: string, action: 'approved' | 'rejected') => {
    if (action === 'rejected' && !window.confirm('Reject this vendor lead?')) {
      return
    }
    setBusyVendorLeadId(externalId)
    try {
      await api.updateVendorLeadStatus(externalId, action)
      toast.success(action === 'approved' ? 'Vendor lead approved' : 'Vendor lead rejected')
      load()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not update vendor lead')
    } finally {
      setBusyVendorLeadId(null)
    }
  }

  const handleMeetAction = async (
    action: 'confirm' | 'reschedule',
    meetLinkId: string,
    slotId: string,
  ) => {
    if (!slotId || !meetLinkId) return
    setBusySlotId(slotId)
    try {
      if (action === 'confirm') {
        await api.confirmMeetSlot(meetLinkId, slotId)
        toast.success('Meet slot confirmed')
      } else {
        await api.rescheduleMeetSlot(slotId)
        toast.success('Meet slot rescheduled')
      }
      load()
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Action failed'
      if (msg.includes('501') || msg.toLowerCase().includes('not configured')) {
        toast.error(`${action === 'confirm' ? 'Confirm' : 'Reschedule'} API coming soon`)
      } else {
        toast.error(msg)
      }
    } finally {
      setBusySlotId(null)
    }
  }

  const meetRows = useMemo(() => {
    const rows: { record: MeetLinkRecord; slot: MeetSlot }[] = []
    for (const record of meetRecords) {
      for (const slot of record.slots || []) {
        rows.push({ record, slot })
      }
    }
    return rows
  }, [meetRecords])

  const tabLabel = tab === 'user' ? 'user' : tab === 'vendor' ? 'vendor' : 'meet'

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="page-title">My Leads</h1>
        <p className="text-sm text-slate-500 mt-1">
          {tab === 'meet'
            ? `${total} meet schedule${total !== 1 ? 's' : ''}`
            : `${total} assigned ${tabLabel} lead${total !== 1 ? 's' : ''}`}
        </p>
      </div>

      <div className="flex gap-2 border-b border-slate-200/80 dark:border-slate-700/50">
        {([
          { key: 'user' as const, label: 'User Leads' },
          { key: 'vendor' as const, label: 'Vendor Leads' },
          { key: 'meet' as const, label: 'Meet' },
        ]).map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={clsx(
              'px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors',
              tab === key
                ? 'border-indigo-500 text-indigo-300'
                : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <div className="card text-red-400 text-sm">{error}</div>}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          {tab === 'meet' ? (
            <table className="data-table w-full text-sm text-left">
              <thead>
                <tr className="">
                  <th className="px-4 py-3 font-medium">Customer</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">Scheduled</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Meet link</th>
                  <th className="px-4 py-3 font-medium">Description</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {loading && meetRows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-slate-500">Loading meet schedules...</td>
                  </tr>
                ) : meetRows.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                      No meet schedules found.
                    </td>
                  </tr>
                ) : (
                  meetRows.map(({ record, slot }) => {
                    const user = record.userId
                    const meetLinkId = record._id || ''
                    const slotId = resolveMeetSlotId(slot)
                    const busy = busySlotId === slotId
                    return (
                      <tr
                        key={slotId || `${record._id}-${slot.scheduledAt}`}
                        className=""
                      >
                        <td className="px-4 py-3 text-theme-primary whitespace-nowrap">
                          {meetCustomerName(record)}
                        </td>
                        <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">
                          {user?.phoneNumber || '—'}
                        </td>
                        <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                          {user?.email || '—'}
                        </td>
                        <td className="px-4 py-3 text-theme-secondary whitespace-nowrap text-xs">
                          {formatSlotWhen(slot.scheduledAt)}
                        </td>
                        <td className="px-4 py-3">
                          <span className={clsx('badge uppercase text-[10px]', slotStatusClass(slot.status))}>
                            {slot.status || 'pending'}
                          </span>
                        </td>
                        <td className="px-4 py-3 max-w-[160px]">
                          {record.meetLink ? (
                            <a
                              href={record.meetLink}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-indigo-400 hover:text-indigo-300 text-xs inline-flex items-center gap-1 truncate"
                              title={record.meetLink}
                            >
                              Join <ExternalLink className="w-3 h-3 shrink-0" />
                            </a>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="px-4 py-3 text-slate-400 max-w-[140px] truncate" title={record.description}>
                          {record.description || '—'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            <button
                              type="button"
                              className="btn-ghost text-xs text-slate-400"
                              disabled={!slotId || !meetLinkId || busy}
                              onClick={() => handleMeetAction('reschedule', meetLinkId, slotId)}
                            >
                              Reschedule
                            </button>
                            <button
                              type="button"
                              className="btn-ghost text-xs text-teal-400"
                              disabled={!slotId || !meetLinkId || busy}
                              onClick={() => handleMeetAction('confirm', meetLinkId, slotId)}
                            >
                              Confirm
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          ) : tab === 'user' ? (
            <table className="data-table w-full text-sm text-left">
              <thead>
                <tr className="">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Flag</th>
                  <th className="px-4 py-3 font-medium">Location</th>
                  <th className="px-4 py-3 font-medium">Track</th>
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
                    <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                      No user leads assigned yet.
                    </td>
                  </tr>
                ) : (
                  items.map(row => (
                    <tr key={row.external_id} className="">
                      <td className="px-4 py-3 text-slate-200">{snap(row, 'name')}</td>
                      <td className="px-4 py-3 text-slate-300">{snap(row, 'phoneNumber', 'phone')}</td>
                      <td className="px-4 py-3">
                        <span className={clsx(
                          'badge uppercase',
                          snap(row, 'flag') === 'high' ? 'bg-teal-600/20 text-teal-300' : 'bg-amber-600/20 text-amber-300',
                        )}>
                          {snap(row, 'flag')}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-slate-400 max-w-[160px] truncate">
                        {snap(row, 'location', 'propertyLocation')}
                      </td>
                      <td className="px-4 py-3">
                        <LeadProgressButton
                          leadName={leadDisplayName(row)}
                          externalId={row.external_id}
                          leadType="user"
                          status={row.status}
                          commentCount={row.comment_log?.length ?? 0}
                          commentLog={row.comment_log || []}
                          customStages={row.custom_progress_stages || []}
                          assignedAt={row.assigned_at}
                          completedAt={row.presales_completed_at}
                          createdAt={row.assigned_at}
                          onStagesChange={stages => handleProgressStagesChange(row.external_id, stages)}
                        />
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">{formatDate(row.assigned_at)}</td>
                      <td className="px-4 py-3 align-top">
                        <div className="flex flex-col gap-2">
                          <button
                            type="button"
                            className="btn-ghost text-slate-400 p-1 self-start relative"
                            title="Comment log"
                            onClick={() => setLogModal({
                              externalId: row.external_id,
                              leadName: leadDisplayName(row),
                              leadType: 'user',
                              entries: row.comment_log || [],
                            })}
                          >
                            <MessageSquare className="w-4 h-4" />
                            {(row.comment_log?.length ?? 0) > 0 && (
                              <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full bg-indigo-600 text-[10px] text-white leading-4 text-center">
                                {row.comment_log!.length}
                              </span>
                            )}
                          </button>
                          {row.status !== 'presales_completed' && (
                            <button
                              type="button"
                              className="btn-ghost text-teal-400 text-xs"
                              onClick={() => handleComplete(row.external_id)}
                            >
                              Mark complete
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          ) : (
            <table className="data-table w-full text-sm text-left">
              <thead>
                <tr className="">
                  <th className="px-4 py-3 font-medium">Vendor</th>
                  <th className="px-4 py-3 font-medium">Company</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">Location</th>
                  <th className="px-4 py-3 font-medium">Service</th>
                  <th className="px-4 py-3 font-medium">Track</th>
                  <th className="px-4 py-3 font-medium">Assigned</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {loading && items.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-12 text-center text-slate-500">Loading...</td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-4 py-12 text-center text-slate-500">
                      No vendor leads assigned yet.
                    </td>
                  </tr>
                ) : (
                  items.map(row => {
                    const approvalStatus = vendorLeadApprovalStatus(row)
                    const canReview = canReviewVendorLead(approvalStatus)
                    const busy = busyVendorLeadId === row.external_id
                    return (
                    <tr key={row.external_id} className="">
                      <td className="px-4 py-3 text-theme-primary whitespace-nowrap">
                        {snap(row, 'name', 'fullName', 'contactName', 'vendorName')}
                      </td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                        {snap(row, 'companyName', 'businessName', 'company', 'vendorName')}
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">
                        {snap(row, 'phoneNumber', 'phone', 'mobile')}
                      </td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                        {snap(row, 'email')}
                      </td>
                      <td className="px-4 py-3 text-slate-400 max-w-[140px] truncate">
                        {snap(row, 'location', 'city', 'address')}
                      </td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                        {snap(row, 'service', 'serviceCategory', 'serviceType', 'category')}
                      </td>
                      <td className="px-4 py-3">
                        <LeadProgressButton
                          leadName={leadDisplayName(row)}
                          externalId={row.external_id}
                          leadType="vendor"
                          status={row.status}
                          commentCount={row.comment_log?.length ?? 0}
                          commentLog={row.comment_log || []}
                          customStages={row.custom_progress_stages || []}
                          assignedAt={row.assigned_at}
                          completedAt={row.presales_completed_at}
                          createdAt={row.assigned_at}
                          onStagesChange={stages => handleProgressStagesChange(row.external_id, stages)}
                        />
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">{formatDate(row.assigned_at)}</td>
                      <td className="px-4 py-3 align-middle">
                        <div className="flex items-center gap-2.5">
                          <button
                            type="button"
                            className="relative h-8 w-8 shrink-0 flex items-center justify-center rounded-md text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-colors"
                            title="Comment log"
                            onClick={() => setLogModal({
                              externalId: row.external_id,
                              leadName: leadDisplayName(row),
                              leadType: 'vendor',
                              entries: row.comment_log || [],
                            })}
                          >
                            <MessageSquare className="w-4 h-4" />
                            {(row.comment_log?.length ?? 0) > 0 && (
                              <span className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full bg-indigo-600 text-[10px] text-white leading-4 text-center">
                                {row.comment_log!.length}
                              </span>
                            )}
                          </button>
                          <div className="flex flex-col gap-2">
                            {canReview && (
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  className={leadActionButtonClass('approve')}
                                  disabled={busy}
                                  onClick={() => handleVendorReview(row.external_id, 'approved')}
                                >
                                  Approve
                                </button>
                                <span className="h-3.5 w-px bg-slate-600/80 shrink-0" aria-hidden="true" />
                                <button
                                  type="button"
                                  className={leadActionButtonClass('reject')}
                                  disabled={busy}
                                  onClick={() => handleVendorReview(row.external_id, 'rejected')}
                                >
                                  Reject
                                </button>
                              </div>
                            )}
                            {row.status !== 'presales_completed' && (
                              <button
                                type="button"
                                className={leadActionButtonClass('complete')}
                                onClick={() => handleComplete(row.external_id)}
                              >
                                Mark complete
                              </button>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          )}
        </div>

        <div className="table-footer flex items-center justify-between">
          <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <button type="button" className="btn-ghost disabled:opacity-40" disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}>Previous</button>
            <button type="button" className="btn-ghost disabled:opacity-40" disabled={page >= totalPages || loading} onClick={() => setPage(p => p + 1)}>Next</button>
          </div>
        </div>
      </div>

      {logModal && (
        <CommentLogModal
          leadName={logModal.leadName}
          externalId={logModal.externalId}
          leadType={logModal.leadType}
          entries={logModal.entries}
          onSaved={log => handleCommentSaved(logModal.externalId, log)}
          onClose={() => setLogModal(null)}
        />
      )}
    </div>
  )
}
