import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { Filter, X } from 'lucide-react'
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
        'w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-left transition-colors',
        'hover:bg-navy-700/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500',
        selected ? 'bg-indigo-600/15 ring-1 ring-indigo-500/40' : 'bg-transparent',
      )}
    >
      <span className="flex items-center gap-2.5 min-w-0">
        {dot && <span className={clsx('w-2.5 h-2.5 rounded-full shrink-0', dot)} />}
        <span className={clsx('text-sm truncate', selected ? 'text-indigo-200 font-medium' : 'text-slate-300')}>
          {label}
        </span>
      </span>
      <span className={clsx('text-lg font-bold tabular-nums shrink-0', selected ? 'text-slate-100' : 'text-slate-200')}>
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

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Filter className="w-4 h-4 text-indigo-400" />
            Lead Acquisition
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Analyze and filter incoming leads by Source and Medium.
          </p>
        </div>
        {hasFilters && (
          <button
            type="button"
            className="btn-ghost text-xs inline-flex items-center gap-1"
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
        <div className="card">
          <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-3 pb-2 border-b border-slate-700/50">
            Sources
          </h3>
          <div className="space-y-1">
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

        <div className="card">
          <h3 className="text-xs font-medium uppercase tracking-wide text-slate-500 mb-3 pb-2 border-b border-slate-700/50">
            Mediums
          </h3>
          <div className="space-y-1">
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
        <div className="card flex flex-wrap items-center justify-between gap-4">
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
            className="text-xs font-medium text-indigo-400 hover:text-indigo-300 w-full sm:w-auto text-right"
          >
            Open in Pre-sales →
          </Link>
        </div>
      )}
    </section>
  )
}
