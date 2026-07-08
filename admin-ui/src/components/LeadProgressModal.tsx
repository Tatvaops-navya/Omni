import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { Check, ChevronDown, ChevronUp, Plus, X } from 'lucide-react'
import toast from 'react-hot-toast'
import { api } from '../api/client'
import type { LeadCommentLogEntry } from './CommentLogModal'
import type { CustomProgressStage } from '../types/leadProgress'
import { buildProgressInsertAfterOptions } from '../types/leadProgress'
import { extractCustomProgressStages } from '../utils/customProgressStages'
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

function MilestoneNode({ state, isCustom }: { state: TimelineMilestone['state']; isCustom?: boolean }) {
  return (
    <div
      className={clsx(
        'w-7 h-7 rounded-full border-2 flex items-center justify-center shrink-0 z-10',
        state === 'done' && (isCustom ? 'bg-teal-500 border-teal-500 text-white' : 'bg-indigo-500 border-indigo-500 text-white'),
        state === 'active' && (isCustom
          ? 'bg-teal-500/20 border-teal-400 ring-2 ring-teal-500/40'
          : 'bg-indigo-500/20 border-indigo-400 ring-2 ring-indigo-500/40'),
        state === 'upcoming' && 'bg-navy-900 border-slate-600',
      )}
    >
      {state === 'done' && <Check className="w-4 h-4" strokeWidth={2.5} />}
      {state === 'active' && (
        <span className={clsx('w-2.5 h-2.5 rounded-full', isCustom ? 'bg-teal-400' : 'bg-indigo-400')} />
      )}
    </div>
  )
}

