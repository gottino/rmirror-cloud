'use client';

import { NotebookTreeNode } from '@/lib/api';

interface BreadcrumbProps {
  currentFolder: NotebookTreeNode | null;
  onNavigate: (folderId: string | null, node: NotebookTreeNode | null) => void;
}

export default function Breadcrumb({ currentFolder, onNavigate }: BreadcrumbProps) {
  // Build breadcrumb trail by traversing up the tree
  const buildBreadcrumbTrail = (): Array<{ id: string | null; name: string; node: NotebookTreeNode | null }> => {
    const trail: Array<{ id: string | null; name: string; node: NotebookTreeNode | null }> = [
      { id: null, name: 'All Notebooks', node: null }
    ];

    if (currentFolder) {
      // For now, we'll just show the current folder since we don't have parent traversal
      // In a more complete implementation, we'd build the full path
      trail.push({
        id: currentFolder.notebook_uuid,
        name: currentFolder.visible_name,
        node: currentFolder
      });
    }

    return trail;
  };

  const trail = buildBreadcrumbTrail();

  return (
    <nav className="flex items-center space-x-2 text-sm text-gray-600 mb-4">
      {trail.map((item, index) => (
        <div key={item.id || 'root'} className="flex items-center">
          {index > 0 && <span className="mx-2 text-gray-400">/</span>}
          {index === trail.length - 1 ? (
            <span className="font-medium text-gray-900">{item.name}</span>
          ) : (
            <button
              onClick={() => onNavigate(item.id, item.node)}
              className="hover:text-purple-600 hover:underline"
            >
              {item.name}
            </button>
          )}
        </div>
      ))}
    </nav>
  );
}
