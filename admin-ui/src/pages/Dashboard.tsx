import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  api,
  TatvaEmployee,
  tatvaEmployeeId,
  tatvaEmployeeName,
} from '../api/client'
import LeadAcquisitionDashboard from '../components/LeadAcquisitionDashboard'
import {
  PeriodKey,
  TeamPerformanceData,
  TeamPerformanceSection,
} from '../components/TeamPerformancePanel'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  MessageSquare, Mic, FileText, CheckCircle, Activity,
  BarChart3, Radio, Sparkles,
} from 'lucide-react'
import clsx from 'clsx'
import { useTheme } from '../theme/ThemeProvider'

const CAT_COLORS_LIGHT = ['#7B6EF6', '#F4B740', '#B4E44F', '#4FC4E8', '#F49097']
const CAT_COLORS_DARK = ['#6366f1', '#14b8a6', '#34d399', '#22d3ee', '#fb7185']

const STAT_PASTELS: Record<string, { pastel: string; iconBg: string }> = {
  'Active Sessions': { pastel: 'pastel-mint', iconBg: 'bg-indigo-500/15 text-indigo-400' },
  'Completed Enquiries': { pastel: 'pastel-lilac', iconBg: 'bg-teal-500/15 text-teal-400' },
  'Summaries Generated': { pastel: 'pastel-peach', iconBg: 'bg-violet-500/15 text-violet-400' },
  'WhatsApp Today': { pastel: 'pastel-sky', iconBg: 'bg-emerald-500/15 text-emerald-400' },
  'Voice Calls Today': { pastel: 'pastel-butter', iconBg: 'bg-sky-500/15 text-sky-400' },
  'Total Sessions': { pastel: 'pastel-violet', iconBg: 'bg-slate-500/15 text-slate-400' },
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
      <div className="p-3 rounded-xl bg-slate-100 dark:bg-navy-700/40 border border-slate-200/80 dark:border-slate-700/30">
        <Icon className="w-5 h-5 text-slate-500" />
      </div>
      <p className="text-sm text-slate-500">{message}</p>
    </div>
  )
}

export default function Dashboard() {
  const { theme } = useTheme()
  const isLight = theme === 'light'
  const catColors = isLight ? CAT_COLORS_LIGHT : CAT_COLORS_DARK
  const chartGrid = isLight ? '#EDEEF3' : '#1e293b'
  const chartTick = isLight ? '#9496A2' : '#64748b'
  const barColor = isLight ? '#F4B740' : '#F59E0B'
  const barHover = isLight ? '#E0A52E' : '#FBBF24'
  const tooltipStyle = isLight
    ? {
        background: '#FFFFFF',
        border: '1px solid #EDEEF3',
        borderRadius: 10,
        boxShadow: '0 8px 20px rgba(31,33,48,0.08)',
        color: '#1F2130',
      }
    : {
        background: 'rgba(17, 29, 53, 0.95)',
        border: '1px solid rgba(99, 102, 241, 0.3)',
        borderRadius: 10,
        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
      }

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
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">Dashboard</h1>
            <div className="flex items-center gap-2.5 mt-2">
              <span className="live-pulse" />
              <p className="text-sm text-slate-400">
                Live · refreshes every 15s · {new Date(data.generated_at).toLocaleTimeString()}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl panel-muted border border-slate-200/80 dark:border-slate-700/40">
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-wider text-slate-500">Active now</p>
              <p className="text-xl font-bold text-indigo-300 tabular-nums">{stats.active_sessions}</p>
            </div>
            <div className="w-px h-8 bg-slate-300 dark:bg-slate-700/60" />
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
            const accent = STAT_PASTELS[label] || STAT_PASTELS['Total Sessions']
            return (
              <div
                key={label}
                className={clsx('stat-card pastel', accent.pastel)}
                style={{ animationDelay: `${i * 60}ms` }}
              >
                <div className="stat-card-accent" />
                <div className={clsx('stat-card-gradient absolute inset-0 bg-gradient-to-br to-transparent opacity-60 pointer-events-none dark:from-indigo-500/10', isLight ? 'hidden' : '')} />
                <div className="relative flex items-start justify-between">
                  <div>
                    <p className="stat-label text-xs font-medium text-slate-400 mb-1.5">{label}</p>
                    <p className="stat-value text-3xl font-bold text-slate-900 dark:text-slate-100 tabular-nums tracking-tight">{value}</p>
                  </div>
                  <div className={clsx('stat-icon-wrap p-2.5 rounded-xl border border-white/5', accent.iconBg)}>
                    <Icon className="w-4 h-4" />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </section>

      {/* Team performance */}
      <TeamPerformanceSection
        staffType={staffType}
        staffId={staffId}
        period={period}
        salesEmployees={salesEmployees}
        rmEmployees={rmEmployees}
        onStaffTypeChange={handleStaffTypeChange}
        onStaffIdChange={setStaffId}
        onPeriodChange={setPeriod}
        data={teamData}
        loading={teamLoading}
        error={teamError || null}
        editableTarget
        onTargetSaved={loadTeamPerformance}
      />

      <LeadAcquisitionDashboard />

      {/* Charts */}
      <section>
        <p className="section-label mb-4">Analytics</p>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="chart-card lg:col-span-2">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="section-title">Messages Per Hour</h3>
                <p className="text-xs text-slate-500 mt-0.5">Conversation volume throughout the day</p>
              </div>
              <BarChart3 className="w-4 h-4 text-indigo-400/60" />
            </div>
            {hourlyData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={hourlyData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="0" stroke={chartGrid} vertical={false} />
                  <XAxis dataKey="hour" tick={{ fill: chartTick, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: chartTick, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={{ color: chartTick, fontSize: 12 }}
                    itemStyle={{ color: isLight ? '#1F2130' : '#c7d2fe' }}
                    cursor={{ fill: isLight ? 'rgba(244, 183, 64, 0.12)' : 'rgba(245, 158, 11, 0.12)' }}
                  />
                  <Bar
                    dataKey="count"
                    fill={barColor}
                    radius={[6, 6, 0, 0]}
                    maxBarSize={40}
                    activeBar={{ fill: barHover }}
                  />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart icon={BarChart3} message="No message data yet" />
            )}
          </div>

          <div className="chart-card">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h3 className="section-title">Channel Split</h3>
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
                    strokeWidth={0}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {channelData.map((_, i) => (
                      <Cell key={i} fill={catColors[i % catColors.length]} stroke="transparent" />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={tooltipStyle} />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart icon={Radio} message="No conversations yet" />
            )}
            {totalChannel > 0 && (
              <div className="flex justify-center gap-5 mt-2">
                {channelData.map((d, i) => (
                  <div key={d.name} className="flex items-center gap-2 text-xs text-slate-400">
                    <span className="w-2.5 h-2.5 rounded-full" style={{ background: catColors[i % catColors.length] }} />
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
