'use client';

import { useAuth, useUser } from '@clerk/nextjs';
import UserMenu from '@/components/UserMenu';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Settings, Download, Trash2, AlertTriangle, Menu, Loader2 } from 'lucide-react';
import Sidebar from '@/components/Sidebar';
import { trackEvent } from '@/lib/analytics';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

interface DataSummary {
  notebooks: number;
  pages: number;
  files: number;
  integrations: string[];
  member_since: string | null;
  subscription: string;
}

export default function SettingsPage() {
  const { getToken, isSignedIn, signOut } = useAuth();
  const { user: clerkUser } = useUser();
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dataSummary, setDataSummary] = useState<DataSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState('');
  const [deleteUnderstood, setDeleteUnderstood] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');

  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  const getAuthToken = async (): Promise<string> => {
    if (isDevelopmentMode) {
      return process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || '';
    }
    const token = await getToken();
    if (!token) throw new Error('Failed to get authentication token');
    return token;
  };

  useEffect(() => {
    const fetchSummary = async () => {
      if (!effectiveIsSignedIn) {
        setLoading(false);
        return;
      }

      try {
        const token = await getAuthToken();
        const response = await fetch(`${API_URL}/account/data-summary`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (response.ok) {
          const data = await response.json();
          setDataSummary(data);
        }
      } catch (err) {
        console.error('Error fetching data summary:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchSummary();
  }, [effectiveIsSignedIn]);

  const handleExport = async () => {
    setExporting(true);
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/account/export`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) {
        throw new Error('Export failed');
      }

      trackEvent({ name: 'data_exported' });
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = response.headers.get('Content-Disposition')?.match(/filename="(.+)"/)?.[1]
        || `rmirror-export-${new Date().toISOString().split('T')[0]}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export error:', err);
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteError('');
    try {
      const token = await getAuthToken();
      const response = await fetch(`${API_URL}/account`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ confirmation: deleteConfirmation }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || 'Deletion failed');
      }

      // Sign out and redirect to landing page
      if (signOut) {
        await signOut();
      }
      router.push('/?deleted=true');
    } catch (err: any) {
      setDeleteError(err.message || 'Failed to delete account');
    } finally {
      setDeleting(false);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Unknown';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const canDelete = deleteConfirmation === 'delete my account' && deleteUnderstood;

  return (
    <div className="flex h-screen overflow-hidden" style={{ backgroundColor: 'var(--background)' }}>
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <main className="flex-1 overflow-auto">
        {/* Header */}
        <header className="sticky top-0 z-30 border-b bg-white px-6 py-4" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 hover:bg-gray-100 rounded-lg"
              >
                <Menu className="w-5 h-5" />
              </button>
              <div>
                <h1 className="text-2xl font-semibold" style={{ color: 'var(--warm-charcoal)' }}>
                  Settings
                </h1>
                <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                  Manage your account and data
                </p>
              </div>
            </div>
            {isDevelopmentMode ? (
              <div style={{
                fontSize: '0.75em',
                color: 'var(--warm-gray)',
                padding: '0.5rem',
                backgroundColor: 'var(--soft-cream)',
                borderRadius: 'var(--radius)',
                border: '1px solid var(--border)',
              }}>
                DEV MODE
              </div>
            ) : (
              isSignedIn && <UserMenu />
            )}
          </div>
        </header>

        {/* Content */}
        <div className="p-6" style={{ backgroundColor: 'var(--soft-cream)' }}>
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto" style={{ borderColor: 'var(--terracotta)' }} />
              <p className="mt-4" style={{ color: 'var(--warm-gray)' }}>Loading settings...</p>
            </div>
          ) : (
            <div className="space-y-6 max-w-3xl mx-auto">
              {/* Account Information */}
              <div
                className="p-6 rounded-lg"
                style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-center gap-3 mb-4">
                  <Settings className="w-5 h-5" style={{ color: 'var(--warm-charcoal)' }} />
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
                    Account Information
                  </h2>
                </div>

                <div className="space-y-3">
                  <div className="flex justify-between items-center py-2 border-b" style={{ borderColor: 'var(--border)' }}>
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-gray)' }}>Email</span>
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)', fontWeight: 500 }}>
                      {clerkUser?.primaryEmailAddress?.emailAddress || 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b" style={{ borderColor: 'var(--border)' }}>
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-gray)' }}>Name</span>
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)', fontWeight: 500 }}>
                      {clerkUser?.fullName || 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b" style={{ borderColor: 'var(--border)' }}>
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-gray)' }}>Member since</span>
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)', fontWeight: 500 }}>
                      {formatDate(dataSummary?.member_since ?? null)}
                    </span>
                  </div>
                  <div className="flex justify-between items-center py-2">
                    <span style={{ fontSize: '0.925em', color: 'var(--warm-gray)' }}>Subscription</span>
                    <span
                      className="px-3 py-1 rounded-full"
                      style={{
                        fontSize: '0.75em',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        backgroundColor: 'var(--sage-green)',
                        color: 'white',
                      }}
                    >
                      {dataSummary?.subscription || 'free'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Data Export */}
              <div
                className="p-6 rounded-lg"
                style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-center gap-3 mb-4">
                  <Download className="w-5 h-5" style={{ color: 'var(--warm-charcoal)' }} />
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
                    Data Export
                  </h2>
                </div>

                <p className="mb-4" style={{ fontSize: '0.925em', color: 'var(--warm-gray)', lineHeight: 1.6 }}>
                  Download a ZIP file containing all your notebooks as PDFs and OCR text files,
                  plus account metadata. Your folder structure is preserved.
                </p>

                {dataSummary && (
                  <p className="mb-4" style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
                    Your export will include {dataSummary.notebooks} notebook{dataSummary.notebooks !== 1 ? 's' : ''} with {dataSummary.pages} page{dataSummary.pages !== 1 ? 's' : ''}.
                  </p>
                )}

                <button
                  onClick={handleExport}
                  disabled={exporting}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg transition-colors font-medium"
                  style={{
                    backgroundColor: 'var(--sage-green)',
                    color: 'white',
                    fontSize: '0.925em',
                    opacity: exporting ? 0.7 : 1,
                    cursor: exporting ? 'not-allowed' : 'pointer',
                  }}
                >
                  {exporting ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Generating export...
                    </>
                  ) : (
                    <>
                      <Download className="w-4 h-4" />
                      Download My Data
                    </>
                  )}
                </button>
              </div>

              {/* Danger Zone */}
              <div
                className="p-6 rounded-lg"
                style={{
                  backgroundColor: '#fef2f2',
                  border: '2px solid #fca5a5',
                }}
              >
                <div className="flex items-center gap-3 mb-4">
                  <AlertTriangle className="w-5 h-5" style={{ color: '#dc2626' }} />
                  <h2 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#dc2626' }}>
                    Danger Zone
                  </h2>
                </div>

                <p className="mb-2" style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)', lineHeight: 1.6 }}>
                  Permanently delete your account and all associated data. This action is
                  <strong> immediate and irreversible</strong>.
                </p>

                {dataSummary && (
                  <p className="mb-4" style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
                    This will delete {dataSummary.notebooks} notebook{dataSummary.notebooks !== 1 ? 's' : ''}, {dataSummary.pages} page{dataSummary.pages !== 1 ? 's' : ''}, {dataSummary.files} stored file{dataSummary.files !== 1 ? 's' : ''}
                    {dataSummary.integrations.length > 0 && (
                      <>, and disconnect {dataSummary.integrations.join(', ')} integration{dataSummary.integrations.length !== 1 ? 's' : ''}</>
                    )}
                    .
                  </p>
                )}

                <button
                  onClick={() => setShowDeleteModal(true)}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg transition-colors font-medium"
                  style={{
                    backgroundColor: '#dc2626',
                    color: 'white',
                    fontSize: '0.925em',
                  }}
                >
                  <Trash2 className="w-4 h-4" />
                  Delete Account
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Delete Confirmation Modal */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50">
          <div
            className="w-full max-w-md rounded-xl p-6"
            style={{ backgroundColor: 'var(--card)', boxShadow: 'var(--shadow-lg, 0 10px 25px rgba(0,0,0,0.15))' }}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ backgroundColor: '#fef2f2' }}>
                <AlertTriangle className="w-5 h-5" style={{ color: '#dc2626' }} />
              </div>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 600, color: 'var(--warm-charcoal)' }}>
                Delete your account?
              </h3>
            </div>

            {/* Download reminder */}
            <div
              className="p-3 rounded-lg mb-4 flex items-start gap-3"
              style={{ backgroundColor: '#fffbeb', border: '1px solid #fcd34d' }}
            >
              <Download className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#d97706' }} />
              <div>
                <p style={{ fontSize: '0.875em', color: '#92400e', fontWeight: 500, margin: 0 }}>
                  Download your data first
                </p>
                <button
                  onClick={() => {
                    setShowDeleteModal(false);
                    handleExport();
                  }}
                  style={{
                    fontSize: '0.8em',
                    color: '#d97706',
                    textDecoration: 'underline',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    padding: 0,
                  }}
                >
                  Export my data before deleting
                </button>
              </div>
            </div>

            <p className="mb-4" style={{ fontSize: '0.925em', color: 'var(--warm-gray)', lineHeight: 1.6 }}>
              All your notebooks, pages, files, and integration data will be
              permanently removed. Your Notion pages will <strong>not</strong> be affected.
            </p>

            {/* Confirmation input */}
            <div className="mb-4">
              <label
                style={{ fontSize: '0.875em', fontWeight: 500, color: 'var(--warm-charcoal)', display: 'block', marginBottom: '0.5rem' }}
              >
                Type <strong>delete my account</strong> to confirm:
              </label>
              <input
                type="text"
                value={deleteConfirmation}
                onChange={(e) => setDeleteConfirmation(e.target.value)}
                placeholder="delete my account"
                className="w-full px-4 py-2.5 rounded-lg"
                style={{
                  border: '1px solid var(--border)',
                  fontSize: '0.925em',
                  backgroundColor: 'var(--card)',
                  color: 'var(--foreground)',
                }}
              />
            </div>

            {/* Checkbox */}
            <label className="flex items-start gap-3 mb-4 cursor-pointer">
              <input
                type="checkbox"
                checked={deleteUnderstood}
                onChange={(e) => setDeleteUnderstood(e.target.checked)}
                className="mt-0.5"
                style={{ accentColor: '#dc2626' }}
              />
              <span style={{ fontSize: '0.875em', color: 'var(--warm-charcoal)' }}>
                I understand this action is permanent and cannot be undone
              </span>
            </label>

            {deleteError && (
              <div className="mb-4 p-3 rounded-lg" style={{ backgroundColor: '#fef2f2', border: '1px solid #fca5a5' }}>
                <p style={{ fontSize: '0.875em', color: '#dc2626', margin: 0 }}>{deleteError}</p>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeleteConfirmation('');
                  setDeleteUnderstood(false);
                  setDeleteError('');
                }}
                className="px-4 py-2.5 rounded-lg transition-colors"
                style={{
                  fontSize: '0.925em',
                  fontWeight: 500,
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--card)',
                  color: 'var(--warm-charcoal)',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={!canDelete || deleting}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg transition-colors"
                style={{
                  fontSize: '0.925em',
                  fontWeight: 600,
                  backgroundColor: canDelete && !deleting ? '#dc2626' : '#e5e7eb',
                  color: canDelete && !deleting ? 'white' : '#9ca3af',
                  cursor: canDelete && !deleting ? 'pointer' : 'not-allowed',
                }}
              >
                {deleting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  'Delete My Account Forever'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
