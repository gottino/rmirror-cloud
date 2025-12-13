'use client';

import { useAuth, UserButton } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { Search, X } from 'lucide-react';
import { getNotebooksTree, type NotebookTree as NotebookTreeData, NotebookTreeNode } from '@/lib/api';
import FolderSidebar from '@/components/FolderSidebar';
import Breadcrumb from '@/components/Breadcrumb';
import MainContentArea from '@/components/MainContentArea';

export default function Home() {
  const { getToken, isSignedIn } = useAuth();
  const [notebookTree, setNotebookTree] = useState<NotebookTreeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
  const [currentFolder, setCurrentFolder] = useState<NotebookTreeNode | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const [activeFilter, setActiveFilter] = useState<'notebook' | 'epub' | 'pdf' | null>(null);

  const fetchNotebooks = async () => {
    if (!isSignedIn) {
      setLoading(false);
      return;
    }

    try {
      setError(null);
      const token = await getToken();
      if (!token) {
        throw new Error('Failed to get authentication token');
      }

      const data = await getNotebooksTree(token);
      setNotebookTree(data);
    } catch (err) {
      console.error('Error fetching notebooks:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch notebooks');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNotebooks();
  }, [isSignedIn, getToken]);

  // Find a node by UUID in the tree
  const findNodeByUuid = (nodes: NotebookTreeNode[], uuid: string): NotebookTreeNode | null => {
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
  };

  // Search through all nodes recursively
  const searchNodes = (nodes: NotebookTreeNode[], query: string): NotebookTreeNode[] => {
    const results: NotebookTreeNode[] = [];
    const lowerQuery = query.toLowerCase();

    for (const node of nodes) {
      // Check if current node matches
      if (node.visible_name.toLowerCase().includes(lowerQuery)) {
        results.push(node);
      }
      // Search children recursively
      if (node.children && node.children.length > 0) {
        results.push(...searchNodes(node.children, query));
      }
    }

    return results;
  };

  // Flatten tree and get all items of a specific document type
  const getItemsByType = (nodes: NotebookTreeNode[], docType: string): NotebookTreeNode[] => {
    const results: NotebookTreeNode[] = [];

    for (const node of nodes) {
      // Only include non-folder items that match the type
      if (!node.is_folder && node.document_type === docType) {
        results.push(node);
      }
      // Recursively search children
      if (node.children && node.children.length > 0) {
        results.push(...getItemsByType(node.children, docType));
      }
    }

    // Sort by last_synced_at (most recent first)
    return results.sort((a, b) => {
      const dateA = a.last_synced_at ? new Date(a.last_synced_at).getTime() : 0;
      const dateB = b.last_synced_at ? new Date(b.last_synced_at).getTime() : 0;
      return dateB - dateA; // descending order
    });
  };

  // Get items to display in the main content area
  const getCurrentItems = (): NotebookTreeNode[] => {
    if (!notebookTree) return [];

    // If filtering by type, return all items of that type
    if (activeFilter) {
      return getItemsByType(notebookTree.tree, activeFilter);
    }

    // If searching, return search results
    if (searchQuery.trim()) {
      return searchNodes(notebookTree.tree, searchQuery.trim());
    }

    if (currentFolderId === null) {
      // Show root level items
      return notebookTree.tree;
    }

    // Find the current folder and return its children
    const folder = findNodeByUuid(notebookTree.tree, currentFolderId);
    return folder?.children || [];
  };

  const handleFolderSelect = (folderId: string | null, node: NotebookTreeNode | null) => {
    setCurrentFolderId(folderId);
    setCurrentFolder(node);
    // Close sidebar on mobile when folder is selected
    if (window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  };

  // Header component that's always visible
  const Header = () => (
    <header className="bg-white shadow-sm sticky top-0 z-30">
      <div className="max-w-full mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className="lg:hidden text-gray-600 hover:text-gray-900 p-2"
              aria-label="Toggle sidebar"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <div className="flex items-center space-x-2">
              <Image src="/rm-icon.png" alt="rMirror" width={32} height={32} className="inline-block" />
              <h1 className="text-2xl font-bold text-gray-900">rMirror</h1>
            </div>
          </div>

          {/* Search bar */}
          <div className="flex-1 max-w-md hidden sm:block">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
              <input
                type="text"
                placeholder="Search notebooks and folders..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  aria-label="Clear search"
                >
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-2">
            {/* Mobile search icon */}
            <button
              onClick={() => setMobileSearchOpen(!mobileSearchOpen)}
              className="sm:hidden p-2 text-gray-600 hover:text-gray-900"
              aria-label="Toggle search"
            >
              {mobileSearchOpen ? <X className="w-5 h-5" /> : <Search className="w-5 h-5" />}
            </button>
            {isSignedIn && <UserButton afterSignOutUrl="/" />}
          </div>
        </div>

        {/* Mobile search bar */}
        {mobileSearchOpen && (
          <div className="sm:hidden px-4 pb-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
              <input
                type="text"
                placeholder="Search notebooks and folders..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-10 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-600 focus:border-transparent"
                autoFocus
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  aria-label="Clear search"
                >
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );

  if (loading) {
    return (
      <>
        <Header />
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading notebooks...</p>
          </div>
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Header />
        <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
          <div className="text-center max-w-md">
            <div className="text-red-600 text-5xl mb-4">✗</div>
            <h2 className="text-2xl font-bold text-gray-900 mb-2">Error</h2>
            <p className="text-gray-600 mb-6">{error}</p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <button
                onClick={() => fetchNotebooks()}
                className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
              >
                Try Again
              </button>
              <Link
                href="/"
                className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
              >
                Go Home
              </Link>
            </div>
          </div>
        </div>
      </>
    );
  }

  const currentItems = getCurrentItems();

  return (
    <>
      <Header />
      <div className="flex h-screen overflow-hidden bg-gray-50">
        {/* Sidebar */}
        {notebookTree && (
          <FolderSidebar
            nodes={notebookTree.tree}
            selectedFolderId={currentFolderId}
            onFolderSelect={handleFolderSelect}
            isOpen={sidebarOpen}
            onToggle={() => setSidebarOpen(!sidebarOpen)}
          />
        )}

        {/* Main content area */}
        <main className="flex-1 overflow-y-auto">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {!notebookTree || notebookTree.total === 0 ? (
              <div className="text-center py-12 bg-white rounded-lg border border-gray-200 max-w-2xl mx-auto">
                <div className="text-gray-400 text-6xl mb-4">📚</div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  No notebooks yet
                </h3>
                <p className="text-gray-600 mb-6">
                  Download and install the rMirror Agent to sync your reMarkable notebooks.
                </p>
                <div className="space-y-4">
                  <a
                    href="https://f000.backblazeb2.com/file/rmirror-downloads/releases/v1.0.0/rMirror-1.0.0.dmg"
                    className="inline-block px-6 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors font-semibold"
                    download
                  >
                    Download rMirror Agent for macOS
                  </a>
                  <div className="text-sm text-gray-500">
                    Version 1.0.0 • macOS 12.0 or later • 18 MB
                  </div>
                  <div className="mt-6 pt-6 border-t border-gray-200">
                    <h4 className="text-sm font-semibold text-gray-900 mb-3">Getting Started:</h4>
                    <ol className="text-sm text-gray-600 text-left space-y-2 max-w-md mx-auto">
                      <li className="flex items-start">
                        <span className="font-semibold mr-2">1.</span>
                        <span>Download and install the agent on your Mac</span>
                      </li>
                      <li className="flex items-start">
                        <span className="font-semibold mr-2">2.</span>
                        <span>Make sure reMarkable Desktop app is installed and synced</span>
                      </li>
                      <li className="flex items-start">
                        <span className="font-semibold mr-2">3.</span>
                        <span>Launch rMirror Agent and sign in with your account</span>
                      </li>
                      <li className="flex items-start">
                        <span className="font-semibold mr-2">4.</span>
                        <span>Your notebooks will automatically sync to the cloud</span>
                      </li>
                    </ol>
                  </div>
                </div>
              </div>
            ) : (
              <>
                {/* Filters */}
                <div className="mb-4 flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => setActiveFilter(activeFilter === 'notebook' ? null : 'notebook')}
                    className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
                      activeFilter === 'notebook'
                        ? 'bg-purple-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    Notebooks
                  </button>
                  <button
                    onClick={() => setActiveFilter(activeFilter === 'pdf' ? null : 'pdf')}
                    className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
                      activeFilter === 'pdf'
                        ? 'bg-purple-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    PDFs
                  </button>
                  <button
                    onClick={() => setActiveFilter(activeFilter === 'epub' ? null : 'epub')}
                    className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
                      activeFilter === 'epub'
                        ? 'bg-purple-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    EPubs
                  </button>
                </div>

                {/* Filter results header, Search results header, or Breadcrumb */}
                {activeFilter ? (
                  <div className="mb-6">
                    <div className="flex items-center justify-between">
                      <h2 className="text-lg font-semibold text-gray-900">
                        {activeFilter === 'notebook' ? 'All Notebooks' : activeFilter === 'pdf' ? 'All PDFs' : 'All EPubs'}
                      </h2>
                      <button
                        onClick={() => setActiveFilter(null)}
                        className="text-sm text-purple-600 hover:text-purple-700"
                      >
                        Clear filter
                      </button>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      {currentItems.length} {currentItems.length === 1 ? 'item' : 'items'} · Sorted by most recent
                    </p>
                  </div>
                ) : searchQuery.trim() ? (
                  <div className="mb-6">
                    <div className="flex items-center justify-between">
                      <h2 className="text-lg font-semibold text-gray-900">
                        Search results for &quot;{searchQuery}&quot;
                      </h2>
                      <button
                        onClick={() => setSearchQuery('')}
                        className="text-sm text-purple-600 hover:text-purple-700"
                      >
                        Clear search
                      </button>
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      {currentItems.length} {currentItems.length === 1 ? 'result' : 'results'} found
                    </p>
                  </div>
                ) : (
                  <Breadcrumb
                    currentFolder={currentFolder}
                    onNavigate={handleFolderSelect}
                  />
                )}

                {/* Content grid or empty search results */}
                {currentItems.length === 0 && searchQuery.trim() ? (
                  <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                    <Search className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                    <h3 className="text-xl font-semibold text-gray-900 mb-2">
                      No results found
                    </h3>
                    <p className="text-gray-600">
                      Try adjusting your search terms or{' '}
                      <button
                        onClick={() => setSearchQuery('')}
                        className="text-purple-600 hover:text-purple-700 underline"
                      >
                        clear the search
                      </button>
                    </p>
                  </div>
                ) : (
                  <MainContentArea
                    items={currentItems}
                    onFolderClick={handleFolderSelect}
                    skipSort={activeFilter !== null}
                  />
                )}
              </>
            )}
          </div>
        </main>
      </div>
    </>
  );
}
