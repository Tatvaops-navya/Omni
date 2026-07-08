export const UTM_SOURCES = [
  { key: 'google', label: 'Google', dot: 'bg-emerald-400' },
  { key: 'facebook', label: 'Facebook', dot: 'bg-blue-400' },
  { key: 'linkedin', label: 'LinkedIn', dot: 'bg-violet-400' },
  { key: 'youtube', label: 'YouTube', dot: 'bg-red-400' },
  { key: 'newsletter', label: 'Newsletter', dot: 'bg-fuchsia-400' },
  { key: 'twitter', label: 'Twitter', dot: 'bg-cyan-400' },
] as const

export const UTM_MEDIUMS = [
  { key: 'cpc', label: 'CPC' },
  { key: 'organic', label: 'Organic' },
  { key: 'email', label: 'Email' },
  { key: 'referral', label: 'Referral' },
  { key: 'social', label: 'Social' },
  { key: 'banner', label: 'Banner' },
  { key: 'sms', label: 'SMS' },
] as const

export type UtmSourceKey = (typeof UTM_SOURCES)[number]['key']
export type UtmMediumKey = (typeof UTM_MEDIUMS)[number]['key']

export type UtmLeadPreview = {
  id: string
  name: string
  phone: string
  email?: string
  source: UtmSourceKey
  medium: UtmMediumKey
  createdAt: string
}

/** Dashboard card counts — replace with source API. */
export const DASHBOARD_SOURCE_COUNTS: Record<UtmSourceKey, number> = {
  google: 0,
  facebook: 0,
  linkedin: 0,
  youtube: 0,
  newsletter: 0,
  twitter: 0,
}

/** Dashboard card counts — replace with medium API. */
export const DASHBOARD_MEDIUM_COUNTS: Record<UtmMediumKey, number> = {
  cpc: 0,
  organic: 0,
  email: 0,
  referral: 0,
  social: 0,
  banner: 0,
  sms: 0,
}

/** Dropdown option counts — replace with APIs when available. */
export const FILTER_SOURCE_COUNTS: Partial<Record<UtmSourceKey, number>> = DASHBOARD_SOURCE_COUNTS
export const FILTER_MEDIUM_COUNTS: Partial<Record<UtmMediumKey, number>> = DASHBOARD_MEDIUM_COUNTS

/** Demo leads for dashboard table — remove when leads API is wired. */
export const PLACEHOLDER_LEADS: UtmLeadPreview[] = []

export const DASHBOARD_SOURCE_KEYS: UtmSourceKey[] = ['google', 'facebook', 'linkedin', 'youtube']
export const DASHBOARD_MEDIUM_KEYS: UtmMediumKey[] = ['cpc', 'organic', 'email', 'referral']
