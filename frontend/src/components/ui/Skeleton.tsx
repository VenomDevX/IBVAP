export default function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} style={{ height: '1em', width: '100%' }} />;
}
