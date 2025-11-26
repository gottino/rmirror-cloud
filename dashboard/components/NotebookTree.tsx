'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Folder, FolderOpen, NotebookText, FileText, BookOpen, ChevronDown, ChevronRight } from 'lucide-react';
import { NotebookTreeNode } from '@/lib/api';

interface NotebookTreeProps {
  nodes: NotebookTreeNode[];
}

interface TreeNodeProps {
  node: NotebookTreeNode;
  level: number;
}

function TreeNode({ node, level }: TreeNodeProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = node.children && node.children.length > 0;

  const getIcon = () => {
    const iconClass = "w-4 h-4";
    if (node.is_folder || hasChildren) {
      return isExpanded ? <FolderOpen className={iconClass} /> : <Folder className={iconClass} />;
    }
    switch (node.document_type) {
      case 'pdf':
        return <FileText className={iconClass} />;
      case 'epub':
        return <BookOpen className={iconClass} />;
      case 'notebook':
        return <NotebookText className={iconClass} />;
      default:
        return <NotebookText className={iconClass} />;
    }
  };

  const toggleExpand = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  return (
    <div className="select-none">
      <div
        className="flex items-center py-1.5 px-2 hover:bg-gray-50 rounded cursor-pointer group"
        style={{ paddingLeft: `${level * 1.25 + 0.5}rem` }}
      >
        {hasChildren && (
          <button
            onClick={toggleExpand}
            className="mr-1 text-gray-400 hover:text-gray-600 focus:outline-none"
          >
            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </button>
        )}
        {!hasChildren && <span className="mr-1 w-4" />}

        {node.is_folder || hasChildren ? (
          <div className="flex items-center flex-1 min-w-0">
            <span className="mr-2 flex items-center">{getIcon()}</span>
            <span className="font-medium text-gray-900 truncate">
              {node.visible_name}
            </span>
            <span className="ml-2 text-xs text-gray-400">
              ({node.children.length})
            </span>
          </div>
        ) : (
          <Link
            href={`/notebooks/${node.id}`}
            className="flex items-center flex-1 min-w-0 hover:text-blue-600"
          >
            <span className="mr-2 flex items-center">{getIcon()}</span>
            <span className="text-gray-700 group-hover:text-blue-600 truncate">
              {node.visible_name}
            </span>
          </Link>
        )}
      </div>

      {hasChildren && isExpanded && (
        <div>
          {node.children.map((child) => (
            <TreeNode key={child.id} node={child} level={level + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function NotebookTree({ nodes }: NotebookTreeProps) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <div className="max-h-[calc(100vh-250px)] overflow-y-auto">
        {nodes.length === 0 ? (
          <div className="p-8 text-center text-gray-500">
            No notebooks found
          </div>
        ) : (
          <div className="py-2">
            {nodes.map((node) => (
              <TreeNode key={node.id} node={node} level={0} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
