import { describe, it, expect } from 'vitest';
import {
  FIRST_SYNC_HELP_AFTER_MS,
  WIZARD_STEPS,
  firstSyncState,
  initialWizardStep,
  notebooksWithPages,
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

describe('firstSyncState', () => {
  it('waits while there are no notebooks', () => {
    expect(firstSyncState(null, 0)).toEqual({ phase: 'waiting', showHelp: false });
    expect(firstSyncState([], 30_000)).toEqual({ phase: 'waiting', showHelp: false });
  });

  it('shows help after two minutes without anything arriving', () => {
    expect(firstSyncState([], FIRST_SYNC_HELP_AFTER_MS - 1).phase).toBe('waiting');
    expect(firstSyncState([], FIRST_SYNC_HELP_AFTER_MS - 1)).toMatchObject({ showHelp: false });
    expect(firstSyncState([], FIRST_SYNC_HELP_AFTER_MS)).toEqual({ phase: 'waiting', showHelp: true });
  });

  it('keeps waiting for notebooks created by a metadata-only sync (no pages uploaded)', () => {
    const tree = [node({ sync_progress: progress(0, 12) }), node({ id: 2, is_folder: true, document_type: 'folder' })];
    expect(firstSyncState(tree, 0).phase).toBe('waiting');
  });

  it('shows upload progress once the first pages arrive', () => {
    const tree = [node({ sync_progress: progress(4, 12) })];
    expect(firstSyncState(tree, 0)).toEqual({
      phase: 'uploading',
      upload: { id: 1, name: 'Meeting Notes', uploadedPages: 4, totalPages: 12, complete: false },
    });
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
    expect(firstSyncState(tree, 0)).toEqual({
      phase: 'arrived',
      upload: { id: 3, name: 'Book Club', uploadedPages: 8, totalPages: 8, complete: true },
    });
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
