export type CustomProgressStage = {
  id: string
  title: string
  description?: string | null
  /** Default pipeline key (unassigned, assigned, in_progress) or another custom stage id */
  insert_after: string
  completed_at?: string | null
  created_at?: string
  created_by_name?: string | null
}

export type ProgressInsertAfterOption = {
  value: string
  label: string
}

const DEFAULT_STAGE_LABELS: Record<string, string> = {
  unassigned: 'Lead received',
  assigned: 'Assigned to team',
  in_progress: 'In progress',
}

type TimelineOptionSource = {
  key: string
  title: string
  isCustom?: boolean
  stageId?: string
}

/** Build insert-after options in timeline order, including existing custom stages. */
export function buildProgressInsertAfterOptions(
  milestones: TimelineOptionSource[],
): ProgressInsertAfterOption[] {
  const options: ProgressInsertAfterOption[] = []
  for (const milestone of milestones) {
    if (milestone.key === 'presales_completed') continue
    if (milestone.isCustom && milestone.stageId) {
      options.push({
        value: milestone.stageId,
        label: `After ${milestone.title}`,
      })
      continue
    }
    if (!milestone.isCustom) {
      const label = DEFAULT_STAGE_LABELS[milestone.key] || milestone.title
      options.push({
        value: milestone.key,
        label: `After ${label}`,
      })
    }
  }
  return options
}
