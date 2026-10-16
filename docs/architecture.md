# Architecture

```text
Vue 3 + Ant Design Vue
        |
        | Bearer token / JSON
        v
FastAPI application
  |       |         |
  |       |         +-- AI provider adapter (disabled initially)
  |       +------------ Supabase Storage adapter (production files)
  +-------------------- SQLAlchemy database layer
                            |
                  SQLite local / Supabase PostgreSQL
```

The four business modules share local email/password authentication, permissions,
notifications, audit logs, file metadata and AI run records. Business data can use SQLite
locally or Supabase PostgreSQL in cloud mode. Resume files and inventory photos use
Supabase Storage when configured; development keeps a local fallback, while production
fails clearly instead of silently storing files on the server disk.
