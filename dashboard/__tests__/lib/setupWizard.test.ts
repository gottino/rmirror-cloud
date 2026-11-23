import { describe, it, expect } from 'vitest';
import {
  FETCH_FAILURES_BEFORE_NOTICE,
  FIRST_SYNC_HELP_AFTER_MS,
  WIZARD_STEPS,
  firstSyncState,
  initialWizardStep,
  notebooksWithPages,
  shouldShowSetupWizard,
  syncBaseline,
  type FirstSyncInput,
  type SyncBaseline,
} from '../../lib/setupWizard';
import type { NotebookTreeNode } from '../../lib/api';

function node(overrides: Partial<NotebookTreeNode> = {}): NotebookTreeNode {
  return {
    id: 1,
    notebook_uuid: 'nb-1',
    visible_name: 'Meeting Notes',
    document_type: 'notebook',
    parent_uuid: null,
    full_path: null,
    created_at: '2026-11-20T10:00:00',
    last_synced_at: '2026-11-20T10:00:00',
    last_opened: null,
    is_folder: false,
    preview: null,
    sync_progress: null,
    children: [],
    ...overrides,
  };
}

function progress(synced: number, total: number) {
  return { total_pages: total, synced_pages: synced, not_synced_pages: total - synced, pending_quota_pages: 0 };
}

describe('WIZARD_STEPS', () => {
  it('labels every progress step', () => {
    expect(WIZARD_STEPS.map((s) => s.label)).toEqual(['Download', 'Connect', 'Sync', 'Done']);
  });
});

describe('initialWizardStep', () => {
  it('starts at download for a new user', () => {
    expect(initialWizardStep()).toBe('download');
    expect(
      initialWizardStep({ agent_downloaded_at: null, agent_first_connected_at: null, first_notebook_synced_at: null })
    ).toBe('download');
  });

  it('resumes at connect after a download', () => {
    expect(
      initialWizardStep({ agent_downloaded_at: '2026-11-20', agent_first_connected_at: null, first_notebook_synced_at: null })
    ).toBe('connect');
  });

  it('resumes at sync once the Mac app connected, never at done', () => {
    expect(
      initialWizardStep({
        agent_downloaded_at: '2026-11-20',
        agent_first_connected_at: '2026-11-20',
        first_notebook_synced_at: '2026-11-20',
      })
    ).toBe('sync');
  });
});

const EMPTY = new Map() as SyncBaseline;
const state = (tree: NotebookTreeNode[] | null, extra: Partial<FirstSyncInput> = {}) =>
  firstSyncState({ tree, baseline: tree ? EMPTY : null, waitedMs: 0, fetchFailures: 0, ...extra });

function upload(id: number, name: string, uploaded: number, total: number, lastSyncedAt = '2026-11-20T10:00:00') {
  return { id, name, uploadedPages: uploaded, totalPages: total, pendingQuotaPages: 0, lastSyncedAt, complete: uploaded >= total };
}

