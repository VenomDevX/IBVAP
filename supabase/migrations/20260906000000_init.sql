-- Create cameras table
CREATE TABLE cameras (
    id SERIAL PRIMARY KEY,
    camera_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    location_label VARCHAR(200) DEFAULT '',
    stream_url VARCHAR(500) NOT NULL,
    camera_type VARCHAR(50) DEFAULT 'general',
    status VARCHAR(20) DEFAULT 'offline',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create tracks table
CREATE TABLE tracks (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL,
    camera_id VARCHAR(50) REFERENCES cameras(camera_id) NOT NULL,
    object_type VARCHAR(50) NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP WITH TIME ZONE,
    trajectory JSONB DEFAULT '[]'::jsonb,
    total_distance FLOAT DEFAULT 0.0,
    average_speed FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create events table
CREATE TABLE events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(50) UNIQUE NOT NULL,
    camera_id VARCHAR(50) REFERENCES cameras(camera_id) NOT NULL,
    track_id INTEGER,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    duration FLOAT DEFAULT 0.0,
    object_type VARCHAR(50) DEFAULT '',
    confidence FLOAT DEFAULT 0.0,
    risk_score FLOAT DEFAULT 0.0,
    risk_level VARCHAR(20) DEFAULT 'low',
    contributing_factors JSONB DEFAULT '[]'::jsonb,
    spatial_context JSONB DEFAULT '{}'::jsonb,
    temporal_context JSONB DEFAULT '{}'::jsonb,
    evidence_path VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create alerts table
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    alert_id VARCHAR(50) UNIQUE NOT NULL,
    camera_id VARCHAR(50) REFERENCES cameras(camera_id) NOT NULL,
    event_id VARCHAR(50) REFERENCES events(event_id) NOT NULL,
    track_id INTEGER,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    risk_score FLOAT DEFAULT 0.0,
    risk_level VARCHAR(20) DEFAULT 'low',
    object_type VARCHAR(50) DEFAULT '',
    contributing_factors JSONB DEFAULT '[]'::jsonb,
    snapshot_path VARCHAR(500),
    plate_result VARCHAR(50),
    identity_result VARCHAR(100),
    reviewed BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create zones table
CREATE TABLE zones (
    id SERIAL PRIMARY KEY,
    zone_id VARCHAR(50) UNIQUE NOT NULL,
    camera_id VARCHAR(50) NOT NULL,
    name VARCHAR(200) NOT NULL,
    zone_type VARCHAR(50) DEFAULT 'restricted',
    points JSONB DEFAULT '[]'::jsonb,
    color JSONB DEFAULT '[255, 0, 0]'::jsonb,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Create user_profiles table (linking to Supabase Auth auth.users)
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'operator',
    full_name VARCHAR(200) DEFAULT '',
    allowed_areas JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Note: We don't need 'users' table anymore because auth.users handles authentication
-- Note: We don't need audit_logs for now, but could be added later.

-- Enable Row Level Security (RLS) for all tables
ALTER TABLE cameras ENABLE ROW LEVEL SECURITY;
ALTER TABLE tracks ENABLE ROW LEVEL SECURITY;
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE zones ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

-- Create default policies (allow all authenticated users to read/write for now)
CREATE POLICY "Allow authenticated read access" ON cameras FOR SELECT TO authenticated USING (true);
CREATE POLICY "Allow authenticated read access" ON tracks FOR SELECT TO authenticated USING (true);
CREATE POLICY "Allow authenticated read access" ON events FOR SELECT TO authenticated USING (true);
CREATE POLICY "Allow authenticated read access" ON alerts FOR SELECT TO authenticated USING (true);
CREATE POLICY "Allow authenticated read access" ON zones FOR SELECT TO authenticated USING (true);
CREATE POLICY "Allow authenticated read access" ON user_profiles FOR SELECT TO authenticated USING (true);

-- Allow service role (backend) to do everything
CREATE POLICY "Allow service role full access" ON cameras USING (true) WITH CHECK (true);
CREATE POLICY "Allow service role full access" ON tracks USING (true) WITH CHECK (true);
CREATE POLICY "Allow service role full access" ON events USING (true) WITH CHECK (true);
CREATE POLICY "Allow service role full access" ON alerts USING (true) WITH CHECK (true);
CREATE POLICY "Allow service role full access" ON zones USING (true) WITH CHECK (true);
CREATE POLICY "Allow service role full access" ON user_profiles USING (true) WITH CHECK (true);

-- Realtime subscriptions setup
begin;
  drop publication if exists supabase_realtime;
  create publication supabase_realtime;
commit;
alter publication supabase_realtime add table alerts;
alter publication supabase_realtime add table events;
