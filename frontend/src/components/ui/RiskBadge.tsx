import { getRiskEmoji } from '../../api/client';

interface RiskBadgeProps {
  level: string;
  showLabel?: boolean;
}

export default function RiskBadge({ level, showLabel = true }: RiskBadgeProps) {
  return (
    <span className={`risk-badge ${level}`}>
      {getRiskEmoji(level)} {showLabel && level}
    </span>
  );
}
