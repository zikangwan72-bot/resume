import { defineConfig } from '@playwright/test'

const isWindows = process.platform === 'win32'
const python = isWindows ? '.venv\\Scripts\\python.exe' : process.env.PLAYWRIGHT_PYTHON ?? '.venv/bin/python'
const playwrightDbs = ['playwright_enterprise_ai.db', 'playwright_approval.db']
const resetDbs = `${python} -c "import pathlib; [pathlib.Path(p).unlink(missing_ok=True) for p in ${JSON.stringify(playwrightDbs).replaceAll('"', "'")}]"`

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  webServer: [
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5174',
      env: { VITE_API_BASE_URL: 'http://127.0.0.1:8001' },
      url: 'http://127.0.0.1:5174',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      // `&&` works in both cmd.exe (Windows) and sh (Linux/macOS).
      command: `${resetDbs} && ${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8001`,
      cwd: '../backend',
      env: {
        DATABASE_URL: `sqlite:///./${playwrightDbs[0]}`,
        APPROVAL_DATABASE_URL: `sqlite:///./${playwrightDbs[1]}`,
        JWT_SECRET: 'playwright-secret',
        APP_ENV: 'development',
        SEED_DEMO: 'true',
        LOG_LEVEL: 'WARNING',
      },
      url: 'http://127.0.0.1:8001/api/v1/health',
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
  use: {
    baseURL: 'http://127.0.0.1:5174',
    ...(isWindows ? { channel: 'msedge' } : {}),
    trace: 'retain-on-failure',
  },
})
