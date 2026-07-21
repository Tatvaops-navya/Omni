// Omnichannel backend: login, enquiries, CRM. Tatva platform: api.withtatva.ai via /tatva-api proxy.
import type { MeetLinkRecord, MeetLinksResponse, MeetSlot } from '../types/meet'
import type { EnquiryAttachment } from '../types/enquiry'
import { normalizePhone } from '../utils/phone'
import { OMNICHANNEL_API_BASE, TATVA_API_BASE } from './config'

const BASE_URL = OMNICHANNEL_API_BASE

export { OMNICHANNEL_API_BASE, TATVA_API_BASE, TATVA_API_ORIGIN } from './config'

/** Tatva users list — https://api.withtatva.ai/users/api/users */
export const TATVA_USERS_PATH = '/users/api/users'
/** Tatva approved vendors — https://api.withtatva.ai/vendor/api/vendors */
export const TATVA_VENDORS_PATH = '/vendor/api/vendors'
/** Tatva employee projects — https://api.withtatva.ai/admin/api/admin/employees/{id}/projects */
export const TATVA_MY_PROJECTS_EMPLOYEE_ID = '69ef0a0a11db8baeba77b711'
export const TATVA_EMPLOYEE_PROJECTS_PATH =
  `/admin/api/admin/employees/${TATVA_MY_PROJECTS_EMPLOYEE_ID}/projects`
/** My Leads vendor tab — GET /admin/api/admin/vendor-leads/poc/{pocId} */
export const TATVA_MY_VENDOR_LEADS_POC_ID = '69e06fca730c39ce2e45a266'
/** Fallback My Leads user tab POC — prefer logged-in Tatva employee id */
export const TATVA_MY_USER_LEADS_POC_ID = '69ef0a0a11db8baeba77b711'

let authToken: string | null = sessionStorage.getItem('aadhya_admin_token')
/** Tatva JWT (`data.accessToken`) — Bearer for all `/tatva-api` calls */
let tatvaAccessToken: string | null = sessionStorage.getItem('aadhya_tatva_access_token')

export type CrmUser = {
  id?: string | null
  name?: string | null
  email?: string | null
  role: 'admin' | 'presales' | 'rm' | 'campaign_owner' | string
  /** Tatva employee role name (e.g. sales_manager, campaign_owner) */
  tatvaRole?: string | null
  department?: string | null
  phone?: string | null
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

function extractTatvaAccessToken(payload: Record<string, unknown> | null | undefined): string | null {
  if (!payload || typeof payload !== 'object') return null
  const data = payload.data
  const candidates: unknown[] = [
    payload.accessToken,
    payload.access_token,
    payload.token,
  ]
  if (data && typeof data === 'object') {
    const d = data as Record<string, unknown>
    candidates.push(d.accessToken, d.access_token, d.token)
  }
  for (const value of candidates) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

export function setTatvaAccessToken(token: string | null | undefined) {
  const value = typeof token === 'string' ? token.trim() : ''
  tatvaAccessToken = value || null
  if (tatvaAccessToken) {
    sessionStorage.setItem('aadhya_tatva_access_token', tatvaAccessToken)
  } else {
    sessionStorage.removeItem('aadhya_tatva_access_token')
  }
}

export function getTatvaAccessToken(): string | null {
  return tatvaAccessToken || sessionStorage.getItem('aadhya_tatva_access_token')
}

/** Resolve Tatva employee Mongo id from session user id and/or JWT accessToken. */
export function resolveLoggedInTatvaEmployeeId(): string | null {
  const user = getUser()
  const rawId = String(user?.id || '').trim()
  if (rawId.startsWith('tatva:')) {
    const id = rawId.slice('tatva:'.length).trim()
    if (id) return id
  }
  if (/^[a-f0-9]{24}$/i.test(rawId)) return rawId

  const token = getTatvaAccessToken()
  if (!token) return null
  try {
    const part = token.split('.')[1]
    if (!part) return null
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    const payload = JSON.parse(json) as Record<string, unknown>
    const id = String(payload._id || payload.id || '').trim()
    return id || null
  } catch {
    return null
  }
}

export function setToken(
  token: string,
  user?: CrmUser | null,
  options?: { tatvaAccessToken?: string | null },
) {
  authToken = token
  sessionStorage.setItem('aadhya_admin_token', token)
  let nextUser = user || null
  const access = options?.tatvaAccessToken
  if (access) {
    setTatvaAccessToken(access)
    nextUser = enrichUserFromTatvaToken(nextUser, access)
  } else if (options && 'tatvaAccessToken' in (options || {})) {
    setTatvaAccessToken(options.tatvaAccessToken)
  }
  if (nextUser) {
    crmUser = nextUser
    sessionStorage.setItem('aadhya_crm_user', JSON.stringify(nextUser))
  }
}

/** Pull Tatva role / department hints from JWT for incentive matching. */
export function enrichUserFromTatvaToken(
  user: CrmUser | null | undefined,
  accessToken?: string | null,
): CrmUser | null {
  if (!user) return user || null
  const token = accessToken || getTatvaAccessToken()
  if (!token) return user
  try {
    const part = token.split('.')[1]
    if (!part) return user
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'))
    const payload = JSON.parse(json) as Record<string, unknown>
    const tatvaRole = String(payload.role || payload.roleName || user.tatvaRole || '').trim() || null
    const department = String(payload.department || user.department || '').trim() || null
    return {
      ...user,
      tatvaRole: tatvaRole || user.tatvaRole || null,
      department: department || user.department || null,
    }
  } catch {
    return user
  }
}

export function clearToken() {
  authToken = null
  crmUser = null
  tatvaAccessToken = null
  sessionStorage.removeItem('aadhya_admin_token')
  sessionStorage.removeItem('aadhya_crm_user')
  sessionStorage.removeItem('aadhya_tatva_access_token')
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

export function isCampaignOwnerUser(): boolean {
  return getUser()?.role === 'campaign_owner'
}

export function isStaffUser(): boolean {
  const role = getUser()?.role
  return role === 'admin'
    || role === 'presales'
    || role === 'rm'
    || role === 'campaign_owner'
}

export function canViewEnquiryAttachments(): boolean {
  return isStaffUser()
}

async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs = 15000,
): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error(
        'Session setup timed out. Start the backend: python -m backend (port 8000).',
      )
    }
    throw err
  } finally {
    window.clearTimeout(timer)
  }
}

