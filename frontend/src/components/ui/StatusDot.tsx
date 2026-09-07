interface StatusDotProps {
  status: 'online' | 'offline' | 'connecting' | string;
}

export default function StatusDot({ status }: StatusDotProps) {
  const cls = status === 'online' ? 'online' : status === 'connecting' ? 'connecting' : 'offline';
  return <span className={`status-dot ${cls}`} />;
}
