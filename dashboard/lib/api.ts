/**
 * API client for rMirror backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

export interface Notebook {
  id: number;
  visible_name: string;
  document_type: string;
  title: string | null;
  author: string | null;
  notebook_uuid: string;
  user_id: number;
  s3_key: string | null;
  file_hash: string | null;
  file_size: number | null;
  created_at: string;
  updated_at: string;
  last_synced_at: string | null;
}

export interface Page {
  id: number;
  notebook_id: number;
  page_number: number;
  ocr_status: string;
  ocr_text: string | null;
  ocr_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotebookWithPages extends Notebook {
  pages: Page[];
}

export interface NotebookTreeNode {
  id: number;
  notebook_uuid: string;
  visible_name: string;
  document_type: string;
  parent_uuid: string | null;
  full_path: string | null;
  created_at: string | null;
  last_synced_at: string | null;
  is_folder: boolean;
  children: NotebookTreeNode[];
}

export interface NotebookTree {
  tree: NotebookTreeNode[];
  total: number;
}

/**
 * Fetch notebooks for the current user
 */
export async function getNotebooks(token: string): Promise<Notebook[]> {
  const response = await fetch(`${API_URL}/notebooks/`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch notebooks');
  }

  return response.json();
}

/**
 * Fetch notebooks organized in a tree structure
 */
export async function getNotebooksTree(token: string): Promise<NotebookTree> {
  const response = await fetch(`${API_URL}/notebooks/tree`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch notebook tree');
  }

  return response.json();
}

/**
 * Fetch a single notebook with its pages
 */
export async function getNotebook(id: number, token: string): Promise<NotebookWithPages> {
  const response = await fetch(`${API_URL}/notebooks/${id}`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch notebook');
  }

  return response.json();
}

/**
 * Track agent download
 */
export async function trackAgentDownload(token: string): Promise<void> {
  try {
    const response = await fetch(`${API_URL}/onboarding/agent-downloaded`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      console.error('Failed to track agent download');
    }
  } catch (error) {
    // Silent fail - don't block the download
    console.error('Error tracking agent download:', error);
  }
}

export interface AgentStatus {
  has_agent_connected: boolean;
  first_connected_at: string | null;
  onboarding_state: string;
}

/**
 * Get agent connection status
 */
export async function getAgentStatus(token: string): Promise<AgentStatus> {
  const response = await fetch(`${API_URL}/agents/status`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch agent status');
  }

  return response.json();
}
