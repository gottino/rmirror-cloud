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
  },
  elements: {
    // Card styling
    card: 'bg-white shadow-lg border border-[#c9c4be]',
    // Text colors
    headerTitle: 'text-[#2d2a2e]',
    headerSubtitle: 'text-[#6b6660]',
    // Social buttons
    socialButtonsBlockButton: 'border-[#c9c4be] hover:bg-[#faf8f5]',
    socialButtonsBlockButtonText: 'text-[#2d2a2e]',
    // Dividers
    dividerLine: 'bg-[#c9c4be]',
    dividerText: 'text-[#6b6660]',
    // Form fields
    formFieldLabel: 'text-[#2d2a2e]',
    formFieldInput: 'border-[#c9c4be] focus:border-[#c85a54] focus:ring-[#c85a54]',
    // Primary button (terracotta)
    formButtonPrimary: 'bg-[#c85a54] hover:bg-[#b54a44]',
    // Links
    footerActionLink: 'text-[#c85a54] hover:text-[#b54a44]',
    identityPreviewEditButton: 'text-[#c85a54]',
    // User button popover
    userButtonPopoverCard: 'border border-[#c9c4be]',
    userButtonPopoverActionButton: 'hover:bg-[#faf8f5]',
    userButtonPopoverActionButtonText: 'text-[#2d2a2e]',
    userButtonPopoverFooter: 'border-t border-[#c9c4be]',
    // User profile modal
    modalContent: 'bg-white',
    navbarButton: 'text-[#2d2a2e] hover:bg-[#faf8f5]',
    navbarButtonIcon: 'text-[#6b6660]',
    profileSectionPrimaryButton: 'text-[#c85a54]',
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
