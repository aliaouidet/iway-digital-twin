import { defineConfig, devices } from '@playwright/test';

/**
 * E2E config — runs against the mock-mode Docker stack.
 * Bring it up first: `docker compose up -d` (frontend :4200, api :8000).
 * Override the target with E2E_BASE_URL (e.g. the :4321 preview server).
 */
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:4200',
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
