'use client';

import { useState, useEffect, useCallback } from 'react';
import { Users, Download, Wifi, BookOpen, FileText, ArrowUpDown } from 'lucide-react';
import {
  getAdminUsers,
  type AdminUser,
  type AdminUsersResponse,
} from '@/lib/api';

interface AdminUsersTabProps {
  getAuthToken: () => Promise<string | null>;
}

type SortField = 'created_at' | 'email' | 'onboarding_state';
type SortDir = 'asc' | 'desc';

function timeAgo(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function MilestoneCell({ date }: { date: string | null }) {
  if (!date) {
    return (
      <span style={{ color: 'var(--warm-gray)', opacity: 0.4 }}>&mdash;</span>
    );
  }
  return (
    <span title={new Date(date).toLocaleString()} style={{ color: 'var(--sage-green)', fontSize: '0.8125rem' }}>
      &#10003; {timeAgo(date)}
    </span>
  );
}

function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, { bg: string; color: string }> = {
    free: { bg: 'var(--soft-cream)', color: 'var(--warm-gray)' },
    pro: { bg: 'var(--sage-green)', color: 'white' },
    enterprise: { bg: 'var(--terracotta)', color: 'white' },
  };
  const s = colors[tier] || colors.free;
  return (
    <span
      className="px-2 py-0.5 rounded-full text-xs font-medium capitalize"
      style={{ background: s.bg, color: s.color, border: tier === 'free' ? '1px solid var(--border)' : 'none' }}
    >
      {tier}
    </span>
  );
}

