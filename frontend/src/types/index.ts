// ======================== API Types ========================

export interface Camera {
  camera_id: string;
  name: string;
  source?: string;
  location?: string;
  latitude?: number | null;
  longitude?: number | null;
  type?: string;
  status: 'online' | 'offline' | 'connecting' | 'error' | 'stopped' | 'retired';
  enabled?: boolean;
  fps?: number;
  active_tracks?: number;
  fps_limit?: number;
  resolution?: number[] | null;
  last_frame_at?: string | null;
  last_heartbeat?: string | null;
  stream_status?: string;
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
  status?: 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'false_positive' | 'reopened';
  disposition?: 'true_alarm' | 'false_alarm' | 'test' | 'escalated' | null;
  assignee?: string | null;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
  acknowledged_by?: string | null;
  resolved_by?: string | null;
  false_positive?: boolean;
  notes?: Array<{ author: string; note: string; created_at: string }>;
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
  score_breakdown?: Record<string, { raw_score: number; weight: number; contribution: number; reasons: string[] }>;
  evidence?: Array<{ evidence_id: number; type: string; created_at: string; download_url: string }>;
}

export interface Zone {
  zone_id: string;
  name: string;
  camera_id: string;
  type: string;
  enabled: boolean;
  points: number[][];
  color?: number[];
}

export interface User {
  username: string;
  full_name: string;
  role: 'admin' | 'operator';
  is_active: boolean;
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

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

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
