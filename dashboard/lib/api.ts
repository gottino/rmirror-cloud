/**
 * API client for rMirror backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';

// Debug: log API URL on client side
if (typeof window !== 'undefined') {
  console.log('API_URL configured as:', API_URL);
}

/**
 * Handle API response and check for quota exceeded errors
 */
async function handleApiResponse<T>(response: Response): Promise<T> {
  // Check for 402 Payment Required (quota exceeded)
  if (response.status === 402) {
    const errorData = await response.json();
    if (errorData.quota) {
      throw new QuotaExceededError(errorData.quota);
    }
    throw new Error('Quota exceeded');
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `API error: ${response.status}`);
  }

  return response.json();
}

// Export for use in components
export class QuotaExceededError extends Error {
  quota: QuotaStatus;

  constructor(quota: QuotaStatus) {
    super('Quota exceeded');
    this.name = 'QuotaExceededError';
    this.quota = quota;
  }
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

export interface SyncProgress {
  total_pages: number;
  synced_pages: number;
  not_synced_pages: number;
  pending_quota_pages: number;
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
  last_opened: string | null;
  is_folder: boolean;
  preview: string | null;
  sync_progress: SyncProgress | null;
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

  return handleApiResponse<Notebook[]>(response);
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

  return handleApiResponse<NotebookTree>(response);
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

