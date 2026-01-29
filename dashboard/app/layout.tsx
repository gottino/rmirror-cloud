import type { Metadata } from "next";
import { ClerkProvider } from '@clerk/nextjs'
import "./globals.css";

export const metadata: Metadata = {
  title: "rMirror Dashboard",
  description: "View your transcribed reMarkable notebooks",
};

// rMirror design system colors for Clerk components
const clerkAppearance = {
  variables: {
    // Primary color affects buttons, links, focus rings, avatar background
    colorPrimary: '#c85a54',
    colorPrimaryHover: '#b54a44',
    // Text colors
    colorText: '#2d2a2e',
    colorTextSecondary: '#8b8680',
    // Background colors
    colorBackground: '#ffffff',
    colorInputBackground: '#ffffff',
    colorInputText: '#2d2a2e',
    // Border colors (darker for better contrast)
    colorNeutral: '#c9c4be',
  },
  elements: {
    // Card styling
    card: 'shadow-lg',
    // Social buttons
    socialButtonsBlockButton: 'border-[#c9c4be] hover:bg-[#faf8f5]',
    socialButtonsBlockButtonText: 'text-[#2d2a2e]',
    // User button
    userButtonPopoverCard: 'border border-[#c9c4be]',
    userButtonPopoverActionButton: 'hover:bg-[#faf8f5]',
    userButtonPopoverActionButtonText: 'text-[#2d2a2e]',
    userButtonPopoverFooter: 'border-t border-[#c9c4be]',
    // User profile modal
    modalContent: 'bg-white',
    navbarButton: 'text-[#2d2a2e] hover:bg-[#faf8f5]',
    navbarButtonIcon: 'text-[#8b8680]',
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider appearance={clerkAppearance}>
      <html lang="en">
        <body className="antialiased">
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
