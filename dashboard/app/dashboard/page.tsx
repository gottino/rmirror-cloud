'use client';

import { useAuth, UserButton } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import Link from 'next/link';
import { Search, X, Grid3x3, List, ChevronRight, BookOpen, Puzzle, CreditCard, Menu, Home as HomeIcon, Folder } from 'lucide-react';
import { getNotebooksTree, trackAgentDownload, getAgentStatus, getQuotaStatus, type NotebookTree as NotebookTreeData, NotebookTreeNode, type AgentStatus, type QuotaStatus } from '@/lib/api';
import { QuotaWarning } from '@/components/QuotaWarning';
import { QuotaDisplay } from '@/components/QuotaDisplay';
import { QuotaExceededModal } from '@/components/QuotaExceededModal';

// Group notebooks by date
function groupNotebooksByDate(notebooks: NotebookTreeNode[]) {
  const now = new Date();
  const groups: Record<string, NotebookTreeNode[]> = {
    'Today': [],
    'Last Week': [],
    'Last Month': [],
    'Last Year': [],
    'Older': []
  };

  notebooks.forEach((notebook) => {
    if (!notebook.last_synced_at) {
      groups['Older'].push(notebook);
      return;
    }

    const syncedDate = new Date(notebook.last_synced_at);
    const diffInMs = now.getTime() - syncedDate.getTime();
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24));

    if (diffInDays === 0) {
      groups['Today'].push(notebook);
    } else if (diffInDays <= 7) {
      groups['Last Week'].push(notebook);
    } else if (diffInDays <= 30) {
      groups['Last Month'].push(notebook);
    } else if (diffInDays <= 365) {
      groups['Last Year'].push(notebook);
    } else {
      groups['Older'].push(notebook);
    }
  });

  return groups;
}

// Check if a folder contains any notebooks in its hierarchy
function folderHasNotebooks(node: NotebookTreeNode): boolean {
  // If this is a notebook itself
  if (!node.is_folder && node.document_type === 'notebook') {
    return true;
  }

  // Check children recursively
  if (node.children && node.children.length > 0) {
    return node.children.some(child => folderHasNotebooks(child));
  }

  return false;
}

// Get all notebooks from a node and its descendants
function getNotebooksFromNode(node: NotebookTreeNode): NotebookTreeNode[] {
  const results: NotebookTreeNode[] = [];

  if (!node.is_folder && node.document_type === 'notebook') {
    results.push(node);
  }

  if (node.children && node.children.length > 0) {
    for (const child of node.children) {
      results.push(...getNotebooksFromNode(child));
    }
  }

  return results;
}

// Get all notebooks from an array of nodes
function getAllNotebooks(nodes: NotebookTreeNode[]): NotebookTreeNode[] {
  const results: NotebookTreeNode[] = [];
  for (const node of nodes) {
    results.push(...getNotebooksFromNode(node));
  }
  return results;
}

// Get folders at a specific level that contain notebooks
function getFoldersWithNotebooks(nodes: NotebookTreeNode[]): NotebookTreeNode[] {
  return nodes.filter(node => node.is_folder && folderHasNotebooks(node));
}

// Find a node by UUID in the tree
function findNodeByUuid(nodes: NotebookTreeNode[], uuid: string): NotebookTreeNode | null {
  for (const node of nodes) {
    if (node.notebook_uuid === uuid) {
      return node;
    }
    if (node.children && node.children.length > 0) {
      const found = findNodeByUuid(node.children, uuid);
      if (found) return found;
    }
  }
  return null;
}

