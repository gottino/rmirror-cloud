'use client';

import { ReactNode } from 'react';

interface MacWindowFrameProps {
  children: ReactNode;
  title?: string;
  className?: string;
  titleBarColor?: string;
}

export function MacWindowFrame({ children, title, className = '', titleBarColor = '#ffffff' }: MacWindowFrameProps) {
  return (
    <div className={`mac-window-frame ${className}`}>
      {/* Tahoe-style title bar - blends with content */}
      <div className="mac-title-bar" style={{ background: titleBarColor }}>
        <div className="mac-traffic-lights">
          <span className="mac-button mac-close" />
          <span className="mac-button mac-minimize" />
          <span className="mac-button mac-maximize" />
        </div>
        {title && <span className="mac-title">{title}</span>}
      </div>
      {/* Content */}
      <div className="mac-content">
        {children}
      </div>
      <style jsx>{`
        .mac-window-frame {
          border-radius: 12px;
          overflow: hidden;
          box-shadow: 0 20px 40px -8px rgba(0, 0, 0, 0.2),
                      0 0 0 0.5px rgba(0, 0, 0, 0.12);
          background: #fff;
        }
        .mac-title-bar {
          padding: 12px 14px;
          display: flex;
          align-items: center;
          min-height: 42px;
        }
        .mac-traffic-lights {
          display: flex;
          gap: 8px;
        }
        .mac-button {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          display: inline-block;
          box-shadow: inset 0 0 0 0.5px rgba(0, 0, 0, 0.12);
        }
        .mac-close {
          background: linear-gradient(180deg, #ff6058 0%, #ff5048 100%);
        }
        .mac-minimize {
          background: linear-gradient(180deg, #ffbe2f 0%, #ffb420 100%);
        }
        .mac-maximize {
          background: linear-gradient(180deg, #2aca44 0%, #24b93c 100%);
        }
        .mac-title {
          flex: 1;
          text-align: center;
          font-size: 13px;
          color: rgba(0, 0, 0, 0.85);
          font-weight: 500;
          margin-right: 52px; /* Balance the traffic lights */
          letter-spacing: -0.01em;
        }
        .mac-content {
          line-height: 0;
        }
        .mac-content :global(img) {
          display: block;
          width: 100%;
          height: auto;
        }
      `}</style>
    </div>
  );
}
