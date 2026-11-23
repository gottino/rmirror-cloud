import type { NotebookTreeNode } from './api';

/**
 * Setup wizard state, kept free of React so it can be tested directly.
 *
 * Steps: `download` and `connect` share one screen (download button on top,
 * install steps and "waiting for your Mac" below); `sync` waits for the first
 * notebook to arrive; `done` is only reachable once real data exists.
 */
export type WizardStep = 'download' | 'connect' | 'sync' | 'done';

export const WIZARD_STEPS: { step: WizardStep; label: string }[] = [
  { step: 'download', label: 'Download' },
  { step: 'connect', label: 'Connect' },
  { step: 'sync', label: 'Sync' },
  { step: 'done', label: 'Done' },
];

export function stepIndex(step: WizardStep): number {
  return WIZARD_STEPS.findIndex((s) => s.step === step);
}

/** Polling interval for the connect and sync steps. */
export const WIZARD_POLL_MS = 5000;

/** Show troubleshooting help when nothing has arrived after this long. */
export const FIRST_SYNC_HELP_AFTER_MS = 2 * 60 * 1000;

export interface WizardProgress {
  agent_downloaded_at: string | null;
  agent_first_connected_at: string | null;
  first_notebook_synced_at: string | null;
}

/** Resume at the right step after a refresh, from the backend's milestones. */
export function initialWizardStep(progress?: WizardProgress): WizardStep {
  if (progress?.agent_first_connected_at) return 'sync';
  if (progress?.agent_downloaded_at) return 'connect';
  return 'download';
}

export interface NotebookUpload {
  id: number;
  name: string;
  uploadedPages: number;
  totalPages: number;
  /** Uploaded pages waiting for next month's OCR allowance. */
  pendingQuotaPages: number;
  lastSyncedAt: string | null;
  /** All known pages of this notebook have reached the server. */
  complete: boolean;
}

/** Notebooks with pages already on the server when the sync step opened. */
export type SyncBaseline = Map<number, { lastSyncedAt: string | null; uploadedPages: number }>;

/** Consecutive failed tree fetches before the "can't reach" notice. */
export const FETCH_FAILURES_BEFORE_NOTICE = 3;

export type FirstSyncState =
  /**
   * Nothing new has reached the server since the step opened. `existing` is
   * the newest notebook that was already there (re-running setup);
   * `unreachable` means the server has not answered several polls in a row.
   */
  | { phase: 'waiting'; showHelp: boolean; unreachable: boolean; existing: NotebookUpload | null }
  /** Pages are arriving; `upload` is the notebook to show progress for. */
  | { phase: 'uploading'; upload: NotebookUpload }
  /** A notebook finished uploading: the wizard can move to `done`. */
  | { phase: 'arrived'; upload: NotebookUpload };

function flattenNotebooks(nodes: NotebookTreeNode[], out: NotebookTreeNode[] = []): NotebookTreeNode[] {
  for (const node of nodes) {
    if (!node.is_folder && node.document_type === 'notebook') out.push(node);
    if (node.children?.length) flattenNotebooks(node.children, out);
  }
  return out;
}

function timestamp(node: NotebookTreeNode): number {
  const value = node.last_synced_at || node.created_at;
  return value ? new Date(value).getTime() || 0 : 0;
}

function toUpload(node: NotebookTreeNode): NotebookUpload {
  const total = node.sync_progress?.total_pages ?? 0;
  const uploaded = node.sync_progress?.synced_pages ?? 0;
  return {
    id: node.id,
    name: node.visible_name,
    uploadedPages: uploaded,
    totalPages: total,
    pendingQuotaPages: node.sync_progress?.pending_quota_pages ?? 0,
    lastSyncedAt: node.last_synced_at,
    complete: total > 0 && uploaded >= total,
  };
}

/**
 * Notebooks that have at least one page on the server, newest first. A
 * notebook created by a metadata-only sync (POST /sync/metadata) has pages in
 * `not_synced` state and does not count: nothing the user can read has
 * arrived yet.
 */
