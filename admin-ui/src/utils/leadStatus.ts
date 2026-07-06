export type LeadPipelineKey = 'unassigned' | 'assigned' | 'in_progress' | 'presales_completed'

export const LEAD_PIPELINE_STEPS: { key: LeadPipelineKey; label: string }[] = [
  { key: 'unassigned', label: 'New' },
  { key: 'assigned', label: 'Assigned' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'presales_completed', label: 'Completed' },
]

export function normalizeLeadStatus(status?: string | null): LeadPipelineKey {
  const value = (status || 'unassigned').trim().toLowerCase()
  if (value === 'presales_completed') return 'presales_completed'
  if (value === 'in_progress') return 'in_progress'
  if (value === 'assigned') return 'assigned'
  return 'unassigned'
}

/** Team activity (comments) bumps assigned → in progress for the tracker. */
export function resolveLeadPipelineStatus(
  status?: string | null,
  commentCount = 0,
): LeadPipelineKey {
  const normalized = normalizeLeadStatus(status)
  if (normalized === 'assigned' && commentCount > 0) {
    return 'in_progress'
  }
  return normalized
}

export function leadPipelineStepIndex(status?: string | null, commentCount = 0): number {
  const key = resolveLeadPipelineStatus(status, commentCount)
  const idx = LEAD_PIPELINE_STEPS.findIndex(step => step.key === key)
  return idx >= 0 ? idx : 0
}

export function leadPipelineStatusLabel(status?: string | null, commentCount = 0): string {
  const key = resolveLeadPipelineStatus(status, commentCount)
  return LEAD_PIPELINE_STEPS.find(step => step.key === key)?.label || 'New'
}
