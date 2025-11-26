'use client';

import { useAuth, UserButton } from '@clerk/nextjs';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
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

  // Get items to display in the main content area
  const getCurrentItems = (): NotebookTreeNode[] => {
    if (!notebookTree) return [];

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
        <div className="flex items-center justify-between">
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
          <div className="flex items-center space-x-4">
            {isSignedIn && <UserButton afterSignOutUrl="/" />}
          </div>
        </div>
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
              <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                <div className="text-gray-400 text-6xl mb-4">📚</div>
                <h3 className="text-xl font-semibold text-gray-900 mb-2">
                  No notebooks yet
                </h3>
                <p className="text-gray-600">
                  Sync your reMarkable notebooks using the Mac agent to get started.
                </p>
              </div>
            ) : (
              <>
                {/* Breadcrumb */}
                <Breadcrumb
                  currentFolder={currentFolder}
                  onNavigate={handleFolderSelect}
                />

                {/* Content grid */}
                <MainContentArea
                  items={currentItems}
                  onFolderClick={handleFolderSelect}
                />
              </>
            )}
          </div>
        </main>
      </div>
    </>
  );
}
