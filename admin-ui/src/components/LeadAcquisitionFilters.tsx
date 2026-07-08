import clsx from 'clsx'
import { Filter, X } from 'lucide-react'
import {
  FILTER_MEDIUM_COUNTS,
  FILTER_SOURCE_COUNTS,
  UTM_MEDIUMS,
  UTM_SOURCES,
  type UtmMediumKey,
  type UtmSourceKey,
} from '../data/leadAcquisition'

function formatOptionLabel(label: string, count: number | undefined): string {
  if (count == null) return label
  return `${label} (${count})`
}

type LeadAcquisitionFiltersProps = {
  selectedSource: UtmSourceKey | ''
  selectedMedium: UtmMediumKey | ''
  onSourceChange: (value: UtmSourceKey | '') => void
  onMediumChange: (value: UtmMediumKey | '') => void
}

export default function LeadAcquisitionFilters({
  selectedSource,
  selectedMedium,
  onSourceChange,
  onMediumChange,
}: LeadAcquisitionFiltersProps) {
  const hasFilters = Boolean(selectedSource || selectedMedium)
  const sourceLabel = UTM_SOURCES.find(s => s.key === selectedSource)?.label
  const mediumLabel = UTM_MEDIUMS.find(m => m.key === selectedMedium)?.label

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
          <Filter className="w-4 h-4 text-indigo-400" />
          Lead Acquisition
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Analyze and filter incoming leads by Source and Medium.
        </p>
      </div>

      <div className="card">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex-1 min-w-[180px] max-w-xs">
            <label htmlFor="utm-source" className="block text-xs text-slate-500 mb-1.5">
              UTM Source
            </label>
            <select
              id="utm-source"
              className="input"
              value={selectedSource}
              onChange={e => onSourceChange(e.target.value as UtmSourceKey | '')}
            >
              <option value="">All sources</option>
              {UTM_SOURCES.map(item => (
                <option key={item.key} value={item.key}>
                  {formatOptionLabel(item.label, FILTER_SOURCE_COUNTS[item.key])}
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1 min-w-[180px] max-w-xs">
            <label htmlFor="utm-medium" className="block text-xs text-slate-500 mb-1.5">
              UTM Medium
            </label>
            <select
              id="utm-medium"
              className="input"
              value={selectedMedium}
              onChange={e => onMediumChange(e.target.value as UtmMediumKey | '')}
            >
              <option value="">All mediums</option>
              {UTM_MEDIUMS.map(item => (
                <option key={item.key} value={item.key}>
                  {formatOptionLabel(item.label, FILTER_MEDIUM_COUNTS[item.key])}
                </option>
              ))}
            </select>
          </div>

          {hasFilters && (
            <button
              type="button"
              className="btn-ghost text-xs inline-flex items-center gap-1 shrink-0"
              onClick={() => {
                onSourceChange('')
                onMediumChange('')
              }}
            >
              <X className="w-3.5 h-3.5" />
              Clear
            </button>
          )}
        </div>

        {hasFilters && (
          <div className="flex flex-wrap items-center gap-2 mt-4 pt-4 border-t border-slate-700/50">
            <span className="text-xs text-slate-500">Active filters:</span>
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
        )}
      </div>
    </section>
  )
}
