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
  /** All known pages of this notebook have reached the server. */
  complete: boolean;
}

export type FirstSyncState =
  /** No page has reached the server yet. */
  | { phase: 'waiting'; showHelp: boolean }
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
    complete: total > 0 && uploaded >= total,
  };
}

/**
 * Notebooks that have at least one page on the server, newest first. A
 * notebook created by a metadata-only sync has pages in `not_synced` state
 * and does not count: nothing the user can read has arrived yet.
 */
export function notebooksWithPages(tree: NotebookTreeNode[]): NotebookUpload[] {
  return flattenNotebooks(tree)
    .filter((n) => (n.sync_progress?.synced_pages ?? 0) > 0)
    .sort((a, b) => timestamp(b) - timestamp(a))
    .map(toUpload);
}

/**
 * What the sync step shows, from the latest notebook tree and the time spent
 * waiting. The wizard advances to `done` on `arrived`; while `uploading`, the
 * user may also continue by hand (a page limit in the Mac app can leave a
 * notebook partly uploaded for good).
 */
export function firstSyncState(tree: NotebookTreeNode[] | null, waitedMs: number): FirstSyncState {
  const uploads = tree ? notebooksWithPages(tree) : [];
  if (uploads.length === 0) {
    return { phase: 'waiting', showHelp: waitedMs >= FIRST_SYNC_HELP_AFTER_MS };
  }
  const complete = uploads.find((u) => u.complete);
  if (complete) return { phase: 'arrived', upload: complete };
  return { phase: 'uploading', upload: uploads[0] };
}
