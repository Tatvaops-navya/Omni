import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import clsx from 'clsx'
import { format } from 'date-fns'
import {
  LayoutDashboard,
  Users,
  Briefcase,
  Clock,
  CheckCircle2,
  Target,
} from 'lucide-react'

type PeriodKey = 'day' | 'month' | 'quarter' | 'half_year' | 'year' | 'all'

type LeadBucket = {
  total: number
  pending: number
  completed: number
  achievement_pct: number
}

type TeamDashboardData = {
  period: string
  period_start?: string | null
  period_end?: string | null
  user_leads: LeadBucket
  vendor_leads: LeadBucket
  overall: LeadBucket
  generated_at?: string
}

const PERIOD_OPTIONS: { key: PeriodKey; label: string }[] = [
  { key: 'day', label: 'Today' },
  { key: 'month', label: 'This month' },
  { key: 'quarter', label: 'This quarter' },
  { key: 'half_year', label: 'Bi-annually' },
  { key: 'year', label: 'This year' },
  { key: 'all', label: 'All time' },
]

function formatPeriodRange(data: TeamDashboardData): string {
  if (data.period === 'all' || !data.period_start) return 'All assigned leads'
  try {
    const start = format(new Date(data.period_start), 'dd MMM yyyy')
    const end = data.period_end
      ? format(new Date(data.period_end), 'dd MMM yyyy')
      : 'now'
    return `${start} – ${end}`
  } catch {
    return 'Selected period'
  }
}

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string
  value: number | string
  icon: typeof Users
  color: string
}) {
  return (
    <div className="card">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs text-slate-500 mb-1">{label}</p>
          <p className="text-3xl font-bold text-slate-800 dark:text-slate-200">{value}</p>
        </div>
        <div className={clsx('p-2 bg-slate-200 dark:bg-navy-700 rounded-lg', color)}>
          <Icon className="w-4 h-4" />
        </div>
      </div>
    </div>
  )
}

function LeadSection({
  title,
  subtitle,
  icon: Icon,
  stats,
}: {
  title: string
  subtitle: string
  icon: typeof Users
  stats: LeadBucket
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-300">
          <Icon className="w-4 h-4" />
        </div>
        <div>
          <h2 className="section-title">{title}</h2>
          <p className="text-xs text-slate-500">{subtitle}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Total leads" value={stats.total} icon={Icon} color="text-indigo-400" />
        <StatCard label="Pending" value={stats.pending} icon={Clock} color="text-amber-400" />
        <StatCard label="Completed" value={stats.completed} icon={CheckCircle2} color="text-teal-400" />
        <StatCard label="Achievement" value={`${stats.achievement_pct}%`} icon={Target} color="text-teal-300" />
      </div>
    </div>
  )
}

export default function TeamDashboard() {
  const [period, setPeriod] = useState<PeriodKey>('month')
  const [data, setData] = useState<TeamDashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await api.myDashboard(period) as { data?: TeamDashboardData }
      setData(res.data || null)
    } catch {
      setError('Failed to load dashboard.')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [period])

  useEffect(() => {
    load()
    const id = setInterval(load, 30000)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <LayoutDashboard className="w-5 h-5 text-indigo-400" />
            Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Your assigned leads overview
            {data?.generated_at && (
              <> · updated {format(new Date(data.generated_at), 'HH:mm')}</>
            )}
          </p>
          {data && (
            <p className="text-xs text-slate-600 mt-0.5">{formatPeriodRange(data)}</p>
          )}
        </div>
        <select
          className="input w-44"
          value={period}
          onChange={e => setPeriod(e.target.value as PeriodKey)}
        >
          {PERIOD_OPTIONS.map(opt => (
            <option key={opt.key} value={opt.key}>{opt.label}</option>
          ))}
        </select>
      </div>

      {error && <div className="card text-red-400 text-sm">{error}</div>}

      {loading && !data ? (
        <div className="text-slate-500 text-sm">Loading dashboard...</div>
      ) : data ? (
        <>
          <div className="card bg-indigo-500/5 border-indigo-500/20">
            <p className="text-xs uppercase tracking-wide text-indigo-300 mb-3">Overall performance</p>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <StatCard label="Total leads" value={data.overall.total} icon={LayoutDashboard} color="text-indigo-400" />
              <StatCard label="Pending" value={data.overall.pending} icon={Clock} color="text-amber-400" />
              <StatCard label="Completed" value={data.overall.completed} icon={CheckCircle2} color="text-teal-400" />
              <StatCard label="Sales achievement" value={`${data.overall.achievement_pct}%`} icon={Target} color="text-teal-300" />
            </div>
          </div>

          <div className="card space-y-8">
            <LeadSection
              title="User leads"
              subtitle="Presales leads assigned to you"
              icon={Users}
              stats={data.user_leads}
            />
            <div className="border-t border-slate-200/80 dark:border-slate-700/50" />
            <LeadSection
              title="Vendor leads"
              subtitle="Vendor leads assigned to you"
              icon={Briefcase}
              stats={data.vendor_leads}
            />
          </div>
        </>
      ) : null}
    </div>
  )
}
