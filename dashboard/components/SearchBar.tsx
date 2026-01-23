'use client';

import { Search, X } from 'lucide-react';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function SearchBar({ value, onChange, placeholder = 'Search notebooks...' }: SearchBarProps) {
  return (
    <div
      className="flex items-center gap-3"
      style={{
        backgroundColor: 'var(--card-paper)',
        border: '1px solid var(--border-sketch)',
        borderRadius: 'var(--radius-pill)',
        padding: '0 1rem',
        height: 44,
        width: 480,
        maxWidth: '100%',
      }}
    >
      <Search
        className="w-[18px] h-[18px] flex-shrink-0"
        style={{ color: 'var(--muted-sepia)' }}
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="flex-1 bg-transparent outline-none"
        style={{
          color: 'var(--warm-ink)',
          fontSize: '0.875rem',
          fontFamily: 'var(--font-body)',
        }}
      />
      {value && (
        <button
          onClick={() => onChange('')}
          className="flex-shrink-0 p-1 rounded-full transition-colors hover:bg-[var(--secondary)]"
          style={{ color: 'var(--muted-sepia)' }}
        >
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
