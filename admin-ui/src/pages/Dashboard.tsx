import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  TatvaEmployee,
  tatvaEmployeeId,
  tatvaEmployeeLabel,
  tatvaEmployeeName,
} from '../api/client'
import LeadAcquisitionDashboard from '../components/LeadAcquisitionDashboard'
import {
  PERIOD_OPTIONS,
  PeriodKey,
  TeamPerformanceData,
  TeamPerformancePanel,
} from '../components/TeamPerformancePanel'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  MessageSquare, Mic, FileText, CheckCircle, Activity, Users,
  BarChart3, Radio, Sparkles,
} from 'lucide-react'
import clsx from 'clsx'

const PIE_COLORS = ['#6366f1', '#14b8a6']

const STAT_ACCENTS: Record<string, { gradient: string; glow: string; iconBg: string }> = {
  'Active Sessions': { gradient: 'from-indigo-500/20', glow: 'shadow-indigo-500/10', iconBg: 'bg-indigo-500/15 text-indigo-400' },
  'Completed Enquiries': { gradient: 'from-teal-500/20', glow: 'shadow-teal-500/10', iconBg: 'bg-teal-500/15 text-teal-400' },
  'Summaries Generated': { gradient: 'from-violet-500/20', glow: 'shadow-violet-500/10', iconBg: 'bg-violet-500/15 text-violet-400' },
  'WhatsApp Today': { gradient: 'from-emerald-500/20', glow: 'shadow-emerald-500/10', iconBg: 'bg-emerald-500/15 text-emerald-400' },
  'Voice Calls Today': { gradient: 'from-sky-500/20', glow: 'shadow-sky-500/10', iconBg: 'bg-sky-500/15 text-sky-400' },
  'Total Sessions': { gradient: 'from-slate-500/20', glow: 'shadow-slate-500/10', iconBg: 'bg-slate-500/15 text-slate-400' },
}

type StaffFilterType = '' | 'sales' | 'rm'

function DashboardSkeleton() {
  return (
    <div className="p-6 space-y-6">
      <div className="dashboard-hero">
        <div className="skeleton h-8 w-48 mb-3" />
        <div className="skeleton h-4 w-72" />
      </div>
      <div className="glass-card space-y-4">
        <div className="skeleton h-5 w-40" />
        <div className="filter-bar">
          <div className="skeleton h-9 w-36" />
          <div className="skeleton h-9 w-56" />
        </div>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="stat-card">
            <div className="skeleton h-4 w-24 mb-3" />
            <div className="skeleton h-9 w-16" />
          </div>
        ))}
      </div>
    </div>
  )
}

function EmptyChart({ icon: Icon, message }: { icon: typeof BarChart3; message: string }) {
  return (
    <div className="h-[200px] flex flex-col items-center justify-center gap-3 text-slate-600">
      <div className="p-3 rounded-xl bg-navy-700/40 border border-slate-700/30">
        <Icon className="w-5 h-5 text-slate-500" />
      </div>
      <p className="text-sm text-slate-500">{message}</p>
    </div>
  )
}

