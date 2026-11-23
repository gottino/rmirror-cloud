'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  Download,
  CheckCircle,
  Monitor,
  Loader2,
  ArrowRight,
  ArrowLeft,
  ExternalLink,
  FolderOpen,
  ShieldCheck,
  KeyRound,
  Info,
} from 'lucide-react';
import {
  getLatestAgentVersion,
  getAgentStatus,
  getNotebooksTree,
  trackAgentDownload,
  type AgentVersionInfo,
  type NotebookTreeNode,
} from '@/lib/api';
import { useApiQuery } from '@/lib/useApiQuery';
import { trackEvent } from '@/lib/analytics';
import { DOWNLOAD_UNAVAILABLE_MESSAGE } from '@/lib/agentDownload';
import {
  WIZARD_STEPS,
  WIZARD_POLL_MS,
  firstSyncState,
  initialWizardStep,
  stepIndex,
  type NotebookUpload,
  type WizardProgress,
  type WizardStep,
} from '@/lib/setupWizard';

interface SetupWizardProps {
  getToken: () => Promise<string | null>;
  onComplete: () => void;
  onboardingProgress?: WizardProgress;
}

const headingStyle = { color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' };
const panelStyle = { background: 'var(--warm-bg)', border: '1px solid var(--warm-border)' };

function StepNumber({ n }: { n: number }) {
  return (
    <span
      className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold"
      style={{ background: 'var(--terracotta)', color: 'white' }}
    >
      {n}
    </span>
  );
}

function ProgressSteps({ current }: { current: WizardStep }) {
  const currentIndex = stepIndex(current);
  return (
    <ol className="flex items-start gap-2 mb-12" aria-label="Setup progress">
      {WIZARD_STEPS.map(({ step, label }, index) => {
        const reached = currentIndex >= index;
        const done = currentIndex > index;
        return (
          <li key={step} className="flex items-start gap-2" aria-current={index === currentIndex ? 'step' : undefined}>
            <div className="flex flex-col items-center gap-1.5 w-16">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all"
                style={{
                  background: reached ? 'var(--terracotta)' : 'var(--warm-bg)',
                  color: reached ? 'white' : 'var(--warm-gray)',
                  border: reached ? 'none' : '2px solid var(--warm-border)',
                }}
              >
                {done ? <CheckCircle className="w-4 h-4" /> : index + 1}
              </div>
              <span
                className="text-xs"
                style={{
                  color: reached ? 'var(--warm-charcoal)' : 'var(--warm-gray)',
                  fontWeight: index === currentIndex ? 600 : 400,
                }}
              >
                {label}
              </span>
            </div>
            {index < WIZARD_STEPS.length - 1 && (
              <div
                className="w-6 h-0.5 mt-4"
                style={{ background: done ? 'var(--terracotta)' : 'var(--warm-border)' }}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

export default function SetupWizard({ getToken, onComplete, onboardingProgress }: SetupWizardProps) {
  // Derived from backend milestones so a refresh resumes at the right step
  const [step, setStep] = useState<WizardStep>(() => initialWizardStep(onboardingProgress));
  const [agentConnected, setAgentConnected] = useState(false);
  const [tree, setTree] = useState<NotebookTreeNode[] | null>(null);
  const [syncStartedAt, setSyncStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [arrived, setArrived] = useState<NotebookUpload | null>(null);

  const versionQuery = useApiQuery<AgentVersionInfo>('agent-version', (signal) => getLatestAgentVersion(signal));
  const macosUrl = versionQuery.data?.platforms.macos?.url;
  const version = versionQuery.data?.version;

  // Download + Connect screen: poll for the Mac app from the moment it is shown
  useEffect(() => {
    if (step !== 'download' && step !== 'connect') return;
    let cancelled = false;
    let interval: ReturnType<typeof setInterval> | undefined;
    let advanceTimer: ReturnType<typeof setTimeout> | undefined;

    const checkAgent = async () => {
      try {
        const token = await getToken();
        if (!token || cancelled) return;
        const status = await getAgentStatus(token);
        if (cancelled || !status.has_agent_connected) return;
        setAgentConnected(true);
        clearInterval(interval);
        // Brief "Mac connected" confirmation before moving on
        advanceTimer = setTimeout(() => setStep('sync'), 1500);
      } catch {
        // Retry on the next poll
      }
    };

    void checkAgent();
    interval = setInterval(checkAgent, WIZARD_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
      if (advanceTimer) clearTimeout(advanceTimer);
    };
  }, [step, getToken]);

  // Sync screen: poll the notebook tree until the first notebook arrives
  useEffect(() => {
    if (step !== 'sync') return;
    let cancelled = false;
    const started = Date.now();
    setSyncStartedAt(started);
    setNow(started);

    const checkNotebooks = async () => {
      try {
        const token = await getToken();
        if (!token || cancelled) return;
        const data = await getNotebooksTree(token);
        if (!cancelled) setTree(data.tree);
      } catch {
        // Retry on the next poll
      } finally {
        if (!cancelled) setNow(Date.now());
      }
    };

    void checkNotebooks();
    const interval = setInterval(checkNotebooks, WIZARD_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [step, getToken]);

  const syncState = step === 'sync' ? firstSyncState(tree, syncStartedAt ? now - syncStartedAt : 0) : null;

  const finishWith = useCallback((upload: NotebookUpload) => {
    setArrived(upload);
    setStep('done');
  }, []);

  // Advance on its own once a notebook has fully arrived
  const arrivedUpload = syncState?.phase === 'arrived' ? syncState.upload : null;
  useEffect(() => {
    if (arrivedUpload) finishWith(arrivedUpload);
  }, [arrivedUpload, finishWith]);

  const handleDownloadClick = useCallback(() => {
    // The <a href> starts the download; this only records it and moves on
    setStep('connect');
    trackEvent({ name: 'agent_downloaded' });
    void (async () => {
      const token = await getToken();
      if (token) await trackAgentDownload(token);
    })();
  }, [getToken]);

  const onInstallScreen = step === 'download' || step === 'connect';

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-12">
      <ProgressSteps current={step} />

      <div className="w-full max-w-lg">
        {onInstallScreen && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: agentConnected ? '#e8f0ea' : '#f5e6e5' }}>
              {agentConnected ? (
                <CheckCircle className="w-8 h-8" style={{ color: 'var(--sage-green)' }} />
              ) : (
                <Monitor className="w-8 h-8" style={{ color: 'var(--terracotta)' }} />
              )}
            </div>
            <h2 className="text-2xl font-bold mb-3" style={headingStyle}>
              {agentConnected ? 'Mac connected' : 'Install rMirror for Mac'}
            </h2>
            <p className="text-base mb-6" style={{ color: agentConnected ? 'var(--sage-green)' : 'var(--warm-gray)' }}>
              {agentConnected
                ? 'rMirror is running and connected to your account.'
                : 'Your reMarkable notebooks, searchable and synced to Notion. Setup takes a few minutes.'}
            </p>

            {!agentConnected && (
              <>
                <p className="text-sm mb-4 flex items-center justify-center gap-1.5" style={{ color: 'var(--warm-charcoal)' }}>
                  <Info className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--warm-gray)' }} />
                  Before you start: have the reMarkable desktop app installed and synced on this Mac.
                </p>

                <div className="rounded-xl p-6 mb-6" style={panelStyle}>
                  {macosUrl ? (
                    <>
                      <a
                        href={macosUrl}
                        onClick={handleDownloadClick}
                        className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105"
                        style={{ background: 'var(--terracotta)', color: 'white' }}
                      >
                        <Download className="w-5 h-5" />
                        Download for macOS
                      </a>
                      {version && (
                        <p className="text-xs mt-3" style={{ color: 'var(--warm-gray)' }}>
                          Version {version} &middot; macOS 12+ &middot; Windows support coming soon
                        </p>
                      )}
                      {step === 'connect' && (
                        <p className="text-sm mt-3" style={{ color: 'var(--warm-gray)' }}>
                          Download didn&apos;t start?{' '}
                          <a href={macosUrl} onClick={handleDownloadClick} className="underline" style={{ color: 'var(--terracotta)' }}>
                            Download again
                          </a>
                        </p>
                      )}
                    </>
                  ) : versionQuery.error ? (
                    <div role="alert">
                      <p className="text-sm mb-3" style={{ color: 'var(--warning-text)' }}>{DOWNLOAD_UNAVAILABLE_MESSAGE}</p>
                      <button
                        onClick={() => void versionQuery.reload()}
                        className="text-sm underline hover:opacity-80"
                        style={{ color: 'var(--terracotta)' }}
                      >
                        Try again
                      </button>
                    </div>
                  ) : (
                    <button
                      disabled
                      className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium opacity-50"
                      style={{ background: 'var(--terracotta)', color: 'white' }}
                    >
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Download for macOS
                    </button>
                  )}
                </div>

                <div className="text-left rounded-xl p-6 mb-4" style={panelStyle}>
                  <ol className="space-y-4">
                    <li className="flex gap-3">
                      <StepNumber n={1} />
                      <div>
                        <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Open the downloaded file</p>
                        <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                          Double-click{' '}
                          <code className="px-1 py-0.5 rounded text-xs" style={{ background: 'var(--warm-border)' }}>
                            rMirror-{version || '…'}.dmg
                          </code>{' '}
                          in your Downloads folder
                        </p>
                      </div>
                    </li>
                    <li className="flex gap-3">
                      <StepNumber n={2} />
                      <div>
                        <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Drag rMirror to Applications</p>
                      </div>
                    </li>
                    <li className="flex gap-3">
                      <StepNumber n={3} />
                      <div>
                        <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Open rMirror</p>
                        <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                          Start it from Applications. Its window opens by itself the first time; later, click the
                          rMirror icon in the menu bar and choose &quot;Open rMirror&quot;.
                        </p>
                      </div>
                    </li>
                    <li className="flex gap-3">
                      <StepNumber n={4} />
                      <div>
                        <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Sign in</p>
                        <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                          Click &quot;Sign In&quot; in the rMirror window and sign in with this account in your browser.
                        </p>
                      </div>
                    </li>
                  </ol>
                </div>

                <div
                  className="text-left rounded-xl p-5 mb-4 flex gap-3"
                  style={{ background: 'var(--warning-light)', border: '1px solid var(--warning-border)' }}
                >
                  <ShieldCheck className="w-6 h-6 flex-shrink-0" style={{ color: 'var(--warning-accent)' }} />
                  <div>
                    <p className="font-medium mb-1" style={{ color: 'var(--warning-text)' }}>
                      macOS will ask if you want to open rMirror
                    </p>
                    <p className="text-sm" style={{ color: 'var(--warning-text)' }}>
                      Because rMirror comes from the internet, macOS asks &quot;Are you sure you want to open it?&quot;
                      the first time. Click &quot;Open&quot;. rMirror is signed and notarized by Apple.
                    </p>
                  </div>
                </div>

                <div className="text-left rounded-xl p-5 mb-6 flex gap-3" style={panelStyle}>
                  <KeyRound className="w-6 h-6 flex-shrink-0" style={{ color: 'var(--terracotta)' }} />
                  <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                    rMirror will ask for permission to read your reMarkable folder (Full Disk Access in System Settings).
                    It needs this to find your notebooks, and the app guides you through each step.
                  </p>
                </div>

                <div className="flex items-center justify-center gap-2 mb-6" style={{ color: 'var(--warm-gray)' }} role="status">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Waiting for your Mac to connect…</span>
                </div>

                <div className="flex justify-end">
                  <button
                    onClick={() => setStep('sync')}
                    className="text-sm underline hover:opacity-80"
                    style={{ color: 'var(--warm-gray)' }}
                  >
                    I already have rMirror installed and signed in
                  </button>
                </div>
              </>
            )}
          </div>
        )}

        {step === 'sync' && syncState && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: '#f5e6e5' }}>
              <FolderOpen className="w-8 h-8" style={{ color: 'var(--terracotta)' }} />
            </div>
            <h2 className="text-2xl font-bold mb-3" style={headingStyle}>
              Sync your first notebooks
            </h2>
            <p className="text-base mb-6" style={{ color: 'var(--warm-gray)' }}>
              In the rMirror window on your Mac, press the &quot;Sync&quot; button (it shows how many notebooks
              it will send). Can&apos;t see the window? Click the rMirror icon in the menu bar and choose
              &quot;Open rMirror&quot;.
            </p>

            <div className="rounded-xl p-6 mb-6 text-left" style={panelStyle} role="status" aria-live="polite">
              {syncState.phase === 'waiting' ? (
                <div className="flex items-center justify-center gap-2" style={{ color: 'var(--warm-gray)' }}>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Waiting for your first notebook…</span>
                </div>
              ) : (
                <UploadProgress upload={syncState.upload} />
              )}
            </div>

            {syncState.phase === 'waiting' && syncState.showHelp && (
              <div
                className="rounded-xl p-5 mb-6 text-left"
                style={{ background: 'var(--warning-light)', border: '1px solid var(--warning-border)' }}
              >
                <p className="font-medium mb-2" style={{ color: 'var(--warning-text)' }}>
                  Nothing has arrived yet. Please check:
                </p>
                <ul className="text-sm space-y-1.5 list-disc pl-5" style={{ color: 'var(--warning-text)' }}>
                  <li>rMirror is open on your Mac: click its menu bar icon and choose &quot;Open rMirror&quot;.</li>
                  <li>You pressed the &quot;Sync&quot; button in the rMirror window.</li>
                  <li>
                    rMirror is allowed to read your reMarkable folder. If it asked for Full Disk Access, finish its
                    steps in System Settings.
                  </li>
                  <li>The reMarkable desktop app is installed and has synced your notebooks to this Mac.</li>
                </ul>
                <p className="text-sm mt-3" style={{ color: 'var(--warning-text)' }}>
                  Still stuck? Write to{' '}
                  <a href="mailto:support@rmirror.io" className="underline">support@rmirror.io</a>.
                </p>
              </div>
            )}

            {syncState.phase === 'uploading' && (
              <button
                onClick={() => finishWith(syncState.upload)}
                className="flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105 mx-auto mb-6"
                style={{ background: 'var(--terracotta)', color: 'white' }}
              >
                Continue
                <ArrowRight className="w-4 h-4" />
              </button>
            )}

            <div className="rounded-xl p-5 mb-6 text-left" style={panelStyle}>
              <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                Your free tier includes <strong>30 pages</strong> of OCR per month. You can always sync more later.
              </p>
            </div>

            {!agentConnected && (
              <button
                onClick={() => setStep('connect')}
                className="flex items-center gap-1 text-sm hover:opacity-80 mx-auto"
                style={{ color: 'var(--warm-gray)' }}
              >
                <ArrowLeft className="w-4 h-4" /> Back to install steps
              </button>
            )}
          </div>
        )}

        {step === 'done' && arrived && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: '#e8f0ea' }}>
              <CheckCircle className="w-8 h-8" style={{ color: 'var(--sage-green)' }} />
            </div>
            <h2 className="text-2xl font-bold mb-3" style={headingStyle}>
              You&apos;re All Set!
            </h2>
            <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
              <strong style={{ color: 'var(--warm-charcoal)' }}>{arrived.name}</strong> has arrived. Its handwriting
              is turned into text in the background; this takes a minute or two. rMirror keeps running in your menu
              bar, so you don&apos;t need to keep this page open.
            </p>

            <div className="flex flex-col gap-3 items-center">
              <Link
                href={`/notebooks/${arrived.id}`}
                className="flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105"
                style={{ background: 'var(--terracotta)', color: 'white' }}
              >
                Open {arrived.name}
                <ArrowRight className="w-4 h-4" />
              </Link>
              <button
                onClick={onComplete}
                className="text-sm hover:opacity-80"
                style={{ color: 'var(--warm-charcoal)' }}
              >
                Go to all notebooks
              </button>
              <a
                href="/integrations/notion/setup"
                className="flex items-center gap-1 text-sm hover:opacity-80"
                style={{ color: 'var(--terracotta)' }}
              >
                Connect Notion <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function UploadProgress({ upload }: { upload: NotebookUpload }) {
  const percent = upload.totalPages > 0 ? Math.min(100, Math.round((upload.uploadedPages / upload.totalPages) * 100)) : 0;
  return (
    <div>
      <p className="text-sm mb-2" style={{ color: 'var(--warm-charcoal)' }}>
        <strong>{upload.name}</strong> &middot; {upload.uploadedPages} of {upload.totalPages} pages uploaded
      </p>
      <div
        className="h-2 rounded-full overflow-hidden"
        style={{ background: 'var(--warm-border)' }}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={upload.totalPages}
        aria-valuenow={upload.uploadedPages}
      >
        <div className="h-full transition-all" style={{ width: `${percent}%`, background: 'var(--terracotta)' }} />
      </div>
    </div>
  );
}