function extractTatvaEmployeeFromLogin(payload: Record<string, unknown>) {
  const data = payload.data
  if (!data || typeof data !== 'object') return null
  const employee = (data as Record<string, unknown>).employee
  if (!employee || typeof employee !== 'object') return null
  const emp = employee as Record<string, unknown>
  const role = emp.role
  const roleName = role && typeof role === 'object' && !Array.isArray(role)
    ? String((role as { name?: string }).name || '')
    : String(role || '')
  return {
    userId: String(emp._id || emp.id || '').trim() || undefined,
    name: String(emp.fullName || emp.name || '').trim() || undefined,
    roleName: roleName || undefined,
  }
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
  if (!res.ok) {
    const body = await res.json().catch(() => ({} as Record<string, unknown>))
    let detail = ''
    if (typeof body.detail === 'string') {
      detail = body.detail
    } else if (Array.isArray(body.detail) && body.detail[0] && typeof body.detail[0] === 'object') {
      const first = body.detail[0] as { msg?: string }
      detail = first.msg || ''
    } else if (typeof body.message === 'string') {
      detail = body.message
    }
    if (res.status === 404 && path.includes('/progress-stages')) {
      throw new Error(
        detail
        || 'Progress stages API not found. Restart the backend (python -m backend) so the new route is loaded.',
      )
    }
    if (res.status === 503) {
      throw new Error(detail || 'CRM database not configured on the backend.')
    }
    throw new Error(detail || `HTTP ${res.status}`)
  }
  return res.json()
}

