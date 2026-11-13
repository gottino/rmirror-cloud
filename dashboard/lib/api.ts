/**
 * API client for rMirror backend.
 *
 * Every request goes through `apiFetch` (lib/apiClient.ts); components call
 * these functions and never build backend URLs themselves.
 */
import { apiFetch, ApiError, filenameFromResponse, type ApiFetchOptions } from './apiClient';

export { ApiError, QuotaExceededError } from './apiClient';

/** Rethrow a 403 from an admin endpoint with the message the admin pages show. */
async function adminFetch<T>(path: string, options: ApiFetchOptions): Promise<T> {
  try {
    return await apiFetch<T>(path, options);
  } catch (err) {
    if (err instanceof ApiError && err.status === 403) {
      throw new ApiError(403, 'Admin access required', err.detail, err.statusText);
    }
    throw err;
  }
}

/** `{success, message}` body returned by several integration endpoints. */
export interface SuccessMessageResponse {
  success: boolean;
  message: string;
}

/** A downloaded file and the filename the backend suggested, if any. */
export interface DownloadedFile {
  blob: Blob;
  filename: string | null;
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

/** Values of backend app/models/page.py `OcrStatus`. */
export type OcrStatus =
  | 'not_synced'
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'skipped'
  | 'pending_quota';

export interface Page {
  id: number;
  notebook_id: number;
  page_number: number;
  ocr_status: OcrStatus;
  ocr_text: string | null;
  ocr_error: string | null;
  pdf_s3_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface NotebookPageCounts {
  total_pages: number;
  synced_pages: number;
  not_synced_pages: number;
  pending_quota_pages: number;
}

export interface NotebookWithPages extends Notebook {
  pages: Page[];
  /** Counts over all pages; present even when pages were not requested. */
  page_counts?: NotebookPageCounts | null;
}

export interface NotebookPagesResponse {
  items: Page[];
  total: number;
  offset: number;
  limit: number;
  has_more: boolean;
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
 * Fetch notebooks organized in a tree structure
 */
export async function getNotebooksTree(token: string, signal?: AbortSignal): Promise<NotebookTree> {
  return apiFetch<NotebookTree>('/notebooks/tree', { token, signal });
}

/**
 * Fetch a single notebook with its pages
 */
export async function getNotebook(
  id: number,
  token: string,
  options?: { includePages?: boolean }
): Promise<NotebookWithPages> {
  return apiFetch<NotebookWithPages>(`/notebooks/${id}`, {
    token,
    query: { include_pages: options?.includePages === false ? 'false' : undefined },
  });
}

/**
 * Fetch one window of a notebook's pages (with OCR text), ordered by page number
 */
export async function getNotebookPages(
  id: number,
  token: string,
  options: { offset: number; limit: number; order?: 'asc' | 'desc' }
): Promise<NotebookPagesResponse> {
  return apiFetch<NotebookPagesResponse>(`/notebooks/${id}/pages`, {
    token,
    query: { offset: options.offset, limit: options.limit, order: options.order ?? 'asc' },
  });
}

/**
 * Fetch a page's PDF (authenticated)
 */
export async function getPagePdf(token: string, pageId: number): Promise<Blob> {
  return apiFetch<Blob>(`/pages/${pageId}/pdf`, {
    token,
    responseType: 'blob',
    errorMessage: 'Failed to load PDF',
  });
}

/**
 * Export a notebook as Markdown or PDF. Throws QuotaExceededError on 402.
 */
export async function exportNotebook(
  token: string,
  notebookId: number,
  format: 'markdown' | 'pdf'
): Promise<DownloadedFile> {
  const response = await apiFetch<Response>(`/notebooks/${notebookId}/export`, {
    token,
    query: { format },
    responseType: 'response',
    fallbackMessage: (status) => `Export failed (${status})`,
  });
  return { blob: await response.blob(), filename: filenameFromResponse(response) };
}

/**
 * Track agent download
 */
export async function trackAgentDownload(token: string): Promise<void> {
  try {
    await apiFetch('/onboarding/agent-downloaded', { token, method: 'POST', responseType: 'void' });
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
export async function getAgentStatus(token: string, signal?: AbortSignal): Promise<AgentStatus> {
  return apiFetch<AgentStatus>('/agents/status', {
    token,
    signal,
    errorMessage: 'Failed to fetch agent status',
  });
}

/** backend app/schemas/auth.py `Token` */
export interface AgentTokenResponse {
  access_token: string;
  token_type: string;
}

/**
 * Exchange a Clerk session token for a long-lived agent token
 */
export async function exchangeAgentToken(clerkToken: string): Promise<AgentTokenResponse> {
  return apiFetch<AgentTokenResponse>('/auth/agent-token', { token: clerkToken, method: 'POST' });
}

// ==================== Agent Version ====================

export interface AgentVersionInfo {
  version: string;
  platforms: {
    macos?: {
      url: string;
      min_os: string;
    };
    windows?: {
      url: string;
    };
  };
}

/**
 * Get latest agent version and download URLs (public, no auth needed)
 */
export async function getLatestAgentVersion(signal?: AbortSignal): Promise<AgentVersionInfo> {
  return apiFetch<AgentVersionInfo>('/agents/latest-version', { signal });
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

/** backend notion_oauth.py / todoist.py `OAuthUrlResponse` */
export interface OAuthUrlResponse {
  authorization_url: string;
  state: string;
}

export type NotionOAuthUrlResponse = OAuthUrlResponse;

/** backend notion_oauth.py `OAuthCallbackResponse` */
export interface NotionOAuthCallbackResponse extends SuccessMessageResponse {
  workspace_name?: string | null;
  workspace_id?: string | null;
}

/** backend notion_oauth.py `select_database` return value */
export interface SelectNotionDatabaseResponse extends SuccessMessageResponse {
  database_id: string;
  database_title: string | null;
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
  return apiFetch<IntegrationConfig[]>('/integrations/', {
    token,
    errorMessage: 'Failed to fetch integrations',
  });
}

/**
 * Get Notion OAuth authorization URL
 */
export async function getNotionOAuthUrl(token: string): Promise<NotionOAuthUrlResponse> {
  return apiFetch<NotionOAuthUrlResponse>('/integrations/notion/oauth/authorize', {
    token,
    errorMessage: 'Failed to get OAuth URL',
  });
}

/**
 * Complete Notion OAuth callback
 */
export async function notionOAuthCallback(
  token: string,
  code: string,
  state: string
): Promise<NotionOAuthCallbackResponse> {
  return apiFetch<NotionOAuthCallbackResponse>('/integrations/notion/oauth/callback', {
    token,
    method: 'POST',
    body: { code, state },
    errorMessage: 'Failed to complete OAuth',
  });
}

/**
 * List available Notion databases
 */
export async function listNotionDatabases(token: string): Promise<NotionDatabase[]> {
  return apiFetch<NotionDatabase[]>('/integrations/notion/databases', {
    token,
    errorMessage: 'Failed to list databases',
  });
}

/**
 * List available Notion pages (for parent selection)
 */
export async function listNotionPages(token: string): Promise<NotionPage[]> {
  return apiFetch<NotionPage[]>('/integrations/notion/pages', {
    token,
    errorMessage: 'Failed to list pages',
  });
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
  return apiFetch<CreateDatabaseResponse>('/integrations/notion/databases/create', {
    token,
    method: 'POST',
    body: {
      database_title: databaseTitle,
      database_type: databaseType,
      parent_page_id: parentPageId,
    },
    errorMessage: 'Failed to create database',
  });
}

/**
 * Select an existing Notion database for syncing
 */
export async function selectNotionDatabase(
  token: string,
  databaseId: string,
  databaseType: 'notebooks' | 'todos'
): Promise<SelectNotionDatabaseResponse> {
  return apiFetch<SelectNotionDatabaseResponse>(`/integrations/notion/databases/${databaseId}/select`, {
    token,
    method: 'POST',
    query: { database_type: databaseType },
    errorMessage: 'Failed to select database',
  });
}

/**
 * Test an integration connection
 */
export interface IntegrationTestResult {
  success: boolean;
  target_name: string;
  message: string;
  details?: Record<string, unknown>;
}

export async function testIntegrationConnection(token: string, targetName: string): Promise<IntegrationTestResult> {
  return apiFetch<IntegrationTestResult>(`/integrations/${targetName}/test`, {
    token,
    method: 'POST',
    errorMessage: 'Failed to test integration connection',
  });
}

/**
 * Delete an integration
 */
export async function deleteIntegration(token: string, targetName: string): Promise<SuccessMessageResponse> {
  return apiFetch<SuccessMessageResponse>(`/integrations/${targetName}`, {
    token,
    method: 'DELETE',
    errorMessage: 'Failed to delete integration',
  });
}

// ==================== Notebook Deletion ====================

export interface DeleteNotebookResponse {
  notebook_uuid: string;
  visible_name: string;
  pages_deleted: number;
  s3_files_deleted: number;
  sync_records_deleted: number;
  notion_cleanup: string;
}

export async function deleteNotebook(
  token: string,
  notebookId: number,
  cleanupNotion: boolean = false
): Promise<DeleteNotebookResponse> {
  return apiFetch<DeleteNotebookResponse>(`/notebooks/${notebookId}`, {
    token,
    method: 'DELETE',
    query: { cleanup_notion: cleanupNotion ? 'true' : undefined },
  });
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
  return apiFetch<QuotaStatus>('/quota/status', { token });
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
export async function getOnboardingProgress(token: string, signal?: AbortSignal): Promise<OnboardingProgress> {
  return apiFetch<OnboardingProgress>('/onboarding/progress', { token, signal });
}

/**
 * Dismiss the onboarding checklist
 */
export async function dismissOnboarding(token: string): Promise<void> {
  try {
    await apiFetch('/onboarding/dismiss', { token, method: 'POST', responseType: 'void' });
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

/**
 * Get waitlist entries (admin only)
 */
export async function getWaitlistAdmin(
  token: string,
  status?: string,
  skip?: number,
  limit?: number
): Promise<WaitlistAdminResponse> {
  return adminFetch<WaitlistAdminResponse>('/waitlist/admin', {
    token,
    query: { status: status || undefined, skip: skip || undefined, limit: limit || undefined },
  });
}

/**
 * Approve a single waitlist entry (admin only)
 */
export async function approveWaitlistEntry(
  token: string,
  entryId: number
): Promise<WaitlistEntry> {
  return apiFetch<WaitlistEntry>(`/waitlist/admin/${entryId}/approve`, { token, method: 'POST' });
}

/**
 * Approve multiple waitlist entries (admin only)
 */
export async function approveWaitlistBulk(
  token: string,
  ids: number[]
): Promise<{ approved: number; errors: Array<{ id: number; error: string }> }> {
  return apiFetch<{ approved: number; errors: Array<{ id: number; error: string }> }>(
    '/waitlist/admin/approve-bulk',
    { token, method: 'POST', body: { ids } }
  );
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
  return adminFetch<AdminUsersResponse>('/admin/users', {
    token,
    query: {
      skip: skip || undefined,
      limit: limit || undefined,
      sort_by: sortBy || undefined,
      sort_dir: sortDir || undefined,
    },
  });
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
  return apiFetch<SearchResponse>('/search', {
    token,
    query: {
      q: query,
      skip: options?.skip || undefined,
      limit: options?.limit || undefined,
      parent_uuid: options?.parentUuid || undefined,
      notebook_id: options?.notebookId || undefined,
      date_from: options?.dateFrom || undefined,
      date_to: options?.dateTo || undefined,
    },
  });
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
export async function getLegalStatus(token: string, signal?: AbortSignal): Promise<LegalStatus> {
  return apiFetch<LegalStatus>('/users/legal-status', { token, signal });
}

/**
 * Accept the current ToS and Privacy Policy
 */
export async function acceptTerms(token: string): Promise<LegalStatus> {
  return apiFetch<LegalStatus>('/users/accept-terms', { token, method: 'POST' });
}

// ==================== Obsidian Integration ====================

export interface ObsidianEnableResponse {
  api_key: string;
  enabled: boolean;
}

export interface ObsidianStatusResponse {
  enabled: boolean;
  last_sync: string | null;
  total_notebooks_synced: number;
  total_pages_synced: number;
  pending_notebooks: number;
}

export async function enableObsidian(token: string): Promise<ObsidianEnableResponse> {
  return apiFetch<ObsidianEnableResponse>('/integrations/obsidian/enable', {
    token,
    method: 'POST',
    fallbackMessage: 'Failed to enable Obsidian',
  });
}

export async function regenerateObsidianKey(token: string): Promise<ObsidianEnableResponse> {
  return apiFetch<ObsidianEnableResponse>('/integrations/obsidian/regenerate-key', {
    token,
    method: 'POST',
    fallbackMessage: 'Failed to regenerate key',
  });
}

export async function disableObsidian(token: string): Promise<void> {
  return apiFetch<void>('/integrations/obsidian/disable', {
    token,
    method: 'POST',
    responseType: 'void',
    fallbackMessage: 'Failed to disable Obsidian',
  });
}

export async function getObsidianStatus(token: string): Promise<ObsidianStatusResponse> {
  return apiFetch<ObsidianStatusResponse>('/integrations/obsidian/status', {
    token,
    fallbackMessage: 'Failed to get Obsidian status',
  });
}

// ==================== Todoist Integration ====================

export interface TodoistProject {
  id: string;
  name: string;
  is_inbox_project: boolean;
}

export interface TodoistStatus {
  connected: boolean;
  project_name: string | null;
  project_id: string | null;
  last_sync: string | null;
  todos_synced: number;
}

/** backend todoist.py `set_project` return value */
export interface SetTodoistProjectResponse extends SuccessMessageResponse {
  todos_queued: number;
}

export async function getTodoistOAuthUrl(token: string): Promise<OAuthUrlResponse> {
  return apiFetch<OAuthUrlResponse>('/integrations/todoist/oauth/authorize', {
    token,
    errorMessage: 'Failed to get Todoist OAuth URL',
  });
}

export async function todoistOAuthCallback(
  token: string,
  code: string,
  state: string
): Promise<SuccessMessageResponse> {
  return apiFetch<SuccessMessageResponse>('/integrations/todoist/oauth/callback', {
    token,
    method: 'POST',
    body: { code, state },
    errorMessage: 'Failed to complete Todoist OAuth',
  });
}

export async function getTodoistProjects(token: string): Promise<TodoistProject[]> {
  return apiFetch<TodoistProject[]>('/integrations/todoist/projects', {
    token,
    errorMessage: 'Failed to fetch Todoist projects',
  });
}

export async function setTodoistProject(
  token: string,
  projectId: string,
  projectName: string
): Promise<SetTodoistProjectResponse> {
  return apiFetch<SetTodoistProjectResponse>('/integrations/todoist/project', {
    token,
    method: 'POST',
    body: { project_id: projectId, project_name: projectName },
    errorMessage: 'Failed to set Todoist project',
  });
}

export async function getTodoistStatus(token: string): Promise<TodoistStatus> {
  return apiFetch<TodoistStatus>('/integrations/todoist/status', {
    token,
    errorMessage: 'Failed to get Todoist status',
  });
}

export async function createTodoistProject(token: string, name: string = 'reMarkable Notes'): Promise<TodoistProject> {
  return apiFetch<TodoistProject>('/integrations/todoist/projects/create', {
    token,
    method: 'POST',
    body: { name },
    errorMessage: 'Failed to create Todoist project',
  });
}

export async function disconnectTodoist(token: string): Promise<SuccessMessageResponse> {
  return apiFetch<SuccessMessageResponse>('/integrations/todoist/disconnect', {
    token,
    method: 'DELETE',
    errorMessage: 'Failed to disconnect Todoist',
  });
}

// ==================== Account ====================

/** backend services/account_service.py `get_data_summary` */
export interface AccountDataSummary {
  notebooks: number;
  pages: number;
  files: number;
  integrations: string[];
  member_since: string | null;
  subscription: string;
}

export async function getAccountDataSummary(token: string): Promise<AccountDataSummary> {
  return apiFetch<AccountDataSummary>('/account/data-summary', { token });
}

/** Download a ZIP of all the user's data */
export async function exportAccountData(token: string): Promise<DownloadedFile> {
  const response = await apiFetch<Response>('/account/export', {
    token,
    method: 'POST',
    responseType: 'response',
    errorMessage: 'Export failed',
  });
  return { blob: await response.blob(), filename: filenameFromResponse(response) };
}

/** Permanently delete the account; `confirmation` must be the exact phrase */
export async function deleteAccount(token: string, confirmation: string): Promise<void> {
  return apiFetch<void>('/account', {
    token,
    method: 'DELETE',
    body: { confirmation },
    responseType: 'void',
    fallbackMessage: 'Deletion failed',
  });
}
