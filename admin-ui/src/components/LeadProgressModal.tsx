import { useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { format } from 'date-fns'
import { Check, ChevronDown, ChevronUp, Circle, Plus, X } from 'lucide-react'
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

function formatWhenShort(iso?: string): string {
  if (!iso) return ''
  try {
    return format(new Date(iso), 'dd MMM yyyy')
  } catch {
    return iso
  }
}

function stepAccent(milestone: TimelineMilestone) {
  if (milestone.isCustom) {
    return {
      ring: 'ring-teal-500/40',
      fill: 'bg-teal-500 border-teal-400',
      activeBg: 'bg-teal-500/15 border-teal-500/30',
      text: 'text-teal-300',
      line: 'from-teal-500 to-teal-400',
      dot: 'bg-teal-400',
    }
  }
  return {
    ring: 'ring-indigo-500/40',
    fill: 'bg-indigo-500 border-indigo-400',
    activeBg: 'bg-indigo-500/15 border-indigo-500/30',
    text: 'text-indigo-300',
    line: 'from-indigo-500 to-indigo-400',
    dot: 'bg-indigo-400',
  }
}

function StepNode({ milestone, index }: { milestone: TimelineMilestone; index: number }) {
  const accent = stepAccent(milestone)
  const { state } = milestone

  return (
    <div
      className={clsx(
        'relative flex items-center justify-center w-11 h-11 rounded-full border-2 transition-all duration-300',
        state === 'done' && clsx(accent.fill, 'text-white shadow-lg shadow-indigo-500/20'),
        state === 'active' && clsx(
          'bg-white dark:bg-navy-800 border-indigo-400 ring-4',
          accent.ring,
          milestone.isCustom && 'border-teal-400 ring-teal-500/40',
        ),
        state === 'upcoming' && 'bg-slate-100 dark:bg-navy-900/80 border-slate-300 dark:border-slate-600 text-slate-500',
      )}
    >
      {state === 'done' && <Check className="w-5 h-5" strokeWidth={2.5} />}
      {state === 'active' && (
        <span className={clsx('w-3 h-3 rounded-full animate-pulse', accent.dot)} />
      )}
      {state === 'upcoming' && (
        <span className="text-xs font-semibold tabular-nums">{index + 1}</span>
      )}
    </div>
  )
}

function StepConnector({
  leftDone,
  isCustom,
}: {
  leftDone: boolean
  isCustom?: boolean
}) {
  return (
    <div className="flex-1 min-w-[24px] max-w-[80px] h-11 flex items-center px-1">
      <div
        className={clsx(
          'w-full h-1 rounded-full transition-colors duration-300',
          leftDone
            ? clsx('bg-gradient-to-r', isCustom ? 'from-teal-500 to-teal-400' : 'from-indigo-500 to-indigo-400')
            : 'bg-slate-700/80',
        )}
      />
    </div>
  )
}

function HorizontalStepper({
  milestones,
  expandedKey,
  onToggle,
  onCompleteStage,
  completingStageId,
}: {
  milestones: TimelineMilestone[]
  expandedKey: string | null
  onToggle: (key: string) => void
  onCompleteStage?: (stageId: string) => void
  completingStageId?: string | null
}) {
  const activeMilestone = milestones.find(m => m.state === 'active')

  return (
    <div className="rounded-xl border border-slate-200/80 bg-slate-50 dark:border-white/[0.06] dark:bg-navy-900/60 p-5 sm:p-6 space-y-5">
      <div className="flex items-start w-full min-w-0">
        {milestones.map((milestone, index) => {
          const hasSubEvents = (milestone.subEvents?.length ?? 0) > 0
          const isExpanded = expandedKey === milestone.key
          const accent = stepAccent(milestone)
          const isActive = milestone.state === 'active'
          const isDone = milestone.state === 'done'

          return (
            <div key={milestone.key} className="flex items-start flex-1 min-w-0 last:flex-none">
              <div className="flex flex-col items-center flex-1 min-w-[88px] max-w-[140px]">
                <StepNode milestone={milestone} index={index} />

                <button
                  type="button"
                  className={clsx(
                    'mt-3 w-full rounded-lg px-2 py-2 text-center transition-colors',
                    isActive && clsx('border', accent.activeBg),
                    hasSubEvents && 'hover:bg-white/[0.03] cursor-pointer',
                    !hasSubEvents && 'cursor-default',
                  )}
                  onClick={hasSubEvents ? () => onToggle(milestone.key) : undefined}
                >
                  <p
                    className={clsx(
                      'text-[11px] font-semibold leading-snug line-clamp-2',
                      isActive && 'text-slate-900 dark:text-slate-100',
                      isDone && 'text-theme-secondary',
                      milestone.state === 'upcoming' && 'text-slate-500',
                    )}
                  >
                    {milestone.title}
                  </p>

                  {milestone.isCustom && (
                    <span className="inline-block mt-1 text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-teal-500/10 text-teal-300 border border-teal-500/20">
                      Custom
                    </span>
                  )}

                  {milestone.timestamp && milestone.state !== 'upcoming' && (
                    <p className={clsx('text-[10px] mt-1 tabular-nums', accent.text)}>
                      {formatWhenShort(milestone.timestamp)}
                    </p>
                  )}

                  {hasSubEvents && (
                    <span className="inline-flex items-center gap-0.5 mt-1 text-[10px] text-slate-500">
                      {milestone.subEvents!.length} update{milestone.subEvents!.length !== 1 ? 's' : ''}
                      {isExpanded
                        ? <ChevronUp className="w-3 h-3" />
                        : <ChevronDown className="w-3 h-3" />}
                    </span>
                  )}
                </button>

                {milestone.isCustom && milestone.stageId && isActive && onCompleteStage && (
                  <button
                    type="button"
                    className="mt-1 text-[10px] font-medium text-teal-400 hover:text-teal-300 disabled:opacity-50"
                    disabled={completingStageId === milestone.stageId}
                    onClick={() => onCompleteStage(milestone.stageId!)}
                  >
                    {completingStageId === milestone.stageId ? 'Saving...' : 'Mark complete'}
                  </button>
                )}
              </div>

              {index < milestones.length - 1 && (
                <StepConnector leftDone={milestone.state === 'done'} isCustom={milestone.isCustom} />
              )}
            </div>
          )
        })}
      </div>

      {activeMilestone?.description && (
        <div className="flex items-start gap-2.5 rounded-lg border border-indigo-500/20 bg-indigo-500/[0.06] px-3.5 py-3">
          <Circle className="w-3.5 h-3.5 text-indigo-400 mt-0.5 shrink-0 fill-indigo-400/30" />
          <p className="text-xs text-slate-400 leading-relaxed">{activeMilestone.description}</p>
        </div>
      )}
    </div>
  )
}

function SubEventsPanel({ milestone }: { milestone: TimelineMilestone }) {
  if (!milestone.subEvents?.length) return null
  return (
    <div className="rounded-xl border border-indigo-500/25 bg-indigo-500/[0.06] p-4">
      <p className="text-xs font-semibold text-indigo-300 mb-3">{milestone.title} — team updates</p>
      <div className="space-y-3 max-h-52 overflow-y-auto pr-1">
        {milestone.subEvents.map((event, idx) => (
          <div
            key={`${event.timestamp || 'e'}-${idx}`}
            className="rounded-lg border border-slate-200/80 bg-slate-50 dark:border-slate-700/40 dark:bg-navy-900/50 px-3 py-2.5"
          >
            {event.timestamp && (
              <p className="text-[11px] text-indigo-300/70 tabular-nums">{formatWhen(event.timestamp)}</p>
            )}
            <p className="text-sm text-theme-secondary mt-0.5 whitespace-pre-wrap break-words">{event.text}</p>
            {event.author && (
              <p className="text-[11px] text-slate-500 mt-1">— {event.author}</p>
            )}
          </div>
        ))}
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

  const expandedMilestone = milestones.find(m => m.key === expandedKey)

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-3xl max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 mb-5">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-theme-heading">Lead progress</h2>
            <p className="text-sm text-slate-400 mt-0.5 truncate">{leadName}</p>
            <span className="inline-flex items-center gap-1.5 mt-2.5 text-[10px] uppercase tracking-[0.12em] font-semibold px-2.5 py-1 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/25">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Current · {stage}
            </span>
          </div>
          <button type="button" className="btn-ghost p-1.5 shrink-0 rounded-lg" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-x-auto -mx-1 px-1">
          <HorizontalStepper
            milestones={milestones}
            expandedKey={expandedKey}
            onToggle={key => setExpandedKey(prev => (prev === key ? null : key))}
            onCompleteStage={externalId ? handleCompleteStage : undefined}
            completingStageId={completingStageId}
          />
        </div>

        {expandedMilestone && (expandedMilestone.subEvents?.length ?? 0) > 0 && (
          <div className="mt-4">
            <SubEventsPanel milestone={expandedMilestone} />
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-slate-200/80 dark:border-slate-700/50">
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
