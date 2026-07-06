// Omnichannel backend: login, enquiries, CRM. Tatva platform: api.withtatva.ai via /tatva-api proxy.
import type { MeetLinkRecord, MeetLinksResponse, MeetSlot } from '../types/meet'
import type { EnquiryAttachment } from '../types/enquiry'
import { normalizePhone } from '../utils/phone'
import { OMNICHANNEL_API_BASE, TATVA_API_BASE } from './config'

const BASE_URL = OMNICHANNEL_API_BASE

export { OMNICHANNEL_API_BASE, TATVA_API_BASE, TATVA_API_ORIGIN } from './config'

/** Tatva approved vendors — https://api.withtatva.ai/vendor/api/vendors */
export const TATVA_VENDORS_PATH = '/vendor/api/vendors'
/** Tatva employee projects — https://api.withtatva.ai/admin/api/admin/employees/{id}/projects */
export const TATVA_MY_PROJECTS_EMPLOYEE_ID = '69ef0a0a11db8baeba77b711'
export const TATVA_EMPLOYEE_PROJECTS_PATH =
  `/admin/api/admin/employees/${TATVA_MY_PROJECTS_EMPLOYEE_ID}/projects`

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

async function fetchTatva(path: string, options: RequestInit = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`
  }
  if (method !== 'GET' && method !== 'HEAD') {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json'
  }
  const res = await fetch(`${TATVA_API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({} as Record<string, unknown>))
    const msg = typeof body.message === 'string'
      ? body.message
      : typeof body.detail === 'string'
        ? body.detail
        : `Tatva API HTTP ${res.status}`
    throw new Error(msg)
  }
  return res.json()
}

export function resolveMeetSlotId(slot: MeetSlot | Record<string, unknown>): string {
  const s = slot as Record<string, unknown>
  return String(s.slotId || s._id || s.id || '').trim()
}

function normalizeMeetLinkRecord(record: MeetLinkRecord): MeetLinkRecord {
  return {
    ...record,
    slots: (record.slots || []).map(slot => ({
      ...slot,
      slotId: resolveMeetSlotId(slot),
    })),
  }
}

function extractMeetLinkFromPayload(payload: unknown): MeetLinkRecord | null {
  if (!payload || typeof payload !== 'object') return null
  const root = payload as Record<string, unknown>
  const data = root.data
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    return data as MeetLinkRecord
  }
  return root as MeetLinkRecord
}

function filterMeetLinksForUser(
  payload: MeetLinksResponse,
  userId?: string,
  phone?: string,
): MeetLinksResponse {
  const needle = normalizePhone(phone)
  const items = (payload.data || []).filter(item => {
    const uid = item.userId?._id || ''
    if (userId && uid === userId) return true
    if (needle) {
      const itemPhone = normalizePhone(item.userId?.phoneNumber)
      if (itemPhone && itemPhone === needle) return true
    }
    return !userId && !needle
  })
  return { ...payload, data: items }
}

function normalizeTatvaPagedItems(
  payload: Record<string, unknown>,
  listKeys: string[] = ['items', 'leads', 'users', 'vendorLeads', 'vendor_leads'],
) {
  const raw = (
    payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)
  ) ? payload.data as Record<string, unknown> : {}

  let items: unknown[] = []
  for (const key of listKeys) {
    const value = raw[key]
    if (Array.isArray(value)) {
      items = value
      break
    }
  }

  const pagination = (
    raw.pagination && typeof raw.pagination === 'object'
  ) ? raw.pagination as Record<string, unknown> : {}

  return {
    items,
    total: Number(pagination.total ?? raw.total ?? items.length),
    page: Number(pagination.page ?? raw.page ?? 1),
    limit: Number(pagination.limit ?? raw.limit ?? 20),
    totalPages: Number(pagination.pages ?? pagination.totalPages ?? raw.totalPages ?? 1),
  }
}

export type LeadAssignmentMeta = {
  status?: string
  presales_user_id?: string | null
  rm_user_id?: string | null
  staff_user_id?: string | null
  assignee_name?: string | null
  assignee_email?: string | null
  assigned_at?: string | null
  presales_completed_at?: string | null
  notes?: string | null
}

