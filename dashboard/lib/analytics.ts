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
