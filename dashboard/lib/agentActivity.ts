import type { AgentStatus } from './api';
import { timeAgo } from './utils';

/** After this long without any Mac app activity the sidebar switches to the warning style. */
export const AGENT_STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export type AgentActivity =
  /** No Mac app has ever connected: offer setup. */
  | { kind: 'not-set-up' }
  /** Connected, but the Mac app has not synced anything yet. */
  | { kind: 'no-activity' }
  /**
   * The Mac app synced something (an upload or notebook metadata);
   * `stale` after a day of silence.
   */
  | { kind: 'active'; label: string; stale: boolean };

/**
 * Parse a server timestamp. Some API fields are naive UTC without an offset;
 * `new Date()` would read those as local time, so treat them as UTC.
 */
export function parseServerDate(value: string): Date {
  const hasOffset = /(Z|[+-]\d{2}:?\d{2})$/i.test(value);
  return new Date(hasOffset ? value : `${value}Z`);
}

export function describeAgentActivity(status: AgentStatus, now: number = Date.now()): AgentActivity {
  if (!status.has_agent_connected) return { kind: 'not-set-up' };
  if (!status.last_activity_at) return { kind: 'no-activity' };

  const last = parseServerDate(status.last_activity_at);
  if (Number.isNaN(last.getTime())) return { kind: 'no-activity' };

  return {
    kind: 'active',
    label: `Last active ${timeAgo(last.toISOString())}`,
    stale: now - last.getTime() > AGENT_STALE_AFTER_MS,
  };
}
