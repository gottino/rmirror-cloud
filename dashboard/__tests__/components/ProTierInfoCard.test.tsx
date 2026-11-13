import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ProTierInfoCard } from '../../components/ProTierInfoCard';

describe('ProTierInfoCard', () => {
  it('is informational only: no email input or waitlist form', () => {
    const { container } = render(<ProTierInfoCard />);

    expect(screen.getByText('Pro Tier')).toBeInTheDocument();
    expect(container.querySelector('input')).toBeNull();
    expect(container.querySelector('form')).toBeNull();
    expect(screen.queryByText(/waitlist/i)).toBeNull();
  });
});