export default function AdminUsersTab({ getAuthToken }: AdminUsersTabProps) {
  const [data, setData] = useState<AdminUsersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<SortField>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [page, setPage] = useState(0);
  const pageSize = 50;

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const token = await getAuthToken();
      if (!token) return;

      const result = await getAdminUsers(token, page * pageSize, pageSize, sortBy, sortDir);
      setData(result);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, [getAuthToken, sortBy, sortDir, page]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const toggleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortDir('desc');
    }
    setPage(0);
  };

  const totalPages = data ? Math.ceil(data.total / pageSize) : 0;

  return (
    <div>
      {/* Stats */}
      {data?.stats && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
          {[
            { label: 'Total Users', value: data.stats.total_users, icon: Users, color: 'var(--warm-charcoal)' },
            { label: 'Agent DL\'d', value: data.stats.agent_downloaded, icon: Download, color: 'var(--amber-gold)' },
            { label: 'Connected', value: data.stats.agent_connected, icon: Wifi, color: 'var(--sage-green)' },
            { label: 'First Sync', value: data.stats.first_notebook_synced, icon: BookOpen, color: 'var(--sage-green)' },
            { label: 'OCR Done', value: data.stats.first_ocr_completed, icon: FileText, color: 'var(--sage-green)' },
            { label: 'Notion', value: data.stats.notion_connected, icon: () => <span style={{ fontSize: '1rem' }}>N</span>, color: 'var(--warm-charcoal)' },
          ].map(({ label, value, icon: Icon, color }) => (
            <div
              key={label}
              className="p-3 rounded-xl"
              style={{ background: 'var(--card)', border: '1px solid var(--border)' }}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <Icon className="w-3.5 h-3.5" style={{ color }} />
                <span className="text-xs" style={{ color: 'var(--warm-gray)' }}>{label}</span>
              </div>
              <span className="text-xl font-bold" style={{ color: 'var(--warm-charcoal)' }}>
                {value}
              </span>
            </div>
          ))}
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
          className="rounded-xl overflow-x-auto"
          style={{ background: 'var(--card)', border: '1px solid var(--border)' }}
        >
          <table className="w-full" style={{ minWidth: '900px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                {[
                  { label: 'Email', field: 'email' as SortField, sortable: true },
                  { label: 'Signed up', field: 'created_at' as SortField, sortable: true },
                  { label: 'Agent DL\'d', field: null, sortable: false },
                  { label: 'Connected', field: null, sortable: false },
                  { label: '1st Notebook', field: null, sortable: false },
                  { label: '1st OCR', field: null, sortable: false },
                  { label: 'Notion', field: null, sortable: false },
                  { label: 'Notebooks', field: null, sortable: false },
                  { label: 'Pages', field: null, sortable: false },
                  { label: 'Quota', field: null, sortable: false },
                  { label: 'Tier', field: null, sortable: false },
                  { label: 'Last active', field: null, sortable: false },
                ].map(({ label, field, sortable }) => (
                  <th
                    key={label}
                    className={`px-3 py-3 text-left text-xs font-semibold uppercase tracking-wider whitespace-nowrap ${sortable ? 'cursor-pointer select-none' : ''}`}
                    style={{ color: 'var(--warm-gray)' }}
                    onClick={sortable && field ? () => toggleSort(field) : undefined}
                  >
                    <span className="flex items-center gap-1">
                      {label}
                      {sortable && field && sortBy === field && (
                        <ArrowUpDown className="w-3 h-3" style={{ color: 'var(--terracotta)' }} />
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.users.map((user) => (
                <tr
                  key={user.id}
                  style={{ borderBottom: '1px solid var(--border)' }}
                >
                  <td className="px-3 py-2.5 text-sm" style={{ color: 'var(--warm-charcoal)' }}>
                    {user.email}
                  </td>
                  <td className="px-3 py-2.5 text-sm whitespace-nowrap" style={{ color: 'var(--warm-gray)' }} title={new Date(user.created_at).toLocaleString()}>
                    {timeAgo(user.created_at)}
                  </td>
                  <td className="px-3 py-2.5"><MilestoneCell date={user.agent_downloaded_at} /></td>
                  <td className="px-3 py-2.5"><MilestoneCell date={user.agent_first_connected_at} /></td>
                  <td className="px-3 py-2.5"><MilestoneCell date={user.first_notebook_synced_at} /></td>
                  <td className="px-3 py-2.5"><MilestoneCell date={user.first_ocr_completed_at} /></td>
                  <td className="px-3 py-2.5"><MilestoneCell date={user.notion_connected_at} /></td>
                  <td className="px-3 py-2.5 text-sm text-center" style={{ color: 'var(--warm-charcoal)' }}>
                    {user.notebook_count}
                  </td>
                  <td className="px-3 py-2.5 text-sm text-center" style={{ color: 'var(--warm-charcoal)' }}>
                    {user.page_count}
                  </td>
                  <td className="px-3 py-2.5 text-sm whitespace-nowrap" style={{ color: 'var(--warm-gray)' }}>
                    {user.quota_used}/{user.quota_limit}
                  </td>
                  <td className="px-3 py-2.5">
                    <TierBadge tier={user.subscription_tier} />
                  </td>
                  <td className="px-3 py-2.5 text-sm whitespace-nowrap" style={{ color: 'var(--warm-gray)' }} title={user.last_active_at ? new Date(user.last_active_at).toLocaleString() : ''}>
                    {user.last_active_at ? timeAgo(user.last_active_at) : '\u2014'}
                  </td>
                </tr>
              ))}
              {data.users.length === 0 && (
                <tr>
                  <td
                    colSpan={12}
                    className="px-4 py-12 text-center text-sm"
                    style={{ color: 'var(--warm-gray)' }}
                  >
                    <Users className="w-8 h-8 mx-auto mb-2" style={{ color: 'var(--border)' }} />
                    No users found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-sm" style={{ color: 'var(--warm-gray)' }}>
            Showing {page * pageSize + 1}&ndash;{Math.min((page + 1) * pageSize, data?.total || 0)} of {data?.total}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 rounded-lg text-sm"
              style={{
                background: 'var(--card)',
                color: page === 0 ? 'var(--warm-gray)' : 'var(--warm-charcoal)',
                border: '1px solid var(--border)',
                opacity: page === 0 ? 0.5 : 1,
              }}
            >
              Previous
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 rounded-lg text-sm"
              style={{
                background: 'var(--card)',
                color: page >= totalPages - 1 ? 'var(--warm-gray)' : 'var(--warm-charcoal)',
                border: '1px solid var(--border)',
                opacity: page >= totalPages - 1 ? 0.5 : 1,
              }}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
