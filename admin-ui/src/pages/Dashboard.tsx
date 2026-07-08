import { useEffect, useState } from 'react'
import { api } from '../api/client'
import LeadAcquisitionDashboard from '../components/LeadAcquisitionDashboard'
import { BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import { MessageSquare, Mic, FileText, CheckCircle, Activity } from 'lucide-react'

const PIE_COLORS = ['#6366f1', '#14b8a6']

export default function Dashboard() {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const d = await api.dashboard()
      setData(d)
    } catch {
      setError('Failed to load dashboard data.')
    }
  }

  useEffect(() => {
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [])

  if (error) return <div className="p-6 text-red-400">{error}</div>
  if (!data) return <div className="p-6 text-slate-500">Loading...</div>

  const { stats, charts } = data

  const statCards = [
    { label: 'Active Sessions', value: stats.active_sessions, icon: Activity, color: 'text-indigo-400' },
    { label: 'Completed Enquiries', value: stats.completed_enquiries, icon: CheckCircle, color: 'text-teal-400' },
    { label: 'Summaries Generated', value: stats.summaries_generated, icon: FileText, color: 'text-indigo-400' },
    { label: 'WhatsApp Today', value: stats.whatsapp_conversations_today, icon: MessageSquare, color: 'text-teal-400' },
    { label: 'Voice Calls Today', value: stats.voice_calls_today, icon: Mic, color: 'text-indigo-400' },
    { label: 'Total Sessions', value: stats.total_sessions, icon: Activity, color: 'text-slate-400' },
  ]

  const hourlyData = Object.entries(charts.messages_per_hour || {}).map(([hour, count]) => ({
    hour, count
  }))

  const channelData = [
    { name: 'WhatsApp', value: charts.channel_distribution?.whatsapp || 0 },
    { name: 'Voice', value: charts.channel_distribution?.voice || 0 },
  ]

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-200">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">
          Live overview · refreshes every 15s · {new Date(data.generated_at).toLocaleTimeString()}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {statCards.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="card">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs text-slate-500 mb-1">{label}</p>
                <p className="text-3xl font-bold text-slate-200">{value}</p>
              </div>
              <div className={`p-2 bg-navy-700 rounded-lg ${color}`}>
                <Icon className="w-4 h-4" />
              </div>
            </div>
          </div>
        ))}
      </div>

      <LeadAcquisitionDashboard />

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Hourly messages */}
        <div className="card lg:col-span-2">
          <h3 className="text-sm font-medium text-slate-400 mb-4">Messages Per Hour</h3>
          {hourlyData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={hourlyData}>
                <XAxis dataKey="hour" tick={{ fill: '#64748b', fontSize: 11 }} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#111d35', border: '1px solid #334155', borderRadius: 8 }}
                  labelStyle={{ color: '#94a3b8' }}
                />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[180px] flex items-center justify-center text-slate-600 text-sm">
              No message data yet
            </div>
          )}
        </div>

        {/* Channel split */}
        <div className="card">
          <h3 className="text-sm font-medium text-slate-400 mb-4">Channel Split</h3>
          {channelData.some(d => d.value > 0) ? (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={channelData} cx="50%" cy="50%" innerRadius={50} outerRadius={75}
                  dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {channelData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: '#111d35', border: '1px solid #334155', borderRadius: 8 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-[180px] flex items-center justify-center text-slate-600 text-sm">
              No conversations yet
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
