'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Image from 'next/image';
import { HomeIcon, Puzzle, X, MessageSquare, Mail, Shield } from 'lucide-react';
import { useAuth } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import { getAgentStatus, type AgentStatus } from '@/lib/api';

interface SidebarProps {
  open?: boolean;
  onClose?: () => void;
}

const ADMIN_USER_IDS = (process.env.NEXT_PUBLIC_ADMIN_USER_IDS || '').split(',').map(s => s.trim()).filter(Boolean);

export default function Sidebar({ open = true, onClose }: SidebarProps) {
  const pathname = usePathname();
  const { getToken, isSignedIn, userId } = useAuth();
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);

  // Development mode bypass — only works on localhost, backend still enforces auth
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true'
    && typeof window !== 'undefined' && window.location.hostname === 'localhost';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  const fetchAgentStatus = async () => {
    if (!effectiveIsSignedIn) return;

    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();

      if (!token) return;

      const status = await getAgentStatus(token);
      setAgentStatus(status);
    } catch (err) {
      console.error('Error fetching agent status:', err);
    }
  };

  useEffect(() => {
    fetchAgentStatus();
    // Poll every 60 seconds
    const interval = setInterval(fetchAgentStatus, 60000);
    return () => clearInterval(interval);
  }, [effectiveIsSignedIn]);

  const isActive = (path: string) => {
    if (path === '/') {
      return pathname === '/';
    }
    return pathname?.startsWith(path);
  };

  return (
    <aside
      className={`
        fixed lg:static inset-y-0 left-0 z-50
        w-64 border-r flex flex-col h-screen
        transform transition-transform duration-200 ease-in-out
        lg:transform-none
        ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--card)' }}
    >
      {/* Logo */}
      <div className="p-6 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <Image
              src="/rm-icon.png"
              alt="rMirror"
              width={32}
              height={32}
              style={{ marginRight: '8px', marginTop: '3px'}}
            />
            <h1 style={{ fontSize: '1.375rem', fontWeight: 600, color: 'var(--warm-charcoal)', margin: 0 }}>
              rMirror
            </h1>
            <span
              style={{
                fontSize: '0.625rem',
                fontWeight: 700,
                color: 'white',
                background: 'var(--terracotta)',
                padding: '1px 6px',
                borderRadius: '9999px',
                letterSpacing: '0.05em',
                marginLeft: '6px',
                alignSelf: 'center',
              }}
            >
              BETA
            </span>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="lg:hidden p-2"
              style={{ color: 'var(--warm-gray)' }}
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>
        <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)', marginTop: '0.25rem' }}>
          Cloud Sync
        </p>
      </div>

      {/* Navigation */}
      <div className="flex-1 flex flex-col">
        <div className="p-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <Link
            href="/dashboard"
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
            style={{
              backgroundColor: isActive('/dashboard') && !isActive('/integrations')
                ? 'var(--primary)'
                : 'transparent',
              color: isActive('/dashboard') && !isActive('/integrations')
                ? 'var(--primary-foreground)'
                : 'var(--warm-charcoal)',
              fontSize: '0.925em',
              fontWeight: 500
            }}
          >
            <HomeIcon className="w-5 h-5" />
            All Notebooks
          </Link>
        </div>

        <div className="flex-1" />

        {/* Bottom navigation */}
        <div className="border-t p-4 space-y-1" style={{ borderColor: 'var(--border)' }}>
          <Link
            href="/integrations"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
            style={{
              backgroundColor: isActive('/integrations') ? 'var(--primary)' : 'transparent',
              color: isActive('/integrations') ? 'var(--primary-foreground)' : 'var(--warm-charcoal)',
              fontSize: '0.925em',
              fontWeight: 500
            }}
          >
            <Puzzle className="w-5 h-5" />
            Integrations
          </Link>
          <a
            href="https://gottino.notion.site/30ea6c5dacd0808a9d6df5656e847b4b"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
            style={{
              color: 'var(--warm-charcoal)',
              fontSize: '0.925em',
              fontWeight: 500
            }}
          >
            <MessageSquare className="w-5 h-5" />
            Beta Feedback
          </a>
          <a
            href="mailto:support@rmirror.io"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
            style={{
              color: 'var(--warm-charcoal)',
              fontSize: '0.925em',
              fontWeight: 500
            }}
          >
            <Mail className="w-5 h-5" />
            Support
          </a>
          {(isDevelopmentMode || (userId && ADMIN_USER_IDS.includes(userId))) && (
            <Link
              href="/admin/waitlist"
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
              style={{
                backgroundColor: isActive('/admin') ? 'var(--primary)' : 'transparent',
                color: isActive('/admin') ? 'var(--primary-foreground)' : 'var(--warm-charcoal)',
                fontSize: '0.925em',
                fontWeight: 500
              }}
            >
              <Shield className="w-5 h-5" />
              Admin
            </Link>
          )}
        </div>

        {/* Agent Status */}
        {agentStatus && (
          <div className="p-4 border-t space-y-3" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center space-x-2">
              <div
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: agentStatus.has_agent_connected ? 'var(--sage-green)' : 'var(--warm-gray)' }}
              />
              <span style={{ fontSize: '0.875em', color: 'var(--foreground)', fontWeight: 500 }}>
                {agentStatus.has_agent_connected ? 'Agent Connected' : 'No Agent'}
              </span>
            </div>
            {agentStatus.has_agent_connected && (
              <div style={{ fontSize: '0.75em', color: 'var(--warm-gray)' }}>
                Last sync: a few moments ago
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
