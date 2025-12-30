/**
 * API client for rMirror backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

// Debug: log API URL on client side
if (typeof window !== 'undefined') {
  console.log('API_URL configured as:', API_URL);
}

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
  pdf_s3_key: string | null;
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
  preview: string | null;
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

// ==================== Integrations ====================

export interface IntegrationConfig {
  id: number;
  target_name: string;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
  last_synced_at: string | null;
}

export interface NotionOAuthUrlResponse {
  authorization_url: string;
  state: string;
}

export interface NotionDatabase {
  id: string;
  title: string;
  url: string;
  created_time: string;
  last_edited_time?: string;
}

export interface NotionPage {
  id: string;
  title: string;
  url: string;
  created_time: string;
}

export interface CreateDatabaseResponse {
  database_id: string;
  url: string;
  title: string;
  created_time: string;
}

/**
 * Get all integrations for the current user
 */
export async function getIntegrations(token: string): Promise<IntegrationConfig[]> {
  const response = await fetch(`${API_URL}/integrations/`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch integrations');
  }

  return response.json();
}

/**
 * Get Notion OAuth authorization URL
 */
export async function getNotionOAuthUrl(token: string): Promise<NotionOAuthUrlResponse> {
  const response = await fetch(`${API_URL}/integrations/notion/oauth/authorize`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to get OAuth URL');
  }

  return response.json();
}

/**
 * Complete Notion OAuth callback
 */
export async function notionOAuthCallback(token: string, code: string, state: string): Promise<any> {
  const response = await fetch(`${API_URL}/integrations/notion/oauth/callback`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ code, state }),
  });

  if (!response.ok) {
    throw new Error('Failed to complete OAuth');
  }

  return response.json();
}

/**
 * List available Notion databases
 */
export async function listNotionDatabases(token: string): Promise<NotionDatabase[]> {
  const response = await fetch(`${API_URL}/integrations/notion/databases`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to list databases');
  }

  return response.json();
}

/**
 * List available Notion pages (for parent selection)
 */
export async function listNotionPages(token: string): Promise<NotionPage[]> {
  const response = await fetch(`${API_URL}/integrations/notion/pages`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to list pages');
  }

  return response.json();
}

/**
 * Create a new Notion database for syncing
 */
export async function createNotionDatabase(
  token: string,
  databaseTitle: string,
  databaseType: 'notebooks' | 'todos',
  parentPageId?: string
): Promise<CreateDatabaseResponse> {
  const response = await fetch(`${API_URL}/integrations/notion/databases/create`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      database_title: databaseTitle,
      database_type: databaseType,
      parent_page_id: parentPageId,
    }),
  });

  if (!response.ok) {
    throw new Error('Failed to create database');
  }

  return response.json();
}

/**
 * Select an existing Notion database for syncing
 */
export async function selectNotionDatabase(
  token: string,
  databaseId: string,
  databaseType: 'notebooks' | 'todos'
): Promise<any> {
  const response = await fetch(`${API_URL}/integrations/notion/databases/${databaseId}/select?database_type=${databaseType}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to select database');
  }

  return response.json();
}

/**
 * Delete an integration
 */
export async function deleteIntegration(token: string, targetName: string): Promise<any> {
  const response = await fetch(`${API_URL}/integrations/${targetName}`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to delete integration');
  }

  return response.json();
}
