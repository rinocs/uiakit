import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:3100',
    trace: 'retain-on-failure',
    extraHTTPHeaders: { Origin: 'http://127.0.0.1:3100' },
  },
  webServer: [
    {
      command: 'node tests/browser/mock-gateway.mjs',
      port: 3101,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'node build',
      port: 3100,
      env: {
        PORT: '3100',
        ORIGIN: 'http://127.0.0.1:3100',
        UAI_GATEWAY_URL: 'http://127.0.0.1:3101',
        BODY_SIZE_LIMIT: '24M',
      },
      reuseExistingServer: !process.env.CI,
    },
  ],
});
