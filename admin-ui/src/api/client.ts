// API client for the Aadhya admin panel
// Dev: Vite proxy /admin → localhost:8000
// Production (Vercel): same-origin /admin → Render via vercel.json rewrite (no CORS)
import type { MeetLinksResponse } from '../types/meet'
const BASE_URL = import.meta.env.DEV
  ? (import.meta.env.VITE_API_URL || 'http://localhost:8000')
  : ''

let authToken: string | null = sessionStorage.getItem('aadhya_admin_token')

export type CrmUser = {
  id?: string | null
  name?: string | null
  email?: string | null
  role: 'admin' | 'presales' | 'rm' | string
}

function loadStoredUser(): CrmUser | null {
  try {
    const raw = sessionStorage.getItem('aadhya_crm_user')
    return raw ? JSON.parse(raw) as CrmUser : null
  } catch {
    return null
  }
}

let crmUser: CrmUser | null = loadStoredUser()

export function setToken(token: string, user?: CrmUser | null) {
  authToken = token
  sessionStorage.setItem('aadhya_admin_token', token)
  if (user) {
    crmUser = user
    sessionStorage.setItem('aadhya_crm_user', JSON.stringify(user))
  }
}

export function clearToken() {
  authToken = null
  crmUser = null
  sessionStorage.removeItem('aadhya_admin_token')
  sessionStorage.removeItem('aadhya_crm_user')
}

export function getUser(): CrmUser | null {
  return crmUser || loadStoredUser()
}

export function isAuthenticated(): boolean {
  return !!authToken
}

export function isAdminUser(): boolean {
  return getUser()?.role === 'admin'
}

export function isPresalesUser(): boolean {
  return getUser()?.role === 'presales'
}

export function isRmUser(): boolean {
  return getUser()?.role === 'rm'
}

export function isStaffUser(): boolean {
  const role = getUser()?.role
  return role === 'admin' || role === 'presales' || role === 'rm'
}

export function canViewEnquiryAttachments(): boolean {
  return isStaffUser()
}

