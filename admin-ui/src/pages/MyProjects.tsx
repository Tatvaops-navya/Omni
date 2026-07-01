import { useCallback, useEffect, useState } from 'react'
import { api, type EmployeeProjectItem } from '../api/client'
import clsx from 'clsx'
import { format } from 'date-fns'

function formatDate(iso: string | undefined): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy, HH:mm')
  } catch {
    return iso
  }
}

function projectField(row: EmployeeProjectItem, ...keys: string[]): string {
  for (const key of keys) {
    const v = row[key]
    if (v != null && String(v).trim()) return String(v)
  }
  return '—'
}

function projectCustomer(row: EmployeeProjectItem): string {
  const nested = row.user || row.customer || row.userId
  if (nested && typeof nested === 'object') {
    const name = nested.fullName || nested.name || nested.phoneNumber || nested.email
    if (name && String(name).trim()) return String(name)
  }
  return projectField(row, 'customerName', 'clientName', 'userName', 'client')
}

function projectEmployeeName(row: EmployeeProjectItem, fallback = ''): string {
  const emp = row.employeeId
  if (emp && typeof emp === 'object') {
    const name = emp.fullName || emp.name
    if (name && String(name).trim()) return String(name)
  }
  const direct = projectField(row, 'employeeName', 'employeeFullName', 'assignedEmployeeName')
  if (direct !== '—') return direct
  return fallback || '—'
}

function projectStatusClass(status: string | undefined): string {
  const value = (status || 'pending').toLowerCase()
  if (value.includes('complete') || value.includes('active') || value.includes('progress')) {
    return 'bg-teal-600/20 text-teal-300'
  }
  if (value.includes('cancel') || value.includes('reject') || value.includes('hold')) {
    return 'bg-red-600/20 text-red-300'
  }
  return 'bg-amber-600/20 text-amber-300'
}

export default function MyProjects() {
  const [projects, setProjects] = useState<EmployeeProjectItem[]>([])
  const [employeeName, setEmployeeName] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.myProjects()
      if (!data.success && data.message) {
        setError(data.message)
      }
      setProjects(data.data?.items || [])
      setEmployeeName(data.data?.employee_name || '')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load projects')
      setProjects([])
      setEmployeeName('')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [load])

  const total = projects.length

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-200">My Projects</h1>
        <p className="text-sm text-slate-500 mt-1">
          {total} assigned project{total !== 1 ? 's' : ''}
        </p>
      </div>

      {error && <div className="card text-red-400 text-sm">{error}</div>}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead>
              <tr className="border-b border-slate-700/50 text-xs text-slate-500 uppercase tracking-wide">
                <th className="px-4 py-3 font-medium">Project</th>
                <th className="px-4 py-3 font-medium">Customer</th>
                <th className="px-4 py-3 font-medium">Employee</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Assigned</th>
              </tr>
            </thead>
            <tbody>
              {loading && projects.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-slate-500">Loading projects...</td>
                </tr>
              ) : projects.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-slate-500">
                    No projects assigned yet.
                  </td>
                </tr>
              ) : (
                projects.map(row => {
                  const key = String(row._id || row.id || row.projectId || row.project_id || projectField(row, 'name', 'projectName', 'title'))
                  const status = projectField(row, 'status', 'stage')
                  return (
                    <tr key={key} className="border-b border-slate-700/30 hover:bg-navy-700/30">
                      <td className="px-4 py-3 text-slate-200 whitespace-nowrap">
                        {projectField(row, 'projectName', 'name', 'title', 'projectId', 'project_id')}
                      </td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                        {projectCustomer(row)}
                      </td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                        {projectEmployeeName(row, employeeName)}
                      </td>
                      <td className="px-4 py-3">
                        <span className={clsx('badge uppercase text-[10px]', projectStatusClass(status))}>
                          {status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">
                        {formatDate(String(row.assignedAt || row.assigned_at || row.createdAt || ''))}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
