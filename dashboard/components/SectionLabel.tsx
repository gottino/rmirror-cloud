interface SectionLabelProps {
  children: React.ReactNode;
}

export function SectionLabel({ children }: SectionLabelProps) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div
        className="w-6 h-px"
        style={{ backgroundColor: 'var(--warm-ink)' }}
      />
      <span
        style={{
          fontSize: '0.6875rem',
          fontWeight: 600,
          color: 'var(--warm-ink)',
          textTransform: 'uppercase',
          letterSpacing: '0.2em',
          fontFamily: 'var(--font-body)',
        }}
      >
        {children}
      </span>
    </div>
  );
}
