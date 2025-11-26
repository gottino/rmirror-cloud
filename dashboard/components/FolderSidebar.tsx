'use client';

import { useState } from 'react';
import { Folder, FolderOpen, Home, ChevronDown, ChevronRight } from 'lucide-react';
import { NotebookTreeNode } from '@/lib/api';

interface FolderSidebarProps {
  nodes: NotebookTreeNode[];
  selectedFolderId: string | null;
  onFolderSelect: (folderId: string | null, node: NotebookTreeNode | null) => void;
  isOpen: boolean;
  onToggle: () => void;
}

interface FolderNodeProps {
  node: NotebookTreeNode;
  level: number;
  selectedFolderId: string | null;
  onFolderSelect: (folderId: string | null, node: NotebookTreeNode | null) => void;
}

function FolderNode({ node, level, selectedFolderId, onFolderSelect }: FolderNodeProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = node.children && node.children.length > 0;
  const isFolder = node.is_folder || hasChildren;

  // Only show folders in the sidebar
  if (!isFolder) {
    return null;
  }

  const isSelected = selectedFolderId === node.notebook_uuid;

  const handleClick = () => {
    onFolderSelect(node.notebook_uuid, node);
  };

  const toggleExpand = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  const folderChildren = node.children.filter(child =>
    child.is_folder || (child.children && child.children.length > 0)
  );

  return (
    <div>
      <div
        className={`flex items-center py-2 px-2 rounded cursor-pointer transition-colors ${
          isSelected
            ? 'bg-purple-100 text-purple-900 font-medium'
            : 'hover:bg-gray-100 text-gray-700'
        }`}
        style={{ paddingLeft: `${level * 0.75 + 0.5}rem` }}
        onClick={handleClick}
      >
        {folderChildren.length > 0 && (
          <button
            onClick={toggleExpand}
            className="mr-1 text-gray-400 hover:text-gray-600 focus:outline-none"
          >
            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        )}
        {folderChildren.length === 0 && <span className="mr-1 w-4" />}

        <span className="mr-2 flex items-center">{isExpanded ? <FolderOpen className="w-4 h-4" /> : <Folder className="w-4 h-4" />}</span>
        <span className="truncate flex-1">{node.visible_name}</span>
        <span className="ml-1 text-xs text-gray-400">
          {node.children.length}
        </span>
      </div>

      {folderChildren.length > 0 && isExpanded && (
        <div>
          {folderChildren.map((child) => (
            <FolderNode
              key={child.id}
              node={child}
              level={level + 1}
              selectedFolderId={selectedFolderId}
              onFolderSelect={onFolderSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function FolderSidebar({
  nodes,
  selectedFolderId,
  onFolderSelect,
  isOpen,
  onToggle
}: FolderSidebarProps) {
  const handleRootClick = () => {
    onFolderSelect(null, null);
  };

  return (
    <>
      {/* Mobile overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={onToggle}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:sticky top-0 left-0 h-screen
          w-64 bg-white border-r border-gray-200
          flex flex-col z-50
          transform transition-transform duration-200 ease-in-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="font-semibold text-gray-900">Folders</h2>
          <button
            onClick={onToggle}
            className="lg:hidden text-gray-500 hover:text-gray-700"
          >
            ✕
          </button>
        </div>

        {/* Root folder option */}
        <div className="border-b border-gray-200">
          <div
            className={`flex items-center py-2 px-4 cursor-pointer transition-colors ${
              selectedFolderId === null
                ? 'bg-purple-100 text-purple-900 font-medium'
                : 'hover:bg-gray-100 text-gray-700'
            }`}
            onClick={handleRootClick}
          >
            <span className="mr-2 flex items-center"><Home className="w-4 h-4" /></span>
            <span>All Notebooks</span>
          </div>
        </div>

        {/* Folder tree */}
        <div className="flex-1 overflow-y-auto p-2">
          {nodes.map((node) => (
            <FolderNode
              key={node.id}
              node={node}
              level={0}
              selectedFolderId={selectedFolderId}
              onFolderSelect={onFolderSelect}
            />
          ))}
        </div>
      </aside>
    </>
  );
}
