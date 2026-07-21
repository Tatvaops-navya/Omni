import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import { Filter, X, ArrowUpRight } from 'lucide-react'
import SourceBrandIcon from './SourceBrandIcon'
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
import { useTheme } from '../theme/ThemeProvider'

const CAT_COLORS = ['#7B6EF6', '#F4B740', '#B4E44F', '#4FC4E8', '#F49097']
const CAT_COLORS_DARK = ['#6366f1', '#fbbf24', '#34d399', '#22d3ee', '#fb7185']

type MetricRowProps = {
  label: string
  count: number
  max: number
  color: string
  selected: boolean
  onClick: () => void
  icon?: React.ReactNode
}

function MetricRow({ label, count, max, color, selected, onClick, icon }: MetricRowProps) {
  const pct = max > 0 ? Math.min(100, (count / max) * 100) : 0
  const isZero = count === 0

  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'w-full px-3.5 py-3 rounded-xl text-left transition-all duration-200',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]/40',
        selected
          ? 'bg-[var(--accent-soft)] ring-1 ring-[var(--accent)]/30'
          : 'hover:bg-[var(--surface-raised)]',
      )}
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <span className="flex items-center gap-2.5 min-w-0">
          {icon ?? (
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: color }}
            />
          )}
          <span className={clsx(
            'text-sm truncate',
            selected ? 'text-[var(--text-primary)] font-medium' : 'text-[var(--text-secondary)]',
          )}>
            {label}
          </span>
        </span>
        <span className={clsx(
          'text-sm font-bold tabular-nums shrink-0 min-w-[2rem] text-right',
          isZero ? 'text-[var(--text-muted)]' : 'text-[var(--text-primary)]',
        )}>
          {count}
        </span>
      </div>
      <div className="metric-progress-track">
        <div
          className="metric-progress-fill"
          style={{
            width: `${pct}%`,
            background: isZero ? 'transparent' : color,
          }}
        />
      </div>
    </button>
  )
}

export default function LeadAcquisitionDashboard() {
  const { theme } = useTheme()
  const catColors = theme === 'light' ? CAT_COLORS : CAT_COLORS_DARK
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
  const maxSource = Math.max(1, ...DASHBOARD_SOURCE_KEYS.map(k => DASHBOARD_SOURCE_COUNTS[k]))
  const maxMedium = Math.max(1, ...DASHBOARD_MEDIUM_KEYS.map(k => DASHBOARD_MEDIUM_COUNTS[k]))

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="section-label mb-2">Acquisition</p>
          <h2 className="text-base font-semibold text-theme-heading flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-[var(--accent-soft)] border border-[var(--accent)]/15">
              <Filter className="w-4 h-4 text-[var(--accent)]" />
            </span>
            Lead Acquisition
          </h2>
          <p className="text-xs text-theme-muted mt-1.5">
            Analyze and filter incoming leads by Source and Medium.
          </p>
        </div>
        {hasFilters && (
          <button
            type="button"
            className="btn-ghost text-xs inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-[var(--divider)]"
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
        <div className="chart-card">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-[var(--divider)]">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-theme-muted">Sources</h3>
            <span className="text-xs text-theme-muted tabular-nums">{totalSources} leads</span>
          </div>
          <div className="space-y-1">
            {DASHBOARD_SOURCE_KEYS.map((key, i) => {
              const item = UTM_SOURCES.find(s => s.key === key)!
              return (
                <MetricRow
                  key={key}
                  label={item.label}
                  count={DASHBOARD_SOURCE_COUNTS[key]}
                  max={maxSource}
                  color={catColors[i % catColors.length]}
                  selected={selectedSource === key}
                  onClick={() => setSelectedSource(prev => (prev === key ? null : key))}
                  icon={<SourceBrandIcon source={key} />}
                />
              )
            })}
          </div>
        </div>

        <div className="chart-card">
          <div className="flex items-center justify-between mb-4 pb-3 border-b border-[var(--divider)]">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-theme-muted">Mediums</h3>
            <span className="text-xs text-theme-muted tabular-nums">{totalMediums} leads</span>
          </div>
          <div className="space-y-1">
            {DASHBOARD_MEDIUM_KEYS.map((key, i) => {
              const item = UTM_MEDIUMS.find(m => m.key === key)!
              return (
                <MetricRow
                  key={key}
                  label={item.label}
                  count={DASHBOARD_MEDIUM_COUNTS[key]}
                  max={maxMedium}
                  color={catColors[i % catColors.length]}
                  selected={selectedMedium === key}
                  onClick={() => setSelectedMedium(prev => (prev === key ? null : key))}
                />
              )
            })}
          </div>
        </div>
      </div>

      {hasFilters && (
        <div className="chart-card flex flex-wrap items-center justify-between gap-4 border-[var(--accent)]/20 bg-[var(--accent-soft)]">
          <div className="min-w-0">
            <div className="flex flex-wrap gap-2 mb-2">
              {selectedSource && (
                <span className="badge badge-info">
                  source: {sourceLabel || selectedSource}
                </span>
              )}
              {selectedMedium && (
                <span className="badge badge-success">
                  medium: {mediumLabel || selectedMedium}
                </span>
              )}
            </div>
            <p className="text-xs text-theme-muted">{filterSummary}</p>
          </div>
          <div className="text-right shrink-0">
            <p className="text-3xl font-bold text-theme-primary tabular-nums">{filteredCount}</p>
            <p className="text-xs text-theme-muted mt-0.5">
              lead{filteredCount !== 1 ? 's' : ''} match{filteredCount === 1 ? 'es' : ''}
            </p>
          </div>
          <Link
            to={`/krsna/presales${presalesQuery}`}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors w-full sm:w-auto justify-end group"
          >
            Open in Pre-sales
            <ArrowUpRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
          </Link>
        </div>
      )}
    </section>
  )
}
