import type { LeadCommentLogEntry } from '../components/CommentLogModal'
import {
  LEAD_PIPELINE_STEPS,
  leadPipelineStepIndex,
  leadPipelineStatusLabel,
} from './leadStatus'

export type TimelineMilestoneState = 'done' | 'active' | 'upcoming'

export type TimelineSubEvent = {
  text: string
  timestamp?: string
  author?: string | null
}

export type TimelineMilestone = {
  key: string
  title: string
  description?: string
  timestamp?: string
  state: TimelineMilestoneState
  subEvents?: TimelineSubEvent[]
}

export function buildLeadTimeline({
  status,
  commentCount = 0,
  commentLog = [],
  createdAt,
  assignedAt,
  completedAt,
  assigneeName,
}: {
  status?: string | null
  commentCount?: number
  commentLog?: LeadCommentLogEntry[]
  createdAt?: string | null
  assignedAt?: string | null
  completedAt?: string | null
  assigneeName?: string | null
}): TimelineMilestone[] {
  const currentIndex = leadPipelineStepIndex(status, commentCount)
  const assignee = (assigneeName || '').trim()

  const definitions = [
    {
      key: 'unassigned',
      title: 'Lead received',
      description: 'Lead entered the presales pipeline.',
      timestamp: createdAt || undefined,
    },
    {
      key: 'assigned',
      title: assignee ? `Assigned to ${assignee}` : 'Assigned to team',
      description: assignee
        ? `${assignee} is working this lead.`
        : 'Awaiting team member assignment.',
      timestamp: assignedAt || undefined,
    },
    {
      key: 'in_progress',
      title: 'In progress',
      description: commentLog.length
        ? `${commentLog.length} team update${commentLog.length !== 1 ? 's' : ''} logged.`
        : 'Follow-ups and status updates from the team.',
      timestamp: commentLog.length
        ? commentLog[commentLog.length - 1]?.created_at
        : undefined,
      subEvents: [...commentLog]
        .sort((a, b) => {
          const ta = a.created_at ? new Date(a.created_at).getTime() : 0
          const tb = b.created_at ? new Date(b.created_at).getTime() : 0
          return ta - tb
        })
        .map(entry => ({
          text: entry.text,
          timestamp: entry.created_at,
          author: entry.author_name,
        })),
    },
    {
      key: 'presales_completed',
      title: 'Completed',
      description: 'Presales work has been marked complete.',
      timestamp: completedAt || undefined,
    },
  ]

  return definitions.map((step, index) => ({
    ...step,
    state: (index < currentIndex
      ? 'done'
      : index === currentIndex
        ? 'active'
        : 'upcoming') as TimelineMilestoneState,
  }))
}

export function currentStageLabel(status?: string | null, commentCount = 0): string {
  return leadPipelineStatusLabel(status, commentCount)
}

export { LEAD_PIPELINE_STEPS, leadPipelineStepIndex }
