import type { LeadCommentLogEntry } from '../components/CommentLogModal'
import type { CustomProgressStage } from '../types/leadProgress'
import {
  LEAD_PIPELINE_STEPS,
  leadPipelineStepIndex,
  normalizeLeadStatus,
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
  isCustom?: boolean
  stageId?: string
}

type MilestoneDefinition = {
  key: string
  title: string
  description?: string
  timestamp?: string
  subEvents?: TimelineSubEvent[]
  isCustom?: boolean
  stageId?: string
  completedAt?: string | null
}

function defaultPipelineIndex(status?: string | null, commentCount = 0): number {
  return leadPipelineStepIndex(status, commentCount)
}

function isDefaultMilestoneDone(
  key: string,
  pipelineIndex: number,
  status?: string | null,
): boolean {
  const defIdx = LEAD_PIPELINE_STEPS.findIndex(step => step.key === key)
  if (defIdx < 0) return false
  if (key === 'presales_completed') {
    return normalizeLeadStatus(status) === 'presales_completed'
  }
  return defIdx < pipelineIndex
}

function mergeMilestoneDefinitions(
  defaults: MilestoneDefinition[],
  customStages: CustomProgressStage[],
): MilestoneDefinition[] {
  const customsByAnchor = new Map<string, CustomProgressStage[]>()
  for (const stage of customStages) {
    const anchor = stage.insert_after || 'assigned'
    const list = customsByAnchor.get(anchor) || []
    list.push(stage)
    customsByAnchor.set(anchor, list)
  }
  for (const list of customsByAnchor.values()) {
    list.sort((a, b) => {
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0
      return ta - tb
    })
  }

  const merged: MilestoneDefinition[] = []

  function appendCustomsAfter(anchorKey: string) {
    const customs = customsByAnchor.get(anchorKey) || []
    for (const custom of customs) {
      merged.push({
        key: `custom:${custom.id}`,
        title: custom.title,
        description: custom.description || `Custom stage added by ${custom.created_by_name || 'team'}.`,
        timestamp: custom.completed_at || custom.created_at || undefined,
        isCustom: true,
        stageId: custom.id,
        completedAt: custom.completed_at,
      })
      appendCustomsAfter(custom.id)
    }
  }

  for (const step of defaults) {
    merged.push(step)
    appendCustomsAfter(step.key)
  }
  return merged
}

function applyMilestoneStates(
  definitions: MilestoneDefinition[],
  pipelineIndex: number,
  status?: string | null,
): TimelineMilestone[] {
  let activeAssigned = false
  return definitions.map(step => {
    const done = step.isCustom
      ? !!step.completedAt
      : isDefaultMilestoneDone(step.key, pipelineIndex, status)

    let state: TimelineMilestoneState
    if (done) {
      state = 'done'
    } else if (!activeAssigned) {
      state = 'active'
      activeAssigned = true
    } else {
      state = 'upcoming'
    }

    return {
      key: step.key,
      title: step.title,
      description: step.description,
      timestamp: step.timestamp,
      state,
      subEvents: step.subEvents,
      isCustom: step.isCustom,
      stageId: step.stageId,
    }
  })
}

export function buildLeadTimeline({
  status,
  commentCount = 0,
  commentLog = [],
  customStages = [],
  createdAt,
  assignedAt,
  completedAt,
  assigneeName,
}: {
  status?: string | null
  commentCount?: number
  commentLog?: LeadCommentLogEntry[]
  customStages?: CustomProgressStage[]
  createdAt?: string | null
  assignedAt?: string | null
  completedAt?: string | null
  assigneeName?: string | null
}): TimelineMilestone[] {
  const pipelineIndex = defaultPipelineIndex(status, commentCount)
  const assignee = (assigneeName || '').trim()

  const defaults: MilestoneDefinition[] = [
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

  const merged = mergeMilestoneDefinitions(defaults, customStages)
  return applyMilestoneStates(merged, pipelineIndex, status)
}

export function currentStageLabel(
  status?: string | null,
  commentCount = 0,
  customStages: CustomProgressStage[] = [],
  assigneeName?: string | null,
  createdAt?: string | null,
  assignedAt?: string | null,
  completedAt?: string | null,
  commentLog: LeadCommentLogEntry[] = [],
): string {
  const milestones = buildLeadTimeline({
    status,
    commentCount,
    commentLog,
    customStages,
    createdAt,
    assignedAt,
    completedAt,
    assigneeName,
  })
  const active = milestones.find(m => m.state === 'active')
  if (active) return active.title
  const lastDone = [...milestones].reverse().find(m => m.state === 'done')
  return lastDone?.title || 'New'
}

export function timelineProgressRatio(
  status?: string | null,
  commentCount = 0,
  customStages: CustomProgressStage[] = [],
  assigneeName?: string | null,
  createdAt?: string | null,
  assignedAt?: string | null,
  completedAt?: string | null,
  commentLog: LeadCommentLogEntry[] = [],
): number {
  const milestones = buildLeadTimeline({
    status,
    commentCount,
    commentLog,
    customStages,
    createdAt,
    assignedAt,
    completedAt,
    assigneeName,
  })
  if (milestones.length === 0) return 0
  const doneCount = milestones.filter(m => m.state === 'done').length
  const activeCount = milestones.some(m => m.state === 'active') ? 0.5 : 0
  return Math.min(1, (doneCount + activeCount) / milestones.length)
}

export { LEAD_PIPELINE_STEPS, leadPipelineStepIndex }