export default function Dashboard() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')
  const [salesEmployees, setSalesEmployees] = useState<TatvaEmployee[]>([])
  const [rmEmployees, setRmEmployees] = useState<TatvaEmployee[]>([])
  const [staffType, setStaffType] = useState<StaffFilterType>('')
  const [staffId, setStaffId] = useState('')
  const [period, setPeriod] = useState<PeriodKey>('month')
  const [teamData, setTeamData] = useState<TeamPerformanceData | null>(null)
  const [teamLoading, setTeamLoading] = useState(false)
  const [teamError, setTeamError] = useState('')

  const load = async () => {
    try {
      const d = await api.dashboard()
      setData(d)
      setError('')
    } catch {
      setError('Failed to load dashboard data.')
    }
  }

  const loadTeamOptions = useCallback(async () => {
    try {
      const [employeesRes, rmRes] = await Promise.all([
        api.tatvaEmployees('sales', { page: 1, limit: 100 }),
        api.tatvaEmployees('rm', { page: 1, limit: 100 }),
      ])
      setSalesEmployees(employeesRes.employees || [])
      setRmEmployees(rmRes.employees || [])
    } catch {
      setSalesEmployees([])
      setRmEmployees([])
    }
  }, [])

  const selectedStaffMeta = useMemo(() => {
    if (!staffType || !staffId) return null
    const list = staffType === 'sales' ? salesEmployees : rmEmployees
    const emp = list.find(item => tatvaEmployeeId(item) === staffId)
    if (!emp) return { name: staffType === 'sales' ? 'Sales' : 'RM', email: '' }
    return {
      name: tatvaEmployeeName(emp),
      email: String(emp.email || '').trim(),
    }
  }, [staffType, staffId, salesEmployees, rmEmployees])

  const loadTeamPerformance = useCallback(async () => {
    if (!staffType || !staffId) {
      setTeamData(null)
      setTeamError('')
      return
    }
    setTeamLoading(true)
    setTeamError('')
    try {
      const res = await api.teamPerformance({
        staff_type: staffType,
        staff_id: staffId,
        period,
        staff_email: selectedStaffMeta?.email,
        staff_name: selectedStaffMeta?.name,
      }) as { data?: TeamPerformanceData }
      setTeamData(res.data || null)
    } catch {
      setTeamError('Failed to load team performance.')
      setTeamData(null)
    } finally {
      setTeamLoading(false)
    }
  }, [staffType, staffId, period, selectedStaffMeta])

  useEffect(() => {
    load()
    loadTeamOptions()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [loadTeamOptions])

  useEffect(() => {
    loadTeamPerformance()
    if (!staffType || !staffId) return undefined
    const id = setInterval(loadTeamPerformance, 30000)
    return () => clearInterval(id)
  }, [loadTeamPerformance, staffType, staffId])

  const handleStaffTypeChange = (nextType: StaffFilterType) => {
    setStaffType(nextType)
    setStaffId('')
    setTeamData(null)
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="glass-card border-red-500/20 bg-red-950/20 text-red-300 text-sm">
          {error}
        </div>
      </div>
    )
  }
  if (!data) return <DashboardSkeleton />

  const { stats, charts } = data

  const statCards = [
    { label: 'Active Sessions', value: stats.active_sessions, icon: Activity },
    { label: 'Completed Enquiries', value: stats.completed_enquiries, icon: CheckCircle },
    { label: 'Summaries Generated', value: stats.summaries_generated, icon: FileText },
    { label: 'WhatsApp Today', value: stats.whatsapp_conversations_today, icon: MessageSquare },
    { label: 'Voice Calls Today', value: stats.voice_calls_today, icon: Mic },
    { label: 'Total Sessions', value: stats.total_sessions, icon: Radio },
  ]

  const hourlyData = Object.entries(charts.messages_per_hour || {}).map(([hour, count]) => ({
    hour, count,
  }))

  const channelData = [
    { name: 'WhatsApp', value: charts.channel_distribution?.whatsapp || 0 },
    { name: 'Voice', value: charts.channel_distribution?.voice || 0 },
  ]

  const totalChannel = channelData.reduce((s, d) => s + d.value, 0)

  return (
    <div className="p-6 space-y-8 max-w-[1400px]">
      {/* Hero header */}
      <div className="dashboard-hero">
        <div className="absolute -top-20 -right-20 w-64 h-64 bg-indigo-600/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-16 -left-16 w-48 h-48 bg-teal-500/8 rounded-full blur-3xl pointer-events-none" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-4 h-4 text-indigo-400" />
              <span className="section-label">Operations Overview</span>
            </div>
            <h1 className="text-2xl font-bold text-slate-100 tracking-tight">Dashboard</h1>
            <div className="flex items-center gap-2.5 mt-2">
              <span className="live-pulse" />
              <p className="text-sm text-slate-400">
                Live · refreshes every 15s · {new Date(data.generated_at).toLocaleTimeString()}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl bg-navy-900/60 border border-slate-700/40">
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-wider text-slate-500">Active now</p>
              <p className="text-xl font-bold text-indigo-300 tabular-nums">{stats.active_sessions}</p>
            </div>
            <div className="w-px h-8 bg-slate-700/60" />
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-wider text-slate-500">Today</p>
              <p className="text-xl font-bold text-teal-300 tabular-nums">
                {(stats.whatsapp_conversations_today || 0) + (stats.voice_calls_today || 0)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <section>
        <p className="section-label mb-4">Key Metrics</p>
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
          {statCards.map(({ label, value, icon: Icon }, i) => {
            const accent = STAT_ACCENTS[label] || STAT_ACCENTS['Total Sessions']
            return (
              <div
                key={label}
                className={clsx('stat-card shadow-lg', accent.glow)}
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <div className="stat-card-accent" />
                <div className={clsx('absolute inset-0 bg-gradient-to-br to-transparent opacity-60 pointer-events-none', accent.gradient)} />
                <div className="relative flex items-start justify-between">
                  <div>
                    <p className="text-xs font-medium text-slate-400 mb-1.5">{label}</p>
                    <p className="text-3xl font-bold text-slate-100 tabular-nums tracking-tight">{value}</p>
                  </div>
                  <div className={clsx('p-2.5 rounded-xl border border-white/5', accent.iconBg)}>
                    <Icon className="w-4 h-4" />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Team performance */}
      <section className="glass-card space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2.5">
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

        <div className="filter-bar">
          <div>
            <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Role</label>
            <select
              className="input w-36"
              value={staffType}
              onChange={e => handleStaffTypeChange(e.target.value as StaffFilterType)}
            >
              <option value="">All (overview)</option>
              <option value="sales">Sales</option>
              <option value="rm">RM</option>
            </select>
          </div>
          {staffType === 'sales' && (
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Sales person</label>
              <select
                className="input w-56"
                value={staffId}
                onChange={e => setStaffId(e.target.value)}
              >
                <option value="">Select sales person...</option>
                {salesEmployees.map(emp => {
                  const id = tatvaEmployeeId(emp)
                  if (!id) return null
                  return (
                    <option key={id} value={id}>
                      {tatvaEmployeeLabel(emp)}
                    </option>
                  )
                })}
              </select>
            </div>
          )}
          {staffType === 'rm' && (
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">RM</label>
              <select
                className="input w-56"
                value={staffId}
                onChange={e => setStaffId(e.target.value)}
              >
                <option value="">Select RM...</option>
                {rmEmployees.map(emp => {
                  const id = tatvaEmployeeId(emp)
                  if (!id) return null
                  return (
                    <option key={id} value={id}>
                      {tatvaEmployeeLabel(emp)}
                    </option>
                  )
                })}
              </select>
            </div>
          )}
          {staffType && staffId && (
            <div>
              <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Period</label>
              <select
                className="input w-40"
                value={period}
                onChange={e => setPeriod(e.target.value as PeriodKey)}
              >
                {PERIOD_OPTIONS.map(opt => (
                  <option key={opt.key} value={opt.key}>{opt.label}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {!staffType || !staffId ? (
          <div className="flex flex-col items-center justify-center py-10 px-4 rounded-xl border border-dashed border-slate-700/50 bg-navy-900/30">
            <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 mb-3">
              <Users className="w-5 h-5 text-indigo-400" />
            </div>
            <p className="text-sm text-slate-400 text-center max-w-sm">
              Choose a sales person or RM to see their closed leads, pending work, and target progress.
            </p>
          </div>
        ) : teamLoading && !teamData ? (
          <div className="py-10 flex flex-col items-center gap-3">
            <div className="w-6 h-6 border-2 border-indigo-500/30 border-t-indigo-400 rounded-full animate-spin" />
            <p className="text-sm text-slate-500">Loading performance...</p>
          </div>
        ) : teamError ? (
          <div className="py-4 px-4 rounded-xl bg-red-950/20 border border-red-500/20 text-sm text-red-300">
            {teamError}
          </div>
        ) : teamData ? (
          <TeamPerformancePanel
            data={teamData}
            editableTarget
            staffType={staffType}
            staffId={staffId}
            onTargetSaved={loadTeamPerformance}
          />
        ) : null}
      </section>

      <LeadAcquisitionDashboard />

      {/* Charts */}
      <section>
        <p className="section-label mb-4">Analytics</p>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="chart-card lg:col-span-2">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-sm font-semibold text-slate-200">Messages Per Hour</h3>
                <p className="text-xs text-slate-500 mt-0.5">Conversation volume throughout the day</p>
              </div>
              <BarChart3 className="w-4 h-4 text-indigo-400/60" />
            </div>
            {hourlyData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={hourlyData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="barGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#818cf8" />
                      <stop offset="100%" stopColor="#6366f1" />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="hour" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      background: 'rgba(17, 29, 53, 0.95)',
                      border: '1px solid rgba(99, 102, 241, 0.3)',
                      borderRadius: 10,
                      boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                    }}
                    labelStyle={{ color: '#94a3b8', fontSize: 12 }}
                    itemStyle={{ color: '#c7d2fe' }}
                    cursor={{ fill: 'rgba(99, 102, 241, 0.08)' }}
                  />
                  <Bar dataKey="count" fill="url(#barGradient)" radius={[6, 6, 0, 0]} maxBarSize={40} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart icon={BarChart3} message="No message data yet" />
            )}
          </div>

          <div className="chart-card">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="text-sm font-semibold text-slate-200">Channel Split</h3>
                <p className="text-xs text-slate-500 mt-0.5">WhatsApp vs Voice</p>
              </div>
              {totalChannel > 0 && (
                <span className="text-xs font-medium text-slate-400 tabular-nums">{totalChannel} total</span>
              )}
            </div>
            {channelData.some(d => d.value > 0) ? (
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={channelData}
                    cx="50%"
                    cy="50%"
                    innerRadius={52}
                    outerRadius={78}
                    dataKey="value"
                    paddingAngle={3}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {channelData.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: 'rgba(17, 29, 53, 0.95)',
                      border: '1px solid rgba(99, 102, 241, 0.3)',
                      borderRadius: 10,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart icon={Radio} message="No conversations yet" />
            )}
            {totalChannel > 0 && (
              <div className="flex justify-center gap-5 mt-2">
                {channelData.map((d, i) => (
                  <div key={d.name} className="flex items-center gap-2 text-xs text-slate-400">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: PIE_COLORS[i] }} />
                    {d.name}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
