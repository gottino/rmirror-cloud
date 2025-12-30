'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import Image from 'next/image';
import { HomeIcon, Puzzle, CreditCard, X } from 'lucide-react';

interface SidebarProps {
  open?: boolean;
  onClose?: () => void;
}

export default function Sidebar({ open = true, onClose }: SidebarProps) {
  const pathname = usePathname();

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
            href="/"
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
            style={{
              backgroundColor: isActive('/') && !isActive('/integrations') && !isActive('/billing')
                ? 'var(--primary)'
                : 'transparent',
              color: isActive('/') && !isActive('/integrations') && !isActive('/billing')
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
          <Link
            href="/billing"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
            style={{
              backgroundColor: isActive('/billing') ? 'var(--primary)' : 'transparent',
              color: isActive('/billing') ? 'var(--primary-foreground)' : 'var(--warm-charcoal)',
              fontSize: '0.925em',
              fontWeight: 500
            }}
          >
            <CreditCard className="w-5 h-5" />
            Billing
          </Link>
        </div>
      </div>
    </aside>
  );
}
