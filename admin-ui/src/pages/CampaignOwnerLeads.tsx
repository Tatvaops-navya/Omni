import { useMemo, useState } from 'react'
import { BarChart3, Megaphone, Search, Users } from 'lucide-react'
import { getUser } from '../api/client'

export type CampaignOwnerLead = {
  id: string
  campaignId: string
  campaignName: string
  customerName: string
  phone?: string
  source?: string
  status?: string
  createdAt?: string
}

// Replace this adapter with the Tatva campaign-owner leads API when available.
const CAMPAIGN_LEADS: CampaignOwnerLead[] = []

function displayDate(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString()
}

export default function CampaignOwnerLeads() {
  const user = getUser()
  const [campaign, setCampaign] = useState('')
  const [search, setSearch] = useState('')

  const campaigns = useMemo(() => {
    const names = CAMPAIGN_LEADS.map(lead => lead.campaignName).filter(Boolean)
    return [...new Set(names)].sort()
  }, [])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return CAMPAIGN_LEADS.filter(lead => {
      if (campaign && lead.campaignName !== campaign) return false
      if (!query) return true
      return [
        lead.campaignName,
        lead.customerName,
        lead.phone,
        lead.source,
        lead.status,
      ].some(value => String(value || '').toLowerCase().includes(query))
    })
  }, [campaign, search])

  const campaignCounts = useMemo(() => {
    const counts = new Map<string, number>()
    CAMPAIGN_LEADS.forEach(lead => {
      const name = lead.campaignName || 'Unassigned campaign'
      counts.set(name, (counts.get(name) || 0) + 1)
    })
    return [...counts.entries()].sort((a, b) => b[1] - a[1])
  }, [])

  return (
    <div className="p-6 space-y-6 max-w-[1400px]">
      <div>
        <h1 className="page-title flex items-center gap-2.5">
          <span className="p-1.5 rounded-lg bg-[var(--accent-soft)]">
            <Megaphone className="w-4 h-4 text-[var(--accent)]" />
          </span>
          My Leads
        </h1>
        <p className="text-sm text-theme-muted mt-1.5">
          Campaign leads assigned to {user?.name || 'you'}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="stat-card pastel pastel-lilac">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="stat-label text-xs font-semibold uppercase tracking-wider">Total leads</p>
              <p className="stat-value text-3xl font-bold tabular-nums mt-2">{CAMPAIGN_LEADS.length}</p>
            </div>
            <span className="stat-icon-wrap p-2.5 rounded-xl">
              <Users className="w-4 h-4" />
            </span>
          </div>
        </div>
        <div className="stat-card pastel pastel-mint">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="stat-label text-xs font-semibold uppercase tracking-wider">Campaigns</p>
              <p className="stat-value text-3xl font-bold tabular-nums mt-2">{campaignCounts.length}</p>
            </div>
            <span className="stat-icon-wrap p-2.5 rounded-xl">
              <Megaphone className="w-4 h-4" />
            </span>
          </div>
        </div>
        <div className="stat-card pastel pastel-butter">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="stat-label text-xs font-semibold uppercase tracking-wider">Data source</p>
              <p className="stat-value text-lg font-semibold mt-3">Tatva API pending</p>
            </div>
            <span className="stat-icon-wrap p-2.5 rounded-xl">
              <BarChart3 className="w-4 h-4" />
            </span>
          </div>
        </div>
      </div>

      {campaignCounts.length > 0 && (
        <div className="chart-card">
          <h2 className="section-title mb-4">Leads by campaign</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {campaignCounts.map(([name, count], index) => (
              <button
                key={name}
                type="button"
                onClick={() => setCampaign(name)}
                className="text-left rounded-xl p-4 bg-[var(--surface-sunken)] hover:bg-[var(--accent-soft)] transition-colors"
              >
                <p className="text-sm font-medium text-theme-primary truncate">{name}</p>
                <p className="text-2xl font-bold text-[var(--accent)] tabular-nums mt-2">{count}</p>
                <p className="text-xs text-theme-muted mt-1">lead{count === 1 ? '' : 's'}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <div className="flex flex-wrap items-end gap-3 p-4 border-b border-[var(--divider)]">
          <div className="relative min-w-[220px] flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-theme-muted" />
            <input
              className="input pl-9"
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder="Search campaign leads..."
            />
          </div>
          <select
            className="input w-full sm:w-56"
            value={campaign}
            onChange={event => setCampaign(event.target.value)}
          >
            <option value="">All campaigns</option>
            {campaigns.map(name => <option key={name} value={name}>{name}</option>)}
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="data-table w-full text-sm text-left">
            <thead>
              <tr>
                <th className="px-4 py-3 font-medium">Campaign</th>
                <th className="px-4 py-3 font-medium">Customer</th>
                <th className="px-4 py-3 font-medium">Phone</th>
                <th className="px-4 py-3 font-medium">Source</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Received</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-14 text-center">
                    <Megaphone className="w-7 h-7 text-[var(--accent)] mx-auto mb-3 opacity-70" />
                    <p className="text-sm font-medium text-theme-primary">No campaign leads available yet</p>
                    <p className="text-xs text-theme-muted mt-1">
                      Leads will appear here after the campaign-owner API is connected.
                    </p>
                  </td>
                </tr>
              ) : filtered.map(lead => (
                <tr key={lead.id}>
                  <td className="px-4 py-3 font-medium text-theme-primary">{lead.campaignName || '—'}</td>
                  <td className="px-4 py-3 text-theme-secondary">{lead.customerName || '—'}</td>
                  <td className="px-4 py-3 text-theme-secondary whitespace-nowrap">{lead.phone || '—'}</td>
                  <td className="px-4 py-3 text-theme-secondary">{lead.source || '—'}</td>
                  <td className="px-4 py-3">
                    <span className="badge badge-info capitalize">{lead.status || 'New'}</span>
                  </td>
                  <td className="px-4 py-3 text-theme-muted whitespace-nowrap">{displayDate(lead.createdAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
