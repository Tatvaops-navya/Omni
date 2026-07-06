import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { format } from 'date-fns'
import toast from 'react-hot-toast'
import { api } from '../api/client'
import { extractCommentLog } from '../utils/commentLog'

export type LeadCommentLogEntry = {
  text: string
  created_at?: string
  author_name?: string | null
  author_id?: string | null
}

function formatLogWhen(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy, hh:mm a')
  } catch {
    return iso
  }
}

export default function CommentLogModal({
  leadName,
  externalId,
  leadType,
  entries,
  onClose,
  onSaved,
}: {
  leadName: string
  externalId: string
  leadType: 'user' | 'vendor'
  entries: LeadCommentLogEntry[]
  onClose: () => void
  onSaved: (log: LeadCommentLogEntry[]) => void
}) {
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [localEntries, setLocalEntries] = useState(entries)

  useEffect(() => {
    setLocalEntries(entries)
    setDraft('')
  }, [entries, externalId])

  const sorted = [...localEntries].sort((a, b) => {
    const ta = a.created_at ? new Date(a.created_at).getTime() : 0
    const tb = b.created_at ? new Date(b.created_at).getTime() : 0
    return ta - tb
  })

  const handleSave = async () => {
    const text = draft.trim()
    if (!text) {
      toast.error('Enter a comment before saving')
      return
    }
    setSaving(true)
    try {
      const res = await api.saveMyLeadComment(externalId, text, leadType) as {
        assignment?: Record<string, unknown>
      }
      let log = extractCommentLog(res.assignment)
      if (log.length === 0) {
        log = [
          ...localEntries,
          {
            text,
            created_at: new Date().toISOString(),
          },
        ]
      }
      setLocalEntries(log)
      onSaved(log)
      setDraft('')
      toast.success('Comment saved')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Could not save comment')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-lg max-h-[85vh] overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 pb-4 border-b border-slate-700/50">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-slate-200">Comment log</h2>
            <p className="text-xs text-slate-500 mt-1 truncate">{leadName}</p>
          </div>
          <button type="button" className="btn-ghost p-1 shrink-0" onClick={onClose} aria-label="Close">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 py-4 space-y-3 min-h-0">
          {sorted.length === 0 ? (
            <p className="text-center text-sm text-slate-500 py-6">No comments yet. Add your first note below.</p>
          ) : (
            sorted.map((entry, idx) => (
              <div
                key={`${entry.created_at || 'entry'}-${idx}`}
                className="rounded-lg border border-slate-700/50 bg-navy-800/40 px-3 py-2.5"
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-slate-500 mb-1.5">
                  <span>{formatLogWhen(entry.created_at)}</span>
                  {entry.author_name && (
                    <>
                      <span className="text-slate-600">·</span>
                      <span className="text-slate-400">{entry.author_name}</span>
                    </>
                  )}
                </div>
                <p className="text-sm text-slate-200 whitespace-pre-wrap break-words">{entry.text}</p>
              </div>
            ))
          )}
        </div>

        <div className="pt-4 border-t border-slate-700/50 space-y-2">
          <textarea
            className="input text-sm py-2 min-h-[72px] resize-y w-full"
            value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder="Add a comment (e.g. rescheduled to tomorrow)..."
            rows={3}
            maxLength={2000}
          />
          <button
            type="button"
            className="btn-primary text-sm disabled:opacity-50"
            disabled={saving || !draft.trim()}
            onClick={handleSave}
          >
            {saving ? 'Saving...' : 'Save comment'}
          </button>
        </div>
      </div>
    </div>
  )
}
