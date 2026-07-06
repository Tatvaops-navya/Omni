export type MeetSlot = {
  _id?: string
  id?: string
  scheduledAt?: string
  status?: string
  slotId?: string
  transcriptFile?: string | null
}

export type MeetLinkUser = {
  _id?: string
  phoneNumber?: string
  email?: string
  fullName?: string
  userName?: string
}

export type MeetLinkRecord = {
  _id?: string
  userId?: MeetLinkUser
  meetLink?: string
  description?: string
  slots?: MeetSlot[]
  createdAt?: string
  updatedAt?: string
}

export type MeetLinksResponse = {
  success: boolean
  message?: string
  data: MeetLinkRecord[]
  pagination?: {
    page: number
    limit: number
    total: number
    totalPages: number
  }
}
