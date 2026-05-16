export function PageShell({
  children,
  className = '',
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`space-y-8 ${className}`.trim()}>{children}</div>;
}
