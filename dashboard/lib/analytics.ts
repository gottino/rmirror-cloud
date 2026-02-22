// Umami analytics utility — typed event tracking wrapper
// Umami's script.js auto-tracks pageviews. This module adds typed custom events.

declare global {
  interface Window {
    umami?: {
      track: (name: string, data?: Record<string, string | number | boolean>) => void
      identify: (data: Record<string, string>) => void
    }
  }
}

type AnalyticsEvent =
  | { name: 'waitlist_signup'; data: { source: string } }
  | { name: 'notebook_opened'; data: { notebook_id: string } }
  | { name: 'integration_connected'; data: { service: string } }
  | { name: 'onboarding_step'; data: { step: string; completed: boolean } }
  | { name: 'search_performed'; data: { query_length: number; results: number } }
  | { name: 'quota_warning_shown'; data: { percent_used: number } }
  | { name: 'terms_accepted'; data: { tos_version: string } }
  | { name: 'agent_downloaded'; data?: Record<string, never> }
  | { name: 'integration_setup_started'; data: { service: string } }
  | { name: 'notion_database_configured'; data: { action: string } }
  | { name: 'data_exported'; data?: Record<string, never> }
  | { name: 'billing_page_viewed'; data?: Record<string, never> }
  | { name: 'pro_waitlist_signup'; data: { source: string } }
  | { name: 'onboarding_dismissed'; data?: Record<string, never> }
  | { name: 'integration_disconnected'; data: { service: string } }

export function trackEvent(event: AnalyticsEvent) {
  if (typeof window !== 'undefined' && window.umami) {
    window.umami.track(event.name, event.data as Record<string, string | number | boolean>)
  }
}

export function identifyUser(userId: string) {
  if (typeof window !== 'undefined' && window.umami) {
    window.umami.identify({ userId })
  }
}
