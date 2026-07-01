import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { MeetLinkRecord, MeetSlot } from '../types/meet'
import clsx from 'clsx'
import { format } from 'date-fns'
import { ExternalLink } from 'lucide-react'
import toast from 'react-hot-toast'

type LeadTab = 'user' | 'vendor' | 'meet'

type MyLeadRow = {
  external_id: string
  status: string
  snapshot: Record<string, unknown>
  assigned_at?: string
  notes?: string
}

function LeadCommentCell({
  externalId,
  initialNote,
  leadType,
}: {
  externalId: string
  initialNote?: string
  leadType: LeadTab
}) {
  const [draft, setDraft] = useState(initialNote || '')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setDraft(initialNote || '')
  }, [initialNote, externalId])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.saveMyLeadComment(externalId, draft, leadType)
      toast.success('Comment saved')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save comment')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col gap-1.5 min-w-[200px] max-w-[260px]">
      <textarea
        className="input text-xs py-1.5 min-h-[56px] resize-y"
        value={draft}
        onChange={e => setDraft(e.target.value)}
        placeholder="Add a comment..."
        rows={2}
        maxLength={2000}
      />
      <button
        type="button"
        className="btn-ghost text-indigo-400 text-xs self-start disabled:opacity-50"
        disabled={saving}
        onClick={handleSave}
      >
        {saving ? 'Saving...' : 'Save comment'}
      </button>
    </div>
  )
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

export default function MyLeads() {
  const [tab, setTab] = useState<LeadTab>('user')
  const [items, setItems] = useState<MyLeadRow[]>([])
  const [meetRecords, setMeetRecords] = useState<MeetLinkRecord[]>([])
  const [busySlotId, setBusySlotId] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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
      } else {
        const data = await api.myLeads({ page, limit: 20, lead_type: tab })
        setItems(data.data?.items || [])
        setTotal(data.data?.total ?? 0)
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

  const handleMeetAction = async (action: 'confirm' | 'reschedule', slotId: string) => {
    if (!slotId) return
    setBusySlotId(slotId)
    try {
      if (action === 'confirm') {
        await api.confirmMeetSlot(slotId)
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
        <h1 className="text-xl font-semibold text-slate-200">My Leads</h1>
        <p className="text-sm text-slate-500 mt-1">
          {tab === 'meet'
            ? `${total} meet schedule${total !== 1 ? 's' : ''}`
            : `${total} assigned ${tabLabel} lead${total !== 1 ? 's' : ''}`}
        </p>
      </div>

      <div className="flex gap-2 border-b border-slate-700/50">
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
                : 'border-transparent text-slate-500 hover:text-slate-300',
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
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-slate-700/50 text-xs text-slate-500 uppercase tracking-wide">
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
                    const slotId = slot.slotId || ''
                    const busy = busySlotId === slotId
                    return (
                      <tr
                        key={slotId || `${record._id}-${slot.scheduledAt}`}
                        className="border-b border-slate-700/30 hover:bg-navy-700/30"
                      >
                        <td className="px-4 py-3 text-slate-200 whitespace-nowrap">
                          {meetCustomerName(record)}
                        </td>
                        <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                          {user?.phoneNumber || '—'}
                        </td>
                        <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                          {user?.email || '—'}
                        </td>
                        <td className="px-4 py-3 text-slate-300 whitespace-nowrap text-xs">
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
                              disabled={!slotId || busy}
                              onClick={() => handleMeetAction('reschedule', slotId)}
                            >
                              Reschedule
                            </button>
                            <button
                              type="button"
                              className="btn-ghost text-xs text-teal-400"
                              disabled={!slotId || busy}
                              onClick={() => handleMeetAction('confirm', slotId)}
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
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-slate-700/50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Flag</th>
                  <th className="px-4 py-3 font-medium">Location</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Assigned</th>
                  <th className="px-4 py-3 font-medium">Comments</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {loading && items.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-slate-500">Loading...</td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-slate-500">
                      No user leads assigned yet.
                    </td>
                  </tr>
                ) : (
                  items.map(row => (
                    <tr key={row.external_id} className="border-b border-slate-700/30 hover:bg-navy-700/30">
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
                      <td className="px-4 py-3 capitalize text-slate-400">{row.status.replace(/_/g, ' ')}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">{formatDate(row.assigned_at)}</td>
                      <td className="px-4 py-3 align-top">
                        <LeadCommentCell
                          externalId={row.external_id}
                          initialNote={row.notes}
                          leadType="user"
                        />
                      </td>
                      <td className="px-4 py-3 align-top">
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
          ) : (
            <table className="w-full text-sm text-left">
              <thead>
                <tr className="border-b border-slate-700/50 text-xs text-slate-500 uppercase tracking-wide">
                  <th className="px-4 py-3 font-medium">Vendor</th>
                  <th className="px-4 py-3 font-medium">Company</th>
                  <th className="px-4 py-3 font-medium">Phone</th>
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">Location</th>
                  <th className="px-4 py-3 font-medium">Service</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Assigned</th>
                  <th className="px-4 py-3 font-medium">Comments</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {loading && items.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="px-4 py-12 text-center text-slate-500">Loading...</td>
                  </tr>
                ) : items.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="px-4 py-12 text-center text-slate-500">
                      No vendor leads assigned yet.
                    </td>
                  </tr>
                ) : (
                  items.map(row => (
                    <tr key={row.external_id} className="border-b border-slate-700/30 hover:bg-navy-700/30">
                      <td className="px-4 py-3 text-slate-200 whitespace-nowrap">
                        {snap(row, 'name', 'fullName', 'contactName', 'vendorName')}
                      </td>
                      <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                        {snap(row, 'companyName', 'businessName', 'company', 'vendorName')}
                      </td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
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
                      <td className="px-4 py-3 capitalize text-slate-400">{row.status.replace(/_/g, ' ')}</td>
                      <td className="px-4 py-3 text-xs text-slate-500">{formatDate(row.assigned_at)}</td>
                      <td className="px-4 py-3 align-top">
                        <LeadCommentCell
                          externalId={row.external_id}
                          initialNote={row.notes}
                          leadType="vendor"
                        />
                      </td>
                      <td className="px-4 py-3 align-top">
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
          )}
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