export default function Home() {
  const { getToken, isSignedIn } = useAuth();
  const router = useRouter();
  const [tree, setTree] = useState<NotebookTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [currentFolderPath, setCurrentFolderPath] = useState<string[]>([]); // Array of folder UUIDs
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  const [showQuotaModal, setShowQuotaModal] = useState(false);

  // Development mode bypass
  const isDevelopmentMode = process.env.NEXT_PUBLIC_DEV_MODE === 'true';
  const effectiveIsSignedIn = isDevelopmentMode || isSignedIn;

  const handleDownloadClick = async () => {
    if (effectiveIsSignedIn) {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (token) {
        await trackAgentDownload(token);
      }
    }
    window.location.href = 'https://f000.backblazeb2.com/file/rmirror-downloads/releases/v1.4.0/rMirror-1.4.0.dmg';
  };

  const fetchNotebooks = async () => {
    if (!effectiveIsSignedIn) {
      setLoading(false);
      return;
    }

    try {
      setError(null);
      // In dev mode, get JWT token from env var or localStorage
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) {
        throw new Error('Failed to get authentication token');
      }

      const data = await getNotebooksTree(token);
      setTree(data.tree);
    } catch (err) {
      console.error('Error fetching notebooks:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch notebooks');
    } finally {
      setLoading(false);
    }
  };

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

  const fetchQuota = async () => {
    if (!effectiveIsSignedIn) return;

    try {
      const token = isDevelopmentMode
        ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
        : await getToken();
      if (!token) return;

      const quotaData = await getQuotaStatus(token);
      setQuota(quotaData);
    } catch (err) {
      console.error('Error fetching quota:', err);
    }
  };

  useEffect(() => {
    fetchNotebooks();
    fetchAgentStatus();
    fetchQuota();
  }, [effectiveIsSignedIn]);

  // Get current folder node and its contents
  const getCurrentFolderNode = (): NotebookTreeNode[] => {
    if (currentFolderPath.length === 0) {
      // At root level
      return tree;
    }

    // Navigate to current folder
    let currentNodes = tree;
    for (const folderUuid of currentFolderPath) {
      const found = findNodeByUuid(currentNodes, folderUuid);
      if (found && found.children) {
        currentNodes = found.children;
      } else {
        return [];
      }
    }
    return currentNodes;
  };

  const currentNode = getCurrentFolderNode();

  // Get all notebooks in current scope (current folder + all subfolders)
  const notebooks = getAllNotebooks(currentNode);

  // Get folders at current level that contain notebooks
  const currentFolders = getFoldersWithNotebooks(currentNode);

  // Filter notebooks by search query
  const filteredNotebooks = notebooks.filter((notebook) =>
    notebook.visible_name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const groupedNotebooks = groupNotebooksByDate(filteredNotebooks);

  // Build breadcrumb path
  const breadcrumbs: { name: string; uuid: string | null }[] = [{ name: 'Home', uuid: null }];
  if (currentFolderPath.length > 0) {
    let currentNodes = tree;
    for (const folderUuid of currentFolderPath) {
      const found = findNodeByUuid(currentNodes, folderUuid);
      if (found) {
        breadcrumbs.push({ name: found.visible_name, uuid: found.notebook_uuid });
        if (found.children) {
          currentNodes = found.children;
        }
      }
    }
  }

  // Sidebar
  const Sidebar = () => (
    <>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-50
          w-64 border-r flex flex-col h-screen
          transform transition-transform duration-200 ease-in-out
          lg:transform-none
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--card)' }}
      >
        {/* Logo */}
        <div className="p-6 border-b" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Image src="/rm-icon.png" alt="rMirror" width={32} height={32} style={{ marginRight: '8px', marginTop: '3px'}} />
              <h1 style={{ fontSize: '1.375rem', fontWeight: 600, color: 'var(--warm-charcoal)', margin: 0 }}>rMirror</h1>
            </div>
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden p-2"
              style={{ color: 'var(--warm-gray)' }}
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <p style={{ fontSize: '0.875em', color: 'var(--warm-gray)', marginTop: '0.25rem' }}>Cloud Sync</p>
        </div>

      {/* Folder Navigation */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Home button - always visible */}
        <div className="p-4 border-b" style={{ borderColor: 'var(--border)' }}>
          <button
            onClick={() => setCurrentFolderPath([])}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all"
            style={{
              backgroundColor: currentFolderPath.length === 0 ? 'var(--primary)' : 'transparent',
              color: currentFolderPath.length === 0 ? 'var(--primary-foreground)' : 'var(--warm-charcoal)',
              fontSize: '0.925em',
              fontWeight: 500
            }}
          >
            <HomeIcon className="w-5 h-5" />
            All Notebooks
          </button>
        </div>

        {/* Breadcrumbs */}
        {breadcrumbs.length > 1 && (
          <div className="px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center flex-wrap gap-1" style={{ fontSize: '0.8em', color: 'var(--warm-gray)' }}>
              {breadcrumbs.map((crumb, index) => (
                <div key={index} className="flex items-center gap-1">
                  {index > 0 && <ChevronRight className="w-3 h-3" />}
                  <button
                    onClick={() => {
                      if (crumb.uuid === null) {
                        setCurrentFolderPath([]);
                      } else {
                        setCurrentFolderPath(currentFolderPath.slice(0, index));
                      }
                    }}
                    className="hover:opacity-60 transition-opacity"
                    style={{
                      color: index === breadcrumbs.length - 1 ? 'var(--terracotta)' : 'var(--warm-gray)',
                      fontWeight: index === breadcrumbs.length - 1 ? 500 : 400
                    }}
                  >
                    {crumb.name}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Folder list */}
        <div className="flex-1 overflow-y-auto p-4">
          {currentFolders.length > 0 ? (
            <div className="space-y-1">
              <div style={{ fontSize: '0.7em', fontWeight: 600, color: 'var(--warm-gray)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.5rem', paddingLeft: '0.75rem' }}>
                Folders
              </div>
              {currentFolders.map((folder) => {
                const notebookCount = getNotebooksFromNode(folder).length;
                return (
                  <button
                    key={folder.notebook_uuid}
                    onClick={() => setCurrentFolderPath([...currentFolderPath, folder.notebook_uuid])}
                    className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-all hover:bg-[var(--soft-cream)] group"
                    style={{
                      fontSize: '0.925em',
                      fontWeight: 500,
                      color: 'var(--warm-charcoal)'
                    }}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <Folder className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--terracotta)' }} />
                      <span className="truncate">{folder.visible_name}</span>
                    </div>
                    <span style={{ fontSize: '0.75em', color: 'var(--warm-gray)' }}>
                      {notebookCount}
                    </span>
                  </button>
                );
              })}
            </div>
          ) : currentFolderPath.length > 0 ? (
            <div className="text-center py-8" style={{ color: 'var(--warm-gray)', fontSize: '0.875em' }}>
              No subfolders
            </div>
          ) : null}
        </div>

        {/* Integrations and Billing links */}
        <div className="border-t p-4 space-y-1" style={{ borderColor: 'var(--border)' }}>
          <Link
            href="/integrations"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all hover:bg-[var(--soft-cream)]"
            style={{
              color: 'var(--warm-charcoal)',
              fontSize: '0.925em',
              fontWeight: 500
            }}
          >
            <Puzzle className="w-5 h-5" />
            Integrations
          </Link>
          <Link
            href="/billing"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all hover:bg-[var(--soft-cream)]"
            style={{
              color: 'var(--warm-charcoal)',
              fontSize: '0.925em',
              fontWeight: 500
            }}
          >
            <CreditCard className="w-5 h-5" />
            Billing
          </Link>
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
    </>
  );


  if (loading) {
    return (
      <div className="flex h-screen">
        <Sidebar />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 mx-auto" style={{ borderColor: 'var(--terracotta)' }}></div>
            <p className="mt-4" style={{ color: 'var(--warm-gray)' }}>Loading notebooks...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-screen">
        <Sidebar />
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="text-center max-w-md">
            <div style={{ color: 'var(--destructive)', fontSize: '3rem', marginBottom: '1rem' }}>✗</div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>Error</h2>
            <p style={{ color: 'var(--warm-gray)', marginBottom: '1.5rem' }}>{error}</p>
            <button
              onClick={() => fetchNotebooks()}
              className="px-6 py-2 rounded-lg transition-colors"
              style={{
                backgroundColor: 'var(--primary)',
                color: 'var(--primary-foreground)'
              }}
            >
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Quota Warning Banner */}
        <QuotaWarning onUpgradeClick={() => setShowQuotaModal(true)} />

        {/* Header */}
        <header className="bg-white shadow-sm sticky top-0 z-30" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="max-w-full mx-auto px-6 lg:px-8 py-4">
            <div className="flex items-center justify-between gap-4">
              {/* Hamburger menu button for mobile */}
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 -ml-2"
                style={{ color: 'var(--warm-charcoal)' }}
              >
                <Menu className="w-6 h-6" />
              </button>

              <div className="flex-1 max-w-md">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5" style={{ color: 'var(--warm-gray)' }} />
                  <input
                    type="text"
                    placeholder="Search notebooks..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-10 pr-10 py-2 rounded-lg"
                    style={{
                      border: '1px solid var(--border)',
                      fontSize: '0.925em',
                      backgroundColor: 'var(--card)',
                      color: 'var(--foreground)'
                    }}
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery('')}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2"
                      style={{ color: 'var(--warm-gray)' }}
                    >
                      <X className="w-5 h-5" />
                    </button>
                  )}
                </div>
              </div>

              <div className="flex items-center space-x-4">
                {/* Quota Display */}
                <QuotaDisplay variant="compact" onQuotaExceeded={() => setShowQuotaModal(true)} />

                {isDevelopmentMode ? (
                  <div style={{
                    fontSize: '0.75em',
                    color: 'var(--warm-gray)',
                    padding: '0.5rem',
                    backgroundColor: 'var(--soft-cream)',
                    borderRadius: 'var(--radius)',
                    border: '1px solid var(--border)'
                  }}>
                    DEV MODE
                  </div>
                ) : (
                  isSignedIn && <UserButton afterSignOutUrl="/" />
                )}
              </div>
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto px-6 lg:px-8 py-8">
          {notebooks.length === 0 ? (
            <div className="text-center py-12 rounded-lg max-w-2xl mx-auto" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
              <BookOpen className="w-20 h-20 mx-auto mb-4" style={{ color: 'var(--warm-gray)', opacity: 0.3 }} />
              <h3 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                No notebooks yet
              </h3>
              <p style={{ color: 'var(--warm-gray)', marginBottom: '1.5rem' }}>
                Download and install the rMirror Agent to sync your reMarkable notebooks.
                <br />
                <span style={{ fontSize: '0.875em' }}>Free tier includes 30 pages of OCR transcription per month</span>
              </p>
              <button
                onClick={handleDownloadClick}
                className="px-6 py-3 rounded-lg transition-colors font-semibold cursor-pointer"
                style={{
                  backgroundColor: 'var(--primary)',
                  color: 'var(--primary-foreground)'
                }}
              >
                Download rMirror Agent for macOS
              </button>
            </div>
          ) : (
            <>
              {/* View toggle */}
              <div className="flex items-center justify-between mb-6">
                <h2 style={{ fontSize: '1.5rem', fontWeight: 600, margin: 0 }}>
                  {currentFolderPath.length > 0 ? breadcrumbs[breadcrumbs.length - 1].name : 'All Notebooks'}
                </h2>
                <div className="flex gap-2">
                  <button
                    onClick={() => setViewMode('list')}
                    className="px-3 py-2 rounded-lg flex items-center gap-2 transition-all"
                    style={{
                      backgroundColor: viewMode === 'list' ? 'var(--primary)' : 'transparent',
                      color: viewMode === 'list' ? 'var(--primary-foreground)' : 'var(--warm-gray)',
                      border: '1px solid var(--border)'
                    }}
                  >
                    <List className="w-4 h-4" />
                    <span style={{ fontSize: '0.875em' }}>List</span>
                  </button>
                  <button
                    onClick={() => setViewMode('grid')}
                    className="px-3 py-2 rounded-lg flex items-center gap-2 transition-all"
                    style={{
                      backgroundColor: viewMode === 'grid' ? 'var(--primary)' : 'transparent',
                      color: viewMode === 'grid' ? 'var(--primary-foreground)' : 'var(--warm-gray)',
                      border: '1px solid var(--border)'
                    }}
                  >
                    <Grid3x3 className="w-4 h-4" />
                    <span style={{ fontSize: '0.875em' }}>Grid</span>
                  </button>
                </div>
              </div>

              {/* Notebooks by date group */}
              <div className="space-y-8">
                {Object.entries(groupedNotebooks).map(([groupName, groupNotebooks]) => {
                  if (groupNotebooks.length === 0) return null;

                  return (
                    <div key={groupName}>
                      <h3 style={{
                        fontSize: '0.8em',
                        fontWeight: 600,
                        color: 'var(--warm-gray)',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        marginBottom: '1rem',
                        paddingLeft: '0.75rem'
                      }}>
                        {groupName}
                      </h3>

                      {viewMode === 'grid' ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-5">
                          {groupNotebooks.map((notebook) => (
                            <Link
                              key={notebook.notebook_uuid}
                              href={`/notebooks/${notebook.id}`}
                              className="p-5 rounded-lg transition-all group"
                              style={{
                                backgroundColor: 'var(--card)',
                                border: '1px solid var(--border)',
                                cursor: 'pointer',
                                boxShadow: 'var(--shadow-md)'
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.boxShadow = 'var(--shadow-lg)';
                                e.currentTarget.style.transform = 'translateY(-4px)';
                                e.currentTarget.style.borderColor = 'var(--terracotta)';
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                                e.currentTarget.style.transform = 'translateY(0)';
                                e.currentTarget.style.borderColor = 'var(--border)';
                              }}
                            >
                              <div className="aspect-[3/4] rounded mb-3 flex items-start p-3 overflow-hidden"
                                style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                              >
                                {notebook.preview ? (
                                  <p style={{
                                    fontSize: '0.7em',
                                    color: 'var(--warm-charcoal)',
                                    lineHeight: '1.4',
                                    margin: 0,
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    display: '-webkit-box',
                                    WebkitLineClamp: 6,
                                    WebkitBoxOrient: 'vertical'
                                  }}>
                                    {notebook.preview}
                                  </p>
                                ) : notebook.sync_progress && notebook.sync_progress.not_synced_pages > 0 ? (
                                  <div className="flex flex-col items-center justify-center w-full h-full px-2">
                                    <svg className="w-6 h-6 mb-2" style={{ color: 'var(--warm-gray)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                    </svg>
                                    <span style={{ fontSize: '0.7em', color: 'var(--warm-gray)', textAlign: 'center', fontWeight: 500, marginBottom: '0.25rem' }}>
                                      Awaiting upload
                                    </span>
                                    <span style={{ fontSize: '0.6em', color: 'var(--warm-gray)', textAlign: 'center' }}>
                                      {notebook.sync_progress.synced_pages}/{notebook.sync_progress.total_pages} ready
                                    </span>
                                  </div>
                                ) : notebook.sync_progress && notebook.sync_progress.pending_quota_pages > 0 ? (
                                  <div className="flex flex-col items-center justify-center w-full h-full px-2">
                                    <span style={{ fontSize: '0.7em', color: 'var(--amber-gold)', textAlign: 'center', fontWeight: 500, marginBottom: '0.25rem' }}>
                                      OCR Pending
                                    </span>
                                    <button
                                      onClick={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        router.push('/billing');
                                      }}
                                      style={{ fontSize: '0.6em', color: 'var(--terracotta)', textAlign: 'center', textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                                    >
                                      Upgrade
                                    </button>
                                  </div>
                                ) : (
                                  <div className="flex flex-col items-center justify-center w-full h-full px-2">
                                    <span style={{ fontSize: '0.7em', color: 'var(--amber-gold)', textAlign: 'center', fontWeight: 500, marginBottom: '0.25rem' }}>
                                      OCR Pending
                                    </span>
                                    <button
                                      onClick={(e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        router.push('/billing');
                                      }}
                                      style={{ fontSize: '0.6em', color: 'var(--terracotta)', textAlign: 'center', textDecoration: 'underline', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                                    >
                                      Upgrade
                                    </button>
                                  </div>
                                )}
                              </div>
                              <h4 style={{
                                fontSize: '0.875em',
                                fontWeight: 500,
                                color: 'var(--warm-charcoal)',
                                marginBottom: '0.25rem',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }} className="group-hover:text-[var(--terracotta)]">
                                {notebook.visible_name}
                              </h4>
                              <p style={{ fontSize: '0.75em', color: 'var(--warm-gray)' }}>
                                {notebook.last_synced_at ? new Date(notebook.last_synced_at).toLocaleDateString('en-US', {
                                  month: 'short',
                                  day: 'numeric'
                                }) : 'Never synced'}
                              </p>
                            </Link>
                          ))}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {groupNotebooks.map((notebook) => (
                            <Link
                              key={notebook.notebook_uuid}
                              href={`/notebooks/${notebook.id}`}
                              className="flex items-center justify-between p-5 rounded-lg transition-all group"
                              style={{
                                backgroundColor: 'var(--card)',
                                border: '1px solid var(--border)',
                                cursor: 'pointer',
                                boxShadow: 'var(--shadow-sm)'
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.boxShadow = 'var(--shadow-md)';
                                e.currentTarget.style.transform = 'translateX(6px)';
                                e.currentTarget.style.borderColor = 'var(--terracotta)';
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
                                e.currentTarget.style.transform = 'translateX(0)';
                                e.currentTarget.style.borderColor = 'var(--border)';
                              }}
                            >
                              <div className="flex items-center gap-4 flex-1 min-w-0">
                                <div className="w-12 h-16 rounded flex items-start p-2 flex-shrink-0 overflow-hidden"
                                  style={{ backgroundColor: 'var(--soft-cream)', border: '1px solid var(--border)' }}
                                >
                                  {notebook.preview ? (
                                    <p style={{
                                      fontSize: '0.5em',
                                      color: 'var(--warm-charcoal)',
                                      lineHeight: '1.3',
                                      margin: 0,
                                      overflow: 'hidden',
                                      textOverflow: 'ellipsis',
                                      display: '-webkit-box',
                                      WebkitLineClamp: 4,
                                      WebkitBoxOrient: 'vertical'
                                    }}>
                                      {notebook.preview}
                                    </p>
                                  ) : notebook.sync_progress && notebook.sync_progress.not_synced_pages > 0 ? (
                                    <div className="flex flex-col items-center justify-center w-full h-full">
                                      <svg className="w-4 h-4 mb-1" style={{ color: 'var(--warm-gray)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                      </svg>
                                      <span style={{ fontSize: '0.45em', color: 'var(--warm-gray)', textAlign: 'center', fontWeight: 500 }}>
                                        Pending
                                      </span>
                                    </div>
                                  ) : (
                                    <div className="flex flex-col items-center justify-center w-full h-full">
                                      <span style={{ fontSize: '0.5em', color: 'var(--amber-gold)', textAlign: 'center', fontWeight: 500 }}>
                                        OCR Pending
                                      </span>
                                    </div>
                                  )}
                                </div>
                                <div className="flex-1 min-w-0">
                                  <h4 style={{
                                    fontSize: '0.925em',
                                    fontWeight: 500,
                                    color: 'var(--warm-charcoal)',
                                    marginBottom: '0.125rem',
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap'
                                  }} className="group-hover:text-[var(--terracotta)]">
                                    {notebook.visible_name}
                                  </h4>
                                  <p style={{ fontSize: '0.8em', color: 'var(--warm-gray)' }}>
                                    {notebook.last_synced_at ? new Date(notebook.last_synced_at).toLocaleDateString('en-US', {
                                      year: 'numeric',
                                      month: 'short',
                                      day: 'numeric'
                                    }) : 'Never synced'}
                                  </p>
                                </div>
                              </div>
                              <ChevronRight className="w-5 h-5" style={{ color: 'var(--warm-gray)' }} />
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {filteredNotebooks.length === 0 && searchQuery && (
                <div className="text-center py-12 rounded-lg" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
                  <Search className="w-16 h-16 mx-auto mb-4" style={{ color: 'var(--warm-gray)' }} />
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                    No results found
                  </h3>
                  <p style={{ color: 'var(--warm-gray)' }}>
                    Try adjusting your search terms or{' '}
                    <button
                      onClick={() => setSearchQuery('')}
                      style={{ color: 'var(--terracotta)', textDecoration: 'underline' }}
                    >
                      clear the search
                    </button>
                  </p>
                </div>
              )}
            </>
          )}
        </main>

        {/* Quota Exceeded Modal */}
        <QuotaExceededModal
          isOpen={showQuotaModal}
          onClose={() => setShowQuotaModal(false)}
          quota={quota}
        />
      </div>
    </div>
  );
}
