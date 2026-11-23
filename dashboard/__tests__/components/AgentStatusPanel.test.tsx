import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { AgentStatusPanel, SETUP_WIZARD_HREF } from '../../components/AgentStatusPanel';
import type { AgentStatus } from '../../lib/api';

function status(overrides: Partial<AgentStatus> = {}): AgentStatus {
  return {
    has_agent_connected: true,
    first_connected_at: '2026-11-01T10:00:00',
    last_activity_at: null,
    onboarding_state: 'agent_connected',
    ...overrides,
  };
}

describe('AgentStatusPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-11-23T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('links to the setup wizard when no Mac app is connected', () => {
    render(<AgentStatusPanel status={status({ has_agent_connected: false })} />);
    const link = screen.getByRole('link', { name: /set up the mac app/i });
    expect(link).toHaveAttribute('href', SETUP_WIZARD_HREF);
    expect(screen.queryByText(/no agent/i)).not.toBeInTheDocument();
  });

  it('shows the real last upload time, never a fixed text', () => {
    render(<AgentStatusPanel status={status({ last_activity_at: '2026-11-23T09:00:00Z' })} />);
    expect(screen.getByText('Mac app connected')).toBeInTheDocument();
    expect(screen.getByText('Last upload 3h ago')).toBeInTheDocument();
    expect(screen.queryByText(/a few moments ago/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/is rmirror running/i)).not.toBeInTheDocument();
  });

  it('warns after a day without uploads', () => {
    render(<AgentStatusPanel status={status({ last_activity_at: '2026-11-20T12:00:00Z' })} />);
    expect(screen.getByText('No recent uploads')).toBeInTheDocument();
    expect(screen.getByText('Last upload 3d ago')).toBeInTheDocument();
    expect(screen.getByText(/is rmirror running on your mac/i)).toBeInTheDocument();
  });

  it('says when nothing was uploaded yet', () => {
    render(<AgentStatusPanel status={status()} />);
    expect(screen.getByText('No uploads yet')).toBeInTheDocument();
  });
});
