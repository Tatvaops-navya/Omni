import type { LeadCommentLogEntry } from '../components/CommentLogModal'

export function extractCommentLog(
  assignment: Record<string, unknown> | undefined,
): LeadCommentLogEntry[] {
  if (!assignment) return []

  const direct = assignment.comment_log
  if (Array.isArray(direct)) {
    return direct
      .filter((entry): entry is LeadCommentLogEntry => (
        !!entry
        && typeof entry === 'object'
        && typeof (entry as LeadCommentLogEntry).text === 'string'
        && (entry as LeadCommentLogEntry).text.trim().length > 0
      ))
  }

  const snapshot = assignment.snapshot
  if (snapshot && typeof snapshot === 'object') {
    const stored = (snapshot as Record<string, unknown>).__team_comment_log
    if (Array.isArray(stored)) {
      return stored
        .filter((entry): entry is LeadCommentLogEntry => (
          !!entry
          && typeof entry === 'object'
          && typeof (entry as LeadCommentLogEntry).text === 'string'
          && (entry as LeadCommentLogEntry).text.trim().length > 0
        ))
    }
  }

  const notes = String(assignment.notes || '').trim()
  if (notes) {
    return [{
      text: notes,
      created_at: typeof assignment.updated_at === 'string' ? assignment.updated_at : undefined,
    }]
  }

  return []
}
