import { useEffect, useState } from 'react'
import { X, Loader2, ExternalLink } from 'lucide-react'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { api, resolveMeetSlotId, TatvaUserItem } from '../api/client'
import type { MeetLinkRecord, MeetSlot } from '../types/meet'
import clsx from 'clsx'

function formatSlotWhen(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy, hh:mm a')
  } catch {
    return iso
  }
}

function slotStatusBadge(status: string | undefined) {
  const value = (status || 'pending').toLowerCase()
  if (value === 'scheduled' || value === 'confirmed') {
    return 'bg-teal-600/20 text-teal-300 border-teal-500/30'
  }
  if (value === 'cancelled' || value === 'canceled') {
    return 'bg-red-600/20 text-red-300 border-red-500/30'
  }
  return 'bg-amber-600/20 text-amber-300 border-amber-500/30'
}

function MeetSlotCard({
  record,
  slot,
  onAction,
  busySlotId,
}: {
  record: MeetLinkRecord
  slot: MeetSlot
  onAction: (action: 'confirm' | 'reschedule', meetLinkId: string, slotId: string) => void
  busySlotId: string | null
}) {
  const user = record.userId || {}
  const name = user.fullName || user.userName || 'Customer'
  const phone = user.phoneNumber || '—'
  const email = user.email || '—'
  const slotId = resolveMeetSlotId(slot)
  const meetLinkId = record._id || ''
  const busy = busySlotId === slotId

  return (
    <div className="rounded-lg border border-slate-200/80 bg-white dark:border-slate-700/50 dark:bg-navy-800/50 p-4 space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide">Customer</p>
          <p className="text-theme-primary font-medium">{name}</p>
          <p className="text-xs text-slate-400 mt-1">{phone}</p>
          <p className="text-xs text-slate-500">{email}</p>
        </div>
        <span
          className={clsx(
            'text-[10px] uppercase px-2 py-0.5 rounded-full border',
            slotStatusBadge(slot.status),
          )}
        >
          {slot.status || 'pending'}
        </span>
      </div>

      <div>
        <p className="text-xs text-slate-500 uppercase tracking-wide">Date &amp; time</p>
        <p className="text-slate-200">{formatSlotWhen(slot.scheduledAt)}</p>
      </div>

      {record.description && (
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide">Description</p>
          <p className="text-theme-secondary text-sm">{record.description}</p>
        </div>
      )}

      {record.meetLink && (
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wide">Meeting link</p>
          <a
            href={record.meetLink}
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-300 hover:text-indigo-200 text-sm inline-flex items-center gap-1 break-all"
          >
            {record.meetLink}
            <ExternalLink className="w-3 h-3 shrink-0" />
          </a>
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        <button
          type="button"
          className="btn-ghost text-xs uppercase tracking-wide"
          disabled={!slotId || !meetLinkId || busy}
          onClick={() => onAction('reschedule', meetLinkId, slotId)}
        >
          Reschedule
        </button>
        <button
          type="button"
          className="btn-primary text-xs uppercase tracking-wide"
          disabled={!slotId || !meetLinkId || busy}
          onClick={() => onAction('confirm', meetLinkId, slotId)}
        >
          Confirm
        </button>
      </div>
    </div>
  )
}

export default function MeetScheduleModal({
  user,
  onClose,
}: {
  user: TatvaUserItem
  onClose: () => void
}) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [records, setRecords] = useState<MeetLinkRecord[]>([])
  const [busySlotId, setBusySlotId] = useState<string | null>(null)

  const displayName = user.fullName || user.userName || user.phoneNumber || 'User'

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    api.meetLinks({ user_id: user._id, phone: user.phoneNumber, limit: 20 })
      .then(data => {
        if (cancelled) return
        if (!data.success && data.message) {
          setError(data.message)
          setRecords([])
          return
        }
        setRecords(data.data || [])
        if ((data.data || []).length === 0) {
          setError('No meet schedules found for this user.')
        }
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load meet schedules.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [user._id, user.phoneNumber])

  const handleAction = async (
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

  const slots: { record: MeetLinkRecord; slot: MeetSlot }[] = []
  for (const record of records) {
    for (const slot of record.slots || []) {
      slots.push({ record, slot })
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-lg max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-theme-primary">Meet schedules</h2>
            <p className="text-sm text-slate-500 mt-1">{displayName}</p>
          </div>
          <button type="button" className="btn-ghost p-1 shrink-0" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            Loading schedules…
          </div>
        ) : error && slots.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-sm">{error}</div>
        ) : (
          <div className="space-y-3">
            {slots.map(({ record, slot }) => (
              <MeetSlotCard
                key={slot.slotId || `${record._id}-${slot.scheduledAt}`}
                record={record}
                slot={slot}
                onAction={handleAction}
                busySlotId={busySlotId}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
