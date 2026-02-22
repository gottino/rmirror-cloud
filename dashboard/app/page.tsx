'use client';

import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';
import Image from 'next/image';
import { useSearchParams } from 'next/navigation';
import { useState, useEffect, useRef, Suspense } from 'react';
import { flushSync } from 'react-dom';
import { Check, ArrowRight, Github, Zap, Search as SearchIcon, Cloud, Puzzle, CheckCircle } from 'lucide-react';
import { MacWindowFrame } from '@/components/MacWindowFrame';
import { trackEvent } from '@/lib/analytics';

export default function LandingPage() {
  return (
    <Suspense>
      <LandingPageInner />
    </Suspense>
  );
}

function LandingPageInner() {
  const { isSignedIn } = useAuth();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [showError, setShowError] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const [showDeletedBanner, setShowDeletedBanner] = useState(false);
  const heroRef = useRef<HTMLDivElement>(null);
  const heroContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (searchParams.get('deleted') === 'true') {
      setShowDeletedBanner(true);
      // Auto-dismiss after 8 seconds
      const timer = setTimeout(() => setShowDeletedBanner(false), 8000);
      // Clean up the URL
      window.history.replaceState({}, '', '/');
      return () => clearTimeout(timer);
    }
  }, [searchParams]);

  useEffect(() => {
    const handleScroll = () => {
      // Trigger animation when user scrolls down 250px from top
      setIsScrolled(window.scrollY > 250);
    };

    window.addEventListener('scroll', handleScroll);
    handleScroll(); // Run on mount
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const scrollToWaitlist = (e: React.MouseEvent) => {
    e.preventDefault();
    // The hero container's paddingBottom transitions from 0 to 850px over 1s,
    // which shifts the waitlist element during animation and breaks scrollIntoView.
    // Fix: temporarily disable the transition so layout settles instantly.
    const container = heroContainerRef.current;
    if (container) {
      container.style.transition = 'none';
    }
    flushSync(() => setIsScrolled(true));
    // Force reflow so the browser computes layout with final paddingBottom
    document.getElementById('waitlist')?.offsetTop;
    document.getElementById('waitlist')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // Re-enable transition after a frame
    requestAnimationFrame(() => {
      if (container) {
        container.style.transition = '';
      }
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setShowSuccess(false);
    setShowError(false);
    setIsSubmitting(true);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://rmirror.io/api/v1';
      const response = await fetch(`${apiUrl}/waitlist`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, name: name || undefined }),
      });

      if (response.ok) {
        trackEvent({ name: 'waitlist_signup', data: { source: 'landing_hero' } });
        setShowSuccess(true);
        setEmail('');
      } else {
        setShowError(true);
      }
    } catch (error) {
      setShowError(true);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen" style={{ background: 'var(--background)' }}>
      {/* Account deleted banner */}
      {showDeletedBanner && (
        <div
          className="fixed top-4 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 px-6 py-3 rounded-lg shadow-lg"
          style={{ backgroundColor: 'var(--card)', border: '1px solid var(--sage-green)' }}
        >
          <CheckCircle className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--sage-green)' }} />
          <span style={{ fontSize: '0.925em', color: 'var(--warm-charcoal)', fontWeight: 500 }}>
            Your account has been deleted. All your data has been removed.
          </span>
          <button
            onClick={() => setShowDeletedBanner(false)}
            style={{ color: 'var(--warm-gray)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.25em', lineHeight: 1 }}
          >
            &times;
          </button>
        </div>
      )}

      {/* Hero Section */}
      <section
        ref={heroRef}
        className="relative overflow-visible py-20 lg:py-28 transition-all duration-1000 ease-out"
      >
        <div className="max-w-7xl mx-auto px-6">
          {/* Desktop layout */}
          <div
            ref={heroContainerRef}
            className="hidden lg:block relative transition-all duration-1000 ease-out"
            style={{
              minHeight: '400px',
              paddingBottom: isScrolled ? '850px' : '0'
            }}
          >
            {/* Title & Tagline */}
            <div
              className="transition-all duration-1000 ease-in-out"
              style={{
                position: 'relative',
                width: isScrolled ? '100%' : '50%',
                opacity: 1
              }}
            >
              <div
                className="mb-8 flex items-center gap-4 transition-all duration-1000 ease-in-out"
                style={{
                  justifyContent: isScrolled ? 'center' : 'flex-start'
                }}
              >
                <Image
                  src="/landing-logo.png"
                  alt="rMirror"
                  width={80}
                  height={80}
                />
                <h1
                  className="text-5xl font-bold"
                  style={{ color: 'var(--warm-charcoal)' }}
                >
                  rMirror
                </h1>
              </div>

              <h2
                className="text-4xl lg:text-5xl font-bold mb-6 transition-all duration-1000 ease-in-out"
                style={{
                  color: 'var(--warm-charcoal)',
                  lineHeight: '1.1',
                  textAlign: isScrolled ? 'center' : 'left'
                }}
              >
                Your reMarkable Notes,
                <br />
                <span style={{ color: 'var(--terracotta)' }}>Searchable Everywhere</span>
              </h2>

              <p
                className="text-xl lg:text-2xl mb-10 transition-all duration-1000 ease-in-out"
                style={{
                  color: 'var(--warm-gray)',
                  lineHeight: '1.5',
                  textAlign: isScrolled ? 'center' : 'left'
                }}
              >
                Auto-sync your handwritten notes to the cloud with OCR.
                Search, access, and integrate with your favorite tools.
              </p>

              <div
                className="flex transition-all duration-1000 ease-in-out"
                style={{
                  justifyContent: isScrolled ? 'center' : 'flex-start'
                }}
              >
                {isSignedIn ? (
                  <Link
                    href="/dashboard"
                    className="inline-flex items-center gap-2 px-8 py-4 rounded-lg text-lg font-semibold transition-all hover:scale-105"
                    style={{
                      background: 'var(--terracotta)',
                      color: 'white',
                      boxShadow: 'var(--shadow-md)'
                    }}
                  >
                    Go to Dashboard
                    <ArrowRight className="w-5 h-5" />
                  </Link>
                ) : (
                  <div className="flex flex-col sm:flex-row gap-4">
                    <a
                      href="#waitlist"
                      onClick={scrollToWaitlist}
                      className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-lg text-lg font-semibold transition-all hover:scale-105"
                      style={{
                        background: 'var(--terracotta)',
                        color: 'white',
                        boxShadow: 'var(--shadow-md)'
                      }}
                    >
                      Request Early Access
                      <ArrowRight className="w-5 h-5" />
                    </a>
                    <a
                      href="https://github.com/gottino/rmirror-cloud"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-lg text-lg font-semibold transition-all"
                      style={{
                        background: 'white',
                        color: 'var(--warm-charcoal)',
                        border: '2px solid var(--border)',
                        boxShadow: 'var(--shadow-sm)'
                      }}
                    >
                      <Github className="w-5 h-5" />
                      View on GitHub
                    </a>
                  </div>
                )}
              </div>

              <p
                className="mt-6 text-sm transition-all duration-1000 ease-in-out"
                style={{
                  color: 'var(--warm-gray)',
                  textAlign: isScrolled ? 'center' : 'left'
                }}
              >
                Early beta &bull; Beta special: 200 pages of OCR per month
              </p>
            </div>

            {/* Screenshot - GPU-accelerated animation using only transform/opacity */}
            <div
              className="absolute top-0 right-0 w-1/2"
              style={{
                willChange: 'transform, opacity',
                transform: isScrolled
                  ? 'translateX(-50%) translateY(550px) scale(1.7)'
                  : 'translateY(0) scale(0.85)',
                opacity: isScrolled ? 1 : 0.95,
                zIndex: isScrolled ? 1 : 10,
                transformOrigin: 'top center',
                transition: 'transform 800ms cubic-bezier(0.4, 0, 0.2, 1), opacity 800ms cubic-bezier(0.4, 0, 0.2, 1)'
              }}
            >
              <Image
                src="/dashboard-screenshot.png"
                alt="rMirror Dashboard"
                width={1920}
                height={1080}
                className="w-full h-auto"
                priority
              />
            </div>
          </div>

          {/* Mobile layout */}
          <div className="lg:hidden">
            <div className="text-center">
              <div className="mb-8 flex items-center gap-4 justify-center">
                <Image
                  src="/landing-logo.png"
                  alt="rMirror"
                  width={80}
                  height={80}
                />
                <h1
                  className="text-5xl font-bold"
                  style={{ color: 'var(--warm-charcoal)' }}
                >
                  rMirror
                </h1>
              </div>

              <h2
                className="text-4xl font-bold mb-6"
                style={{ color: 'var(--warm-charcoal)', lineHeight: '1.1' }}
              >
                Your reMarkable Notes,
                <br />
                <span style={{ color: 'var(--terracotta)' }}>Searchable Everywhere</span>
              </h2>

              <p
                className="text-xl mb-10"
                style={{ color: 'var(--warm-gray)', lineHeight: '1.5' }}
              >
                Auto-sync your handwritten notes to the cloud with OCR.
                Search, access, and integrate with your favorite tools.
              </p>

              <div className="flex justify-center">
                {isSignedIn ? (
                  <Link
                    href="/dashboard"
                    className="inline-flex items-center gap-2 px-8 py-4 rounded-lg text-lg font-semibold transition-all hover:scale-105"
                    style={{
                      background: 'var(--terracotta)',
                      color: 'white',
                      boxShadow: 'var(--shadow-md)'
                    }}
                  >
                    Go to Dashboard
                    <ArrowRight className="w-5 h-5" />
                  </Link>
                ) : (
                  <div className="flex flex-col sm:flex-row gap-4">
                    <a
                      href="#waitlist"
                      onClick={scrollToWaitlist}
                      className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-lg text-lg font-semibold transition-all hover:scale-105"
                      style={{
                        background: 'var(--terracotta)',
                        color: 'white',
                        boxShadow: 'var(--shadow-md)'
                      }}
                    >
                      Request Early Access
                      <ArrowRight className="w-5 h-5" />
                    </a>
                    <a
                      href="https://github.com/gottino/rmirror-cloud"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center justify-center gap-2 px-8 py-4 rounded-lg text-lg font-semibold transition-all"
                      style={{
                        background: 'white',
                        color: 'var(--warm-charcoal)',
                        border: '2px solid var(--border)',
                        boxShadow: 'var(--shadow-sm)'
                      }}
                    >
                      <Github className="w-5 h-5" />
                      View on GitHub
                    </a>
                  </div>
                )}
              </div>

              <p className="mt-6 text-sm" style={{ color: 'var(--warm-gray)' }}>
                Early beta &bull; Beta special: 200 pages of OCR per month
              </p>
            </div>

            <div className="mt-12">
              <Image
                src="/dashboard-screenshot.png"
                alt="rMirror Dashboard"
                width={1920}
                height={1080}
                className="w-full h-auto"
                priority
              />
            </div>
          </div>
        </div>
      </section>

      {/* Problem Section */}
      <section className="py-12 lg:py-16">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2
            className="text-4xl lg:text-5xl font-bold mb-8"
            style={{ color: 'var(--warm-charcoal)' }}
          >
            Love your reMarkable, but...
          </h2>
          <div className="text-lg lg:text-xl leading-relaxed" style={{ color: 'var(--warm-gray)' }}>
            <ul className="space-y-3 mb-6">
              <li className="flex items-start gap-3">
                <span style={{ color: 'var(--terracotta)' }}>•</span>
                <span>Your handwritten notes are trapped on the device and the reMarkable apps?</span>
              </li>
              <li className="flex items-start gap-3">
                <span style={{ color: 'var(--terracotta)' }}>•</span>
                <span>No automatic transcription to text?</span>
              </li>
              <li className="flex items-start gap-3">
                <span style={{ color: 'var(--terracotta)' }}>•</span>
                <span>No seamless integration with your other tools and your workflow?</span>
              </li>
              <li className="flex items-start gap-3">
                <span style={{ color: 'var(--terracotta)' }}>•</span>
                <span>Notes gathering digital dust?</span>
              </li>
              <li className="flex items-start gap-3">
                <span style={{ color: 'var(--terracotta)' }}>•</span>
                <span>Todos remaining undone because they don't show up in your todo app?</span>
              </li>
            </ul>
            <p className="text-center">
              <span style={{ color: 'var(--terracotta)', fontWeight: 600 }}>Until now.</span>
            </p>
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-12 lg:py-16" style={{ background: 'var(--soft-cream)' }}>
        <div className="max-w-5xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2
              className="text-4xl lg:text-5xl font-bold mb-4"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              How It Works
            </h2>
            <p className="text-lg" style={{ color: 'var(--warm-gray)' }}>
              Get started in 3 simple steps
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                step: '1',
                title: 'Download Agent',
                description: 'Install the rMirror agent on your Mac. It runs quietly in the background.',
                icon: <Cloud className="w-8 h-8" />
              },
              {
                step: '2',
                title: 'Connect to rMirror',
                description: 'Sign in and connect the agent with rMirror. The agent syncs your notebooks automatically as they change.',
                icon: <Zap className="w-8 h-8" />
              },
              {
                step: '3',
                title: 'Access Anywhere',
                description: 'Search your handwritten notes from any device. Sync to Notion, your Todo app, Readwise, and more.',
                icon: <SearchIcon className="w-8 h-8" />
              }
            ].map((item) => (
              <div
                key={item.step}
                className="relative p-8 rounded-xl"
                style={{ background: 'white', boxShadow: 'var(--shadow-sm)' }}
              >
                <div
                  className="absolute -top-4 -left-4 w-12 h-12 rounded-full flex items-center justify-center text-white font-bold text-xl"
                  style={{ background: 'var(--terracotta)' }}
                >
                  {item.step}
                </div>
                <div className="mb-4" style={{ color: 'var(--terracotta)' }}>
                  {item.icon}
                </div>
                <h3 className="text-xl font-semibold mb-3" style={{ color: 'var(--warm-charcoal)' }}>
                  {item.title}
                </h3>
                <p style={{ color: 'var(--warm-gray)' }}>
                  {item.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Agent in Action */}
      <section className="py-12 lg:py-16">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-10">
            <h2
              className="text-4xl lg:text-5xl font-bold mb-4"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Runs Quietly in the Background
            </h2>
            <p className="text-lg" style={{ color: 'var(--warm-gray)' }}>
              The rMirror agent syncs your notebooks automatically - no manual exports needed
            </p>
          </div>
          <MacWindowFrame>
            <Image
              src="/agent-screenshot.png?v=2"
              alt="rMirror Agent Running"
              width={1920}
              height={1080}
              className="w-full h-auto"
            />
          </MacWindowFrame>
        </div>
      </section>

      {/* Features */}
      <section className="py-12 lg:py-16" style={{ background: 'var(--soft-cream)' }}>
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2
              className="text-4xl lg:text-5xl font-bold mb-4"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Everything You Need
            </h2>
            <p className="text-lg" style={{ color: 'var(--warm-gray)' }}>
              Powerful features to unlock your handwritten notes
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8">
            {[
              {
                icon: <Zap className="w-6 h-6" />,
                title: 'Automatic Sync',
                description: 'Your notebooks sync automatically in the background as soon as the reMarkable Mac app receives changes.',
                benefits: ['Updates as reMarkable syncs', 'Zero maintenance', 'Bulk upload possible']
              },
              {
                icon: <SearchIcon className="w-6 h-6" />,
                title: 'Full-Text Transcription',
                description: 'Transcribe your handwritten notes instantly with powerful AI-driven OCR.',
                benefits: ['Recognizes Formatting', 'Output in Markdown format', 'Copy text with one click']
              },
              {
                icon: <Cloud className="w-6 h-6" />,
                title: 'Web Access',
                description: 'Access your notes from any browser. Phone, tablet, or computer.',
                benefits: ['No app install needed', 'Works anywhere', 'Secure cloud storage']
              },
              {
                icon: <Puzzle className="w-6 h-6" />,
                title: 'Powerful Integrations',
                description: 'Connect to Notion, Readwise, and more. Fit into your existing workflow.',
                benefits: ['Notion sync', 'Readwise highlights', 'More coming soon']
              }
            ].map((feature, index) => (
              <div
                key={index}
                className="p-8 rounded-xl"
                style={{ background: 'white', boxShadow: 'var(--shadow-sm)' }}
              >
                <div
                  className="w-12 h-12 rounded-lg flex items-center justify-center mb-4"
                  style={{ background: 'var(--soft-cream)', color: 'var(--terracotta)' }}
                >
                  {feature.icon}
                </div>
                <h3 className="text-xl font-semibold mb-3" style={{ color: 'var(--warm-charcoal)' }}>
                  {feature.title}
                </h3>
                <p className="mb-4" style={{ color: 'var(--warm-gray)' }}>
                  {feature.description}
                </p>
                <ul className="space-y-2">
                  {feature.benefits.map((benefit, i) => (
                    <li key={i} className="flex items-center gap-2">
                      <Check className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--sage-green)' }} />
                      <span className="text-sm" style={{ color: 'var(--warm-gray)' }}>
                        {benefit}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* OCR in Action */}
      <section className="py-12 lg:py-16">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-10">
            <h2
              className="text-4xl lg:text-5xl font-bold mb-4"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Powerful OCR Search
            </h2>
            <p className="text-lg" style={{ color: 'var(--warm-gray)' }}>
              Find anything in your handwritten notes instantly
            </p>
          </div>
          <Image
            src="/notebook-details-screenshot.png"
            alt="OCR Search in Action"
            width={1920}
            height={1080}
            className="w-full h-auto"
          />
        </div>
      </section>

      {/* Integrations Showcase */}
      <section className="py-12 lg:py-16" style={{ background: 'var(--soft-cream)' }}>
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-10">
            <h2
              className="text-4xl lg:text-5xl font-bold mb-4"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Seamless Integrations
            </h2>
            <p className="text-lg" style={{ color: 'var(--warm-gray)' }}>
              Sync your notes to Notion, Readwise, and more
            </p>
          </div>
          <MacWindowFrame>
            <Image
              src="/integrations-screenshot.png?v=2"
              alt="Integrations Dashboard"
              width={1920}
              height={1080}
              className="w-full h-auto"
            />
          </MacWindowFrame>
        </div>
      </section>

      {/* Pricing */}
      <section className="py-12 lg:py-16">
        <div className="max-w-4xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2
              className="text-4xl lg:text-5xl font-bold mb-4"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Simple, Transparent Pricing
            </h2>
            <p className="text-lg" style={{ color: 'var(--warm-gray)' }}>
              Start free, upgrade when you need more
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-8">
            {/* Beta Tier */}
            <div
              className="p-8 rounded-xl border-2 relative"
              style={{
                background: 'white',
                borderColor: 'var(--border)',
                boxShadow: 'var(--shadow-sm)'
              }}
            >
              <div
                className="absolute -top-4 left-1/2 transform -translate-x-1/2 px-4 py-1 rounded-full text-sm font-semibold text-white"
                style={{ background: 'var(--amber-gold)' }}
              >
                Beta Special
              </div>
              <h3 className="text-2xl font-bold mb-2" style={{ color: 'var(--warm-charcoal)' }}>
                Beta
              </h3>
              <div className="mb-6">
                <span className="text-4xl font-bold" style={{ color: 'var(--warm-charcoal)' }}>$0</span>
                <span className="text-lg" style={{ color: 'var(--warm-gray)' }}>/month</span>
              </div>
              <ul className="space-y-3 mb-8">
                {[
                  'Automatic sync',
                  'Web access',
                  'Basic integrations',
                  'Community support'
                ].map((feature, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <Check className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--sage-green)' }} />
                    <span style={{ color: 'var(--warm-charcoal)' }}>{feature}</span>
                  </li>
                ))}
                <li className="flex items-center gap-2">
                  <Check className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--sage-green)' }} />
                  <span style={{ color: 'var(--warm-charcoal)' }}>
                    <s style={{ color: 'var(--warm-gray)' }}>30</s>{' '}
                    <strong style={{ color: 'var(--terracotta)' }}>200</strong> pages OCR per month
                  </span>
                </li>
              </ul>
              <a
                href="#waitlist"
                onClick={scrollToWaitlist}
                className="block w-full text-center px-6 py-3 rounded-lg font-semibold transition-all"
                style={{
                  background: 'var(--soft-cream)',
                  color: 'var(--warm-charcoal)',
                  border: '2px solid var(--border)'
                }}
              >
                Request Access
              </a>
            </div>

            {/* Pro Tier */}
            <div
              className="p-8 rounded-xl border-2 relative"
              style={{
                background: 'white',
                borderColor: 'var(--terracotta)',
                boxShadow: 'var(--shadow-md)'
              }}
            >
              <div
                className="absolute -top-4 left-1/2 transform -translate-x-1/2 px-4 py-1 rounded-full text-sm font-semibold text-white"
                style={{ background: 'var(--terracotta)' }}
              >
                Coming Soon
              </div>
              <h3 className="text-2xl font-bold mb-2" style={{ color: 'var(--warm-charcoal)' }}>
                Pro
              </h3>
              <div className="mb-6">
                <span className="text-4xl font-bold" style={{ color: 'var(--warm-charcoal)' }}>$9</span>
                <span className="text-lg" style={{ color: 'var(--warm-gray)' }}>/month</span>
              </div>
              <ul className="space-y-3 mb-8">
                {[
                  'Unlimited OCR pages',
                  'Priority sync',
                  'All integrations',
                  'Advanced search',
                  'Priority support',
                  'Self-hosting option'
                ].map((feature, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <Check className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--sage-green)' }} />
                    <span style={{ color: 'var(--warm-charcoal)' }}>{feature}</span>
                  </li>
                ))}
              </ul>
              <button
                disabled
                className="block w-full text-center px-6 py-3 rounded-lg font-semibold opacity-50 cursor-not-allowed"
                style={{
                  background: 'var(--terracotta)',
                  color: 'white'
                }}
              >
                Coming Soon
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Social Proof */}
      <section className="py-12 lg:py-16" style={{ background: 'var(--soft-cream)' }}>
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2
            className="text-4xl lg:text-5xl font-bold mb-6"
            style={{ color: 'var(--warm-charcoal)' }}
          >
            Open Source & Self-Hostable
          </h2>
          <p className="text-lg mb-8" style={{ color: 'var(--warm-gray)' }}>
            rMirror is completely open source. Host it yourself or use our cloud service.
            Your data, your choice.
          </p>
          <a
            href="https://github.com/gottino/rmirror-cloud"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-3 px-8 py-4 rounded-lg font-semibold transition-all hover:scale-105"
            style={{
              background: 'var(--warm-charcoal)',
              color: 'white',
              boxShadow: 'var(--shadow-md)'
            }}
          >
            <Github className="w-6 h-6" />
            <span>Star on GitHub</span>
          </a>
        </div>
      </section>

      {/* FAQ Section */}
      <section className="py-12 lg:py-16">
        <div className="max-w-4xl mx-auto px-6">
          <div className="text-center mb-12">
            <h2
              className="text-4xl lg:text-5xl font-bold mb-4"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Frequently Asked Questions
            </h2>
            <p className="text-lg" style={{ color: 'var(--warm-gray)' }}>
              Everything you need to know about rMirror
            </p>
          </div>

          <div className="space-y-6">
            {[
              {
                question: 'Do I need a reMarkable Cloud subscription?',
                answer: 'rMirror works with both free and paid reMarkable Cloud plans. The free plan includes basic cloud sync, which is all you need. The agent monitors the local folder where reMarkable syncs your files.'
              },
              {
                question: 'What platforms does the agent support?',
                answer: 'The rMirror agent is available for macOS only. The web dashboard works on any device with a browser - phone, tablet, or computer.'
              },
              {
                question: 'Is my data secure?',
                answer: 'Absolutely. All data is encrypted in transit and at rest. Your notebooks are stored securely in the cloud, and you can delete them anytime. For maximum privacy, you can self-host the entire stack since rMirror is open source.'
              },
              {
                question: 'How accurate is the OCR?',
                answer: 'We use advanced AI-powered OCR that handles most handwriting styles well. Accuracy depends on handwriting legibility, but most users see 85-95% accuracy. The OCR also recognizes formatting like bullet points and headings.'
              },
              {
                question: 'Can I export my data?',
                answer: 'Yes! You can download all your notebooks and OCR text at any time. Integrations with Notion and Readwise give you additional export options. Plus, being open source means you have full control over your data.'
              },
              {
                question: 'What happens when I hit my OCR limit?',
                answer: 'You can still upload notebooks and access everything you\'ve already uploaded. New pages won\'t be OCR\'d until your quota resets (monthly). Beta testers get 200 pages/month — plenty for most users.'
              }
            ].map((faq, index) => (
              <div
                key={index}
                className="p-6 rounded-xl"
                style={{
                  background: 'white',
                  border: '1px solid var(--border)',
                  boxShadow: 'var(--shadow-sm)'
                }}
              >
                <h3 className="text-lg font-semibold mb-3" style={{ color: 'var(--warm-charcoal)' }}>
                  {faq.question}
                </h3>
                <p style={{ color: 'var(--warm-gray)', lineHeight: '1.6' }}>
                  {faq.answer}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA / Waitlist Form */}
      {!isSignedIn && (
        <section className="py-20 lg:py-28">
          <div id="waitlist" className="max-w-lg mx-auto px-6 text-center" style={{ scrollMarginTop: '2rem' }}>
            <h2
              className="text-4xl lg:text-5xl font-bold mb-6"
              style={{ color: 'var(--warm-charcoal)' }}
            >
              Ready to Unlock Your Notes?
            </h2>
            <p className="text-xl mb-10" style={{ color: 'var(--warm-gray)' }}>
              rMirror is in early beta. Request access and we'll send you an invite.
            </p>

            {!showSuccess ? (
              <form onSubmit={handleSubmit} className="space-y-4">
                <input
                  type="text"
                  placeholder="Name (optional)"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-5 py-3.5 rounded-lg text-base"
                  style={{
                    background: 'white',
                    border: '2px solid var(--border)',
                    color: 'var(--warm-charcoal)',
                  }}
                />
                <input
                  type="email"
                  placeholder="Email address"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="w-full px-5 py-3.5 rounded-lg text-base"
                  style={{
                    background: 'white',
                    border: '2px solid var(--border)',
                    color: 'var(--warm-charcoal)',
                  }}
                />
                <button
                  type="submit"
                  disabled={isSubmitting || !email}
                  className="w-full py-3.5 rounded-lg text-lg font-semibold transition-all hover:scale-105"
                  style={{
                    background: 'var(--terracotta)',
                    color: 'white',
                    boxShadow: 'var(--shadow-md)',
                    opacity: isSubmitting || !email ? 0.6 : 1,
                  }}
                >
                  {isSubmitting ? 'Requesting...' : 'Request Early Access'}
                </button>
                {showError && (
                  <p className="text-sm" style={{ color: 'var(--terracotta)' }}>
                    Something went wrong. Please try again.
                  </p>
                )}
              </form>
            ) : (
              <div
                className="p-6 rounded-xl"
                style={{ background: 'var(--soft-cream)', border: '1px solid var(--sage-green)' }}
              >
                <CheckCircle className="w-8 h-8 mx-auto mb-3" style={{ color: 'var(--sage-green)' }} />
                <p className="text-lg font-semibold mb-1" style={{ color: 'var(--warm-charcoal)' }}>
                  You're on the list!
                </p>
                <p style={{ color: 'var(--warm-gray)' }}>
                  We'll email you when your invite is ready.
                </p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Footer */}
      <footer
        className="py-12 border-t"
        style={{
          borderColor: 'var(--border)',
          background: 'var(--soft-cream)'
        }}
      >
        <div className="max-w-6xl mx-auto px-6">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div className="flex items-center gap-2">
              <Image src="/landing-logo.png" alt="rMirror" width={32} height={32} />
              <span className="font-semibold" style={{ color: 'var(--warm-charcoal)' }}>
                rMirror Cloud
              </span>
            </div>

            <div className="flex gap-8">
              <a
                href="https://github.com/gottino/rmirror-cloud"
                target="_blank"
                rel="noopener noreferrer"
                className="transition-colors"
                style={{ color: 'var(--warm-gray)' }}
              >
                GitHub
              </a>
              <a
                href="https://github.com/gottino/rmirror-cloud/blob/main/README.md"
                target="_blank"
                rel="noopener noreferrer"
                className="transition-colors"
                style={{ color: 'var(--warm-gray)' }}
              >
                Docs
              </a>
              <a
                href="mailto:support@rmirror.io"
                className="transition-colors"
                style={{ color: 'var(--warm-gray)' }}
              >
                Support
              </a>
              {isSignedIn && (
                <Link
                  href="/dashboard"
                  className="transition-colors"
                  style={{ color: 'var(--warm-gray)' }}
                >
                  Dashboard
                </Link>
              )}
              <Link
                href="/legal/terms"
                className="transition-colors"
                style={{ color: 'var(--warm-gray)' }}
              >
                Terms
              </Link>
              <Link
                href="/legal/privacy"
                className="transition-colors"
                style={{ color: 'var(--warm-gray)' }}
              >
                Privacy
              </Link>
            </div>
          </div>

          <div className="mt-8 pt-8 border-t text-center" style={{ borderColor: 'var(--border)' }}>
            <p className="text-sm" style={{ color: 'var(--warm-gray)' }}>
              &copy; 2026 rMirror Cloud. Open source and self-hostable.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
