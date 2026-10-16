# Database Modes

## Local mode

The default `DATABASE_URL=sqlite:///./enterprise_ai.db` creates a real local database when
FastAPI starts. It contains demo users, notifications, audit logs and AI run records.

## Supabase mode

1. Create a Supabase project.
2. Run `supabase/migrations/0001_common_foundation.sql` in the SQL editor.
3. Copy `backend/.env.example` to `backend/.env`.
4. Set `DATABASE_URL` to the Supabase PostgreSQL connection string using the `psycopg` driver.
5. Add `SUPABASE_URL`, `SUPABASE_ANON_KEY` and the server-only service role key.
6. Open `/api/v1/health`; Supabase shows `configured` only when PostgreSQL REST, Auth admin API and Storage bucket probes all pass.
7. Replace local email/password JWT validation with Supabase JWT verification before production use.

Do not expose the service role key in the frontend.
