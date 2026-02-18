'use client';

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { Check, Circle, Download, X, ExternalLink, ChevronDown } from 'lucide-react';
import { trackEvent } from '@/lib/analytics';

interface OnboardingStep {
  id: number;
  title: string;
  description: string;
  completed: boolean;
  active: boolean;
  completedMessage?: string;
  action?: {
    label: string;
    onClick?: () => void;
    href?: string;
  };
}

interface OnboardingChecklistProps {
  steps: OnboardingStep[];
  onDismiss: () => void;
  onDownloadAgent: () => void;
}

function StepIcon({ completed, active }: { completed: boolean; active: boolean }) {
  if (completed) {
    return (
      <div
        className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300"
        style={{ backgroundColor: 'var(--sage-green)' }}
      >
        <Check className="w-3.5 h-3.5" style={{ color: 'white' }} />
      </div>
    );
  }

  return (
    <div
      className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-all duration-300"
      style={{
        border: `2px solid ${active ? 'var(--terracotta)' : 'var(--border)'}`,
        backgroundColor: 'transparent',
      }}
    >
      {active && (
        <div
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: 'var(--terracotta)' }}
        />
      )}
    </div>
  );
}

function StepAction({ action, onDownloadAgent }: {
  action: OnboardingStep['action'];
  onDownloadAgent: () => void;
}) {
  if (!action) return null;

  // If the action has an href, render as a link
  if (action.href) {
    return (
      <Link
        href={action.href}
        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg transition-all duration-200"
        style={{
          backgroundColor: 'transparent',
          color: 'var(--terracotta)',
          border: '1px solid var(--terracotta)',
          fontSize: '0.875em',
          fontWeight: 500,
          textDecoration: 'none',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--terracotta)';
          e.currentTarget.style.color = 'var(--primary-foreground)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = 'var(--terracotta)';
        }}
      >
        {action.label}
        <ExternalLink className="w-3.5 h-3.5" />
      </Link>
    );
  }

  // Download button style
  const isDownload = action.label.toLowerCase().includes('download');
  return (
    <button
      onClick={action.onClick || onDownloadAgent}
      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg transition-all duration-200 cursor-pointer"
      style={{
        backgroundColor: isDownload ? 'var(--terracotta)' : 'transparent',
        color: isDownload ? 'var(--primary-foreground)' : 'var(--terracotta)',
        border: isDownload ? '1px solid var(--terracotta)' : '1px solid var(--terracotta)',
        fontSize: '0.875em',
        fontWeight: 500,
      }}
      onMouseEnter={(e) => {
        if (!isDownload) {
          e.currentTarget.style.backgroundColor = 'var(--terracotta)';
          e.currentTarget.style.color = 'var(--primary-foreground)';
        } else {
          e.currentTarget.style.opacity = '0.9';
        }
      }}
      onMouseLeave={(e) => {
        if (!isDownload) {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = 'var(--terracotta)';
        } else {
          e.currentTarget.style.opacity = '1';
        }
      }}
    >
      {isDownload && <Download className="w-3.5 h-3.5" />}
      {action.label}
    </button>
  );
}

