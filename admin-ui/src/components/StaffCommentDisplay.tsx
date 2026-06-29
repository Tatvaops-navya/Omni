export function StaffCommentDisplay({ text }: { text?: string | null }) {
  const value = (text || '').trim()
  if (!value) {
    return <span className="text-slate-600 text-xs">—</span>
  }
  return (
    <p
      className="text-xs text-slate-300 max-w-[220px] whitespace-pre-wrap line-clamp-4"
      title={value}
    >
      {value}
    </p>
  )
}
