import clsx from 'clsx'
import { format } from 'date-fns'
import {
  Briefcase,
  Calendar,
  CheckCircle2,
  ChevronDown,
  Clock,
  LayoutDashboard,
  Target,
  TrendingUp,
  User,
  Users,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import toast from 'react-hot-toast'
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
} from 'recharts'
import {
  api,
  TatvaEmployee,
  tatvaEmployeeId,
  tatvaEmployeeLabel,
} from '../api/client'

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

const FONT = "'Plus Jakarta Sans', Inter, system-ui, sans-serif"

const COLORS = {
  violet: '#6366F1',
  amber: '#F59E0B',
  emerald: '#10B981',
  teal: '#14B8A6',
  track: 'rgba(148, 163, 184, 0.18)',
  muted: 'rgba(148, 163, 184, 0.35)',
}

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

function safePct(part: number, whole: number): number {
  if (!whole || whole <= 0 || !Number.isFinite(part)) return 0
  const pct = (part / whole) * 100
  return Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : 0
}

function useCountUp(target: number, durationMs = 600): number {
  const [value, setValue] = useState(0)
  useEffect(() => {
    const end = Number.isFinite(target) ? Math.max(0, target) : 0
    if (end === 0) {
      setValue(0)
      return undefined
    }
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs)
      const eased = 1 - (1 - t) ** 3
      setValue(Math.round(end * eased))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs])
  return value
}

function RingChart({
  percent,
  color,
  size = 52,
  children,
}: {
  percent: number
  color: string
  size?: number
  children?: ReactNode
}) {
  const pct = Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0
  const data = useMemo(
    () => [
      { name: 'filled', value: emptySafe(pct) },
      { name: 'rest', value: emptySafe(100 - pct) },
    ],
    [pct],
  )
  const empty = pct <= 0
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            cx="50%"
            cy="50%"
            innerRadius="68%"
            outerRadius="92%"
            startAngle={90}
            endAngle={-270}
            stroke="none"
            isAnimationActive
            animationDuration={600}
            animationEasing="ease-out"
          >
            <Cell fill={empty ? COLORS.muted : color} />
            <Cell fill={COLORS.track} />
          </Pie>
        </PieChart>
      </ResponsiveContainer>
      {children && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          {children}
        </div>
      )}
    </div>
  )
}

function emptySafe(n: number): number {
  return Math.max(0.0001, Number.isFinite(n) ? n : 0)
}

function StackedSplitBar({ pending, closed }: { pending: number; closed: number }) {
  const total = pending + closed
  const pendingPct = total > 0 ? (pending / total) * 100 : 0
  const closedPct = total > 0 ? (closed / total) * 100 : 0
  return (
    <div className="mt-3 h-1.5 w-full rounded-full overflow-hidden bg-slate-700/50 flex">
      <div
        className="h-full bg-amber-400 transition-all ease-out"
        style={{ width: `${pendingPct}%`, transitionDuration: '600ms' }}
      />
      <div
        className="h-full bg-emerald-400 transition-all ease-out"
        style={{ width: `${closedPct}%`, transitionDuration: '600ms' }}
      />
      {total === 0 && <div className="h-full w-full bg-slate-600/40" />}
    </div>
  )
}

function AnimatedNumeral({
  value,
  suffix = '',
}: {
  value: number
  suffix?: string
}) {
  const shown = useCountUp(value)
  return (
    <p className="text-2xl sm:text-3xl font-bold text-slate-900 dark:text-slate-100 tabular-nums tracking-tight leading-none">
      {shown}
      {suffix}
    </p>
  )
}

type StatTone = 'violet' | 'amber' | 'emerald' | 'teal'

const STAT_TONES: Record<StatTone, { icon: string; ring: string }> = {
  violet: {
    icon: 'bg-violet-500/15 text-violet-400 border-violet-500/20',
    ring: COLORS.violet,
  },
  amber: {
    icon: 'bg-amber-500/15 text-amber-400 border-amber-500/20',
    ring: COLORS.amber,
  },
  emerald: {
    icon: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20',
    ring: COLORS.emerald,
  },
  teal: {
    icon: 'bg-teal-500/15 text-teal-400 border-teal-500/20',
    ring: COLORS.teal,
  },
}

