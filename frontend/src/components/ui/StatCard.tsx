interface StatCardProps {
  icon: string;
  iconClass?: string;
  value: string | number;
  label: string;
  loading?: boolean;
  className?: string;
}

export default function StatCard({ icon, iconClass = '', value, label, loading = false, className = '' }: StatCardProps) {
  return (
    <div className={`stat-card ${className}`}>
      <div className={`stat-icon ${iconClass}`}>
        <i className={icon} />
      </div>
      <div className="stat-info">
        <span className={`stat-value ${loading ? 'skeleton' : ''}`}>{value}</span>
        <span className="stat-label">{label}</span>
      </div>
    </div>
  );
}
