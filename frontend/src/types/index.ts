// ======================== API Types ========================

export interface Camera {
  camera_id: string;
  name: string;
  source: string;
  status: 'online' | 'offline' | 'connecting';
  fps?: number;
}

export interface Alert {
  alert_id: string;
  event_id: string;
  event_type: string;
  camera_id: string;
  risk_level: RiskLevel;
  risk_score: number;
  timestamp: string;
  reviewed: boolean;
  reviewed_by?: string;
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
  track_id: string;
  object_type: string;
  risk_level: RiskLevel;
  risk_score: number;
  timestamp: string;
  duration: number;
  contributing_factors: string[];
  spatial_context: SpatialContext;
  temporal_context: TemporalContext;
  evidence_path?: string;
}

export interface Zone {
  zone_id: string;
  name: string;
  camera_id: string;
  type: string;
  enabled: boolean;
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
