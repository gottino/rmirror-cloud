/**
 * Shared constants for quota thresholds, polling, and Pro tier info.
 */

export const QUOTA_THRESHOLDS = {
  /** Warning state begins (amber) */
  WARNING: 67,
  /** Warning banner becomes visible */
  WARNING_VISIBLE: 80,
  /** Critical / destructive state */
  CRITICAL: 91,
} as const;

export const QUOTA_POLL_INTERVAL_MS = 60_000;

export const PRO_TIER = {
  launchDate: 'March 2026',
  price: 9,
  pagesPerMonth: 500,
  features: [
    '500 pages/month OCR transcription',
    'All integrations enabled',
    'Priority processing',
    'Email support',
  ],
  featuresBilling: [
    '500 pages/month OCR transcription (16x more!)',
    'All integrations enabled',
    'Priority processing',
    'Email support',
    'Advanced features',
  ],
} as const;
