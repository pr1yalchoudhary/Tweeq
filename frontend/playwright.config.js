import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  outputDir: '../test-results/stage-one/playwright',
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:5174', viewport: { width: 1918, height: 955 }, deviceScaleFactor: 1, serviceWorkers: 'block', trace: 'retain-on-failure' },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174 --strictPort',
    url: 'http://127.0.0.1:5174', reuseExistingServer: false, timeout: 60000,
    env: { VITE_API_BASE_URL: '' },
  },
})
