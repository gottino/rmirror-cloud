import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { AGENT_STALE_AFTER_MS, describeAgentActivity, parseServerDate } from '../../lib/agentActivity';
import type { AgentStatus } from '../../lib/api';

const NOW = new Date('2026-11-23T12:00:00Z');

function status(overrides: Partial<AgentStatus> = {}): AgentStatus {
  return {
    has_agent_connected: true,
    first_connected_at: '2026-11-01T10:00:00',
    last_activity_at: null,
    onboarding_state: 'agent_connected',
    ...overrides,
  };
}

describe('parseServerDate', () => {
  it('reads timestamps without an offset as UTC', () => {
    expect(parseServerDate('2026-11-23T10:00:00').toISOString()).toBe('2026-11-23T10:00:00.000Z');
    expect(parseServerDate('2026-11-23T10:00:00.123456').toISOString()).toBe('2026-11-23T10:00:00.123Z');
  });

  it('keeps explicit offsets', () => {
    expect(parseServerDate('2026-11-23T10:00:00Z').toISOString()).toBe('2026-11-23T10:00:00.000Z');
    expect(parseServerDate('2026-11-23T11:00:00+01:00').toISOString()).toBe('2026-11-23T10:00:00.000Z');
  });
});

describe('describeAgentActivity', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('asks for setup when no Mac app ever connected', () => {
    expect(describeAgentActivity(status({ has_agent_connected: false }))).toEqual({ kind: 'not-set-up' });
  });

  it('says nothing was synced yet when connected without activity', () => {
    expect(describeAgentActivity(status())).toEqual({ kind: 'no-activity' });
    // Older servers do not send the field at all
    expect(describeAgentActivity(status({ last_activity_at: undefined }))).toEqual({ kind: 'no-activity' });
  });

  it('shows the real time of the last activity', () => {
    expect(describeAgentActivity(status({ last_activity_at: '2026-11-23T10:00:00Z' }))).toEqual({
      kind: 'active',
      label: 'Last active 2h ago',
      stale: false,
    });
    expect(describeAgentActivity(status({ last_activity_at: '2026-11-23T11:59:40Z' }))).toMatchObject({
      label: 'Last active just now',
    });
  });

  it('turns stale after a day of silence', () => {
    const justFresh = new Date(NOW.getTime() - AGENT_STALE_AFTER_MS).toISOString();
    const justStale = new Date(NOW.getTime() - AGENT_STALE_AFTER_MS - 60_000).toISOString();
    expect(describeAgentActivity(status({ last_activity_at: justFresh }))).toMatchObject({ stale: false });
    expect(describeAgentActivity(status({ last_activity_at: justStale }))).toMatchObject({
      label: 'Last active 1d ago',
      stale: true,
    });
    expect(describeAgentActivity(status({ last_activity_at: '2026-11-16T12:00:00' }))).toMatchObject({
      label: 'Last active 7d ago',
      stale: true,
    });
  });

  it('treats an unparsable timestamp as no activity', () => {
    expect(describeAgentActivity(status({ last_activity_at: 'not a date' }))).toEqual({ kind: 'no-activity' });
  });
});
