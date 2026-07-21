export type IncentiveRow = {
  id: string
  role: string
  percentage: number
  description: string
  active: boolean
}

export const INCENTIVE_STORAGE_KEY = 'aadhya_incentive_config'

export const DEFAULT_INCENTIVES: IncentiveRow[] = [
  {
    id: 'campaign-owner',
    role: 'Campaign Owner',
    percentage: 3,
    description: 'Standard share for campaign ownership',
    active: true,
  },
  {
    id: 'creative-owner',
    role: 'Creative Owner',
    percentage: 2,
    description: 'Standard share for creative ownership',
    active: true,
  },
  {
    id: 'presales-owner',
    role: 'Presales Owner',
    percentage: 6,
    description: 'Standard share for presales ownership',
    active: true,
  },
  {
    id: 'project-coordinator',
    role: 'Project Coordinator',
    percentage: 8,
    description: 'Standard share for project coordination',
    active: true,
  },
  {
    id: 'vendor-onboarding-owner',
    role: 'Vendor-Onboarding Owner recurring assignment share',
    percentage: 1,
    description: 'Recurring assignment share for vendor onboarding',
    active: true,
  },
  {
    id: 'max-standard-payout',
    role: 'Maximum standard project payout',
    percentage: 20,
    description: 'Cap for total standard project incentive payout',
    active: true,
  },
]

export function loadIncentives(): IncentiveRow[] {
  try {
    const raw = localStorage.getItem(INCENTIVE_STORAGE_KEY)
      || sessionStorage.getItem(INCENTIVE_STORAGE_KEY)
    if (!raw) return DEFAULT_INCENTIVES.map(row => ({ ...row }))
    const parsed = JSON.parse(raw) as IncentiveRow[]
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return DEFAULT_INCENTIVES.map(row => ({ ...row }))
    }
    return parsed.map(row => ({
      id: String(row.id || crypto.randomUUID()),
      role: String(row.role || '').trim() || 'Untitled role',
      percentage: Number.isFinite(Number(row.percentage)) ? Number(row.percentage) : 0,
      description: String(row.description || ''),
      active: row.active !== false,
    }))
  } catch {
    return DEFAULT_INCENTIVES.map(row => ({ ...row }))
  }
}

export function persistIncentives(rows: IncentiveRow[]) {
  localStorage.setItem(INCENTIVE_STORAGE_KEY, JSON.stringify(rows))
}

type IncentiveUserHints = {
  role?: string | null
  tatvaRole?: string | null
  department?: string | null
  name?: string | null
}

function userBlob(user: IncentiveUserHints): string {
  return [
    user.role,
    user.tatvaRole,
    user.department,
    user.name,
  ]
    .map(v => String(v || '').toLowerCase())
    .join(' ')
}

/** Map panel / Tatva roles onto Core Incentive Configuration rows. */
export function matchIncentivesForUser(
  user: IncentiveUserHints | null | undefined,
  rows: IncentiveRow[] = loadIncentives(),
): IncentiveRow[] {
  if (!user) return []
  const blob = userBlob(user)
  const active = rows.filter(row => row.active)

  const matched = active.filter(row => {
    if (row.id === 'max-standard-payout') return false

    switch (row.id) {
      case 'campaign-owner':
        return /campaign/.test(blob)
      case 'creative-owner':
        return /creative|design/.test(blob)
      case 'presales-owner':
        return /presales|pre[\s_-]?sales|sales_manager|sales manager|\bsales\b/.test(blob)
          && !/campaign|creative|coordinator|vendor/.test(blob)
      case 'project-coordinator':
        return /project.?coord|coordinator|project manager|\bpm\b/.test(blob)
      case 'vendor-onboarding-owner':
        return /vendor.?onboard|onboarding|vendor/.test(blob)
      default: {
        const roleWords = row.role.toLowerCase().split(/[^a-z0-9]+/).filter(w => w.length > 3)
        return roleWords.some(word => blob.includes(word))
      }
    }
  })

  // Fallback: CRM role "presales" → Presales Owner when nothing else matched
  if (matched.length === 0 && /presales|sales/.test(blob)) {
    const presales = active.find(row => row.id === 'presales-owner')
    if (presales) matched.push(presales)
  }

  const maxPayout = active.find(row => row.id === 'max-standard-payout')
  if (maxPayout && matched.length > 0) {
    return [...matched, maxPayout]
  }
  return matched
}
