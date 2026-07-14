import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { Filter, X, ArrowUpRight } from 'lucide-react'
import {
  DASHBOARD_MEDIUM_COUNTS,
  DASHBOARD_MEDIUM_KEYS,
  DASHBOARD_SOURCE_COUNTS,
  DASHBOARD_SOURCE_KEYS,
  PLACEHOLDER_LEADS,
  UTM_MEDIUMS,
  UTM_SOURCES,
  type UtmMediumKey,
  type UtmSourceKey,
} from '../data/leadAcquisition'

type MetricRowProps = {
  label: string
  count: number
  dot?: string
  selected: boolean
  onClick: () => void
}

function MetricRow({ label, count, dot, selected, onClick }: MetricRowProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'w-full flex items-center justify-between gap-3 px-3.5 py-3 rounded-xl text-left transition-all duration-200',
        'hover:bg-navy-700/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/50',
        selected
          ? 'bg-indigo-600/15 ring-1 ring-indigo-500/40 shadow-[inset_0_1px_0_rgba(99,102,241,0.1)]'
          : 'bg-navy-900/30 border border-transparent hover:border-slate-700/40',
      )}
    >
      <span className="flex items-center gap-2.5 min-w-0">
        {dot && <span className={clsx('w-2 h-2 rounded-full shrink-0 ring-2 ring-white/5', dot)} />}
        <span className={clsx('text-sm truncate', selected ? 'text-indigo-200 font-medium' : 'text-slate-300')}>
          {label}
        </span>
      </span>
      <span className={clsx(
        'text-base font-bold tabular-nums shrink-0 min-w-[2rem] text-right',
        selected ? 'text-slate-100' : 'text-slate-300',
      )}>
        {count}
      </span>
    </button>
  )
}

export default function LeadAcquisitionDashboard() {
  const [selectedSource, setSelectedSource] = useState<UtmSourceKey | null>(null)
  const [selectedMedium, setSelectedMedium] = useState<UtmMediumKey | null>(null)

  const filteredCount = useMemo(() => {
    return PLACEHOLDER_LEADS.filter(lead => {
      if (selectedSource && lead.source !== selectedSource) return false
      if (selectedMedium && lead.medium !== selectedMedium) return false
      return true
    }).length
  }, [selectedSource, selectedMedium])

  const presalesQuery = useMemo(() => {
    const params = new URLSearchParams()
    if (selectedSource) params.set('utm_source', selectedSource)
    if (selectedMedium) params.set('utm_medium', selectedMedium)
    const qs = params.toString()
    return qs ? `?${qs}` : ''
  }, [selectedSource, selectedMedium])

  const hasFilters = Boolean(selectedSource || selectedMedium)

  const sourceLabel = UTM_SOURCES.find(s => s.key === selectedSource)?.label
  const mediumLabel = UTM_MEDIUMS.find(m => m.key === selectedMedium)?.label

  const filterSummary = [
    selectedSource ? sourceLabel || selectedSource : null,
    selectedMedium ? mediumLabel || selectedMedium : null,
  ].filter(Boolean).join(' · ')

  const totalSources = DASHBOARD_SOURCE_KEYS.reduce((s, k) => s + DASHBOARD_SOURCE_COUNTS[k], 0)
  const totalMediums = DASHBOARD_MEDIUM_KEYS.reduce((s, k) => s + DASHBOARD_MEDIUM_COUNTS[k], 0)

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="section-label mb-2">Acquisition</p>
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-teal-500/15 border border-teal-500/20">
              <Filter className="w-4 h-4 text-teal-400" />
            </span>
            Lead Acquisition
          </h2>
          <p className="text-xs text-slate-500 mt-1.5">
            Analyze and filter incoming leads by Source and Medium.
          </p>
        </div>
        {hasFilters && (
          <button
            type="button"
            className="btn-ghost text-xs inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-700/40 hover:border-slate-600/60"
            onClick={() => {
              setSelectedSource(null)
              setSelectedMedium(null)
            }}
          >
            <X className="w-3.5 h-3.5" />
            Clear filters
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-card">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-700/40">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">Sources</h3>
            <span className="text-xs text-slate-500 tabular-nums">{totalSources} leads</span>
          </div>
          <div className="space-y-1.5">
            {DASHBOARD_SOURCE_KEYS.map(key => {
              const item = UTM_SOURCES.find(s => s.key === key)!
              return (
                <MetricRow
                  key={key}
                  label={item.label}
                  count={DASHBOARD_SOURCE_COUNTS[key]}
                  dot={item.dot}
                  selected={selectedSource === key}
                  onClick={() => setSelectedSource(prev => (prev === key ? null : key))}
                />
              )
            })}
          </div>
        </div>

        <div className="glass-card">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-700/40">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">Mediums</h3>
            <span className="text-xs text-slate-500 tabular-nums">{totalMediums} leads</span>
          </div>
          <div className="space-y-1.5">
            {DASHBOARD_MEDIUM_KEYS.map(key => {
              const item = UTM_MEDIUMS.find(m => m.key === key)!
              return (
                <MetricRow
                  key={key}
                  label={item.label}
                  count={DASHBOARD_MEDIUM_COUNTS[key]}
                  selected={selectedMedium === key}
                  onClick={() => setSelectedMedium(prev => (prev === key ? null : key))}
                />
              )
            })}
          </div>
        </div>
      </div>

      {hasFilters && (
        <div className="glass-card flex flex-wrap items-center justify-between gap-4 border-indigo-500/20 bg-indigo-950/10">
          <div className="min-w-0">
            <div className="flex flex-wrap gap-2 mb-2">
              {selectedSource && (
                <span className="badge bg-indigo-600/20 text-indigo-300 border border-indigo-500/30">
                  source: {sourceLabel || selectedSource}
                </span>
              )}
              {selectedMedium && (
                <span className="badge bg-teal-600/20 text-teal-300 border border-teal-500/30">
                  medium: {mediumLabel || selectedMedium}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500">{filterSummary}</p>
          </div>
          <div className="text-right shrink-0">
            <p className="text-3xl font-bold text-slate-100 tabular-nums">{filteredCount}</p>
            <p className="text-xs text-slate-500 mt-0.5">
              lead{filteredCount !== 1 ? 's' : ''} match{filteredCount === 1 ? 'es' : ''}
            </p>
          </div>
          <Link
            to={`/krsna/presales${presalesQuery}`}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors w-full sm:w-auto justify-end group"
          >
            Open in Pre-sales
            <ArrowUpRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
          </Link>
        </div>
      )}
    </section>
  )
}
