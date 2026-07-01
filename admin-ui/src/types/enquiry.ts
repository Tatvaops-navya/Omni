export type EnquiryAttachment = {
  file_name: string
  file_url: string
  preview_url?: string
  mime_type?: string
}

export type Enquiry = {
  session_id?: string
  phone_number?: string
  channel?: string
  service_category?: string | null
  extracted_fields?: Record<string, unknown>
  completion_pct?: number
  attachment_count?: number
  attachments?: EnquiryAttachment[]
  created_at?: string
  last_active?: string
  status?: string
  requirements_summary?: { label: string; value: string }[]
}
