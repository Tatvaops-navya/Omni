import type { CustomProgressStage } from '../types/leadProgress'

export function extractCustomProgressStages(
  assignment: Record<string, unknown> | undefined,
): CustomProgressStage[] {
  if (!assignment) return []

  const direct = assignment.custom_progress_stages
  if (Array.isArray(direct)) {
    return direct
      .filter((entry): entry is CustomProgressStage => (
        !!entry
        && typeof entry === 'object'
        && typeof (entry as CustomProgressStage).id === 'string'
        && typeof (entry as CustomProgressStage).title === 'string'
      ))
      .map(entry => ({
        ...entry,
        insert_after: String(entry.insert_after || 'assigned'),
      }))
  }

  const snapshot = assignment.snapshot
  if (snapshot && typeof snapshot === 'object') {
    const stored = (snapshot as Record<string, unknown>).__custom_progress_stages
    if (Array.isArray(stored)) {
      return stored
        .filter((entry): entry is CustomProgressStage => (
          !!entry
          && typeof entry === 'object'
          && typeof (entry as CustomProgressStage).id === 'string'
          && typeof (entry as CustomProgressStage).title === 'string'
        ))
        .map(entry => ({
          ...entry,
          insert_after: String(entry.insert_after || 'assigned'),
        }))
    }
  }

  return []
}
