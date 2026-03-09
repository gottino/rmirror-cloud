interface SkeletonProps {
  className?: string;
  style?: React.CSSProperties;
}

export function Skeleton({ className = '', style }: SkeletonProps) {
  return (
    <div
      className={`animate-pulse ${className}`}
      style={{
        backgroundColor: 'var(--border)',
        borderRadius: 'var(--radius-sm)',
        ...style,
      }}
    />
  );
}