export function notebooksWithPages(tree: NotebookTreeNode[]): NotebookUpload[] {
  return flattenNotebooks(tree)
    .filter((n) => (n.sync_progress?.synced_pages ?? 0) > 0)
    .sort((a, b) => timestamp(b) - timestamp(a))
    .map(toUpload);
}

/**
 * The dashboard shows the wizard until a page has actually been uploaded
 * (notebook rows from a metadata-only sync are not enough), or when the user
 * asked for it with ?setup=1.
 */
export function shouldShowSetupWizard(tree: NotebookTreeNode[], setupRequested: boolean): boolean {
  return setupRequested || notebooksWithPages(tree).length === 0;
}

export function syncBaseline(tree: NotebookTreeNode[]): SyncBaseline {
  return new Map(
    notebooksWithPages(tree).map((u) => [u.id, { lastSyncedAt: u.lastSyncedAt, uploadedPages: u.uploadedPages }])
  );
}

function isNewSinceBaseline(upload: NotebookUpload, baseline: SyncBaseline): boolean {
  const before = baseline.get(upload.id);
  if (!before) return true;
  return before.lastSyncedAt !== upload.lastSyncedAt || upload.uploadedPages > before.uploadedPages;
}

export interface FirstSyncInput {
  /** Latest notebook tree, null before the first successful fetch. */
  tree: NotebookTreeNode[] | null;
  /** Snapshot from the first successful fetch of this step. */
  baseline: SyncBaseline | null;
  waitedMs: number;
  /** Consecutive failed fetches. */
  fetchFailures: number;
}

/**
 * What the sync step shows. Only notebooks that are new, or changed since the
 * step opened, count as arriving, so re-running setup does not jump straight
 * to `done`. The wizard advances on `arrived`; while `uploading`, the user may
 * also continue by hand (a page limit in the Mac app can leave a notebook
 * partly uploaded for good).
 */
export function firstSyncState({ tree, baseline, waitedMs, fetchFailures }: FirstSyncInput): FirstSyncState {
  const uploads = tree ? notebooksWithPages(tree) : [];
  const fresh = baseline ? uploads.filter((u) => isNewSinceBaseline(u, baseline)) : [];
  if (fresh.length === 0) {
    const unreachable = fetchFailures >= FETCH_FAILURES_BEFORE_NOTICE;
    const existing = baseline && uploads.length > 0 ? uploads[0] : null;
    return {
      phase: 'waiting',
      showHelp: !unreachable && !existing && waitedMs >= FIRST_SYNC_HELP_AFTER_MS,
      unreachable,
      existing,
    };
  }
  const complete = fresh.find((u) => u.complete);
  if (complete) return { phase: 'arrived', upload: complete };
  return { phase: 'uploading', upload: fresh[0] };
}

/** The file name a download link ends in ("rMirror-2.0.0-arm64.dmg"), or null if it has none. */
export function downloadFileName(url: string | undefined | null): string | null {
  if (!url) return null;
  try {
    const last = new URL(url).pathname.split('/').filter(Boolean).pop();
    return last ? decodeURIComponent(last) : null;
  } catch {
    return null;
  }
}

/** "macOS 13 or later" from a minimum version such as "13.0"; null when unknown. */
export function minimumMacOSLabel(minOs: string | undefined | null): string | null {
  const match = minOs?.trim().match(/^(\d+)(?:\.(\d+))?/);
  if (!match) return null;
  const minor = match[2] && match[2] !== '0' ? `.${match[2]}` : '';
  return `macOS ${match[1]}${minor} or later`;
}

/** The pages line on the sync step. Uses the account's real allowance, never a fixed number. */
export function allowanceLine(quota: { limit: number; remaining: number } | null | undefined): string {
  if (!quota || quota.limit <= 0) {
    return 'Start with a few notebooks. You can always sync more later.';
  }
  const remaining = Math.max(0, quota.remaining);
  if (remaining === 0) {
    return 'You have no pages left this month. Notebooks you sync now are turned into text when your pages reset.';
  }
  return `You have ${remaining} of ${quota.limit} pages left this month. rMirror suggests notebooks that fit, and you can always sync more later.`;
}
