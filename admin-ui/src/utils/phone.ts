import type { Enquiry } from '../types/enquiry'

export function normalizePhone(phone: string | undefined | null): string {
  const digits = String(phone || '').replace(/\D/g, '')
  if (digits.length >= 10) return digits.slice(-10)
  return digits
}

export function enquiryPhones(enquiry: Enquiry): Set<string> {
  const phones = new Set<string>()
  for (const raw of [enquiry.phone_number, enquiry.extracted_fields?.phone_number]) {
    const norm = normalizePhone(raw != null ? String(raw) : '')
    if (norm) phones.add(norm)
  }
  return phones
}

export function findEnquiryByPhone(enquiries: Enquiry[], phone: string | undefined): Enquiry | null {
  const needle = normalizePhone(phone)
  if (!needle) return null
  const matches = enquiries.filter(e => enquiryPhones(e).has(needle))
  if (matches.length === 0) return null
  return matches.sort((a, b) => {
    const aTime = String(a.last_active || a.created_at || '')
    const bTime = String(b.last_active || b.created_at || '')
    return bTime.localeCompare(aTime)
  })[0]
}
