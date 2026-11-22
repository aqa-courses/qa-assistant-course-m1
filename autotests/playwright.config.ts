import { defineConfig, devices } from '@playwright/test';

export const BASE_URL = process.env.SHOPLITE_URL ?? 'http://localhost:8000';

export default defineConfig({
  testDir: './tests',
  // Every test starts from POST /__reset, which wipes the whole stand,
  // so tests run one after another against a single Shoplite instance.
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0, // no retries on purpose: flaky tests must stay visible to the RCA agent
  timeout: 30_000,
  // Short timeouts on purpose. With FLAKY_SEARCH a search answer takes up to 5 s:
  // a click that submits the search waits for that answer within actionTimeout,
  // so a slow answer turns into a flaky failure instead of a slow pass.
  // With DB_DOWN the 3 s also make the whole suite fail fast.
  expect: { timeout: 3_000 },
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
    ['json', { outputFile: 'results/results.json' }],
  ],
  use: {
    baseURL: BASE_URL,
    testIdAttribute: 'data-test',
    actionTimeout: 3_000,
    navigationTimeout: 10_000,
    locale: 'ru-RU',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    channel: process.env.PW_CHANNEL || undefined,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
