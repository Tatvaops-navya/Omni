import { useMemo, useState } from 'react'
import { Pencil, Percent, Plus, Search, Trash2, X } from 'lucide-react'
import toast from 'react-hot-toast'
import clsx from 'clsx'
import { getUser, isAdminUser } from '../api/client'
import {
  type IncentiveRow,
  loadIncentives,
  matchIncentivesForUser,
  persistIncentives,
} from '../data/incentives'

type EditForm = {
  role: string
  percentage: string
  description: string
  active: boolean
}

export default function IncentiveManagement() {
  const admin = isAdminUser()
  const user = getUser()
  const [rows, setRows] = useState<IncentiveRow[]>(() => loadIncentives())
  const [search, setSearch] = useState('')
  const pageSize = 10
  const [page, setPage] = useState(1)
  const [editing, setEditing] = useState<IncentiveRow | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [form, setForm] = useState<EditForm>({
    role: '',
    percentage: '',
    description: '',
    active: true,
  })

  const visibleRows = useMemo(() => {
    if (admin) return rows
    return matchIncentivesForUser(user, rows)
  }, [admin, user, rows])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return visibleRows
    return visibleRows.filter(row =>
      row.role.toLowerCase().includes(q)
      || row.description.toLowerCase().includes(q)
      || String(row.percentage).includes(q),
    )
  }, [visibleRows, search])

  const total = filtered.length
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  const safePage = Math.min(page, totalPages)
  const start = (safePage - 1) * pageSize
  const pageRows = filtered.slice(start, start + pageSize)

  const openEdit = (row: IncentiveRow) => {
    if (!admin) return
    setIsCreating(false)
    setEditing(row)
    setForm({
      role: row.role,
      percentage: String(row.percentage),
      description: row.description,
      active: row.active,
    })
  }

  const openCreate = () => {
    if (!admin) return
    setIsCreating(true)
    setEditing({
      id: '',
      role: '',
      percentage: 0,
      description: '',
      active: true,
    })
    setForm({
      role: '',
      percentage: '',
      description: '',
      active: true,
    })
  }

  const closeModal = () => {
    setEditing(null)
    setIsCreating(false)
  }

  const saveRows = (next: IncentiveRow[]) => {
    setRows(next)
    persistIncentives(next)
  }

  const handleSave = () => {
    if (!admin) return
    const role = form.role.trim()
    const percentage = Number.parseFloat(form.percentage)
    if (!role) {
      toast.error('Role is required')
      return
    }
    if (!Number.isFinite(percentage) || percentage < 0 || percentage > 100) {
      toast.error('Enter a percentage between 0 and 100')
      return
    }

    if (isCreating) {
      const next: IncentiveRow = {
        id: crypto.randomUUID(),
        role,
        percentage,
        description: form.description.trim(),
        active: form.active,
      }
      saveRows([next, ...rows])
      toast.success('Incentive added')
    } else if (editing) {
      saveRows(rows.map(row => (
        row.id === editing.id
          ? {
              ...row,
              role,
              percentage,
              description: form.description.trim(),
              active: form.active,
            }
          : row
      )))
      toast.success('Incentive updated')
    }
    closeModal()
  }

  const handleDelete = (row: IncentiveRow) => {
    if (!admin) return
    if (!window.confirm(`Delete “${row.role}”?`)) return
    saveRows(rows.filter(item => item.id !== row.id))
    toast.success('Incentive removed')
  }

  const roleLabel = user?.tatvaRole || user?.role || 'your role'

  return (
    <div className="p-6 space-y-5 max-w-[1200px]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="page-title text-theme-heading flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-indigo-500/15 border border-indigo-500/20">
              <Percent className="w-4 h-4 text-indigo-400" />
            </span>
            {admin ? 'Incentive management' : 'My Incentive'}
          </h1>
          <p className="text-sm text-slate-500 mt-1.5">
            {admin
              ? 'Core Incentive Configuration — standard role payout percentages'
              : `Incentive for ${user?.name || 'you'} · matched as ${roleLabel}`}
          </p>
        </div>
        {admin && (
          <button type="button" className="btn-primary flex items-center gap-2" onClick={openCreate}>
            <Plus className="w-4 h-4" />
            Add Incentive
          </button>
        )}
      </div>

      {!admin && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {visibleRows.length === 0 ? (
            <div className="sm:col-span-2 lg:col-span-3 rounded-xl border border-dashed border-slate-200/80 bg-white dark:border-slate-700/50 dark:bg-navy-800/40 px-4 py-10 text-center text-sm text-slate-500">
              No incentive is configured for your role yet. Ask an admin if this looks wrong.
            </div>
          ) : visibleRows.map(row => (
            <div
              key={row.id}
              className={clsx(
                'rounded-xl border border-slate-200/80 bg-white dark:border-white/[0.06] dark:bg-navy-800/70 p-4',
                'shadow-[0_8px_24px_rgba(0,0,0,0.25)]',
              )}
            >
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-2">
                {row.id === 'max-standard-payout' ? 'Project cap' : 'Your standard share'}
              </p>
              <p className="text-sm font-medium text-theme-primary mb-3">{row.role}</p>
              <p className="text-3xl font-bold text-indigo-300 tabular-nums">{row.percentage}%</p>
              {row.description && (
                <p className="text-xs text-slate-500 mt-2">{row.description}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {admin && (
        <>
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              className="input pl-9"
              placeholder="Search incentives..."
              value={search}
              onChange={e => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
          </div>

          <div className="glass-card overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="data-table w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200/80 dark:border-slate-700/50 text-left">
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Role</th>
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500 whitespace-nowrap">
                      Standard percentage (%)
                    </th>
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Description</th>
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Active</th>
                    <th className="px-4 py-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-4 py-10 text-center text-slate-500">
                        No incentives found
                      </td>
                    </tr>
                  ) : pageRows.map(row => (
                    <tr key={row.id} className="">
                      <td className="px-4 py-3 text-theme-primary font-medium max-w-[280px]">{row.role}</td>
                      <td className="px-4 py-3 text-theme-primary tabular-nums whitespace-nowrap">{row.percentage}%</td>
                      <td className="px-4 py-3 text-slate-400 max-w-[320px]">{row.description || '—'}</td>
                      <td className="px-4 py-3">
                        <span
                          className={clsx(
                            'inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold',
                            row.active
                              ? 'bg-indigo-600 text-white'
                              : 'bg-slate-700/80 text-slate-400',
                          )}
                        >
                          {row.active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            title="Edit"
                            className="p-1.5 rounded-lg text-emerald-400 hover:bg-emerald-500/10 transition-colors"
                            onClick={() => openEdit(row)}
                          >
                            <Pencil className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            title="Delete"
                            className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/10 transition-colors"
                            onClick={() => handleDelete(row)}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 table-footer">
              <span className="text-xs text-slate-500">
                Showing {total === 0 ? 0 : start + 1} – {Math.min(start + pageSize, total)} of {total}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn-secondary text-xs py-1.5 px-3"
                  disabled={safePage <= 1}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                >
                  Prev
                </button>
                <span className="min-w-[2rem] text-center text-sm font-medium text-indigo-300 bg-indigo-600/15 border border-indigo-500/30 rounded-lg px-2.5 py-1">
                  {safePage}
                </span>
                <button
                  type="button"
                  className="btn-secondary text-xs py-1.5 px-3"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        </>
      )}

      {admin && editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-slate-200/80 bg-white dark:border-slate-700/50 dark:bg-navy-800 shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200/80 dark:border-slate-700/50">
              <h2 className="text-base font-semibold text-theme-heading">
                {isCreating ? 'Add Incentive' : 'Edit Incentive'}
              </h2>
              <button
                type="button"
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-navy-700"
                onClick={closeModal}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Role</label>
                <input
                  className="input"
                  value={form.role}
                  onChange={e => setForm(prev => ({ ...prev, role: e.target.value }))}
                  placeholder="e.g. Campaign Owner"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">
                  Standard percentage (%)
                </label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={0.1}
                  className="input"
                  value={form.percentage}
                  onChange={e => setForm(prev => ({ ...prev, percentage: e.target.value }))}
                  placeholder="e.g. 3"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Description</label>
                <textarea
                  className="input min-h-[80px] resize-y"
                  value={form.description}
                  onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Optional description"
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-theme-secondary cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded border-slate-300 dark:border-slate-600 bg-white dark:bg-navy-900 text-indigo-500 focus:ring-indigo-500"
                  checked={form.active}
                  onChange={e => setForm(prev => ({ ...prev, active: e.target.checked }))}
                />
                Active
              </label>
            </div>

            <div className="flex justify-end gap-2 px-5 py-4 border-t border-slate-200/80 dark:border-slate-700/50">
              <button type="button" className="btn-secondary" onClick={closeModal}>
                Cancel
              </button>
              <button type="button" className="btn-primary" onClick={handleSave}>
                {isCreating ? 'Add' : 'Save changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
