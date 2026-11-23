import { render, screen, act, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  getLatestAgentVersion: vi.fn(),
  getAgentStatus: vi.fn(),
  getNotebooksTree: vi.fn(),
  trackAgentDownload: vi.fn(),
}));
vi.mock('@/lib/analytics', () => ({ trackEvent: vi.fn() }));

import SetupWizard from '../../app/dashboard/components/SetupWizard';
import { getAgentStatus, getLatestAgentVersion, getNotebooksTree, trackAgentDownload } from '@/lib/api';
import { trackEvent } from '@/lib/analytics';
import type { NotebookTreeNode } from '@/lib/api';

const mockVersion = vi.mocked(getLatestAgentVersion);
const mockStatus = vi.mocked(getAgentStatus);
const mockTree = vi.mocked(getNotebooksTree);

const connected = { agent_downloaded_at: '2026-11-20', agent_first_connected_at: '2026-11-20', first_notebook_synced_at: null };

function notebook(synced: number, total: number): NotebookTreeNode {
  return {
    id: 42,
    notebook_uuid: 'nb-42',
    visible_name: 'Meeting Notes',
    document_type: 'notebook',
    parent_uuid: null,
    full_path: null,
    created_at: '2026-11-23T10:00:00',
    last_synced_at: '2026-11-23T10:00:00',
    last_opened: null,
    is_folder: false,
    preview: null,
    sync_progress: { total_pages: total, synced_pages: synced, not_synced_pages: total - synced, pending_quota_pages: 0 },
    children: [],
  };
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function renderWizard(progress?: typeof connected) {
  const onComplete = vi.fn();
  render(<SetupWizard getToken={async () => 'token'} onComplete={onComplete} onboardingProgress={progress} />);
  return { onComplete };
}

describe('SetupWizard', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    mockVersion.mockResolvedValue({
      version: '2.0.0',
      platforms: { macos: { url: 'https://downloads.example/rMirror-2.0.0.dmg', min_os: '12.0' } },
    });
    mockStatus.mockResolvedValue({ has_agent_connected: false, first_connected_at: null, onboarding_state: 'signed_up' });
    mockTree.mockResolvedValue({ tree: [], total: 0 });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('shows download and install on one screen with labelled progress', async () => {
    renderWizard();
    await advance(0);

    for (const label of ['Download', 'Connect', 'Sync', 'Done']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText(/reMarkable desktop app installed and synced/i)).toBeInTheDocument();
    expect(screen.getByText('Open rMirror')).toBeInTheDocument();
    expect(screen.queryByText(/Web UI/i)).not.toBeInTheDocument();
    expect(screen.getByText(/macOS will ask if you want to open rMirror/i)).toBeInTheDocument();
    expect(screen.getByText(/permission to read your reMarkable folder/i)).toBeInTheDocument();
    expect(screen.getByText(/Waiting for your Mac to connect/i)).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();

    const download = screen.getByRole('link', { name: /download for macos/i });
    expect(download).toHaveAttribute('href', 'https://downloads.example/rMirror-2.0.0.dmg');
    fireEvent.click(download);
    await advance(0);

    expect(trackEvent).toHaveBeenCalledWith({ name: 'agent_downloaded' });
    expect(trackAgentDownload).toHaveBeenCalledWith('token');
    expect(screen.getByRole('link', { name: /download again/i })).toBeInTheDocument();
  });

  it('says the download is unavailable instead of linking an old version', async () => {
    mockVersion.mockRejectedValue(new Error('down'));
    renderWizard();
    await advance(0);

    expect(screen.getByText(/Download is temporarily unavailable/i)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /download for macos/i })).not.toBeInTheDocument();
  });

  it('moves to the sync step once the Mac app connects', async () => {
    renderWizard();
    await advance(0);
    expect(screen.queryByText(/Waiting for your first notebook/i)).not.toBeInTheDocument();

    mockStatus.mockResolvedValue({ has_agent_connected: true, first_connected_at: '2026-11-23', onboarding_state: 'agent_connected' });
    await advance(5000);
    expect(screen.getByText('Mac connected')).toBeInTheDocument();

    await advance(1500);
    expect(screen.getByText(/Waiting for your first notebook/i)).toBeInTheDocument();
  });

  it('waits for the first notebook and shows help after two minutes', async () => {
    renderWizard(connected);
    await advance(0);

    expect(screen.getByText(/Waiting for your first notebook/i)).toBeInTheDocument();
    expect(screen.queryByText(/You're All Set/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/Nothing has arrived yet/i)).not.toBeInTheDocument();

    await advance(120_000);
    expect(screen.getByText(/Nothing has arrived yet/i)).toBeInTheDocument();
    expect(screen.queryByText(/You're All Set/i)).not.toBeInTheDocument();
    expect(mockTree.mock.calls.length).toBeGreaterThan(20);
  });

  it('shows upload progress, then advances to a success screen linking the notebook', async () => {
    mockTree.mockResolvedValue({ tree: [notebook(4, 12)], total: 1 });
    const { onComplete } = renderWizard(connected);
    await advance(0);

    expect(screen.getByText(/4 of 12 pages uploaded/i)).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4');

    mockTree.mockResolvedValue({ tree: [notebook(12, 12)], total: 1 });
    await advance(5000);

    expect(screen.getByText(/You're All Set/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open meeting notes/i })).toHaveAttribute('href', '/notebooks/42');
    fireEvent.click(screen.getByRole('button', { name: /go to all notebooks/i }));
    expect(onComplete).toHaveBeenCalled();
  });

  it('lets the user continue by hand while a notebook is still uploading', async () => {
    mockTree.mockResolvedValue({ tree: [notebook(3, 50)], total: 1 });
    renderWizard(connected);
    await advance(0);

    fireEvent.click(screen.getByRole('button', { name: /continue/i }));
    expect(screen.getByText(/You're All Set/i)).toBeInTheDocument();
  });

  it('stops polling when unmounted', async () => {
    const { unmount } = render(
      <SetupWizard getToken={async () => 'token'} onComplete={() => {}} onboardingProgress={connected} />
    );
    await advance(0);
    unmount();
    const calls = mockTree.mock.calls.length;
    await advance(30_000);
    expect(mockTree.mock.calls.length).toBe(calls);
  });
});
