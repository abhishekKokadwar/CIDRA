import { defineConfig } from '@playwright/test';

// Two real dashboard servers on fixed scratch data (e2e/serve.py): one open,
// as on localhost, and one with CIDRA_DASHBOARD_TOKEN set.
const python = process.env.PYTHON || (process.platform === 'win32' ? 'py' : 'python');

export default defineConfig({
  testDir: 'e2e',
  use: { browserName: 'chromium', baseURL: 'http://127.0.0.1:8791' },
  webServer: [
    { command: `${python} e2e/serve.py 8791`, url: 'http://127.0.0.1:8791/', reuseExistingServer: false },
    { command: `${python} e2e/serve.py 8792 e2e-token`, url: 'http://127.0.0.1:8792/', reuseExistingServer: false },
  ],
});