function PerformanceStatCard({
  label,
  value,
  suffix,
  icon: Icon,
  tone,
  accent,
}: {
  label: string
  value: number
  suffix?: string
  icon: typeof Users
  tone: StatTone
  accent: ReactNode
}) {
  const toneStyle = STAT_TONES[tone]
  return (
    <div
      className={clsx(
        'relative overflow-hidden rounded-xl border border-white/[0.06]',
        'bg-slate-100 dark:bg-navy-900/50 p-4 shadow-sm dark:shadow-[0_8px_24px_rgba(0,0,0,0.25)]',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-2">
            {label}
          </p>
          <AnimatedNumeral value={value} suffix={suffix} />
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className={clsx('p-2 rounded-lg border', toneStyle.icon)}>
            <Icon className="w-4 h-4" />
          </div>
          {accent}
        </div>
      </div>
    </div>
  )
}

function OverallStatGrid({ stats }: { stats: LeadBucket }) {
  const total = Math.max(0, stats.total || 0)
  const pending = Math.max(0, stats.pending || 0)
  const closed = Math.max(0, stats.completed || 0)
  const completion = Number.isFinite(stats.achievement_pct) ? Math.max(0, stats.achievement_pct) : 0
  const pendingShare = safePct(pending, total)
  const closedShare = safePct(closed, total)

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <div
        className={clsx(
          'relative overflow-hidden rounded-xl border border-white/[0.06]',
          'bg-slate-100 dark:bg-navy-900/50 p-4 shadow-sm dark:shadow-[0_8px_24px_rgba(0,0,0,0.25)]',
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-2">
              Total leads
            </p>
            <AnimatedNumeral value={total} />
          </div>
          <div className={clsx('p-2 rounded-lg border', STAT_TONES.violet.icon)}>
            <LayoutDashboard className="w-4 h-4" />
          </div>
        </div>
        <StackedSplitBar pending={pending} closed={closed} />
        <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-500">
          <span className="text-amber-400/80">Pending {pending}</span>
          <span className="text-emerald-400/80">Closed {closed}</span>
        </div>
      </div>

      <PerformanceStatCard
        label="Pending"
        value={pending}
        icon={Clock}
        tone="amber"
        accent={<RingChart percent={pendingShare} color={COLORS.amber} size={44} />}
      />
      <PerformanceStatCard
        label="Closed"
        value={closed}
        icon={CheckCircle2}
        tone="emerald"
        accent={<RingChart percent={closedShare} color={COLORS.emerald} size={44} />}
      />
      <PerformanceStatCard
        label="Completion rate"
        value={completion}
        suffix="%"
        icon={Target}
        tone="teal"
        accent={(
          <RingChart percent={completion} color={COLORS.violet} size={52}>
            <span className="text-[10px] font-bold text-indigo-300 tabular-nums">
              {completion}%
            </span>
          </RingChart>
        )}
      />
    </div>
  )
}

function CompactStatGrid({ stats }: { stats: LeadBucket }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <PerformanceStatCard
        label="Total leads"
        value={stats.total}
        icon={LayoutDashboard}
        tone="violet"
        accent={null}
      />
      <PerformanceStatCard
        label="Pending"
        value={stats.pending}
        icon={Clock}
        tone="amber"
        accent={null}
      />
      <PerformanceStatCard
        label="Closed"
        value={stats.completed}
        icon={CheckCircle2}
        tone="emerald"
        accent={null}
      />
      <PerformanceStatCard
        label="Completion rate"
        value={stats.achievement_pct}
        suffix="%"
        icon={Target}
        tone="teal"
        accent={null}
      />
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
      <div className="flex items-center gap-2.5">
        <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-300">
          <Icon className="w-4 h-4" />
        </div>
        <div>
          <h2 className="section-title">{title}</h2>
          <p className="text-xs text-slate-500">{subtitle}</p>
        </div>
      </div>
      <CompactStatGrid stats={stats} />
    </div>
  )
}

function TargetProgressBar({
  closed,
  target,
  pct,
}: {
  closed: number
  target: number
  pct: number
}) {
  const width = Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : 0
  return (
    <div className="space-y-2 pt-1">
      <div className="h-2.5 rounded-full bg-slate-700/70 overflow-hidden border border-white/[0.04]">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-indigo-400"
          style={{
            width: `${width}%`,
            transition: 'width 600ms ease-out',
          }}
        />
      </div>
      <div className="flex items-center justify-between text-[10px] tabular-nums text-slate-500">
        <span>0</span>
        <span className="text-indigo-300/80">{closed} / {target}</span>
        <span>{target}</span>
      </div>
    </div>
  )
}

type StaffFilterType = '' | 'sales' | 'rm'

type FilterOption = { value: string; label: string }

type FilterSelectProps = {
  label: string
  icon: typeof Users
  value: string
  onChange: (value: string) => void
  options: FilterOption[]
  className?: string
}

function FilterSelect({ label, icon: Icon, value, onChange, options, className }: FilterSelectProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const selected = options.find(o => o.value === value)

  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className={clsx('min-w-0 flex-1', className)} ref={rootRef}>
      <label className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-theme-muted mb-1.5">
        {label}
      </label>
      <div className="relative">
        <Icon className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--accent)] z-10" />
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => setOpen(v => !v)}
          className={clsx(
            'input w-full pl-9 pr-9 text-left flex items-center',
            open && 'border-[var(--accent)] ring-2 ring-[var(--accent)]/20',
          )}
        >
          <span className={clsx('truncate', !selected?.label && 'text-theme-muted')}>
            {selected?.label || 'Select...'}
          </span>
          <ChevronDown
            className={clsx(
              'pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--accent)] transition-transform',
              open && 'rotate-180',
            )}
          />
        </button>
        {open && (
          <ul
            role="listbox"
            className="absolute z-50 mt-1.5 w-full max-h-56 overflow-y-auto rounded-xl border border-[var(--divider)] bg-[var(--surface)] py-1 shadow-[0_8px_24px_rgba(31,33,48,0.12)]"
          >
            {options.map(opt => {
              const isActive = opt.value === value
              return (
                <li key={opt.value || '__empty'}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={isActive}
                    onClick={() => {
                      onChange(opt.value)
                      setOpen(false)
                    }}
                    className={clsx(
                      'w-full text-left px-3 py-2 text-sm transition-colors',
                      isActive
                        ? 'bg-[var(--accent)] text-white font-medium'
                        : 'text-[var(--text-primary)] hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]',
                    )}
                  >
                    {opt.label}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

/** Presentational shape for docs / drop-in demos (derived from TeamPerformanceData). */
export type TeamPerformanceViewModel = {
  totalLeads: number
  pending: number
  closed: number
  completionRate: number
  target: number
  closedForTarget: number
  remainingToTarget: number
  targetProgressPct: number
  targetConfigured: boolean
}

export function toViewModel(data: TeamPerformanceData): TeamPerformanceViewModel {
  const target = data.target
  return {
    totalLeads: data.overall.total,
    pending: data.overall.pending,
    closed: data.overall.completed,
    completionRate: data.overall.achievement_pct,
    target: target?.target_leads ?? 0,
    closedForTarget: target?.completed ?? data.overall.completed,
    remainingToTarget: target?.remaining ?? 0,
    targetProgressPct: target?.achievement_pct ?? 0,
    targetConfigured: Boolean(target?.configured),
  }
}

type TeamPerformancePanelProps = {
  data: TeamPerformanceData
  editableTarget?: boolean
  staffType?: 'sales' | 'rm'
  staffId?: string
  onTargetSaved?: () => void
}

/** Stats + sales target block (used when filters live in the parent shell). */
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

  const hasTarget = Boolean(target && target.target_leads > 0)

  return (
    <div className="space-y-4" style={{ fontFamily: FONT }}>
      <div
        className={clsx(
          'rounded-2xl border border-white/[0.06] p-4 sm:p-5 space-y-4',
          'bg-indigo-500/[0.04] shadow-[0_12px_40px_rgba(0,0,0,0.28)]',
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs uppercase tracking-[0.14em] text-indigo-300 font-semibold">
            {data.staff?.name ? `${data.staff.name} — overall performance` : 'Overall performance'}
          </p>
          {hasTarget && (
            <span className="text-xs text-teal-300 tabular-nums">
              {target!.achievement_pct}% of sales target
            </span>
          )}
        </div>

        <OverallStatGrid stats={data.overall} />

        {target && (
          <div className="rounded-xl border border-slate-200/80 bg-slate-50 dark:border-white/[0.06] dark:bg-navy-900/45 p-4 space-y-4">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-200">
              <TrendingUp className="w-4 h-4 text-indigo-300" />
              Sales target
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-1.5">
                  Target (closed leads)
                </p>
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
                  <p className="text-2xl font-bold text-theme-primary tabular-nums">{target.target_leads}</p>
                )}
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-1.5">
                  Closed
                </p>
                <p className="text-2xl font-bold text-emerald-400 tabular-nums">{target.completed}</p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-1.5">
                  Remaining to target
                </p>
                <p className="text-2xl font-bold text-amber-400 tabular-nums">{target.remaining}</p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 mb-1.5">
                  Target progress
                </p>
                <p className="text-2xl font-bold text-indigo-300 tabular-nums">{target.achievement_pct}%</p>
              </div>
            </div>

            {hasTarget ? (
              <TargetProgressBar
                closed={target.completed}
                target={target.target_leads}
                pct={target.achievement_pct}
              />
            ) : (
              editableTarget && (
                <p className="text-xs text-slate-500">
                  No target set yet for this period. Enter a number and save.
                </p>
              )
            )}
          </div>
        )}
      </div>

      <div
        className={clsx(
          'rounded-2xl border border-white/[0.06] p-4 sm:p-5 space-y-8',
          'bg-white dark:bg-navy-800/70 shadow-sm dark:shadow-[0_12px_40px_rgba(0,0,0,0.28)]',
        )}
      >
        <LeadSection
          title="User leads"
          subtitle="Presales leads assigned"
          icon={Users}
          stats={data.user_leads}
        />
        <div className="border-t border-white/[0.06]" />
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

type TeamPerformanceSectionProps = {
  staffType: StaffFilterType
  staffId: string
  period: PeriodKey
  salesEmployees: TatvaEmployee[]
  rmEmployees: TatvaEmployee[]
  onStaffTypeChange: (next: StaffFilterType) => void
  onStaffIdChange: (id: string) => void
  onPeriodChange: (period: PeriodKey) => void
  data: TeamPerformanceData | null
  loading?: boolean
  error?: string | null
  editableTarget?: boolean
  onTargetSaved?: () => void
}

/** Full Team Performance card: header, control rail, and performance body. */
export function TeamPerformanceSection({
  staffType,
  staffId,
  period,
  salesEmployees,
  rmEmployees,
  onStaffTypeChange,
  onStaffIdChange,
  onPeriodChange,
  data,
  loading = false,
  error = null,
  editableTarget = false,
  onTargetSaved,
}: TeamPerformanceSectionProps) {
  const showPerson = staffType === 'sales' || staffType === 'rm'
  const showPeriod = Boolean(staffType && staffId)
  const rangeLabel = data ? formatPeriodRange(data) : null

  return (
    <section
      className={clsx(
        'rounded-2xl border border-white/[0.06] p-5 sm:p-6 space-y-5',
        'bg-white dark:bg-navy-800/70 backdrop-blur-sm shadow-sm dark:shadow-[0_16px_48px_rgba(0,0,0,0.32)]',
      )}
      style={{ fontFamily: FONT }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-theme-heading flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-indigo-500/15 border border-indigo-500/20">
              <Users className="w-4 h-4 text-indigo-400" />
            </span>
            Team Performance
          </h2>
          <p className="text-xs text-slate-500 mt-1.5 max-w-md">
            Filter by sales person or RM to view closed vs pending leads and sales targets
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200/80 bg-slate-50 dark:border-white/[0.05] dark:bg-navy-900/55 p-3 sm:p-4 space-y-3">
        <div className="flex flex-wrap items-end gap-3">
          <FilterSelect
            label="Role"
            icon={Users}
            value={staffType}
            onChange={v => onStaffTypeChange(v as StaffFilterType)}
            className="w-full sm:w-40 sm:flex-none"
            options={[
              { value: '', label: 'All (overview)' },
              { value: 'sales', label: 'Sales' },
              { value: 'rm', label: 'RM' },
            ]}
          />

          {staffType === 'sales' && (
            <FilterSelect
              label="Sales person"
              icon={User}
              value={staffId}
              onChange={onStaffIdChange}
              className="w-full sm:w-56 sm:flex-none"
              options={[
                { value: '', label: 'Select sales person...' },
                ...salesEmployees
                  .map(emp => {
                    const id = tatvaEmployeeId(emp)
                    if (!id) return null
                    return { value: id, label: tatvaEmployeeLabel(emp) }
                  })
                  .filter((o): o is FilterOption => Boolean(o)),
              ]}
            />
          )}

          {staffType === 'rm' && (
            <FilterSelect
              label="RM"
              icon={User}
              value={staffId}
              onChange={onStaffIdChange}
              className="w-full sm:w-56 sm:flex-none"
              options={[
                { value: '', label: 'Select RM...' },
                ...rmEmployees
                  .map(emp => {
                    const id = tatvaEmployeeId(emp)
                    if (!id) return null
                    return { value: id, label: tatvaEmployeeLabel(emp) }
                  })
                  .filter((o): o is FilterOption => Boolean(o)),
              ]}
            />
          )}

          {showPeriod && (
            <FilterSelect
              label="Period"
              icon={Calendar}
              value={period}
              onChange={v => onPeriodChange(v as PeriodKey)}
              className="w-full sm:w-44 sm:flex-none"
              options={PERIOD_OPTIONS.map(opt => ({ value: opt.key, label: opt.label }))}
            />
          )}
        </div>

        {showPerson && showPeriod && rangeLabel && (
          <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200/80 bg-white dark:border-white/[0.06] dark:bg-navy-800/80 px-2.5 py-1 text-[11px] text-slate-400">
            <Calendar className="w-3 h-3 text-slate-500" />
            <span className="tabular-nums">{rangeLabel}</span>
          </div>
        )}
      </div>

      {!staffType || !staffId ? (
        <div className="flex flex-col items-center justify-center py-10 px-4 rounded-xl border border-dashed border-slate-300/80 bg-slate-50 dark:border-slate-700/50 dark:bg-navy-900/30">
          <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 mb-3">
            <Users className="w-5 h-5 text-indigo-400" />
          </div>
          <p className="text-sm text-slate-400 text-center max-w-sm">
            Choose a sales person or RM to see their closed leads, pending work, and target progress.
          </p>
        </div>
      ) : loading && !data ? (
        <div className="py-10 flex flex-col items-center gap-3">
          <div className="w-6 h-6 border-2 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin" />
          <p className="text-sm text-slate-500">Loading performance...</p>
        </div>
      ) : error ? (
        <div className="py-4 px-4 rounded-xl bg-red-950/20 border border-red-500/20 text-sm text-red-300">
          {error}
        </div>
      ) : data ? (
        <TeamPerformancePanel
          data={data}
          editableTarget={editableTarget}
          staffType={staffType}
          staffId={staffId}
          onTargetSaved={onTargetSaved}
        />
      ) : null}
    </section>
  )
}
