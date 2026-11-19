import { api } from '@/lib/api-client'

/** Mirrors backend/app/api/v1/channels.py. Simulator endpoints; no telecom gateway involved. */

export type UssdReply = {
  session_id: string
  text: string
  end: boolean
  timed_out: boolean
  timeout_seconds: number
  election: string
  demo_label: string | null
  notice: string
}

export type SmsReply = {
  message_ref: string
  command: string
  outcome: 'ok' | 'invalid' | 'unknown_location' | 'rate_limited' | string
  parts: string[]
  has_more: boolean
  duplicate: boolean
  provider: string
  notice: string
}

export function startUssdSession(phoneNumber?: string) {
  return api.post<UssdReply>('/ussd/sessions', { phone_number: phoneNumber || null }, { auth: false })
}

export function sendUssdInput(sessionId: string, input: string) {
  return api.post<UssdReply>(`/ussd/sessions/${encodeURIComponent(sessionId)}/input`, { input }, { auth: false })
}

export function sendSms(from: string, text: string, messageId?: string) {
  return api.post<SmsReply>('/sms/incoming', { from, text, message_id: messageId }, { auth: false })
}