  return handleApiResponse<NotebookWithPages>(response);
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

// ==================== Quota ====================

export interface QuotaStatus {
  quota_type: string;
  used: number;
  limit: number;
  remaining: number;
  percentage_used: number;
  is_near_limit: boolean;
  is_exhausted: boolean;
  reset_at: string;
  period_start: string;
  is_beta?: boolean;
}

/**
 * Get quota status for the current user
 */
export async function getQuotaStatus(token: string): Promise<QuotaStatus> {
  const response = await fetch(`${API_URL}/quota/status`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  return handleApiResponse<QuotaStatus>(response);
}

/**
 * Check if user has available quota
 */
export async function checkQuota(token: string): Promise<{ has_quota: boolean; quota: QuotaStatus }> {
  const response = await fetch(`${API_URL}/quota/check`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  return handleApiResponse<{ has_quota: boolean; quota: QuotaStatus }>(response);
}

// ==================== Search ====================

export interface SearchSnippet {
  text: string;
  highlights: [number, number][];
}

export interface MatchedPage {
  page_id: number;
  page_uuid: string | null;
  page_number: number;
  snippet: SearchSnippet;
  score: number;
}

export interface SearchResult {
  notebook_id: number;
  notebook_uuid: string;
  visible_name: string;
  document_type: string;
  full_path: string | null;
  name_match: boolean;
  name_score: number;
  matched_pages: MatchedPage[];
  total_matched_pages: number;
  best_score: number;
  updated_at: string;
}

export interface SearchResponse {
  query: string;
  results: SearchResult[];
  total_results: number;
  has_more: boolean;
  search_mode: 'fuzzy' | 'basic';
}

// ==================== Onboarding ====================

export interface OnboardingProgress {
  state: string;
  onboarding_started_at: string | null;
  onboarding_completed_at: string | null;
  agent_downloaded_at: string | null;
  agent_first_connected_at: string | null;
  first_notebook_synced_at: string | null;
  first_ocr_completed_at: string | null;
  notion_connected_at: string | null;
  onboarding_dismissed: boolean;
  has_notebooks: boolean;
  has_ocr: boolean;
  has_notion: boolean;
}

/**
 * Get onboarding progress for the current user
 */
export async function getOnboardingProgress(token: string): Promise<OnboardingProgress> {
  const response = await fetch(`${API_URL}/onboarding/progress`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  return handleApiResponse<OnboardingProgress>(response);
}

/**
 * Dismiss the onboarding checklist
 */
export async function dismissOnboarding(token: string): Promise<void> {
  try {
    const response = await fetch(`${API_URL}/onboarding/dismiss`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      console.error('Failed to dismiss onboarding');
    }
  } catch (error) {
    console.error('Error dismissing onboarding:', error);
  }
}

// ==================== Waitlist / Beta Invites ====================

export interface WaitlistEntry {
  id: number;
  email: string;
  name: string | null;
  status: 'pending' | 'approved' | 'claimed';
  created_at: string;
  approved_at: string | null;
  claimed_at: string | null;
}

export interface WaitlistAdminResponse {
  entries: WaitlistEntry[];
  total: number;
  stats: {
    pending: number;
    approved: number;
    claimed: number;
  };
}

export interface InviteValidationResponse {
  valid: boolean;
  email?: string;
  reason?: string;
}

/**
 * Validate an invite token (public, no auth needed)
 */
export async function validateInviteToken(token: string): Promise<InviteValidationResponse> {
  const response = await fetch(`${API_URL}/waitlist/validate-invite?token=${encodeURIComponent(token)}`);
  return response.json();
}

/**
 * Get waitlist entries (admin only)
 */
export async function getWaitlistAdmin(
  token: string,
  status?: string,
  skip?: number,
  limit?: number
): Promise<WaitlistAdminResponse> {
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (skip) params.set('skip', skip.toString());
  if (limit) params.set('limit', limit.toString());

  const response = await fetch(`${API_URL}/waitlist/admin?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });

  if (response.status === 403) {
    throw new Error('Admin access required');
  }

  return handleApiResponse<WaitlistAdminResponse>(response);
}

/**
 * Approve a single waitlist entry (admin only)
 */
export async function approveWaitlistEntry(
  token: string,
  entryId: number
): Promise<WaitlistEntry> {
  const response = await fetch(`${API_URL}/waitlist/admin/${entryId}/approve`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
  });

  return handleApiResponse<WaitlistEntry>(response);
}

/**
 * Approve multiple waitlist entries (admin only)
 */
export async function approveWaitlistBulk(
  token: string,
  ids: number[]
): Promise<{ approved: number; errors: Array<{ id: number; error: string }> }> {
  const response = await fetch(`${API_URL}/waitlist/admin/approve-bulk`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ids }),
  });

  return handleApiResponse<{ approved: number; errors: Array<{ id: number; error: string }> }>(response);
}

// ==================== Admin Users ====================

export interface AdminUser {
  id: number;
  email: string;
  full_name: string | null;
  created_at: string;
  subscription_tier: string;
  onboarding_state: string;
  agent_downloaded_at: string | null;
  agent_first_connected_at: string | null;
  first_notebook_synced_at: string | null;
  first_ocr_completed_at: string | null;
  notion_connected_at: string | null;
  notebook_count: number;
  page_count: number;
  quota_used: number;
  quota_limit: number;
  last_active_at: string | null;
}

export interface AdminUsersStats {
  total_users: number;
  agent_downloaded: number;
  agent_connected: number;
  first_notebook_synced: number;
  first_ocr_completed: number;
  notion_connected: number;
}

export interface AdminUsersResponse {
  users: AdminUser[];
  total: number;
  stats: AdminUsersStats;
}

/**
 * Get all users with onboarding and usage data (admin only)
 */
export async function getAdminUsers(
  token: string,
  skip?: number,
  limit?: number,
  sortBy?: string,
  sortDir?: string
): Promise<AdminUsersResponse> {
  const params = new URLSearchParams();
  if (skip) params.set('skip', skip.toString());
  if (limit) params.set('limit', limit.toString());
  if (sortBy) params.set('sort_by', sortBy);
  if (sortDir) params.set('sort_dir', sortDir);

  const response = await fetch(`${API_URL}/admin/users?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });

  if (response.status === 403) {
    throw new Error('Admin access required');
  }

  return handleApiResponse<AdminUsersResponse>(response);
}

// ==================== Search ====================

export async function searchNotebooks(
  token: string,
  query: string,
  options?: {
    skip?: number;
    limit?: number;
    parentUuid?: string;      // Filter to folder and subfolders
    notebookId?: number;      // Filter to single notebook
    dateFrom?: string;        // ISO date string
    dateTo?: string;          // ISO date string
  }
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query });
  if (options?.skip) params.set('skip', options.skip.toString());
  if (options?.limit) params.set('limit', options.limit.toString());
  if (options?.parentUuid) params.set('parent_uuid', options.parentUuid);
  if (options?.notebookId) params.set('notebook_id', options.notebookId.toString());
  if (options?.dateFrom) params.set('date_from', options.dateFrom);
  if (options?.dateTo) params.set('date_to', options.dateTo);

  const response = await fetch(`${API_URL}/search?${params}`, {
    headers: { 'Authorization': `Bearer ${token}` },
  });

  return handleApiResponse<SearchResponse>(response);
}

// ==================== Legal ====================

export interface LegalStatus {
  tos_accepted: boolean;
  privacy_accepted: boolean;
  tos_version: string | null;
  privacy_version: string | null;
  current_tos_version: string;
  current_privacy_version: string;
}

/**
 * Get the user's legal acceptance status
 */
export async function getLegalStatus(token: string): Promise<LegalStatus> {
  const response = await fetch(`${API_URL}/users/legal-status`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  return handleApiResponse<LegalStatus>(response);
}

/**
 * Accept the current ToS and Privacy Policy
 */
export async function acceptTerms(token: string): Promise<LegalStatus> {
  const response = await fetch(`${API_URL}/users/accept-terms`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  return handleApiResponse<LegalStatus>(response);
}
