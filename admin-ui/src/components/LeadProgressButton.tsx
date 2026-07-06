import { useState } from 'react'
import clsx from 'clsx'
import { Package } from 'lucide-react'
import type { LeadCommentLogEntry } from './CommentLogModal'
import LeadProgressModal from './LeadProgressModal'
import { currentStageLabel, leadPipelineStepIndex } from '../utils/leadTimeline'

export default function LeadProgressButton({
  leadName,
  status,
  commentCount = 0,
  commentLog = [],
  createdAt,
  assignedAt,
  completedAt,
  assigneeName,
}: {
  leadName: string
  status?: string | null
  commentCount?: number
  commentLog?: LeadCommentLogEntry[]
  createdAt?: string | null
  assignedAt?: string | null
  completedAt?: string | null
  assigneeName?: string | null
}) {
  const [open, setOpen] = useState(false)
  const stage = currentStageLabel(status, commentCount)
  const stepIndex = leadPipelineStepIndex(status, commentCount)
  const isComplete = stepIndex >= 3

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
            isComplete ? 'bg-teal-400' : stepIndex >= 2 ? 'bg-indigo-400' : stepIndex >= 1 ? 'bg-amber-400' : 'bg-slate-500',
          )}
        />
      </button>

      {open && (
        <LeadProgressModal
          leadName={leadName}
          status={status}
          commentCount={commentCount}
          commentLog={commentLog}
          createdAt={createdAt}
          assignedAt={assignedAt}
          completedAt={completedAt}
          assigneeName={assigneeName}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}
