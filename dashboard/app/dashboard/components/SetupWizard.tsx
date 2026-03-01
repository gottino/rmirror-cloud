'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { Download, CheckCircle, Monitor, Loader2, ArrowRight, ArrowLeft, BookOpen, ExternalLink, FolderOpen } from 'lucide-react';
import { getLatestAgentVersion, type AgentVersionInfo, getAgentStatus } from '@/lib/api';

interface SetupWizardProps {
  getToken: () => Promise<string | null>;
  isDevelopmentMode: boolean;
  onComplete: () => void;
  onDismiss: () => void;
}

type WizardStep = 1 | 2 | 3 | 4;

export default function SetupWizard({
  getToken,
  isDevelopmentMode,
  onComplete,
  onDismiss,
}: SetupWizardProps) {
  const [currentStep, setCurrentStep] = useState<WizardStep>(1);
  const [agentVersion, setAgentVersion] = useState<AgentVersionInfo | null>(null);
  const [agentConnected, setAgentConnected] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Fetch latest agent version on mount
  useEffect(() => {
    getLatestAgentVersion()
      .then(setAgentVersion)
      .catch((err) => console.error('Failed to fetch agent version:', err));
  }, []);

  // Poll for agent connection in step 2
  useEffect(() => {
    if (currentStep !== 2) {
      if (pollingRef.current) clearInterval(pollingRef.current);
      return;
    }

    const checkAgent = async () => {
      try {
        const authToken = isDevelopmentMode
          ? process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN || localStorage.getItem('dev_auth_token') || ''
          : await getToken();
        if (!authToken) return;

        const status = await getAgentStatus(authToken);
        if (status.has_agent_connected) {
          setAgentConnected(true);
          if (pollingRef.current) clearInterval(pollingRef.current);
          // Auto-advance after brief celebration
          setTimeout(() => setCurrentStep(3), 1500);
        }
      } catch {
        // Silently retry on next poll
      }
    };

    checkAgent(); // Check immediately
    pollingRef.current = setInterval(checkAgent, 5000);

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [currentStep, getToken, isDevelopmentMode]);

  const handleDownload = useCallback(() => {
    if (!agentVersion?.platforms.macos?.url) return;
    setDownloading(true);
    window.open(agentVersion.platforms.macos.url, '_blank');
    // Move to step 2 after a short delay
    setTimeout(() => {
      setCurrentStep(2);
      setDownloading(false);
    }, 1000);
  }, [agentVersion]);

  const macosUrl = agentVersion?.platforms.macos?.url;
  const version = agentVersion?.version;

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center px-4 py-12">
      {/* Progress indicator */}
      <div className="flex items-center gap-2 mb-12">
        {([1, 2, 3, 4] as const).map((step) => (
          <div key={step} className="flex items-center gap-2">
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-all"
              style={{
                background: currentStep >= step ? 'var(--terracotta)' : 'var(--warm-bg)',
                color: currentStep >= step ? 'white' : 'var(--warm-gray)',
                border: currentStep >= step ? 'none' : '2px solid var(--warm-border)',
              }}
            >
              {currentStep > step ? <CheckCircle className="w-4 h-4" /> : step}
            </div>
            {step < 4 && (
              <div
                className="w-8 h-0.5"
                style={{ background: currentStep > step ? 'var(--terracotta)' : 'var(--warm-border)' }}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step content */}
      <div className="max-w-lg w-full">
        {currentStep === 1 && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: '#f5e6e5' }}>
              <BookOpen className="w-8 h-8" style={{ color: 'var(--terracotta)' }} />
            </div>
            <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
              Welcome to rMirror
            </h2>
            <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
              Your reMarkable notebooks, searchable and synced to Notion.
              Let&apos;s get you set up — it only takes a few minutes.
            </p>

            <div className="rounded-xl p-6 mb-6" style={{ background: 'var(--warm-bg)', border: '1px solid var(--warm-border)' }}>
              <p className="text-sm font-medium mb-4" style={{ color: 'var(--warm-charcoal)' }}>
                Choose your platform
              </p>
              <div className="flex gap-3 justify-center">
                <button
                  onClick={handleDownload}
                  disabled={!macosUrl || downloading}
                  className="flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105 disabled:opacity-50 disabled:hover:scale-100"
                  style={{ background: 'var(--terracotta)', color: 'white' }}
                >
                  {downloading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Download className="w-5 h-5" />
                  )}
                  Download for macOS
                </button>
              </div>
              {version && (
                <p className="text-xs mt-3" style={{ color: 'var(--warm-gray)' }}>
                  Version {version} &middot; macOS 12+
                </p>
              )}
              <p className="text-xs mt-2" style={{ color: 'var(--warm-gray)' }}>
                Windows support coming soon
              </p>
            </div>

            <button
              onClick={onDismiss}
              className="text-sm underline hover:opacity-80"
              style={{ color: 'var(--warm-gray)' }}
            >
              Skip setup
            </button>
          </div>
        )}

        {currentStep === 2 && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: agentConnected ? '#e8f0ea' : '#f5e6e5' }}>
              {agentConnected ? (
                <CheckCircle className="w-8 h-8" style={{ color: 'var(--sage-green)' }} />
              ) : (
                <Monitor className="w-8 h-8" style={{ color: 'var(--terracotta)' }} />
              )}
            </div>

            {agentConnected ? (
              <>
                <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
                  Agent Connected!
                </h2>
                <p className="text-base mb-6" style={{ color: 'var(--sage-green)' }}>
                  rMirror is running and connected to your account.
                </p>
              </>
            ) : (
              <>
                <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
                  Install & Connect
                </h2>
                <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
                  Follow these steps to get the agent running.
                </p>
              </>
            )}

            {!agentConnected && (
              <div className="text-left rounded-xl p-6 mb-6" style={{ background: 'var(--warm-bg)', border: '1px solid var(--warm-border)' }}>
                <ol className="space-y-4">
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--terracotta)', color: 'white' }}>1</span>
                    <div>
                      <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Open the downloaded DMG</p>
                      <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>Double-click <code className="px-1 py-0.5 rounded text-xs" style={{ background: 'var(--warm-border)' }}>rMirror-{version || '...'}.dmg</code> in your Downloads</p>
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--terracotta)', color: 'white' }}>2</span>
                    <div>
                      <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Drag to Applications</p>
                      <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>Drag the rMirror icon to the Applications folder</p>
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--terracotta)', color: 'white' }}>3</span>
                    <div>
                      <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Launch rMirror</p>
                      <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>Open it from Applications — it will appear in your menu bar</p>
                    </div>
                  </li>
                  <li className="flex gap-3">
                    <span className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: 'var(--terracotta)', color: 'white' }}>4</span>
                    <div>
                      <p className="font-medium" style={{ color: 'var(--warm-charcoal)' }}>Sign in</p>
                      <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>The agent will open a browser window — sign in with your account</p>
                    </div>
                  </li>
                </ol>
              </div>
            )}

            {!agentConnected && (
              <div className="flex items-center justify-center gap-2 mb-6" style={{ color: 'var(--warm-gray)' }}>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Waiting for agent to connect...</span>
              </div>
            )}

            <div className="flex justify-between items-center">
              <button
                onClick={() => setCurrentStep(1)}
                className="flex items-center gap-1 text-sm hover:opacity-80"
                style={{ color: 'var(--warm-gray)' }}
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
              {!agentConnected && (
                <button
                  onClick={() => setCurrentStep(3)}
                  className="text-sm underline hover:opacity-80"
                  style={{ color: 'var(--warm-gray)' }}
                >
                  I already have the agent installed
                </button>
              )}
            </div>
          </div>
        )}

        {currentStep === 3 && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: '#f5e6e5' }}>
              <FolderOpen className="w-8 h-8" style={{ color: 'var(--terracotta)' }} />
            </div>
            <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
              Sync Your Notebooks
            </h2>
            <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
              The agent will sync your reMarkable notebooks to the cloud.
              Open the agent from your menu bar and click &quot;Initial Sync&quot; to get started.
            </p>

            <div className="rounded-xl p-6 mb-6" style={{ background: 'var(--warm-bg)', border: '1px solid var(--warm-border)' }}>
              <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                Your free tier includes <strong>30 pages</strong> of OCR transcription per month.
                The agent will sync notebook structure immediately, and OCR will process your most recent pages first.
              </p>
            </div>

            <button
              onClick={() => setCurrentStep(4)}
              className="flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105 mx-auto"
              style={{ background: 'var(--terracotta)', color: 'white' }}
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </button>

            <div className="mt-4">
              <button
                onClick={() => setCurrentStep(2)}
                className="flex items-center gap-1 text-sm hover:opacity-80 mx-auto"
                style={{ color: 'var(--warm-gray)' }}
              >
                <ArrowLeft className="w-4 h-4" /> Back
              </button>
            </div>
          </div>
        )}

        {currentStep === 4 && (
          <div className="text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-6" style={{ background: '#e8f0ea' }}>
              <CheckCircle className="w-8 h-8" style={{ color: 'var(--sage-green)' }} />
            </div>
            <h2 className="text-2xl font-bold mb-3" style={{ color: 'var(--warm-charcoal)', fontFamily: 'var(--font-display)' }}>
              You&apos;re All Set!
            </h2>
            <p className="text-base mb-8" style={{ color: 'var(--warm-gray)' }}>
              Your notebooks will appear here as they sync.
              The agent runs quietly in your menu bar — you don&apos;t need to keep this page open.
            </p>

            <div className="flex flex-col gap-3 items-center">
              <button
                onClick={onComplete}
                className="flex items-center gap-2 px-6 py-3 rounded-lg font-medium transition-all hover:scale-105"
                style={{ background: 'var(--terracotta)', color: 'white' }}
              >
                Go to Dashboard
                <ArrowRight className="w-4 h-4" />
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
