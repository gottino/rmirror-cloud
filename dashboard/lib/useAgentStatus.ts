'use client';

import { useEffect } from 'react';
import { getAgentStatus, type AgentStatus } from './api';
import { useApiQuery } from './useApiQuery';
import { useApiToken } from './useApiToken';

/**
 * The signed-in user's agent connection status, shared by the dashboard and
 * the sidebar. `pollMs` refreshes it in the background.
 */
export function useAgentStatus({ enabled, pollMs }: { enabled: boolean; pollMs?: number }): AgentStatus | null {
  const getToken = useApiToken();
  const { data, reload } = useApiQuery<AgentStatus>(enabled ? 'agent-status' : null, async (signal) => {
    const token = await getToken();
    if (!token) throw new Error('Failed to get authentication token');
    return getAgentStatus(token, signal);
  });

  useEffect(() => {
    if (!enabled || !pollMs) return;
    const interval = setInterval(() => void reload(), pollMs);
    return () => clearInterval(interval);
  }, [enabled, pollMs, reload]);

  return data;
}
