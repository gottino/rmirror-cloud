'use client';

import { List, Grid3x3 } from 'lucide-react';

interface ViewToggleProps {
  value: 'list' | 'grid';
  onChange: (value: 'list' | 'grid') => void;
}

export function ViewToggle({ value, onChange }: ViewToggleProps) {
  return (
    <div
      className="flex overflow-hidden"
      style={{
        borderRadius: 'var(--radius)',
        border: '1px solid var(--border-sketch)',
      }}
    >
      <button
        onClick={() => onChange('list')}
        className="flex items-center gap-2 px-4 py-2.5 transition-colors"
        style={{
          backgroundColor: value === 'list' ? 'var(--card-paper)' : 'transparent',
          color: value === 'list' ? 'var(--warm-ink)' : 'var(--muted-sepia)',
          fontSize: '0.8125rem',
          fontWeight: 500,
          fontFamily: 'var(--font-body)',
          borderRight: '1px solid var(--border-sketch)',
        }}
      >
        <List className="w-4 h-4" />
        <span>List</span>
      </button>
      <button
        onClick={() => onChange('grid')}
        className="flex items-center gap-2 px-4 py-2.5 transition-colors"
        style={{
          backgroundColor: value === 'grid' ? 'var(--primary)' : 'transparent',
          color: value === 'grid' ? 'var(--primary-foreground)' : 'var(--muted-sepia)',
          fontSize: '0.8125rem',
          fontWeight: 500,
          fontFamily: 'var(--font-body)',
          borderTopRightRadius: 'calc(var(--radius) - 1px)',
          borderBottomRightRadius: 'calc(var(--radius) - 1px)',
        }}
      >
        <Grid3x3 className="w-4 h-4" />
        <span>Grid</span>
      </button>
    </div>
  );
}
