import '@testing-library/jest-dom';
import { vi } from 'vitest';
import React from 'react';

// Mock Next.js router
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
}));

// Mock Next.js Link component
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) =>
    React.createElement('a', { href }, children),
}));

// Mock Clerk hooks
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({
    getToken: vi.fn().mockResolvedValue('mock-token'),
    isSignedIn: true,
    isLoaded: true,
    userId: 'user_mock_id',
  }),
  useUser: () => ({
    user: {
      id: 'user_mock_id',
      emailAddresses: [{ emailAddress: 'test@example.com' }],
      fullName: 'Test User',
    },
    isLoaded: true,
    isSignedIn: true,
  }),
  SignIn: () => React.createElement('div', { 'data-testid': 'clerk-sign-in' }, 'Sign In'),
  SignUp: () => React.createElement('div', { 'data-testid': 'clerk-sign-up' }, 'Sign Up'),
  ClerkProvider: ({ children }: { children: React.ReactNode }) =>
    React.createElement(React.Fragment, null, children),
}));

// Mock CSS variables that components expect
const style = document.createElement('style');
style.innerHTML = `
  :root {
    --primary: #c85a54;
    --primary-foreground: #ffffff;
    --destructive: #c85a54;
    --amber-gold: #e8b65b;
    --sage-green: #9bb7a2;
    --warm-charcoal: #2c2c2c;
    --warm-gray: #6b6b6b;
    --soft-cream: #f5f5dc;
    --card: #ffffff;
    --border: #e0e0e0;
    --terracotta: #c85a54;
  }
`;
document.head.appendChild(style);

// Global test utilities
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock fetch for API tests
global.fetch = vi.fn();