export type VendorAssignmentMeta = {
  status?: string
  vendor_id?: string | null
  vendor_name?: string | null
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
  projectId?: string
  project_id?: string
  assignee?: string
  assigneeName?: string
  assignedTo?: string | { fullName?: string; name?: string; email?: string }
  createdAt?: string
  updatedAt?: string
  assignment?: LeadAssignmentMeta
  vendor_assignment?: VendorAssignmentMeta
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

export type TatvaEmployee = {
  _id?: string
  id?: string
  employeeId?: string
  name?: string
  fullName?: string
  employeeName?: string
  firstName?: string
  lastName?: string
  email?: string
  phoneNumber?: string
  phone?: string
  department?: string
  role?: string
  designation?: string
  [key: string]: unknown
}

export function tatvaEmployeeId(emp: TatvaEmployee): string {
  return String(emp._id || emp.id || emp.employeeId || '').trim()
}

export function tatvaEmployeeName(emp: TatvaEmployee): string {
  const direct = emp.fullName || emp.name || emp.employeeName
  if (direct && String(direct).trim()) return String(direct).trim()
  const first = String(emp.firstName || '').trim()
  const last = String(emp.lastName || '').trim()
  return [first, last].filter(Boolean).join(' ') || 'Employee'
}

export function tatvaEmployeeRoleName(emp: TatvaEmployee): string {
  const role = emp.role
  if (role && typeof role === 'object' && !Array.isArray(role)) {
    const name = (role as { name?: string }).name
    if (name && String(name).trim()) return String(name).trim()
  }
  return String(emp.designation || (typeof role === 'string' ? role : '') || '').trim()
}

export function tatvaEmployeeDepartmentName(emp: TatvaEmployee): string {
  const dept = emp.department
  if (Array.isArray(dept) && dept.length > 0) {
    const first = dept[0]
    if (first && typeof first === 'object' && 'name' in first) {
      return String((first as { name?: string }).name || '').trim()
    }
  }
  return typeof dept === 'string' ? dept.trim() : ''
}

export function tatvaEmployeeLabel(emp: TatvaEmployee): string {
  const name = tatvaEmployeeName(emp)
  const role = tatvaEmployeeRoleName(emp) || tatvaEmployeeDepartmentName(emp)
  return role ? `${name} (${role})` : name
}

function normalizeTatvaEmployees(payload: Record<string, unknown>): TatvaEmployee[] {
  const raw = payload.data
  let list: unknown[] = []
  if (Array.isArray(raw)) {
    list = raw
  } else if (raw && typeof raw === 'object') {
    const data = raw as Record<string, unknown>
    for (const key of ['employees', 'items', 'users', 'staff']) {
      const value = data[key]
      if (Array.isArray(value)) {
        list = value
        break
      }
    }
  }
  if (!list.length) {
    for (const key of ['employees', 'items']) {
      const value = payload[key]
      if (Array.isArray(value)) {
        list = value
        break
      }
    }
  }
  return list.filter((item): item is TatvaEmployee => !!item && typeof item === 'object')
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

function flattenVendorRecord(entry: Record<string, unknown>): VendorLeadItem {
  const vendor = entry.vendor
  if (!vendor || typeof vendor !== 'object' || Array.isArray(vendor)) {
    return entry as VendorLeadItem
  }

  const v = vendor as Record<string, unknown>
  const addresses = Array.isArray(v.addresses) ? v.addresses : []
  const primaryAddress = addresses.find(
    (addr): addr is Record<string, unknown> =>
      !!addr && typeof addr === 'object' && Boolean((addr as { isDefault?: boolean }).isDefault),
  ) || (addresses[0] && typeof addresses[0] === 'object' ? addresses[0] as Record<string, unknown> : null)

  const formattedAddress = primaryAddress
    ? String(primaryAddress.formattedAddress || '').trim()
    : ''
  const mapLocation = v.googleMapLocation
  const mapAddress = mapLocation && typeof mapLocation === 'object' && !Array.isArray(mapLocation)
    ? String((mapLocation as { address?: string }).address || '').trim()
    : ''

  const fullName = String(v.fullName || '').trim()
  const contactName = String(v.primaryContactPerson || '').trim()
  const displayName = fullName && fullName.toLowerCase() !== 'unknown'
    ? fullName
    : contactName || fullName || String(v.designation || '').trim()

  return {
    ...v,
    ...entry,
    _id: String(v._id || v.id || ''),
    id: String(v._id || v.id || ''),
    name: displayName,
    fullName: displayName,
    services: entry.services ?? v.services,
    addresses,
    location: formattedAddress || String(v.businessAddress || '').trim() || mapAddress,
    businessAddress: formattedAddress || String(v.businessAddress || '').trim() || mapAddress,
    assignment: entry.assignment as VendorLeadItem['assignment'],
  } as VendorLeadItem
}

function normalizeVendorsList(payload: Record<string, unknown>): VendorLeadItem[] {
  let raw: unknown[] = []
  const data = payload.data
  if (Array.isArray(data)) {
    raw = data
  } else if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>
    for (const key of ['vendors', 'items', 'leads']) {
      const value = obj[key]
      if (Array.isArray(value)) {
        raw = value
        break
      }
    }
  } else if (Array.isArray(payload.vendors)) {
    raw = payload.vendors
  } else {
    const paged = normalizeTatvaPagedItems(payload, ['vendors', 'items', 'leads'])
    raw = paged.items
  }

  return raw
    .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
    .map(flattenVendorRecord)
}

export type EmployeeProjectItem = {
  _id?: string
  id?: string
  projectId?: string
  project_id?: string
  name?: string
  projectName?: string
  title?: string
  customerName?: string
  clientName?: string
  userName?: string
  location?: string
  propertyLocation?: string
  city?: string
  status?: string
  stage?: string
  role?: string
  assignedAt?: string
  assigned_at?: string
  createdAt?: string
  updatedAt?: string
  user?: { fullName?: string; name?: string; phoneNumber?: string; email?: string }
  customer?: { fullName?: string; name?: string; phoneNumber?: string; email?: string }
  userId?: { fullName?: string; name?: string; phoneNumber?: string; email?: string }
  employeeId?: { _id?: string; fullName?: string; name?: string; email?: string }
  [key: string]: unknown
}

export type EmployeeProjectsResponse = {
  success: boolean
  message?: string
  data: {
    items: EmployeeProjectItem[]
    employee_id?: string | null
    employee_name?: string
    total?: number
  }
}

function normalizeEmployeeProjects(payload: Record<string, unknown>): EmployeeProjectItem[] {
  const data = payload.data
  if (Array.isArray(data)) {
    return data.filter((item): item is EmployeeProjectItem => !!item && typeof item === 'object')
  }
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>
    for (const key of ['projects', 'items', 'assignments']) {
      const value = obj[key]
      if (Array.isArray(value)) {
        return value.filter((item): item is EmployeeProjectItem => !!item && typeof item === 'object')
      }
    }
  }
  const paged = normalizeTatvaPagedItems(payload, ['projects', 'items', 'assignments'])
  return paged.items as EmployeeProjectItem[]
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

  tatvaEmployees: async (
    department = 'sales',
    params?: { page?: number; limit?: number },
  ) => {
    const page = params?.page ?? 1
    const limit = params?.limit ?? 50
    const payload = await fetchTatva(
      `/admin/api/admin/employees/by-department/${encodeURIComponent(department)}?page=${page}&limit=${limit}`,
    ) as Record<string, unknown>
    return { employees: normalizeTatvaEmployees(payload) }
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

  assignEmployeeLead: (
    externalId: string,
    body: {
      employee_id: string
      employee_name?: string
      employee_email?: string
      employee_department?: string
      employee_role?: string
      snapshot: Record<string, unknown>
    },
  ) =>
    fetchAdmin(`/admin/lead-assignments/${externalId}/assign-employee`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  assignPresalesVendor: (
    externalId: string,
    body: {
      vendor_id: string
      vendor_name?: string
      vendor_company?: string
      vendor_phone?: string
      snapshot: Record<string, unknown>
    },
  ) =>
    fetchAdmin(`/admin/lead-assignments/${externalId}/assign-presales-vendor`, {
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

  myDashboard: (period: string = 'month') =>
    fetchAdmin(`/admin/my-dashboard?period=${encodeURIComponent(period)}`),

  myProjects: async () => {
    const payload = await fetchTatva(TATVA_EMPLOYEE_PROJECTS_PATH) as Record<string, unknown>
    const items = normalizeEmployeeProjects(payload)
    const dataObj = (
      payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)
    ) ? payload.data as Record<string, unknown> : {}
    const employee = dataObj.employee
    const employeeName = employee && typeof employee === 'object'
      ? String(
        (employee as { fullName?: string; name?: string }).fullName
        || (employee as { name?: string }).name
        || '',
      ).trim()
      : ''
    return {
      success: Boolean(payload.success ?? true),
      message: typeof payload.message === 'string' ? payload.message : undefined,
      data: {
        items,
        employee_id: TATVA_MY_PROJECTS_EMPLOYEE_ID,
        employee_name: employeeName || undefined,
        total: items.length,
      },
    } satisfies EmployeeProjectsResponse
  },

  employeeProjects: async (employeeId: string) => {
    const payload = await fetchTatva(
      `/admin/api/admin/employees/${encodeURIComponent(employeeId)}/projects`,
    ) as Record<string, unknown>
    const items = normalizeEmployeeProjects(payload)
    return {
      success: Boolean(payload.success ?? true),
      message: typeof payload.message === 'string' ? payload.message : undefined,
      data: {
        items,
        employee_id: employeeId,
        total: items.length,
      },
    } satisfies EmployeeProjectsResponse
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

  refreshEnquiryAttachments: (sessionId: string) =>
    fetchAdmin(`/admin/enquiries/${encodeURIComponent(sessionId)}/attachments/refresh`, {
      method: 'POST',
    }) as Promise<{ attachments?: EnquiryAttachment[]; count?: number }>,

  enquiryAttachments: (sessionId: string) =>
    fetchAdmin(`/admin/enquiries/${encodeURIComponent(sessionId)}/attachments`) as Promise<{
      attachments?: EnquiryAttachment[]
      count?: number
    }>,
  presales: async (params?: { page?: number; limit?: number; flag?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.flag) qs.set('flag', params.flag)
    const query = qs.toString()
    return fetchAdmin(`/admin/presales${query ? `?${query}` : ''}`) as Promise<PresalesResponse>
  },
  deletePresales: async (presalesId: string) => {
    const result = await fetchTatva(`/admin/api/admin/presales/${encodeURIComponent(presalesId)}`, {
      method: 'DELETE',
    })
    try {
      await fetchAdmin(`/admin/presales/${encodeURIComponent(presalesId)}/assignment`, { method: 'DELETE' })
    } catch {
      // CRM assignment cleanup is best-effort
    }
    return result
  },
  users: async (params?: { page?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    const query = qs.toString()
    const tatva = await fetchTatva(`/users/api/users${query ? `?${query}` : ''}`) as TatvaUsersResponse
    const paged = normalizeTatvaPagedItems(tatva as unknown as Record<string, unknown>, ['users', 'items'])
    return {
      success: tatva.success,
      message: tatva.message,
      data: {
        users: paged.items as TatvaUserItem[],
        total: paged.total,
        page: paged.page,
        limit: paged.limit,
        totalPages: paged.totalPages,
      },
    }
  },
  meetLinks: async (params?: { page?: number; limit?: number; user_id?: string; phone?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params?.limit ?? 20))
    const query = qs.toString()
    const payload = await fetchTatva(`/users/api/meet-links/all${query ? `?${query}` : ''}`) as MeetLinksResponse
    const normalized: MeetLinksResponse = {
      ...payload,
      data: (payload.data || []).map(normalizeMeetLinkRecord),
    }
    if (params?.user_id || params?.phone) {
      return filterMeetLinksForUser(normalized, params.user_id, params.phone)
    }
    return normalized
  },
  getMeetLink: (meetLinkId: string) =>
    fetchTatva(`/users/api/meet-links/${encodeURIComponent(meetLinkId)}`).then(payload => {
      const record = extractMeetLinkFromPayload(payload)
      return record ? normalizeMeetLinkRecord(record) : null
    }),
  confirmMeetSlot: async (meetLinkId: string, slotId?: string) => {
    let resolvedSlotId = (slotId || '').trim()
    if (!resolvedSlotId) {
      const payload = await fetchTatva(`/users/api/meet-links/${encodeURIComponent(meetLinkId)}`)
      const record = extractMeetLinkFromPayload(payload)
      const slots = record ? normalizeMeetLinkRecord(record).slots || [] : []
      resolvedSlotId = resolveMeetSlotId(slots[0] || {})
    }
    if (!resolvedSlotId) {
      throw new Error('No slot id found for this meet link')
    }
    return fetchTatva(`/users/api/meet-links/${encodeURIComponent(meetLinkId)}`, {
      method: 'PUT',
      body: JSON.stringify({
        slots: [{ slotId: resolvedSlotId, status: 'scheduled' }],
      }),
    })
  },
  rescheduleMeetSlot: (slotId: string) =>
    fetchAdmin(`/admin/meet-links/slots/${encodeURIComponent(slotId)}/reschedule`, { method: 'PATCH' }),
  vendorLeads: async (params?: { page?: number; limit?: number; status?: string }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.status) qs.set('status', params.status)
    const query = qs.toString()
    const tatva = await fetchTatva(`/admin/api/admin/vendor-leads${query ? `?${query}` : ''}`) as VendorLeadsResponse
    const paged = normalizeTatvaPagedItems(tatva as unknown as Record<string, unknown>, ['leads', 'items', 'vendorLeads', 'vendor_leads'])
    const items = paged.items as VendorLeadItem[]
    try {
      const enrich = await fetchAdmin('/admin/vendor-leads/enrich', {
        method: 'POST',
        body: JSON.stringify({ items }),
      }) as { items?: VendorLeadItem[]; crm_configured?: boolean }
      return {
        success: tatva.success,
        message: tatva.message,
        crm_configured: !!enrich.crm_configured,
        data: {
          items: enrich.items || items,
          total: paged.total,
          page: paged.page,
          limit: paged.limit,
          totalPages: paged.totalPages,
        },
      }
    } catch {
      return {
        success: tatva.success,
        message: tatva.message,
        crm_configured: false,
        data: {
          items,
          total: paged.total,
          page: paged.page,
          limit: paged.limit,
          totalPages: paged.totalPages,
        },
      }
    }
  },

  vendors: async (params?: { page?: number; limit?: number }) => {
    const page = params?.page ?? 1
    const limit = params?.limit ?? 100
    const tatva = await fetchTatva(
      `${TATVA_VENDORS_PATH}?page=${page}&limit=${limit}`,
    ) as Record<string, unknown>
    const items = normalizeVendorsList(tatva)
    const dataObj = (
      tatva.data && typeof tatva.data === 'object' && !Array.isArray(tatva.data)
    ) ? tatva.data as Record<string, unknown> : {}
    const pagination = (
      dataObj.pagination && typeof dataObj.pagination === 'object'
    ) ? dataObj.pagination as Record<string, unknown> : {}
    const paged = normalizeTatvaPagedItems(tatva, ['vendors', 'items', 'leads'])
    const total = Number(pagination.total ?? paged.total ?? items.length)
    const totalPages = Number(
      pagination.pages ?? pagination.totalPages ?? paged.totalPages ?? Math.max(1, Math.ceil(total / limit)),
    )
    try {
      const enrich = await fetchAdmin('/admin/vendor-leads/enrich', {
        method: 'POST',
        body: JSON.stringify({ items }),
      }) as { items?: VendorLeadItem[]; crm_configured?: boolean }
      return {
        success: Boolean(tatva.success ?? true),
        message: typeof tatva.message === 'string' ? tatva.message : undefined,
        crm_configured: !!enrich.crm_configured,
        data: {
          items: enrich.items || items,
          total,
          page,
          limit,
          totalPages,
        },
      } satisfies VendorLeadsResponse
    } catch {
      return {
        success: Boolean(tatva.success ?? true),
        message: typeof tatva.message === 'string' ? tatva.message : undefined,
        crm_configured: false,
        data: {
          items,
          total,
          page,
          limit,
          totalPages,
        },
      } satisfies VendorLeadsResponse
    }
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
