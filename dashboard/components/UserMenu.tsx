'use client';

import { UserButton } from '@clerk/nextjs';
import { Shield, CreditCard } from 'lucide-react';

export default function UserMenu() {
  return (
    <UserButton afterSignOutUrl="/">
      <UserButton.MenuItems>
        <UserButton.Link
          label="Data & Privacy"
          labelIcon={<Shield className="w-4 h-4" />}
          href="/settings"
        />
        <UserButton.Link
          label="Billing"
          labelIcon={<CreditCard className="w-4 h-4" />}
          href="/billing"
        />
      </UserButton.MenuItems>
    </UserButton>
  );
}