async function fetchAdmin(path: string, options: RequestInit = {}) {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`
  }
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  if (res.status === 401) {
    clearToken()
    window.location.href = '/krsna'
    throw new Error('Unauthorized')
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export type LeadAssignmentMeta = {
  status?: string
  presales_user_id?: string | null
  rm_user_id?: string | null
  staff_user_id?: string | null
  assignee_name?: string | null
  assignee_email?: string | null
  assigned_at?: string | null
  notes?: string | null
}

export type PresalesItem = {
  _id: string
  name?: string
  email?: string
  flag?: string
  phoneNumber?: string
  location?: string
  propertyLocation?: string
  createdAt?: string
  updatedAt?: string
  assignment?: LeadAssignmentMeta
}

export type PresalesResponse = {
  success: boolean
  message?: string
  crm_configured?: boolean
  data: {
    items: PresalesItem[]
    total: number
    page: number
    limit: number
    totalPages: number
  }
}

export type TatvaUserItem = {
  _id: string
  phoneNumber?: string
  email?: string
  fullName?: string
  userName?: string
  status?: string
  role?: string
  flag?: string
  isEmailVerified?: boolean
  createdAt?: string
  updatedAt?: string
}

export type TatvaUsersResponse = {
  success: boolean
  message?: string
  data: {
    users: TatvaUserItem[]
    total: number
    page: number
    limit: number
    totalPages: number
  }
}

export type VendorLeadItem = {
  _id?: string
  id?: string
  name?: string
  fullName?: string
  contactName?: string
  vendorName?: string
  companyName?: string
  businessName?: string
  company?: string
  phoneNumber?: string
  phone?: string
  mobile?: string
  email?: string
  location?: string
  city?: string
  address?: string
  service?: string
  serviceCategory?: string
  serviceType?: string
  category?: string
  status?: string
  leadStatus?: string
  createdAt?: string
  created_at?: string
  assignment?: LeadAssignmentMeta
  [key: string]: unknown
}

export type VendorLeadsResponse = {
  success: boolean
  message?: string
  crm_configured?: boolean
  data: {
    items: VendorLeadItem[]
    total: number
    page: number
    limit: number
    totalPages: number
  }
}

export const api = {
  login: async (password: string) => {
    const res = await fetch(`${BASE_URL}/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : 'Invalid password'
      throw new Error(detail)
    }
    return data
  },

  crmLogin: async (email: string, password: string) => {
    const res = await fetch(`${BASE_URL}/admin/crm-login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : 'Invalid credentials'
      throw new Error(detail)
    }
    return data
  },

  me: () => fetchAdmin('/admin/me'),

  crmUsers: (role?: string) => {
    const qs = role ? `?role=${encodeURIComponent(role)}` : ''
    return fetchAdmin(`/admin/crm-users${qs}`) as Promise<{ users: CrmUser[]; configured: boolean }>
  },

  createCrmUser: (body: { name: string; email: string; password: string; role: string }) =>
    fetchAdmin('/admin/crm-users', { method: 'POST', body: JSON.stringify(body) }),

  assignPresalesLead: (externalId: string, body: { presales_user_id: string; snapshot: Record<string, unknown> }) =>
    fetchAdmin(`/admin/lead-assignments/${externalId}/assign-presales`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  assignUserLead: (externalId: string, body: { staff_user_id: string; snapshot: Record<string, unknown> }) =>
    fetchAdmin(`/admin/lead-assignments/${externalId}/assign-user`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  assignVendorLead: (externalId: string, body: { staff_user_id: string; snapshot: Record<string, unknown> }) =>
    fetchAdmin(`/admin/lead-assignments/${externalId}/assign-vendor`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  myLeads: (params?: { page?: number; limit?: number; status?: string; lead_type?: 'user' | 'vendor' }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.status) qs.set('status', params.status)
    if (params?.lead_type) qs.set('lead_type', params.lead_type)
    const query = qs.toString()
    return fetchAdmin(`/admin/my-leads${query ? `?${query}` : ''}`)
  },

  completeMyLead: (externalId: string, notes?: string, leadType: 'user' | 'vendor' = 'user') =>
    fetchAdmin(`/admin/my-leads/${externalId}/complete?lead_type=${leadType}`, {
      method: 'PATCH',
      body: JSON.stringify({ notes: notes || null }),
    }),

  saveMyLeadComment: (externalId: string, notes: string, leadType: 'user' | 'vendor' = 'user') =>
    fetchAdmin(`/admin/my-leads/${externalId}/notes?lead_type=${leadType}`, {
      method: 'PATCH',
      body: JSON.stringify({ notes }),
    }),

  dashboard: () => fetchAdmin('/admin/dashboard'),
  sessions: () => fetchAdmin('/admin/sessions'),
  session: (id: string) => fetchAdmin(`/admin/session/${id}`),
  enquiries: () => fetchAdmin('/admin/enquiries'),
  presales: (params?: { page?: number; limit?: number; flag?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.flag) qs.set('flag', params.flag)
    const query = qs.toString()
    return fetchAdmin(`/admin/presales${query ? `?${query}` : ''}`) as Promise<PresalesResponse>
  },
  deletePresales: (presalesId: string) =>
    fetchAdmin(`/admin/presales/${encodeURIComponent(presalesId)}`, { method: 'DELETE' }),
  users: (params?: { page?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    const query = qs.toString()
    return fetchAdmin(`/admin/users${query ? `?${query}` : ''}`) as Promise<TatvaUsersResponse>
  },
  meetLinks: (params?: { page?: number; limit?: number; user_id?: string; phone?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.user_id) qs.set('user_id', params.user_id)
    if (params?.phone) qs.set('phone', params.phone)
    const query = qs.toString()
    return fetchAdmin(`/admin/meet-links${query ? `?${query}` : ''}`) as Promise<MeetLinksResponse>
  },
  confirmMeetSlot: (slotId: string) =>
    fetchAdmin(`/admin/meet-links/slots/${encodeURIComponent(slotId)}/confirm`, { method: 'PATCH' }),
  rescheduleMeetSlot: (slotId: string) =>
    fetchAdmin(`/admin/meet-links/slots/${encodeURIComponent(slotId)}/reschedule`, { method: 'PATCH' }),
  vendorLeads: (params?: { page?: number; limit?: number; status?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.status) qs.set('status', params.status)
    const query = qs.toString()
    return fetchAdmin(`/admin/vendor-leads${query ? `?${query}` : ''}`) as Promise<VendorLeadsResponse>
  },
  summaries: () => fetchAdmin('/admin/summaries'),
  logs: (params?: { session_id?: string; event?: string; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.session_id) qs.set('session_id', params.session_id)
    if (params?.event) qs.set('event', params.event)
    if (params?.limit) qs.set('limit', String(params.limit))
    return fetchAdmin(`/admin/logs?${qs}`)
  },
  health: () => fetchAdmin('/admin/health'),
  attachments: (sessionId?: string) =>
    fetchAdmin(sessionId ? `/admin/session/${sessionId}/attachments` : '/admin/attachments'),

  resetSession: (id: string) =>
    fetchAdmin(`/admin/session/${id}/reset`, { method: 'POST' }),
  forceSummary: (id: string) =>
    fetchAdmin(`/admin/session/${id}/force-summary`, { method: 'POST' }),
  closeSession: (id: string) =>
    fetchAdmin(`/admin/session/${id}/close`, { method: 'POST' }),
}

export function createSSEStream(onMessage: (data: object) => void) {
  const token = authToken || sessionStorage.getItem('aadhya_admin_token')
  const qs = token ? `?token=${encodeURIComponent(token)}` : ''
  const url = `${BASE_URL}/admin/stream${qs}`
  const es = new EventSource(url)
  es.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch {}
  }
  return es
}
