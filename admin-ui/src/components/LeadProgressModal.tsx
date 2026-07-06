import { useMemo, useState } from 'react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { Check, ChevronDown, ChevronUp, X } from 'lucide-react'
import type { LeadCommentLogEntry } from './CommentLogModal'
import {
  buildLeadTimeline,
  currentStageLabel,
  type TimelineMilestone,
} from '../utils/leadTimeline'

function formatWhen(iso?: string): string {
  if (!iso) return ''
  try {
    return format(new Date(iso), 'HH:mm · dd MMM yyyy')
  } catch {
    return iso
  }
}

function MilestoneNode({ state }: { state: TimelineMilestone['state'] }) {
  return (
    <div
      className={clsx(
        'w-7 h-7 rounded-full border-2 flex items-center justify-center shrink-0 z-10',
        state === 'done' && 'bg-indigo-500 border-indigo-500 text-white',
        state === 'active' && 'bg-indigo-500/20 border-indigo-400 ring-2 ring-indigo-500/40',
        state === 'upcoming' && 'bg-navy-900 border-slate-600',
      )}
    >
      {state === 'done' && <Check className="w-4 h-4" strokeWidth={2.5} />}
      {state === 'active' && <span className="w-2.5 h-2.5 rounded-full bg-indigo-400" />}
    </div>
  )
}

function MilestoneRow({
  milestone,
  isLast,
  expanded,
  onToggle,
}: {
  milestone: TimelineMilestone
  isLast: boolean
  expanded: boolean
  onToggle: () => void
}) {
  const hasSubEvents = (milestone.subEvents?.length ?? 0) > 0
  const lineDone = milestone.state === 'done'

  return (
    <div className="relative flex gap-4 pb-8 last:pb-0">
      {!isLast && (
        <div
          className={clsx(
            'absolute left-[13px] top-7 bottom-0 w-0.5 -translate-x-1/2',
            lineDone ? 'bg-indigo-500' : 'border-l-2 border-dashed border-slate-600',
          )}
        />
      )}

      <MilestoneNode state={milestone.state} />

      <div className="flex-1 min-w-0 pt-0.5">
        <button
          type="button"
          className={clsx(
            'w-full flex items-start justify-between gap-2 text-left',
            hasSubEvents && 'cursor-pointer group',
            !hasSubEvents && 'cursor-default',
          )}
          onClick={hasSubEvents ? onToggle : undefined}
        >
          <div className="min-w-0">
            <p
              className={clsx(
                'text-sm font-semibold',
                milestone.state === 'upcoming' ? 'text-slate-500' : 'text-slate-100',
              )}
            >
              {milestone.title}
            </p>
            {milestone.timestamp && milestone.state !== 'upcoming' && (
              <p className="text-xs text-indigo-300/80 mt-0.5">{formatWhen(milestone.timestamp)}</p>
            )}
            {milestone.description && (
              <p className="text-xs text-slate-500 mt-1">{milestone.description}</p>
            )}
          </div>
          {hasSubEvents && (
            <span className="text-slate-500 group-hover:text-slate-300 shrink-0 mt-0.5">
              {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </span>
          )}
        </button>

        {hasSubEvents && expanded && (
          <div className="mt-3 ml-1 space-y-3 border-l-2 border-indigo-500/30 pl-4">
            {milestone.subEvents!.map((event, idx) => (
              <div key={`${event.timestamp || 'e'}-${idx}`} className="relative">
                <span className="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full bg-indigo-400" />
                {event.timestamp && (
                  <p className="text-[11px] text-indigo-300/70">{formatWhen(event.timestamp)}</p>
                )}
                <p className="text-sm text-slate-300 mt-0.5 whitespace-pre-wrap break-words">{event.text}</p>
                {event.author && (
                  <p className="text-[11px] text-slate-500 mt-0.5">— {event.author}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default function LeadProgressModal({
  leadName,
  status,
  commentCount = 0,
  commentLog = [],
  createdAt,
  assignedAt,
  completedAt,
  assigneeName,
  onClose,
}: {
  leadName: string
  status?: string | null
  commentCount?: number
  commentLog?: LeadCommentLogEntry[]
  createdAt?: string | null
  assignedAt?: string | null
  completedAt?: string | null
  assigneeName?: string | null
  onClose: () => void
}) {
  const milestones = useMemo(
    () => buildLeadTimeline({
      status,
      commentCount,
      commentLog,
      createdAt,
      assignedAt,
      completedAt,
      assigneeName,
    }),
    [status, commentCount, commentLog, createdAt, assignedAt, completedAt, assigneeName],
  )

  const defaultExpanded = milestones.find(
    m => m.key === 'in_progress' && (m.subEvents?.length ?? 0) > 0,
  )?.key
    || milestones.find(m => m.state === 'active')?.key
    || null

  const [expandedKey, setExpandedKey] = useState<string | null>(defaultExpanded)
  const stage = currentStageLabel(status, commentCount)

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-md max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-6">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-slate-200">Lead progress</h2>
            <p className="text-sm text-slate-400 mt-0.5 truncate">{leadName}</p>
            <span className="inline-block mt-2 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
              Current · {stage}
            </span>
          </div>
          <button type="button" className="btn-ghost p-1 shrink-0" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="pl-1">
          {milestones.map((milestone, index) => (
            <MilestoneRow
              key={milestone.key}
              milestone={milestone}
              isLast={index === milestones.length - 1}
              expanded={expandedKey === milestone.key}
              onToggle={() => setExpandedKey(prev => (prev === milestone.key ? null : milestone.key))}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
