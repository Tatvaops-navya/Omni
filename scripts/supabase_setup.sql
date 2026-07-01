-- TatvaOps Omnichannel — run this entire file in Supabase SQL Editor
-- Do NOT paste supabase_store.py (that is Python). Use this file only.
-- When prompted about RLS, choose "Run and enable RLS".

-- Enquiries
CREATE TABLE IF NOT EXISTS enquiries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    phone_number TEXT,
    channel TEXT,
    extracted_fields JSONB,
    completed_fields JSONB,
    service_category TEXT,
    lead_score INTEGER,
    lead_tier TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Project summaries
CREATE TABLE IF NOT EXISTS project_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    phone_number TEXT,
    service_category TEXT,
    next_step TEXT,
    project_overview TEXT,
    scope_of_work JSONB,
    client_requirements TEXT,
    technical_specs TEXT,
    timeline TEXT,
    special_considerations TEXT,
    estimated_scope TEXT,
    design_direction TEXT,
    execution_readiness TEXT,
    enquiry_snapshot JSONB,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Session snapshots (admin / CRM)
CREATE TABLE IF NOT EXISTS sessions_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT UNIQUE NOT NULL,
    phone_number TEXT,
    channel TEXT,
    conversation_stage TEXT,
    field_completion_pct INTEGER,
    turn_count INTEGER,
    service_category TEXT,
    active_consultant TEXT,
    lead_score INTEGER,
    lead_tier TEXT,
    flow_state JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW()
);

-- WhatsApp file metadata (files live in Storage bucket enquiry-files — create public bucket in Supabase)
CREATE TABLE IF NOT EXISTS enquiry_attachments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    session_id TEXT NOT NULL,
    file_name TEXT,
    file_url TEXT,
    mime_type TEXT,
    uploaded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS enquiries_session_id_idx ON enquiries (session_id);
CREATE UNIQUE INDEX IF NOT EXISTS sessions_log_session_id_idx ON sessions_log (session_id);

-- Safe if tables already existed from an older partial run
ALTER TABLE enquiries ADD COLUMN IF NOT EXISTS service_category TEXT;
ALTER TABLE enquiries ADD COLUMN IF NOT EXISTS lead_score INTEGER;
ALTER TABLE enquiries ADD COLUMN IF NOT EXISTS lead_tier TEXT;
ALTER TABLE project_summaries ADD COLUMN IF NOT EXISTS service_category TEXT;
ALTER TABLE sessions_log ADD COLUMN IF NOT EXISTS service_category TEXT;
ALTER TABLE sessions_log ADD COLUMN IF NOT EXISTS active_consultant TEXT;
ALTER TABLE sessions_log ADD COLUMN IF NOT EXISTS lead_score INTEGER;
ALTER TABLE sessions_log ADD COLUMN IF NOT EXISTS lead_tier TEXT;
ALTER TABLE sessions_log ADD COLUMN IF NOT EXISTS flow_state JSONB;