function MilestoneRow({
  milestone,
  isLast,
  expanded,
  onToggle,
  onCompleteStage,
  completingStageId,
}: {
  milestone: TimelineMilestone
  isLast: boolean
  expanded: boolean
  onToggle: () => void
  onCompleteStage?: (stageId: string) => void
  completingStageId?: string | null
}) {
  const hasSubEvents = (milestone.subEvents?.length ?? 0) > 0
  const lineDone = milestone.state === 'done'

  return (
    <div className="relative flex gap-4 pb-8 last:pb-0">
      {!isLast && (
        <div
          className={clsx(
            'absolute left-[13px] top-7 bottom-0 w-0.5 -translate-x-1/2',
            lineDone ? (milestone.isCustom ? 'bg-teal-500' : 'bg-indigo-500') : 'border-l-2 border-dashed border-slate-600',
          )}
        />
      )}

      <MilestoneNode state={milestone.state} isCustom={milestone.isCustom} />

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
            <div className="flex flex-wrap items-center gap-2">
              <p
                className={clsx(
                  'text-sm font-semibold',
                  milestone.state === 'upcoming' ? 'text-slate-500' : 'text-slate-100',
                )}
              >
                {milestone.title}
              </p>
              {milestone.isCustom && (
                <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-300 border border-teal-500/20">
                  Custom
                </span>
              )}
            </div>
            {milestone.timestamp && milestone.state !== 'upcoming' && (
              <p className={clsx('text-xs mt-0.5', milestone.isCustom ? 'text-teal-300/80' : 'text-indigo-300/80')}>
                {formatWhen(milestone.timestamp)}
              </p>
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

        {milestone.isCustom && milestone.stageId && milestone.state === 'active' && onCompleteStage && (
          <button
            type="button"
            className="mt-2 text-xs text-teal-400 hover:text-teal-300 disabled:opacity-50"
            disabled={completingStageId === milestone.stageId}
            onClick={() => onCompleteStage(milestone.stageId!)}
          >
            {completingStageId === milestone.stageId ? 'Saving...' : 'Mark stage complete'}
          </button>
        )}

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
  externalId,
  leadType = 'user',
  status,
  commentCount = 0,
  commentLog = [],
  customStages = [],
  createdAt,
  assignedAt,
  completedAt,
  assigneeName,
  onClose,
  onStagesChange,
}: {
  leadName: string
  externalId?: string
  leadType?: 'user' | 'vendor'
  status?: string | null
  commentCount?: number
  commentLog?: LeadCommentLogEntry[]
  customStages?: CustomProgressStage[]
  createdAt?: string | null
  assignedAt?: string | null
  completedAt?: string | null
  assigneeName?: string | null
  onClose: () => void
  onStagesChange?: (stages: CustomProgressStage[]) => void
}) {
  const [localStages, setLocalStages] = useState(customStages)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [insertAfter, setInsertAfter] = useState('assigned')
  const [saving, setSaving] = useState(false)
  const [completingStageId, setCompletingStageId] = useState<string | null>(null)

  useEffect(() => {
    setLocalStages(customStages)
  }, [customStages, externalId])

  const milestones = useMemo(
    () => buildLeadTimeline({
      status,
      commentCount,
      commentLog,
      customStages: localStages,
      createdAt,
      assignedAt,
      completedAt,
      assigneeName,
    }),
    [status, commentCount, commentLog, localStages, createdAt, assignedAt, completedAt, assigneeName],
  )

  const insertAfterOptions = useMemo(
    () => buildProgressInsertAfterOptions(milestones),
    [milestones],
  )

  useEffect(() => {
    if (!showAddForm) return
    if (insertAfterOptions.some(opt => opt.value === insertAfter)) return
    const active = milestones.find(m => m.state === 'active')
    if (active?.isCustom && active.stageId) {
      setInsertAfter(active.stageId)
      return
    }
    const last = insertAfterOptions[insertAfterOptions.length - 1]
    if (last) setInsertAfter(last.value)
  }, [showAddForm, insertAfterOptions, insertAfter, milestones])

  const defaultExpanded = milestones.find(
    m => m.key === 'in_progress' && (m.subEvents?.length ?? 0) > 0,
  )?.key
    || milestones.find(m => m.state === 'active')?.key
    || null

  const [expandedKey, setExpandedKey] = useState<string | null>(defaultExpanded)
  const stage = currentStageLabel(
    status,
    commentCount,
    localStages,
    assigneeName,
    createdAt,
    assignedAt,
    completedAt,
    commentLog,
  )

  const applyStagesFromAssignment = (assignment: Record<string, unknown> | undefined) => {
    const stages = extractCustomProgressStages(assignment)
    setLocalStages(stages)
    onStagesChange?.(stages)
  }

  const handleAddStage = async () => {
    const title = newTitle.trim()
    if (!title) {
      toast.error('Enter a stage name')
      return
    }
    if (!externalId) {
      toast.error('Lead id missing — cannot save custom stage')
      return
    }
    setSaving(true)
    try {
      const res = await api.addProgressStage(externalId, {
        title,
        description: newDescription.trim() || undefined,
        insert_after: insertAfter,
      }, leadType) as { assignment?: Record<string, unknown> }
      applyStagesFromAssignment(res.assignment)
      setNewTitle('')
      setNewDescription('')
      setShowAddForm(false)
      toast.success('Stage added')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not add stage')
    } finally {
      setSaving(false)
    }
  }

  const handleCompleteStage = async (stageId: string) => {
    if (!externalId) return
    setCompletingStageId(stageId)
    try {
      const res = await api.completeProgressStage(externalId, stageId, leadType) as {
        assignment?: Record<string, unknown>
      }
      applyStagesFromAssignment(res.assignment)
      toast.success('Stage marked complete')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not update stage')
    } finally {
      setCompletingStageId(null)
    }
  }

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
              onCompleteStage={externalId ? handleCompleteStage : undefined}
              completingStageId={completingStageId}
            />
          ))}
        </div>

        <div className="mt-6 pt-4 border-t border-slate-700/50">
          {!showAddForm ? (
            <button
              type="button"
              className="btn-ghost text-sm text-indigo-300 hover:text-indigo-200 inline-flex items-center gap-1.5"
              onClick={() => setShowAddForm(true)}
            >
              <Plus className="w-4 h-4" />
              Add custom stage
            </button>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-slate-500">
                Add a stage between the default steps (e.g. GMeet scheduled, Site visit).
              </p>
              <input
                className="input text-sm w-full"
                value={newTitle}
                onChange={e => setNewTitle(e.target.value)}
                placeholder="Stage name"
                maxLength={120}
              />
              <textarea
                className="input text-sm w-full min-h-[60px] resize-y"
                value={newDescription}
                onChange={e => setNewDescription(e.target.value)}
                placeholder="Optional description"
                maxLength={500}
                rows={2}
              />
              <label className="block text-xs text-slate-500">
                Insert after
                <select
                  className="input text-sm w-full mt-1"
                  value={insertAfter}
                  onChange={e => setInsertAfter(e.target.value)}
                >
                  {insertAfterOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn-primary text-sm disabled:opacity-50"
                  disabled={saving || !newTitle.trim()}
                  onClick={handleAddStage}
                >
                  {saving ? 'Adding...' : 'Add stage'}
                </button>
                <button
                  type="button"
                  className="btn-ghost text-sm"
                  disabled={saving}
                  onClick={() => {
                    setShowAddForm(false)
                    setNewTitle('')
                    setNewDescription('')
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
