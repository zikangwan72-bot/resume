import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/uat',
  timeout: 30_000,
  workers: 1,
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    channel: 'msedge',
    trace: 'retain-on-failure',
  },
})

