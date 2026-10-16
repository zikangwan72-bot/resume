import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: 0,
  reporter: 'list',
  webServer: [
    {
      command:
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "$env:VITE_API_BASE_URL=\'http://127.0.0.1:8001\'; npm.cmd run dev -- --host 127.0.0.1 --port 5174"',
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command:
        'powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-Location ../backend; Remove-Item -Path ./playwright_enterprise_ai.db,./playwright_approval.db -Force -ErrorAction SilentlyContinue; $env:DATABASE_URL=\'sqlite:///./playwright_enterprise_ai.db\'; $env:APPROVAL_DATABASE_URL=\'sqlite:///./playwright_approval.db\'; $env:JWT_SECRET=\'playwright-secret\'; ./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001"',
      url: 'http://127.0.0.1:8001/api/v1/health',
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    channel: 'msedge',
    trace: 'retain-on-failure',
  },
})
