'use client';

import Link from 'next/link';
import { NotebookTreeNode } from '@/lib/api';

interface MainContentAreaProps {
  items: NotebookTreeNode[];
  onFolderClick: (folderId: string, node: NotebookTreeNode) => void;
}

function ItemCard({ item, onFolderClick }: { item: NotebookTreeNode; onFolderClick: (folderId: string, node: NotebookTreeNode) => void }) {
  const hasChildren = item.children && item.children.length > 0;
  const isFolder = item.is_folder || hasChildren;

  const getIcon = () => {
    if (isFolder) {
      return '📂';
    }
    switch (item.document_type) {
      case 'pdf':
        return '📄';
      case 'epub':
        return '📕';
      case 'notebook':
        return '📓';
      default:
        return '📄';
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    if (isFolder) {
      e.preventDefault();
      onFolderClick(item.notebook_uuid, item);
    }
  };

  const content = (
    <div className="group relative bg-white rounded-lg border border-gray-200 p-6 hover:shadow-md transition-all cursor-pointer">
      <div className="flex flex-col items-center text-center">
        <div className="text-5xl mb-3">{getIcon()}</div>
        <h3 className="font-medium text-gray-900 mb-1 line-clamp-2 group-hover:text-purple-600">
          {item.visible_name}
        </h3>
        {isFolder && (
          <p className="text-sm text-gray-500">
            {item.children.length} {item.children.length === 1 ? 'item' : 'items'}
          </p>
        )}
        {!isFolder && item.document_type && (
          <p className="text-xs text-gray-400 uppercase mt-1">
            {item.document_type}
          </p>
        )}
      </div>
    </div>
  );

  if (isFolder) {
    return (
      <div onClick={handleClick}>
        {content}
      </div>
    );
  }

  return (
    <Link href={`/notebooks/${item.id}`}>
      {content}
    </Link>
  );
}

export default function MainContentArea({ items, onFolderClick }: MainContentAreaProps) {
  // Sort: folders first, then alphabetically
  const sortedItems = [...items].sort((a, b) => {
    const aIsFolder = a.is_folder || (a.children && a.children.length > 0);
    const bIsFolder = b.is_folder || (b.children && b.children.length > 0);

    if (aIsFolder && !bIsFolder) return -1;
    if (!aIsFolder && bIsFolder) return 1;

    return a.visible_name.localeCompare(b.visible_name);
  });

  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 bg-white rounded-lg border border-gray-200">
        <div className="text-center text-gray-500">
          <div className="text-6xl mb-4">📂</div>
          <p>This folder is empty</p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4">
      {sortedItems.map((item) => (
        <ItemCard
          key={item.id}
          item={item}
          onFolderClick={onFolderClick}
        />
      ))}
    </div>
  );
}
