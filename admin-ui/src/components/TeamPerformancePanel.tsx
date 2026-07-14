import clsx from 'clsx'
import { format } from 'date-fns'
import {
  Briefcase,
  CheckCircle2,
  Clock,
  LayoutDashboard,
  Target,
  TrendingUp,
  Users,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { api } from '../api/client'

export type PeriodKey = 'day' | 'month' | 'quarter' | 'half_year' | 'year' | 'all'

export type LeadBucket = {
  total: number
  pending: number
  completed: number
  achievement_pct: number
}

export type TeamPerformanceData = {
  period: string
  period_start?: string | null
  period_end?: string | null
  user_leads: LeadBucket
  vendor_leads: LeadBucket
  overall: LeadBucket
  staff?: {
    type: string
    id: string
    name: string
    email?: string | null
  }
  target?: {
    target_leads: number
    completed: number
    pending: number
    remaining: number
    achievement_pct: number
    configured: boolean
  }
  generated_at?: string
}

export const PERIOD_OPTIONS: { key: PeriodKey; label: string }[] = [
  { key: 'day', label: 'Today' },
  { key: 'month', label: 'This month' },
  { key: 'quarter', label: 'This quarter' },
  { key: 'half_year', label: 'Bi-annually' },
  { key: 'year', label: 'This year' },
  { key: 'all', label: 'All time' },
]

function formatPeriodRange(data: TeamPerformanceData): string {
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

const ICON_STYLES: Record<string, string> = {
  'text-indigo-400': 'bg-indigo-500/15 text-indigo-400 border-indigo-500/20',
  'text-amber-400': 'bg-amber-500/15 text-amber-400 border-amber-500/20',
  'text-teal-400': 'bg-teal-500/15 text-teal-400 border-teal-500/20',
  'text-teal-300': 'bg-teal-500/15 text-teal-300 border-teal-500/20',
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
  const iconStyle = ICON_STYLES[color] || 'bg-slate-500/15 text-slate-400 border-slate-500/20'
  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-700/40 p-4 bg-navy-900/40">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">{label}</p>
          <p className="text-2xl font-bold text-slate-100 tabular-nums">{value}</p>
        </div>
        <div className={clsx('p-2 rounded-lg border', iconStyle)}>
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
          <h2 className="text-sm font-semibold text-slate-200">{title}</h2>
          <p className="text-xs text-slate-500">{subtitle}</p>
        </div>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard label="Total leads" value={stats.total} icon={Icon} color="text-indigo-400" />
        <StatCard label="Pending" value={stats.pending} icon={Clock} color="text-amber-400" />
        <StatCard label="Closed" value={stats.completed} icon={CheckCircle2} color="text-teal-400" />
        <StatCard label="Completion rate" value={`${stats.achievement_pct}%`} icon={Target} color="text-teal-300" />
      </div>
    </div>
  )
}

type TeamPerformancePanelProps = {
  data: TeamPerformanceData
  editableTarget?: boolean
  staffType?: 'sales' | 'rm'
  staffId?: string
  onTargetSaved?: () => void
}

export function TeamPerformancePanel({
  data,
  editableTarget = false,
  staffType,
  staffId,
  onTargetSaved,
}: TeamPerformancePanelProps) {
  const target = data.target
  const [targetDraft, setTargetDraft] = useState(String(target?.target_leads ?? 0))
  const [savingTarget, setSavingTarget] = useState(false)

  useEffect(() => {
    setTargetDraft(String(target?.target_leads ?? 0))
  }, [target?.target_leads, data.period, staffId])

  const handleSaveTarget = async () => {
    if (!editableTarget || !staffType || !staffId) return
    const value = Number.parseInt(targetDraft, 10)
    if (!Number.isFinite(value) || value < 0) {
      toast.error('Enter a valid target (0 or more)')
      return
    }
    setSavingTarget(true)
    try {
      await api.upsertSalesTarget({
        staff_type: staffType,
        staff_id: staffId,
        period: data.period,
        target_leads: value,
      })
      toast.success('Sales target updated')
      onTargetSaved?.()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to save target')
    } finally {
      setSavingTarget(false)
    }
  }

  return (
    <div className="space-y-4">
      {data.staff?.name && (
        <p className="text-xs text-slate-500">{formatPeriodRange(data)}</p>
      )}

      <div className="glass-card bg-indigo-500/5 border-indigo-500/20 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs uppercase tracking-wide text-indigo-300">
            {data.staff?.name ? `${data.staff.name} — overall performance` : 'Overall performance'}
          </p>
          {target && target.target_leads > 0 && (
            <span className="text-xs text-teal-300">
              {target.achievement_pct}% of sales target
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard label="Total leads" value={data.overall.total} icon={LayoutDashboard} color="text-indigo-400" />
          <StatCard label="Pending" value={data.overall.pending} icon={Clock} color="text-amber-400" />
          <StatCard label="Closed" value={data.overall.completed} icon={CheckCircle2} color="text-teal-400" />
          <StatCard label="Completion rate" value={`${data.overall.achievement_pct}%`} icon={Target} color="text-teal-300" />
        </div>

        {target && (
          <div className="rounded-lg border border-slate-700/60 bg-navy-800/40 p-4 space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <TrendingUp className="w-4 h-4 text-indigo-300" />
              Sales target
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <div>
                <p className="text-xs text-slate-500 mb-1">Target (closed leads)</p>
                {editableTarget && staffType && staffId ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={0}
                      className="input text-sm py-1.5 w-24"
                      value={targetDraft}
                      onChange={e => setTargetDraft(e.target.value)}
                    />
                    <button
                      type="button"
                      className="btn-secondary text-xs py-1.5 px-3"
                      disabled={savingTarget}
                      onClick={handleSaveTarget}
                    >
                      {savingTarget ? 'Saving...' : 'Save'}
                    </button>
                  </div>
                ) : (
                  <p className="text-2xl font-bold text-slate-200">{target.target_leads}</p>
                )}
              </div>
              <div>
                <p className="text-xs text-slate-500 mb-1">Closed</p>
                <p className="text-2xl font-bold text-teal-300">{target.completed}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 mb-1">Remaining to target</p>
                <p className="text-2xl font-bold text-amber-300">{target.remaining}</p>
              </div>
              <div>
                <p className="text-xs text-slate-500 mb-1">Target progress</p>
                <p className="text-2xl font-bold text-indigo-300">{target.achievement_pct}%</p>
              </div>
            </div>
            {target.target_leads > 0 && (
              <div className="h-2 rounded-full bg-slate-700/80 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-teal-400 transition-all"
                  style={{ width: `${Math.min(100, target.achievement_pct)}%` }}
                />
              </div>
            )}
            {!target.configured && editableTarget && (
              <p className="text-xs text-slate-500">
                No target set yet for this period. Enter a number and save.
              </p>
            )}
          </div>
        )}
      </div>

      <div className="glass-card space-y-8">
        <LeadSection
          title="User leads"
          subtitle="Presales leads assigned"
          icon={Users}
          stats={data.user_leads}
        />
        <div className="border-t border-slate-700/50" />
        <LeadSection
          title="Vendor leads"
          subtitle="Vendor leads assigned"
          icon={Briefcase}
          stats={data.vendor_leads}
        />
      </div>
    </div>
  )
}
