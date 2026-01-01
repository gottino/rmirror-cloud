'use client';

import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';
import Image from 'next/image';
import { useState } from 'react';

export default function LandingPage() {
  const { isSignedIn } = useAuth();
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [showError, setShowError] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setShowSuccess(false);
    setShowError(false);
    setIsSubmitting(true);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/waitlist`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email }),
      });

      if (response.ok) {
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
    <div style={{ margin: 0, padding: 0, boxSizing: 'border-box' }}>
      <style jsx>{`
        :root {
          --primary: #2B2B2B;
          --accent: #E47C37;
          --text: #333;
          --text-light: #666;
          --background: #FAFAFA;
          --white: #FFFFFF;
        }

        .container {
          max-width: 800px;
          margin: 0 auto;
          padding: 0 20px;
        }

        header {
          padding: 60px 0 0;
          text-align: center;
        }

        .logo {
          width: 120px;
          height: auto;
          margin-bottom: 40px;
        }

        h1 {
          font-size: 48px;
          font-weight: 700;
          color: var(--primary);
          margin-bottom: 20px;
          letter-spacing: -1px;
        }

        .tagline {
          font-size: 24px;
          color: var(--text-light);
          margin-bottom: 60px;
          font-weight: 300;
        }

        .hero {
          background: var(--white);
          border-radius: 16px;
          padding: 60px 40px;
          margin-bottom: 40px;
          box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        }

        .features {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 30px;
          margin: 40px 0 60px;
        }

        .feature {
          text-align: center;
        }

        .feature-icon {
          font-size: 40px;
          margin-bottom: 16px;
        }

        .feature h3 {
          font-size: 18px;
          margin-bottom: 8px;
          color: var(--primary);
        }

        .feature p {
          font-size: 14px;
          color: var(--text-light);
        }

        .waitlist-section {
          text-align: center;
          margin: 60px 0;
        }

        .waitlist-section h2 {
          font-size: 32px;
          margin-bottom: 20px;
          color: var(--primary);
        }

        .waitlist-section p {
          font-size: 18px;
          color: var(--text-light);
          margin-bottom: 30px;
        }

        .waitlist-form {
          max-width: 500px;
          margin: 0 auto;
          display: flex;
          gap: 12px;
          flex-wrap: wrap;
          justify-content: center;
        }

        input[type="email"] {
          flex: 1;
          min-width: 250px;
          padding: 16px 20px;
          font-size: 16px;
          border: 2px solid #E0E0E0;
          border-radius: 8px;
          transition: border-color 0.3s;
        }

        input[type="email"]:focus {
          outline: none;
          border-color: var(--accent);
        }

        button {
          padding: 16px 32px;
          font-size: 16px;
          font-weight: 600;
          background: var(--accent);
          color: var(--white);
          border: none;
          border-radius: 8px;
          cursor: pointer;
          transition: transform 0.2s, box-shadow 0.2s;
        }

        button:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(228, 124, 55, 0.3);
        }

        button:active {
          transform: translateY(0);
        }

        button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .success-message {
          padding: 16px;
          background: #E8F5E9;
          color: #2E7D32;
          border-radius: 8px;
          margin-top: 20px;
        }

        .error-message {
          padding: 16px;
          background: #FFEBEE;
          color: #C62828;
          border-radius: 8px;
          margin-top: 20px;
        }

        .cta-section {
          text-align: center;
          margin: 40px 0;
        }

        .dashboard-link {
          display: inline-block;
          padding: 16px 32px;
          font-size: 18px;
          font-weight: 600;
          background: var(--accent);
          color: var(--white);
          text-decoration: none;
          border-radius: 8px;
          transition: transform 0.2s, box-shadow 0.2s;
        }

        .dashboard-link:hover {
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(228, 124, 55, 0.3);
        }

        .github-link {
          margin: 40px 0;
          text-align: center;
        }

        .github-link a {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 12px 24px;
          color: var(--primary);
          text-decoration: none;
          border: 2px solid var(--primary);
          border-radius: 8px;
          font-weight: 500;
          transition: all 0.3s;
        }

        .github-link a:hover {
          background: var(--primary);
          color: var(--white);
        }

        footer {
          text-align: center;
          padding: 40px 0;
          color: var(--text-light);
          font-size: 14px;
        }

        @media (max-width: 600px) {
          h1 {
            font-size: 36px;
          }

          .tagline {
            font-size: 20px;
          }

          .hero {
            padding: 40px 24px;
          }

          .waitlist-form {
            flex-direction: column;
          }

          input[type="email"], button {
            width: 100%;
          }
        }
      `}</style>

      <div className="container">
        <header>
          <Image src="/landing-logo.png" alt="rMirror Logo" width={120} height={120} className="logo" />
          <h1>rMirror Cloud</h1>
          <p className="tagline">Your reMarkable notes, searchable and accessible everywhere</p>
        </header>

        <div className="hero">
          <div className="features">
            <div className="feature">
              <div className="feature-icon">🔄</div>
              <h3>Auto Sync</h3>
              <p>Seamless background sync from your reMarkable to the cloud</p>
            </div>
            <div className="feature">
              <div className="feature-icon">🔍</div>
              <h3>OCR Search</h3>
              <p>Find anything in your handwritten notes with full-text search</p>
            </div>
            <div className="feature">
              <div className="feature-icon">🌐</div>
              <h3>Web Access</h3>
              <p>Browse and search your notes from any device, anywhere</p>
            </div>
            <div className="feature">
              <div className="feature-icon">🔒</div>
              <h3>Self-Hosted</h3>
              <p>Keep your data private on your own server</p>
            </div>
          </div>

          {isSignedIn ? (
            <div className="cta-section">
              <Link href="/dashboard" className="dashboard-link">
                Go to Dashboard
              </Link>
            </div>
          ) : (
            <div className="waitlist-section">
              <h2>Join the Waitlist</h2>
              <p>Be the first to know when rMirror Cloud launches</p>

              <form className="waitlist-form" onSubmit={handleSubmit}>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your.email@example.com"
                  required
                />
                <button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Joining...' : 'Join Waitlist'}
                </button>
              </form>

              {showSuccess && (
                <div className="success-message">
                  Thanks for joining! We'll notify you when we launch.
                </div>
              )}
              {showError && (
                <div className="error-message">
                  Something went wrong. Please try again.
                </div>
              )}
            </div>
          )}

          <div className="github-link">
            <a href="https://github.com/gottino/rmirror-cloud" target="_blank" rel="noopener noreferrer">
              <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"></path>
              </svg>
              View on GitHub
            </a>
          </div>
        </div>

        <footer>
          <p>&copy; 2025 rMirror Cloud. Open source and self-hostable.</p>
        </footer>
      </div>
    </div>
  );
}