describe('firstSyncState', () => {
  it('waits while there are no notebooks', () => {
    expect(state(null)).toEqual({ phase: 'waiting', showHelp: false, unreachable: false, existing: null });
    expect(state([], { waitedMs: 30_000 })).toEqual({ phase: 'waiting', showHelp: false, unreachable: false, existing: null });
  });

  it('shows help after two minutes without anything arriving', () => {
    expect(state([], { waitedMs: FIRST_SYNC_HELP_AFTER_MS - 1 })).toMatchObject({ phase: 'waiting', showHelp: false });
    expect(state([], { waitedMs: FIRST_SYNC_HELP_AFTER_MS })).toMatchObject({ phase: 'waiting', showHelp: true });
  });

  it('says the server is unreachable after repeated failed fetches, instead of blaming the Mac', () => {
    expect(state(null, { fetchFailures: FETCH_FAILURES_BEFORE_NOTICE - 1 })).toMatchObject({ unreachable: false });
    expect(state(null, { fetchFailures: FETCH_FAILURES_BEFORE_NOTICE, waitedMs: FIRST_SYNC_HELP_AFTER_MS })).toEqual({
      phase: 'waiting',
      showHelp: false,
      unreachable: true,
      existing: null,
    });
  });

  it('keeps waiting for notebooks created by a metadata-only sync (no pages uploaded)', () => {
    const tree = [node({ sync_progress: progress(0, 12) }), node({ id: 2, is_folder: true, document_type: 'folder' })];
    expect(state(tree).phase).toBe('waiting');
  });

  it('shows upload progress once the first pages arrive', () => {
    const tree = [node({ sync_progress: progress(4, 12) })];
    expect(state(tree)).toEqual({ phase: 'uploading', upload: upload(1, 'Meeting Notes', 4, 12) });
  });

  it('advances when a notebook has fully arrived, including inside folders', () => {
    const tree = [
      node({
        id: 10,
        is_folder: true,
        document_type: 'folder',
        children: [node({ id: 3, visible_name: 'Book Club', sync_progress: progress(8, 8) })],
      }),
      node({ id: 1, sync_progress: progress(2, 12), last_synced_at: '2026-11-21T10:00:00' }),
    ];
    expect(state(tree)).toEqual({ phase: 'arrived', upload: upload(3, 'Book Club', 8, 8) });
  });

  it('counts nothing as arriving before the first snapshot exists', () => {
    const tree = [node({ sync_progress: progress(8, 8) })];
    expect(firstSyncState({ tree, baseline: null, waitedMs: 0, fetchFailures: 0 }).phase).toBe('waiting');
  });

  describe('re-running setup with notebooks already synced', () => {
    const before = [node({ id: 1, sync_progress: progress(8, 8), last_synced_at: '2026-11-01T10:00:00' })];
    const baseline = syncBaseline(before);

    it('does not jump to done, and says the notebooks are already here', () => {
      expect(firstSyncState({ tree: before, baseline, waitedMs: FIRST_SYNC_HELP_AFTER_MS, fetchFailures: 0 })).toEqual({
        phase: 'waiting',
        showHelp: false,
        unreachable: false,
        existing: upload(1, 'Meeting Notes', 8, 8, '2026-11-01T10:00:00'),
      });
    });

    it('advances for a new notebook', () => {
      const tree = [...before, node({ id: 2, visible_name: 'Travel', sync_progress: progress(3, 3) })];
      expect(firstSyncState({ tree, baseline, waitedMs: 0, fetchFailures: 0 })).toMatchObject({
        phase: 'arrived',
        upload: { id: 2 },
      });
    });

    it('advances for an existing notebook synced again', () => {
      const tree = [node({ id: 1, sync_progress: progress(9, 9), last_synced_at: '2026-11-23T10:00:00' })];
      expect(firstSyncState({ tree, baseline, waitedMs: 0, fetchFailures: 0 })).toMatchObject({
        phase: 'arrived',
        upload: { id: 1, uploadedPages: 9 },
      });
    });
  });
});

describe('shouldShowSetupWizard', () => {
  it('shows the wizard while only metadata-sync stubs exist', () => {
    const stubs = [node({ sync_progress: progress(0, 12) }), node({ id: 2, sync_progress: progress(0, 3) })];
    expect(shouldShowSetupWizard([], false)).toBe(true);
    expect(shouldShowSetupWizard(stubs, false)).toBe(true);
  });

  it('hides it once a page has been uploaded, unless setup was requested', () => {
    const tree = [node({ sync_progress: progress(1, 12) })];
    expect(shouldShowSetupWizard(tree, false)).toBe(false);
    expect(shouldShowSetupWizard(tree, true)).toBe(true);
  });
});

describe('notebooksWithPages', () => {
  it('orders notebooks with uploaded pages newest first', () => {
    const tree = [
      node({ id: 1, visible_name: 'Old', sync_progress: progress(1, 1), last_synced_at: '2026-11-01T10:00:00' }),
      node({ id: 2, visible_name: 'New', sync_progress: progress(1, 3), last_synced_at: '2026-11-22T10:00:00' }),
      node({ id: 3, visible_name: 'Empty', sync_progress: progress(0, 3), last_synced_at: '2026-11-23T10:00:00' }),
    ];
    expect(notebooksWithPages(tree).map((u) => u.name)).toEqual(['New', 'Old']);
  });
});
