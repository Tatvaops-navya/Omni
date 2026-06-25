-- Krsna CRM — lead assignment tables (run in Supabase SQL Editor)

CREATE TABLE IF NOT EXISTS crm_users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'presales', 'rm')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_assignments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'tatva_presales',
    external_id TEXT NOT NULL,
    presales_user_id UUID REFERENCES crm_users(id) ON DELETE SET NULL,
    rm_user_id UUID REFERENCES crm_users(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'unassigned'
        CHECK (status IN ('unassigned', 'assigned', 'in_progress', 'presales_completed', 'rm_assigned', 'closed')),
    notes TEXT,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    assigned_at TIMESTAMPTZ,
    presales_completed_at TIMESTAMPTZ,
    rm_assigned_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, external_id)
);

CREATE INDEX IF NOT EXISTS lead_assignments_presales_user_idx
    ON lead_assignments (presales_user_id) WHERE presales_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS lead_assignments_rm_user_idx
    ON lead_assignments (rm_user_id) WHERE rm_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS lead_assignments_status_idx ON lead_assignments (status);
