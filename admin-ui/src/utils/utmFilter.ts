import type { UtmMediumKey, UtmSourceKey } from '../data/leadAcquisition'

type UtmRecord = Record<string, unknown>

function nestedUtm(record: UtmRecord): UtmRecord | null {
  const utm = record.utm
  if (utm && typeof utm === 'object' && !Array.isArray(utm)) {
    return utm as UtmRecord
  }
  const marketing = record.marketing
  if (marketing && typeof marketing === 'object' && !Array.isArray(marketing)) {
    return marketing as UtmRecord
  }
  return null
}

export function pickUtmSource(record: UtmRecord): string {
  const nested = nestedUtm(record)
  return String(
    record.utm_source
    || record.utmSource
    || record.source
    || nested?.utm_source
    || nested?.utmSource
    || nested?.source
    || '',
  ).trim().toLowerCase()
}

export function pickUtmMedium(record: UtmRecord): string {
  const nested = nestedUtm(record)
  return String(
    record.utm_medium
    || record.utmMedium
    || record.medium
    || nested?.utm_medium
    || nested?.utmMedium
    || nested?.medium
    || '',
  ).trim().toLowerCase()
}

export function pickUtmCampaign(record: UtmRecord): string {
  const nested = nestedUtm(record)
  return String(
    record.utm_campaign
    || record.utmCampaign
    || record.campaign
    || nested?.utm_campaign
    || nested?.utmCampaign
    || nested?.campaign
    || '',
  ).trim().toLowerCase()
}

export function matchesUtmFilter(
  record: UtmRecord,
  source: UtmSourceKey | '',
  medium: UtmMediumKey | '',
): boolean {
  if (source && pickUtmSource(record) !== source) return false
  if (medium && pickUtmMedium(record) !== medium) return false
  return true
}

export function filterByUtm<T extends UtmRecord>(
  records: T[],
  source: UtmSourceKey | '',
  medium: UtmMediumKey | '',
): T[] {
  if (!source && !medium) return records
  return records.filter(record => matchesUtmFilter(record, source, medium))
}
