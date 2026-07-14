-- Sales targets for CRM team performance (run in Supabase SQL editor)

CREATE TABLE IF NOT EXISTS sales_targets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  staff_type TEXT NOT NULL CHECK (staff_type IN ('sales', 'rm')),
  staff_id TEXT NOT NULL,
  period TEXT NOT NULL CHECK (period IN ('day', 'month', 'quarter', 'half_year', 'year', 'all')),
  target_leads INTEGER NOT NULL DEFAULT 0 CHECK (target_leads >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (staff_type, staff_id, period)
);

CREATE INDEX IF NOT EXISTS idx_sales_targets_staff
  ON sales_targets (staff_type, staff_id);