export function OnboardingChecklist({ steps, onDismiss, onDownloadAgent }: OnboardingChecklistProps) {
  const [expandedStepId, setExpandedStepId] = useState<number | null>(
    () => steps.find((s) => s.active && !s.completed)?.id ?? null
  );

  // Track newly completed steps
  const prevCompletedRef = useRef<Set<number>>(new Set(steps.filter(s => s.completed).map(s => s.id)));
  useEffect(() => {
    const prevCompleted = prevCompletedRef.current;
    for (const step of steps) {
      if (step.completed && !prevCompleted.has(step.id)) {
        trackEvent({ name: 'onboarding_step', data: { step: step.title, completed: true } });
      }
    }
    prevCompletedRef.current = new Set(steps.filter(s => s.completed).map(s => s.id));
  }, [steps]);

  const completedCount = steps.filter((s) => s.completed).length;
  const totalCount = steps.length;
  const progressPercent = (completedCount / totalCount) * 100;

  // Determine which steps are "waiting" -- not active, not completed, and come after an incomplete step
  const getWaitingMessage = (step: OnboardingStep): string | null => {
    if (step.completed || step.active) return null;

    switch (step.id) {
      case 3:
        return 'Waiting for agent...';
      case 4:
        return 'Waiting for sync...';
      default:
        return null;
    }
  };

  const toggleStep = (stepId: number) => {
    setExpandedStepId((prev) => (prev === stepId ? null : stepId));
  };

  return (
    <div
      className="rounded-xl overflow-hidden transition-all duration-300"
      style={{
        backgroundColor: 'var(--card)',
        border: '1px solid var(--border)',
        boxShadow: 'var(--shadow-md)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-6 py-4"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div>
          <h3
            style={{
              fontSize: '1.125rem',
              fontWeight: 600,
              color: 'var(--warm-charcoal)',
              margin: 0,
              lineHeight: 1.3,
            }}
          >
            Getting Started
          </h3>
          <p
            style={{
              fontSize: '0.8em',
              color: 'var(--warm-gray)',
              margin: '0.25rem 0 0 0',
            }}
          >
            Set up rMirror in a few simple steps
          </p>
        </div>
        <button
          onClick={onDismiss}
          className="p-1.5 rounded-lg transition-colors duration-200 cursor-pointer"
          style={{ color: 'var(--warm-gray)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--soft-cream)';
            e.currentTarget.style.color = 'var(--warm-charcoal)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.color = 'var(--warm-gray)';
          }}
          aria-label="Dismiss onboarding checklist"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Steps */}
      <div className="px-6 py-3">
        {steps.map((step, index) => {
          const isExpanded = expandedStepId === step.id;
          const waitingMessage = getWaitingMessage(step);

          return (
            <div
              key={step.id}
              className="transition-all duration-300"
              style={{
                borderBottom:
                  index < steps.length - 1
                    ? '1px solid var(--border)'
                    : 'none',
              }}
            >
              {/* Step row */}
              <button
                onClick={() => toggleStep(step.id)}
                className="w-full flex items-center gap-3 py-3.5 text-left cursor-pointer transition-opacity duration-200"
                style={{ background: 'none', border: 'none', padding: '0.875rem 0' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.opacity = '0.8';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.opacity = '1';
                }}
              >
                <StepIcon completed={step.completed} active={step.active} />

                <div className="flex-1 min-w-0">
                  <span
                    style={{
                      fontSize: '0.925em',
                      fontWeight: step.active && !step.completed ? 600 : 500,
                      color: step.completed
                        ? 'var(--warm-gray)'
                        : 'var(--warm-charcoal)',
                      textDecoration: step.completed ? 'none' : 'none',
                    }}
                  >
                    {step.title}
                  </span>

                  {/* Completed message inline */}
                  {step.completed && step.completedMessage && (
                    <span
                      style={{
                        fontSize: '0.8em',
                        color: 'var(--sage-green)',
                        marginLeft: '0.5rem',
                        fontWeight: 500,
                      }}
                    >
                      {step.completedMessage}
                    </span>
                  )}

                  {/* Waiting message inline */}
                  {waitingMessage && (
                    <span
                      style={{
                        fontSize: '0.8em',
                        color: 'var(--warm-gray)',
                        marginLeft: '0.5rem',
                        fontStyle: 'italic',
                      }}
                    >
                      {waitingMessage}
                    </span>
                  )}
                </div>

                <ChevronDown
                  className="w-4 h-4 flex-shrink-0 transition-transform duration-200"
                  style={{
                    color: 'var(--warm-gray)',
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                  }}
                />
              </button>

              {/* Expanded content */}
              <div
                className="overflow-hidden transition-all duration-300 ease-in-out"
                style={{
                  maxHeight: isExpanded ? '200px' : '0px',
                  opacity: isExpanded ? 1 : 0,
                }}
              >
                <div
                  className="pb-4 pl-9"
                  style={{ marginTop: '-0.25rem' }}
                >
                  <p
                    style={{
                      fontSize: '0.85em',
                      color: 'var(--warm-gray)',
                      margin: '0 0 0.75rem 0',
                      lineHeight: 1.5,
                    }}
                  >
                    {step.description}
                  </p>

                  {/* Action button (only for non-completed active or actionable steps) */}
                  {!step.completed && step.action && (step.active || step.action.href) && (
                    <StepAction
                      action={step.action}
                      onDownloadAgent={onDownloadAgent}
                    />
                  )}

                  {/* Completed state in expanded view */}
                  {step.completed && step.completedMessage && (
                    <div
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md"
                      style={{
                        backgroundColor: 'rgba(122, 156, 137, 0.1)',
                        color: 'var(--sage-green)',
                        fontSize: '0.8em',
                        fontWeight: 500,
                      }}
                    >
                      <Check className="w-3.5 h-3.5" />
                      {step.completedMessage}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Progress bar */}
      <div
        className="px-6 py-4"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between mb-2">
          <span
            style={{
              fontSize: '0.8em',
              fontWeight: 500,
              color: 'var(--warm-charcoal)',
            }}
          >
            {completedCount}/{totalCount} complete
          </span>
          {completedCount === totalCount && (
            <span
              style={{
                fontSize: '0.75em',
                fontWeight: 500,
                color: 'var(--sage-green)',
              }}
            >
              All done!
            </span>
          )}
        </div>
        <div
          className="h-2 rounded-full overflow-hidden"
          style={{ backgroundColor: 'var(--soft-cream)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${progressPercent}%`,
              backgroundColor:
                completedCount === totalCount
                  ? 'var(--sage-green)'
                  : 'var(--terracotta)',
            }}
          />
        </div>
      </div>
    </div>
  );
}

/**
 * Default onboarding steps configuration.
 * Use this helper to generate the steps array based on the user's current state.
 */
export function getDefaultOnboardingSteps({
  hasAgent,
  hasNotebook,
  hasOcr,
  hasNotion,
  onDownloadAgent,
}: {
  hasAgent: boolean;
  hasNotebook: boolean;
  hasOcr: boolean;
  hasNotion: boolean;
  onDownloadAgent: () => void;
}): OnboardingStep[] {
  return [
    {
      id: 1,
      title: 'Account created',
      description: 'Your rMirror account is ready to go.',
      completed: true,
      active: false,
      completedMessage: "You're in!",
    },
    {
      id: 2,
      title: 'Set up sync',
      description:
        'Install the reMarkable desktop app and download the rMirror agent to start syncing your notebooks.',
      completed: hasAgent,
      active: !hasAgent,
      completedMessage: 'Agent connected',
      action: {
        label: 'Download Agent',
        onClick: onDownloadAgent,
      },
    },
    {
      id: 3,
      title: 'Sync your first notebook',
      description:
        "Write on your reMarkable -- it'll show up here automatically once the agent is running.",
      completed: hasNotebook,
      active: hasAgent && !hasNotebook,
      completedMessage: 'Notebook synced',
    },
    {
      id: 4,
      title: 'See your handwriting as text',
      description:
        "We'll OCR your pages so you can search your notes and copy text from your handwriting.",
      completed: hasOcr,
      active: hasNotebook && !hasOcr,
      completedMessage: 'OCR complete',
    },
    {
      id: 5,
      title: 'Connect Notion (optional)',
      description:
        'Push your notes to Notion with one click. Keep your digital notebook in sync with your favorite tools.',
      completed: hasNotion,
      active: hasOcr && !hasNotion,
      completedMessage: 'Notion connected',
      action: {
        label: 'Set up \u2192',
        href: '/integrations/notion/setup',
      },
    },
  ];
}
