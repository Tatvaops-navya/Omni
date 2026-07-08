import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { Package } from 'lucide-react'
import type { LeadCommentLogEntry } from './CommentLogModal'
import LeadProgressModal from './LeadProgressModal'
import type { CustomProgressStage } from '../types/leadProgress'
import { currentStageLabel, timelineProgressRatio } from '../utils/leadTimeline'

export default function LeadProgressButton({
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
  onStagesChange?: (stages: CustomProgressStage[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [localStages, setLocalStages] = useState(customStages)

  useEffect(() => {
    setLocalStages(customStages)
  }, [customStages])

  const stages = localStages.length ? localStages : customStages
  const stage = currentStageLabel(
    status,
    commentCount,
    stages,
    assigneeName,
    createdAt,
    assignedAt,
    completedAt,
    commentLog,
  )
  const progress = timelineProgressRatio(
    status,
    commentCount,
    stages,
    assigneeName,
    createdAt,
    assignedAt,
    completedAt,
    commentLog,
  )
  const isComplete = progress >= 1

  const handleStagesChange = (next: CustomProgressStage[]) => {
    setLocalStages(next)
    onStagesChange?.(next)
  }

  return (
    <>
      <button
        type="button"
        className={clsx(
          'p-1.5 rounded-md transition-colors relative',
          'text-slate-400 hover:text-indigo-300 hover:bg-indigo-500/10',
        )}
        title={`Track progress · ${stage}`}
        onClick={() => setOpen(true)}
      >
        <Package className="w-4 h-4" />
        <span
          className={clsx(
            'absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full border border-navy-900',
            isComplete ? 'bg-teal-400' : progress >= 0.66 ? 'bg-indigo-400' : progress >= 0.33 ? 'bg-amber-400' : 'bg-slate-500',
          )}
        />
      </button>

      {open && (
        <LeadProgressModal
          leadName={leadName}
          externalId={externalId}
          leadType={leadType}
          status={status}
          commentCount={commentCount}
          commentLog={commentLog}
          customStages={stages}
          createdAt={createdAt}
          assignedAt={assignedAt}
          completedAt={completedAt}
          assigneeName={assigneeName}
          onStagesChange={handleStagesChange}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
