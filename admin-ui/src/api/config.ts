/** Canonical Tatva API base — https://api.withtatva.ai */
export const TATVA_API_ORIGIN = (
  import.meta.env.VITE_TATVA_API_ORIGIN || 'https://api.withtatva.ai'
).replace(/\/$/, '')

/**
 * Browser path for Tatva calls. Dev/prod proxy `/tatva-api` → TATVA_API_ORIGIN.
 * Network tab shows localhost/tatva-api; upstream is always api.withtatva.ai.
 */
export const TATVA_API_BASE = (
  import.meta.env.VITE_TATVA_API_BASE_URL || '/tatva-api'
).replace(/\/$/, '')

/** Omnichannel backend — login, enquiries, CRM (not on api.withtatva.ai) */
export const OMNICHANNEL_API_BASE = ''
