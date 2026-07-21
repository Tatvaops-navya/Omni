import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type EmployeeProjectItem } from '../api/client'
import clsx from 'clsx'
import { format } from 'date-fns'

const PAGE_SIZE = 10

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

function projectKey(row: EmployeeProjectItem): string {
  return String(
    row._id
    || row.id
    || row.projectId
    || row.project_id
    || projectField(row, 'name', 'projectName', 'title'),
  )
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
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [total, setTotal] = useState(0)
  const [hasMore, setHasMore] = useState(true)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const loadingRef = useRef(false)
  const pageRef = useRef(1)
  const hasMoreRef = useRef(true)

  const loadPage = useCallback(async (pageNum: number, mode: 'replace' | 'append') => {
    if (loadingRef.current) return
    loadingRef.current = true
    if (mode === 'replace') {
      setLoading(true)
      setError('')
    } else {
      setLoadingMore(true)
    }
    try {
      const data = await api.myProjects({ page: pageNum, limit: PAGE_SIZE })
      if (!data.success && data.message && mode === 'replace') {
        setError(data.message)
      }
      const nextItems = data.data?.items || []
      const nextTotal = data.data?.total ?? nextItems.length
      const nextTotalPages = data.data?.totalPages ?? 1
      const more = pageNum < nextTotalPages && nextItems.length > 0
      setTotal(nextTotal)
      setHasMore(more)
      pageRef.current = pageNum
      hasMoreRef.current = more
      if (data.data?.employee_name) {
        setEmployeeName(data.data.employee_name)
      }
      if (mode === 'append') {
        setProjects(prev => {
          const seen = new Set(prev.map(projectKey))
          return [...prev, ...nextItems.filter(row => !seen.has(projectKey(row)))]
        })
      } else {
        setProjects(nextItems)
      }
    } catch (e) {
      if (mode === 'replace') {
        setError(e instanceof Error ? e.message : 'Failed to load projects')
        setProjects([])
        setEmployeeName('')
        setTotal(0)
        setHasMore(false)
        hasMoreRef.current = false
      }
    } finally {
      loadingRef.current = false
      setLoading(false)
      setLoadingMore(false)
    }
  }, [])

  useEffect(() => {
    loadPage(1, 'replace')
  }, [loadPage])

  useEffect(() => {
    const id = window.setInterval(() => {
      if (pageRef.current === 1 && !loadingRef.current) {
        loadPage(1, 'replace')
      }
    }, 60000)
    return () => window.clearInterval(id)
  }, [loadPage])

  useEffect(() => {
    const node = sentinelRef.current
    if (!node) return undefined
    const observer = new IntersectionObserver(
      entries => {
        const entry = entries[0]
        if (!entry?.isIntersecting) return
        if (!hasMoreRef.current || loadingRef.current) return
        loadPage(pageRef.current + 1, 'append')
      },
      { root: null, rootMargin: '200px', threshold: 0 },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [loadPage, projects.length, hasMore])

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="page-title">My Projects</h1>
        <p className="text-sm text-slate-500 mt-1">
          {total} assigned project{total !== 1 ? 's' : ''}
        </p>
      </div>

      {error && <div className="card text-red-400 text-sm">{error}</div>}

      <div className="card p-0 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="data-table w-full text-sm text-left">
            <thead>
              <tr className="">
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
                  const status = projectField(row, 'status', 'stage')
                  return (
                    <tr key={projectKey(row)} className="">
                      <td className="px-4 py-3 text-theme-primary whitespace-nowrap">
                        {projectField(row, 'projectName', 'name', 'title', 'projectId', 'project_id')}
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">
                        {projectCustomer(row)}
                      </td>
                      <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">
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

        <div ref={sentinelRef} className="table-footer">
          {loadingMore ? (
            <span className="text-xs text-slate-500">Loading more...</span>
          ) : hasMore ? (
            <span className="text-xs text-slate-600">Scroll for more</span>
          ) : projects.length > 0 ? (
            <span className="text-xs text-slate-600">
              Showing {projects.length} of {total}
            </span>
          ) : null}
        </div>
      </div>
    </div>
  )
}
