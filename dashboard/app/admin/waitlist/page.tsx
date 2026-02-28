'use client';

import { useAuth, useUser } from '@clerk/nextjs';
import { useState, useEffect, useCallback } from 'react';
import { Check, AlertCircle, Users, Clock, UserCheck, ChevronLeft, ClipboardList } from 'lucide-react';
import Link from 'next/link';
import {
  getWaitlistAdmin,
  approveWaitlistEntry,
  approveWaitlistBulk,
  type WaitlistEntry,
  type WaitlistAdminResponse,
} from '@/lib/api';
import AdminUsersTab from './AdminUsersTab';

const ADMIN_USER_IDS = (process.env.NEXT_PUBLIC_ADMIN_USER_IDS || '').split(',').map(s => s.trim()).filter(Boolean);

type AdminTab = 'users' | 'waitlist';
type StatusFilter = 'all' | 'pending' | 'approved' | 'claimed';

export default function AdminPage() {
  const { getToken, userId, isSignedIn } = useAuth();
  const { isLoaded } = useUser();

  // Development mode bypass — only works on localhost, backend still enforces auth
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true'
    && typeof window !== 'undefined' && window.location.hostname === 'localhost';

  const [activeTab, setActiveTab] = useState<AdminTab>('users');
  const [data, setData] = useState<WaitlistAdminResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [approving, setApproving] = useState<Set<number>>(new Set());
  const [bulkApproving, setBulkApproving] = useState(false);

  // In dev mode, trust the admin check since Clerk may not return userId
  const isAdmin = isDevelopmentMode || (isLoaded && userId && ADMIN_USER_IDS.includes(userId));

  const getAuthToken = useCallback(async (): Promise<string | null> => {
    if (isDevelopmentMode) {
      return process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || '';
    }
    return await getToken();
  }, [isDevelopmentMode, getToken]);

  const fetchWaitlistData = useCallback(async () => {
    try {
      const token = await getAuthToken();
      if (!token) return;

      const result = await getWaitlistAdmin(
        token,
        filter === 'all' ? undefined : filter
      );
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [getAuthToken, filter]);

  useEffect(() => {
    if (isAdmin && activeTab === 'waitlist') {
      setLoading(true);
      fetchWaitlistData();
    } else if (isLoaded) {
      setLoading(false);
    }
  }, [isAdmin, isLoaded, fetchWaitlistData, activeTab]);

  const handleApprove = async (entryId: number) => {
    setApproving(prev => new Set(prev).add(entryId));
    try {
      const token = await getAuthToken();
      if (!token) return;
      await approveWaitlistEntry(token, entryId);
      await fetchWaitlistData();
      setSelected(prev => {
        const next = new Set(prev);
        next.delete(entryId);
        return next;
      });
    } catch (err) {
      console.error('Approve failed:', err);
    } finally {
      setApproving(prev => {
        const next = new Set(prev);
        next.delete(entryId);
        return next;
      });
    }
  };

  const handleBulkApprove = async () => {
    if (selected.size === 0) return;
    setBulkApproving(true);
    try {
      const token = await getAuthToken();
      if (!token) return;
      await approveWaitlistBulk(token, Array.from(selected));
      setSelected(new Set());
      await fetchWaitlistData();
    } catch (err) {
      console.error('Bulk approve failed:', err);
    } finally {
      setBulkApproving(false);
    }
  };

  const toggleSelect = (id: number) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (!data) return;
    const pendingIds = data.entries
      .filter(e => e.status === 'pending')
      .map(e => e.id);

    if (pendingIds.every(id => selected.has(id))) {
      setSelected(new Set());
    } else {
      setSelected(new Set(pendingIds));
    }
  };

  // Access denied
  if (isLoaded && !isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--background)' }}>
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto mb-4" style={{ color: 'var(--terracotta)' }} />
          <h1 className="text-xl font-bold mb-2" style={{ color: 'var(--warm-charcoal)' }}>
            Access Denied
          </h1>
          <p style={{ color: 'var(--warm-gray)' }}>Admin access required.</p>
          <Link
            href="/dashboard"
            className="inline-block mt-4 px-4 py-2 rounded-lg text-sm font-medium"
            style={{ background: 'var(--soft-cream)', color: 'var(--warm-charcoal)', border: '1px solid var(--border)' }}
          >
            Back to Dashboard
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Link
            href="/dashboard"
            className="p-2 rounded-lg transition-colors"
            style={{ color: 'var(--warm-gray)' }}
          >
            <ChevronLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold" style={{ color: 'var(--warm-charcoal)' }}>
              Admin
            </h1>
            <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
              User management &amp; beta access
            </p>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex gap-1 mb-8 p-1 rounded-lg" style={{ background: 'var(--soft-cream)', border: '1px solid var(--border)', display: 'inline-flex' }}>
          {([
            { key: 'users' as AdminTab, label: 'Users', icon: Users },
            { key: 'waitlist' as AdminTab, label: 'Waitlist', icon: ClipboardList },
          ]).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className="flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors"
              style={{
                background: activeTab === key ? 'var(--card)' : 'transparent',
                color: activeTab === key ? 'var(--warm-charcoal)' : 'var(--warm-gray)',
                boxShadow: activeTab === key ? '0 1px 2px rgba(0,0,0,0.05)' : 'none',
              }}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {/* Users tab */}
        {activeTab === 'users' && (
          <AdminUsersTab getAuthToken={getAuthToken} />
        )}

        {/* Waitlist tab */}
        {activeTab === 'waitlist' && (
          <>
            {/* Stats */}
            {data?.stats && (
              <div className="grid grid-cols-3 gap-4 mb-8">
                {[
                  { label: 'Pending', value: data.stats.pending, icon: Clock, color: 'var(--amber-gold)' },
                  { label: 'Approved', value: data.stats.approved, icon: Check, color: 'var(--sage-green)' },
                  { label: 'Signed Up', value: data.stats.claimed, icon: UserCheck, color: 'var(--terracotta)' },
                ].map(({ label, value, icon: Icon, color }) => (
                  <div
                    key={label}
                    className="p-4 rounded-xl"
                    style={{ background: 'var(--card)', border: '1px solid var(--border)' }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Icon className="w-4 h-4" style={{ color }} />
                      <span className="text-sm" style={{ color: 'var(--warm-gray)' }}>{label}</span>
                    </div>
                    <span className="text-2xl font-bold" style={{ color: 'var(--warm-charcoal)' }}>
                      {value}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Filter tabs */}
            <div className="flex gap-2 mb-6">
              {(['all', 'pending', 'approved', 'claimed'] as StatusFilter[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => { setFilter(tab); setSelected(new Set()); }}
                  className="px-4 py-2 rounded-lg text-sm font-medium transition-colors capitalize"
                  style={{
                    background: filter === tab ? 'var(--primary)' : 'var(--card)',
                    color: filter === tab ? 'var(--primary-foreground)' : 'var(--warm-charcoal)',
                    border: filter === tab ? 'none' : '1px solid var(--border)',
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Bulk actions */}
            {selected.size > 0 && (
              <div
                className="flex items-center gap-4 mb-4 p-3 rounded-lg"
                style={{ background: 'var(--soft-cream)', border: '1px solid var(--border)' }}
              >
                <span className="text-sm font-medium" style={{ color: 'var(--warm-charcoal)' }}>
                  {selected.size} selected
                </span>
                <button
                  onClick={handleBulkApprove}
                  disabled={bulkApproving}
                  className="px-4 py-1.5 rounded-lg text-sm font-medium transition-colors"
                  style={{
                    background: 'var(--terracotta)',
                    color: 'white',
                    opacity: bulkApproving ? 0.6 : 1,
                  }}
                >
                  {bulkApproving ? 'Approving...' : 'Approve Selected'}
                </button>
                <button
                  onClick={() => setSelected(new Set())}
                  className="text-sm"
                  style={{ color: 'var(--warm-gray)' }}
                >
                  Clear
                </button>
              </div>
            )}

            {/* Loading */}
            {loading && (
              <div className="text-center py-12" style={{ color: 'var(--warm-gray)' }}>
                Loading...
              </div>
            )}

            {/* Error */}
            {error && (
              <div
                className="p-4 rounded-lg mb-4"
                style={{ background: 'var(--soft-cream)', border: '1px solid var(--terracotta)', color: 'var(--terracotta)' }}
              >
                {error}
              </div>
            )}

            {/* Table */}
            {data && !loading && (
              <div
                className="rounded-xl overflow-hidden"
                style={{ background: 'var(--card)', border: '1px solid var(--border)' }}
              >
                <table className="w-full">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border)' }}>
                      {(filter === 'all' || filter === 'pending') && (
                        <th className="w-10 px-4 py-3 text-left">
                          <input
                            type="checkbox"
                            onChange={toggleSelectAll}
                            checked={
                              data.entries.filter(e => e.status === 'pending').length > 0 &&
                              data.entries.filter(e => e.status === 'pending').every(e => selected.has(e.id))
                            }
                          />
                        </th>
                      )}
                      <th
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                        style={{ color: 'var(--warm-gray)' }}
                      >
                        Email
                      </th>
                      <th
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                        style={{ color: 'var(--warm-gray)' }}
                      >
                        Name
                      </th>
                      <th
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                        style={{ color: 'var(--warm-gray)' }}
                      >
                        Requested
                      </th>
                      <th
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                        style={{ color: 'var(--warm-gray)' }}
                      >
                        Status
                      </th>
                      <th
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider"
                        style={{ color: 'var(--warm-gray)' }}
                      >
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.entries.map((entry) => (
                      <tr
                        key={entry.id}
                        style={{ borderBottom: '1px solid var(--border)' }}
                      >
                        {(filter === 'all' || filter === 'pending') && (
                          <td className="px-4 py-3">
                            {entry.status === 'pending' && (
                              <input
                                type="checkbox"
                                checked={selected.has(entry.id)}
                                onChange={() => toggleSelect(entry.id)}
                              />
                            )}
                          </td>
                        )}
                        <td className="px-4 py-3 text-sm" style={{ color: 'var(--warm-charcoal)' }}>
                          {entry.email}
                        </td>
                        <td className="px-4 py-3 text-sm" style={{ color: 'var(--warm-gray)' }}>
                          {entry.name || '-'}
                        </td>
                        <td className="px-4 py-3 text-sm" style={{ color: 'var(--warm-gray)' }}>
                          {new Date(entry.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={entry.status} date={entry.approved_at || entry.claimed_at} />
                        </td>
                        <td className="px-4 py-3">
                          {entry.status === 'pending' && (
                            <button
                              onClick={() => handleApprove(entry.id)}
                              disabled={approving.has(entry.id)}
                              className="px-3 py-1 rounded-md text-xs font-medium transition-colors"
                              style={{
                                background: 'var(--terracotta)',
                                color: 'white',
                                opacity: approving.has(entry.id) ? 0.6 : 1,
                              }}
                            >
                              {approving.has(entry.id) ? 'Sending...' : 'Approve'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {data.entries.length === 0 && (
                      <tr>
                        <td
                          colSpan={6}
                          className="px-4 py-12 text-center text-sm"
                          style={{ color: 'var(--warm-gray)' }}
                        >
                          <Users className="w-8 h-8 mx-auto mb-2" style={{ color: 'var(--border)' }} />
                          No entries found
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status, date }: { status: string; date?: string | null }) {
  const styles: Record<string, { bg: string; color: string; label: string }> = {
    pending: { bg: 'var(--amber-gold)', color: 'white', label: 'Pending' },
    approved: { bg: 'var(--sage-green)', color: 'white', label: 'Invited' },
    claimed: { bg: 'var(--terracotta)', color: 'white', label: 'Signed Up' },
  };

  const s = styles[status] || styles.pending;

  return (
    <div className="flex items-center gap-2">
      <span
        className="px-2 py-0.5 rounded-full text-xs font-medium"
        style={{ background: s.bg, color: s.color }}
      >
        {s.label}
      </span>
      {date && (
        <span className="text-xs" style={{ color: 'var(--warm-gray)' }}>
          {new Date(date).toLocaleDateString()}
        </span>
      )}
    </div>
  );
}