async function fetchTatva(path: string, options: RequestInit = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  // Always authorize Tatva with login accessToken — never the local panel token
  const bearer = getTatvaAccessToken()
  if (bearer) {
    headers.Authorization = `Bearer ${bearer}`
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
  rm_name?: string | null
  assigned_at?: string | null
  presales_completed_at?: string | null
  notes?: string | null
  comment_log?: Array<{
    text: string
    created_at?: string
    author_name?: string | null
    author_id?: string | null
  }>
  custom_progress_stages?: Array<{
    id: string
    title: string
    description?: string | null
    insert_after: string
    completed_at?: string | null
    created_at?: string
    created_by_name?: string | null
  }>
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
  assignedTo?: string | {
    _id?: string
    id?: string
    fullName?: string
    name?: string
    email?: string
  }
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
  utmSource?: string
  utmMedium?: string
  utmCampaign?: string
  source?: string
  medium?: string
  campaign?: string
  campaignOwner?: string | { fullName?: string; name?: string; email?: string }
  campaign_owner?: string | { fullName?: string; name?: string; email?: string }
  createdAt?: string
  updatedAt?: string
  assignment?: LeadAssignmentMeta
  vendor_assignment?: VendorAssignmentMeta
  poc?: string | { _id?: string; id?: string; fullName?: string; name?: string }
  [key: string]: unknown
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
  utm_source?: string | null
  utm_medium?: string | null
  utm_campaign?: string | null
  utmSource?: string
  utmMedium?: string
  utmCampaign?: string
  createdAt?: string
  updatedAt?: string
  [key: string]: unknown
}

function normalizeTatvaUser(user: Record<string, unknown>): TatvaUserItem {
  return user as TatvaUserItem
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
  poc?: string | { _id?: string; id?: string; fullName?: string; name?: string }
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
    page?: number
    limit?: number
    totalPages?: number
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
  /**
   * Admin password login — browser calls Tatva
   * POST https://devopsapi.withtatva.ai/admin/api/admin/employees/auth/login
   * body: { email, password }, then mints a local panel session.
   */
  login: async (email: string, password: string) => {
    const normalizedEmail = email.trim().toLowerCase()
    const tatvaRes = await fetch(`${TATVA_API_BASE}/admin/api/admin/employees/auth/login`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email: normalizedEmail, password }),
    })
    const tatvaPayload = await tatvaRes.json().catch(() => ({} as Record<string, unknown>))
    if (!tatvaRes.ok || tatvaPayload.success === false) {
      const detail =
        (typeof tatvaPayload.message === 'string' && tatvaPayload.message) ||
        (typeof tatvaPayload.detail === 'string' && tatvaPayload.detail) ||
        (typeof tatvaPayload.error === 'string' && tatvaPayload.error) ||
        `Login failed (${tatvaRes.status})`
      throw new Error(detail)
    }

    const accessToken = extractTatvaAccessToken(tatvaPayload)
    if (!accessToken) {
      throw new Error('Tatva login did not return an accessToken')
    }

    const employee = extractTatvaEmployeeFromLogin(tatvaPayload)

    // Local session for /admin/* — lightweight body, 15s timeout
    let sessionRes: Response
    try {
      sessionRes = await fetchWithTimeout(`${BASE_URL}/admin/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: normalizedEmail,
          accessToken,
          name: employee?.name,
          userId: employee?.userId,
        }),
      })
    } catch (sessionErr) {
      // Fallback if token-only session fails — backend re-verifies password
      sessionRes = await fetchWithTimeout(`${BASE_URL}/admin/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: normalizedEmail, password }),
      })
      if (!sessionRes.ok) {
        throw sessionErr instanceof Error ? sessionErr : new Error('Session setup failed')
      }
    }

    const data = await sessionRes.json().catch(() => ({} as Record<string, unknown>))
    if (!sessionRes.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : 'Session setup failed'
      throw new Error(detail)
    }
    return {
      ...data,
      tatvaAccessToken: accessToken,
      accessToken,
    }
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

  /** Team OTP — POST /admin/api/admin/employees/auth/otp/send */
  sendTeamOtp: async (phoneNumber: string) => {
    const digits = normalizePhone(phoneNumber)
    if (digits.length !== 10) {
      throw new Error('Enter a valid 10-digit mobile number')
    }
    const payload = await fetchTatva('/admin/api/admin/employees/auth/otp/send', {
      method: 'POST',
      body: JSON.stringify({ phoneNumber: digits }),
    }) as Record<string, unknown>

    if (payload.success === false) {
      const message = typeof payload.message === 'string' && payload.message.trim()
        ? payload.message
        : typeof payload.detail === 'string' && payload.detail.trim()
          ? payload.detail
          : 'Failed to send OTP'
      throw new Error(message)
    }
    return payload
  },

  /**
   * Team OTP verify — browser calls Tatva exact endpoint
   * POST /admin/api/admin/employees/auth/otp/verify
   * then mints a local panel session (OTP is single-use; do not re-verify).
   */
  verifyTeamOtp: async (phoneNumber: string, otp: string) => {
    const digits = normalizePhone(phoneNumber)
    const code = String(otp || '').trim()
    if (digits.length !== 10) {
      throw new Error('Enter a valid 10-digit mobile number')
    }
    if (!code) {
      throw new Error('Enter the OTP')
    }

    const tatvaRes = await fetch(`${TATVA_API_BASE}/admin/api/admin/employees/auth/otp/verify`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ phoneNumber: digits, otp: code }),
    })
    const tatvaPayload = await tatvaRes.json().catch(() => ({} as Record<string, unknown>))
    if (!tatvaRes.ok || tatvaPayload.success === false) {
      const detail =
        (typeof tatvaPayload.message === 'string' && tatvaPayload.message) ||
        (typeof tatvaPayload.detail === 'string' && tatvaPayload.detail) ||
        (typeof tatvaPayload.error === 'string' && tatvaPayload.error) ||
        'Invalid OTP'
      throw new Error(detail)
    }

    const accessToken = extractTatvaAccessToken(tatvaPayload)
    if (!accessToken) {
      throw new Error('Tatva OTP verify did not return an accessToken')
    }

    const sessionRes = await fetch(`${BASE_URL}/admin/team-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        phoneNumber: digits,
        accessToken,
        tatvaPayload,
      }),
    })
    const data = await sessionRes.json().catch(() => ({} as Record<string, unknown>))
    if (!sessionRes.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : 'Session setup failed'
      throw new Error(detail)
    }
    return {
      ...data,
      tatvaAccessToken: accessToken,
      accessToken,
    }
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
    const dept = (department || 'sales').trim() || 'sales'
    // RM list uses /employees?department=rm (Tatva query API).
    // Sales and other depts keep the by-department path.
    const path = dept.toLowerCase() === 'rm'
      ? `/admin/api/admin/employees?department=${encodeURIComponent(dept)}&page=${page}&limit=${limit}`
      : `/admin/api/admin/employees/by-department/${encodeURIComponent(dept)}?page=${page}&limit=${limit}`
    const payload = await fetchTatva(path) as Record<string, unknown>
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
      staff_role?: 'presales' | 'rm'
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

  teamPerformance: (params: {
    staff_type: 'sales' | 'rm'
    staff_id: string
    period?: string
    staff_email?: string
    staff_name?: string
  }) => {
    const qs = new URLSearchParams({
      staff_type: params.staff_type,
      staff_id: params.staff_id,
      period: params.period || 'month',
    })
    if (params.staff_email) qs.set('staff_email', params.staff_email)
    if (params.staff_name) qs.set('staff_name', params.staff_name)
    return fetchAdmin(`/admin/team-performance?${qs.toString()}`)
  },

  upsertSalesTarget: (body: {
    staff_type: 'sales' | 'rm'
    staff_id: string
    period: string
    target_leads: number
  }) =>
    fetchAdmin('/admin/sales-targets', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  myProjects: async (params?: { page?: number; limit?: number }) => {
    const page = Math.max(1, params?.page ?? 1)
    const limit = Math.max(1, Math.min(params?.limit ?? 10, 100))
    const qs = new URLSearchParams({
      page: String(page),
      limit: String(limit),
    })
    const payload = await fetchTatva(`${TATVA_EMPLOYEE_PROJECTS_PATH}?${qs}`) as Record<string, unknown>
    const paged = normalizeTatvaPagedItems(payload, ['projects', 'items', 'assignments'])
    let items = (paged.items.length
      ? paged.items
      : normalizeEmployeeProjects(payload)) as EmployeeProjectItem[]

    const dataObj = (
      payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)
    ) ? payload.data as Record<string, unknown> : {}
    const pagination = (
      dataObj.pagination && typeof dataObj.pagination === 'object'
    ) ? dataObj.pagination as Record<string, unknown> : {}

    const total = Number(pagination.total ?? paged.total ?? items.length)
    // If API returns the full list ignoring page/limit, paginate client-side.
    if (items.length > limit) {
      const start = (page - 1) * limit
      items = items.slice(start, start + limit)
    }
    const apiPages = Number(pagination.pages ?? pagination.totalPages)
    const totalPages = Math.max(
      1,
      (Number.isFinite(apiPages) && apiPages > 1 ? apiPages : 0) || Math.ceil(total / limit) || 1,
    )

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
        total,
        page,
        limit,
        totalPages,
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
      method: 'PUT',
      body: JSON.stringify({ notes }),
    }),

  addProgressStage: (
    externalId: string,
    body: { title: string; description?: string; insert_after?: string },
    leadType: 'user' | 'vendor' = 'user',
  ) =>
    fetchAdmin(`/admin/my-leads/${encodeURIComponent(externalId)}/progress-stages?lead_type=${leadType}`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  completeProgressStage: (
    externalId: string,
    stageId: string,
    leadType: 'user' | 'vendor' = 'user',
  ) =>
    fetchAdmin(
      `/admin/my-leads/${encodeURIComponent(externalId)}/progress-stages/${encodeURIComponent(stageId)}/complete?lead_type=${leadType}`,
      { method: 'PATCH' },
    ),

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
  presales: async (params?: {
    page?: number
    limit?: number
    flag?: string
    utm_source?: string
    utm_medium?: string
  }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.flag) qs.set('flag', params.flag)
    if (params?.utm_source) qs.set('utm_source', params.utm_source)
    if (params?.utm_medium) qs.set('utm_medium', params.utm_medium)
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
  assignPresalesPoc: (presalesId: string, pocId: string) =>
    fetchTatva(`/admin/api/admin/presales/${encodeURIComponent(presalesId)}/poc`, {
      method: 'PUT',
      body: JSON.stringify({ poc: pocId }),
    }),
  /** PUT /admin/api/admin/presales/{id}/rm — body: { "rm": "<employeeId>" } */
  assignPresalesRm: (presalesId: string, rmId: string) =>
    fetchTatva(`/admin/api/admin/presales/${encodeURIComponent(presalesId)}/rm`, {
      method: 'PUT',
      body: JSON.stringify({ rm: rmId }),
    }),
  assignVendorLeadPoc: (vendorLeadId: string, pocId: string) =>
    fetchTatva(`/admin/api/admin/vendor-leads/${encodeURIComponent(vendorLeadId)}/poc`, {
      method: 'PUT',
      body: JSON.stringify({ poc: pocId }),
    }),
  updateVendorLeadStatus: (vendorLeadId: string, status: 'approved' | 'rejected') =>
    fetchTatva(`/admin/api/admin/vendor-leads/${encodeURIComponent(vendorLeadId)}`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    }),
  users: async (params?: {
    page?: number
    limit?: number
    utm_source?: string
    utm_medium?: string
  }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit))
    if (params?.utm_source) qs.set('utm_source', params.utm_source)
    if (params?.utm_medium) qs.set('utm_medium', params.utm_medium)
    const query = qs.toString()
    const tatva = await fetchTatva(`${TATVA_USERS_PATH}${query ? `?${query}` : ''}`) as TatvaUsersResponse
    const paged = normalizeTatvaPagedItems(tatva as unknown as Record<string, unknown>, ['users', 'items'])
    const users = paged.items
      .filter((item): item is Record<string, unknown> => !!item && typeof item === 'object')
      .map(normalizeTatvaUser)
    return {
      success: tatva.success,
      message: tatva.message,
      data: {
        users,
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
    fetchAdmin(`/admin/meet-links/slots/${encodeURIComponent(slotId)}/reschedule`, { method: 'PUT' }),
  presalesByPoc: async (pocId: string, params?: { page?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit ?? 20))
    const query = qs.toString()
    const path = `/admin/api/admin/presales/poc/${encodeURIComponent(pocId)}`
    const tatva = await fetchTatva(`${path}${query ? `?${query}` : ''}`) as Record<string, unknown>
    const paged = normalizeTatvaPagedItems(tatva, ['items', 'presales', 'leads'])
    const items = paged.items as PresalesItem[]
    return {
      success: Boolean(tatva.success ?? true),
      message: typeof tatva.message === 'string' ? tatva.message : undefined,
      crm_configured: false,
      data: {
        items,
        total: paged.total,
        page: paged.page,
        limit: paged.limit,
        totalPages: paged.totalPages,
      },
    } satisfies PresalesResponse
  },
  vendorLeadsByPoc: async (pocId: string, params?: { page?: number; limit?: number }) => {
    const qs = new URLSearchParams()
    if (params?.page) qs.set('page', String(params.page))
    if (params?.limit) qs.set('limit', String(params.limit ?? 20))
    const query = qs.toString()
    const path = `/admin/api/admin/vendor-leads/poc/${encodeURIComponent(pocId)}`
    const tatva = await fetchTatva(`${path}${query ? `?${query}` : ''}`) as Record<string, unknown>
    const paged = normalizeTatvaPagedItems(tatva, ['leads', 'items', 'vendorLeads', 'vendor_leads'])
    const items = paged.items as VendorLeadItem[]
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
          total: paged.total,
          page: paged.page,
          limit: paged.limit,
          totalPages: paged.totalPages,
        },
      } satisfies VendorLeadsResponse
    } catch {
      return {
        success: Boolean(tatva.success ?? true),
        message: typeof tatva.message === 'string' ? tatva.message : undefined,
        crm_configured: false,
        data: {
          items,
          total: paged.total,
          page: paged.page,
          limit: paged.limit,
          totalPages: paged.totalPages,
        },
      } satisfies VendorLeadsResponse
    }
  },

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
