import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { Paperclip } from 'lucide-react'

export default function Files() {
  const [attachments, setAttachments] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.attachments()
      .then((r) => setAttachments(r.attachments || []))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="page-title flex items-center gap-2">
          <Paperclip className="w-5 h-5" /> Uploaded Files
        </h1>
        <p className="text-sm text-slate-500 mt-1">Floor plans, photos, and documents from WhatsApp</p>
      </div>
      {loading ? (
        <p className="text-slate-500">Loading...</p>
      ) : attachments.length === 0 ? (
        <p className="text-slate-500">No files uploaded yet.</p>
      ) : (
        <div className="card overflow-x-auto">
          <table className="data-table w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200/80 dark:border-slate-700/50">
                <th className="py-2 pr-4">File</th>
                <th className="py-2 pr-4">Session</th>
                <th className="py-2 pr-4">Service</th>
                <th className="py-2">Link</th>
              </tr>
            </thead>
            <tbody>
              {attachments.map((a, i) => (
                <tr key={i} className="border-b border-slate-800/50 text-slate-300">
                  <td className="py-2 pr-4">{a.file_name}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{a.session_id}</td>
                  <td className="py-2 pr-4">{a.service_category || '-'}</td>
                  <td className="py-2">
                    <a href={a.file_url} target="_blank" rel="noreferrer" className="text-indigo-400 hover:underline">
                      View
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
