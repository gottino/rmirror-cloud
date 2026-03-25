'use client';

import { useEffect, useState } from 'react';
import { X, Trash2, Loader2, CheckCircle } from 'lucide-react';
import { deleteNotebook, type DeleteNotebookResponse } from '@/lib/api';

interface DeleteNotebookModalProps {
  isOpen: boolean;
  onClose: () => void;
  notebook: {
    id: number;
    visible_name: string;
    page_count: number;
  } | null;
  hasNotion: boolean;
  token: string;
  onDeleted: () => void;
}

export function DeleteNotebookModal({
  isOpen,
  onClose,
  notebook,
  hasNotion,
  token,
  onDeleted,
}: DeleteNotebookModalProps) {
  const [cleanupNotion, setCleanupNotion] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [result, setResult] = useState<DeleteNotebookResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setCleanupNotion(false);
      setDeleting(false);
      setResult(null);
      setError(null);
    }
  }, [isOpen]);

  // Close on Escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !deleting) onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose, deleting]);

  if (!isOpen || !notebook) return null;

  const handleDelete = async () => {
    setDeleting(true);
    setError(null);
    try {
      const res = await deleteNotebook(token, notebook.id, cleanupNotion);
      setResult(res);
      // Auto-close after showing success
      setTimeout(() => {
        onDeleted();
        onClose();
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete notebook');
      setDeleting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: 'rgba(0, 0, 0, 0.5)' }}
      onClick={!deleting ? onClose : undefined}
    >
      <div
        className="relative max-w-md w-full rounded-lg shadow-2xl overflow-hidden"
        style={{ backgroundColor: 'var(--card)' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close button */}
        {!deleting && (
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 rounded-lg hover:bg-black/5 transition-colors z-10"
            style={{ color: 'var(--warm-gray)' }}
          >
            <X className="w-5 h-5" />
          </button>
        )}

        {result ? (
          /* Success state */
          <div className="p-8 text-center">
            <CheckCircle
              className="w-12 h-12 mx-auto mb-4"
              style={{ color: 'var(--sage-green)' }}
            />
            <h2
              style={{
                fontSize: '1.25rem',
                fontWeight: 600,
                color: 'var(--warm-charcoal)',
                marginBottom: '0.75rem',
              }}
            >
              Notebook Deleted
            </h2>
            <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)' }}>
              {result.pages_deleted} pages removed, {result.sync_records_deleted} sync records cleaned up
            </p>
          </div>
        ) : (
          /* Confirmation state */
          <>
            {/* Header */}
            <div className="p-6 pb-0">
              <div
                className="w-12 h-12 rounded-full flex items-center justify-center mb-4"
                style={{ backgroundColor: 'rgba(200, 90, 84, 0.1)' }}
              >
                <Trash2 className="w-6 h-6" style={{ color: 'var(--terracotta)' }} />
              </div>
              <h2
                style={{
                  fontSize: '1.25rem',
                  fontWeight: 600,
                  color: 'var(--warm-charcoal)',
                  marginBottom: '0.5rem',
                }}
              >
                Delete &ldquo;{notebook.visible_name}&rdquo;?
              </h2>
            </div>

            {/* Content */}
            <div className="px-6 py-4">
              <p
                style={{
                  fontSize: '0.875em',
                  color: 'var(--warm-gray)',
                  marginBottom: '1rem',
                  lineHeight: 1.6,
                }}
              >
                This will permanently delete:
              </p>
              <ul
                style={{
                  fontSize: '0.875em',
                  color: 'var(--warm-charcoal)',
                  paddingLeft: '1.25rem',
                  marginBottom: '1rem',
                  lineHeight: 1.8,
                }}
              >
                <li>{notebook.page_count} pages with OCR text</li>
                <li>All generated PDFs</li>
                <li>Sync history to integrations</li>
              </ul>
              <div
                className="p-3 rounded-lg"
                style={{
                  backgroundColor: 'var(--soft-cream)',
                  border: '1px solid var(--border)',
                  fontSize: '0.825em',
                  color: 'var(--warm-gray)',
                  lineHeight: 1.5,
                }}
              >
                You can re-sync this notebook from your reMarkable, but OCR quota will be consumed again.
              </div>

              {/* Notion checkbox */}
              {hasNotion && (
                <label
                  className="flex items-center gap-2 mt-4 cursor-pointer"
                  style={{ fontSize: '0.875em', color: 'var(--warm-charcoal)' }}
                >
                  <input
                    type="checkbox"
                    checked={cleanupNotion}
                    onChange={(e) => setCleanupNotion(e.target.checked)}
                    className="rounded"
                    style={{ accentColor: 'var(--terracotta)' }}
                  />
                  Also remove from Notion
                </label>
              )}

              {error && (
                <p
                  className="mt-3"
                  style={{ fontSize: '0.825em', color: 'var(--destructive)' }}
                >
                  {error}
                </p>
              )}
            </div>

            {/* Actions */}
            <div
              className="flex gap-3 justify-end p-6 pt-2"
            >
              <button
                onClick={onClose}
                disabled={deleting}
                className="px-4 py-2 rounded-lg transition-colors"
                style={{
                  fontSize: '0.875em',
                  fontWeight: 500,
                  border: '1px solid var(--border)',
                  backgroundColor: 'var(--card)',
                  color: 'var(--warm-charcoal)',
                  cursor: deleting ? 'not-allowed' : 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
                style={{
                  fontSize: '0.875em',
                  fontWeight: 500,
                  backgroundColor: 'var(--terracotta)',
                  color: 'white',
                  border: 'none',
                  cursor: deleting ? 'not-allowed' : 'pointer',
                  opacity: deleting ? 0.7 : 1,
                }}
              >
                {deleting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  'Delete Permanently'
                )}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
