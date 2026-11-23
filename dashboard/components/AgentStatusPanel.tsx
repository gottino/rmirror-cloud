'use client';

import Link from 'next/link';
import { Laptop } from 'lucide-react';
import type { AgentStatus } from '@/lib/api';
import { describeAgentActivity } from '@/lib/agentActivity';

/** Link that opens the setup wizard even when notebooks already exist. */
export const SETUP_WIZARD_HREF = '/dashboard?setup=1';

/**
 * Sidebar footer showing the Mac app's state: a setup link when no app has
 * connected, otherwise the real time of the last upload (amber after a day).
 */
export function AgentStatusPanel({ status }: { status: AgentStatus }) {
  const activity = describeAgentActivity(status);

  if (activity.kind === 'not-set-up') {
    return (
      <div className="p-4 border-t" style={{ borderColor: 'var(--border)' }}>
        <Link
          href={SETUP_WIZARD_HREF}
          className="flex items-center gap-2 px-3 py-2 rounded-lg transition-all hover:bg-[var(--soft-cream)]"
          style={{ color: 'var(--terracotta)', fontSize: '0.875em', fontWeight: 500 }}
        >
          <Laptop className="w-4 h-4" />
          Set up the Mac app
        </Link>
      </div>
    );
  }

  const stale = activity.kind === 'active' && activity.stale;
  const dotColor = stale ? 'var(--warning-accent)' : 'var(--sage-green)';

  return (
    <div className="p-4 border-t space-y-1" style={{ borderColor: 'var(--border)' }} data-testid="agent-status">
      <div className="flex items-center space-x-2">
        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: dotColor }} />
        <span style={{ fontSize: '0.875em', color: 'var(--foreground)', fontWeight: 500 }}>
          {stale ? 'No recent uploads' : 'Mac app connected'}
        </span>
      </div>
      <div style={{ fontSize: '0.75em', color: stale ? 'var(--warning-text)' : 'var(--warm-gray)' }}>
        {activity.kind === 'active' ? activity.label : 'No uploads yet'}
      </div>
      {stale && (
        <div style={{ fontSize: '0.75em', color: 'var(--warning-text)' }}>
          Is rMirror running on your Mac?
        </div>
      )}
    </div>
  );
}
