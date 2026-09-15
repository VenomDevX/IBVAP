// ======================== API Types ========================

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type CameraStatus = 'online' | 'offline' | 'connecting' | 'error' | 'stopped' | 'retired';

export interface Camera {
  camera_id: string;
  name: string;
  source?: string;
  location?: string;
  latitude?: number | null;
  longitude?: number | null;
  type?: string;
  status: CameraStatus;
  enabled?: boolean;
  fps?: number;
  active_tracks?: number;
  fps_limit?: number;
  resolution?: number[] | null;
  last_frame_at?: string | null;
  last_heartbeat?: string | null;
  stream_status?: string;
}

export type AlertStatus = 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'false_positive' | 'reopened';

export interface IncidentNote {
  author: string;
  note: string;
  created_at: string;
}

export interface Alert {
  alert_id: string;
  event_id: string;
  event_type: string;
  camera_id: string;
  risk_level: RiskLevel;
  risk_score: number;
  timestamp: string;
  track_id?: number | null;
  object_type?: string;
  contributing_factors?: string[];
  snapshot_path?: string;
  snapshot_hash?: string;
  reviewed: boolean;
  reviewed_by?: string;
  status?: AlertStatus;
  disposition?: 'true_alarm' | 'false_alarm' | 'test' | 'escalated' | null;
  assignee?: string | null;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  acknowledged_by?: string | null;
  resolved_by?: string | null;
  false_positive?: boolean;
  notes?: IncidentNote[];
}

export interface SpatialContext {
  in_restricted: boolean;
  fence_crossed: boolean;
  zones: string[];
}

export interface TemporalContext {
  is_night: boolean;
  is_loitering: boolean;
  semantic_description?: string;
}

export interface ScoreBreakdownItem {
  raw_score: number;
  weight: number;
  contribution: number;
  reasons: string[];
}

export interface Event {
  event_id: string;
  event_type: string;
  camera_id: string;
  track_id: number;
  track_uuid?: string;
  zone_id?: string | null;
  object_type: string;
  risk_level: RiskLevel;
  risk_score: number;
  timestamp: string;
  duration: number;
  contributing_factors: string[];
  spatial_context: SpatialContext;
  temporal_context: TemporalContext;
  evidence_path?: string;
  evidence_hash?: string;
  state?: 'PENDING' | 'OPEN' | 'ACTIVE' | 'CLOSED';
  opened_at?: string | null;
  last_updated?: string | null;
  closed_at?: string | null;
  score_breakdown?: Record<string, ScoreBreakdownItem>;
  evidence?: Array<{ evidence_id: number; type: string; created_at: string; download_url: string }>;
}

export type ZoneType = 'restricted' | 'buffer' | 'safe' | 'entry_exit';

export interface Zone {
  zone_id: string;
  name: string;
  camera_id: string;
  type: ZoneType | string;
  enabled: boolean;
  points: number[][];
  color?: number[];
}

export interface DashboardSummary {
  total_cameras: number;
  online_cameras: number;
  total_alerts: number;
  unreviewed_alerts: number;
  critical_alerts: number;
  active_tracks: number;
  open_incidents?: number;
  critical_high_incidents?: number;
}

export interface AlertStats {
  total_alerts: number;
  unreviewed: number;
  by_type: Record<string, number>;
  by_level: Record<string, number>;
}

export interface TimeseriesData {
  labels: string[];
  data: number[];
}

export interface Threat {
  track_id: string;
  camera_id: string;
  object_type: string;
  risk_score: number;
  risk_level: RiskLevel;
  risk_factors: string[];
  duration: number;
}

export interface ThreatsData {
  top_threats: Threat[];
  camera_distribution: Record<string, number>;
}

export interface AuditEntry {
  id: number;
  timestamp: string | number;
  username: string;
  action: string;
  ip_address?: string;
  details?: unknown;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page?: number;
  page_size?: number;
}
