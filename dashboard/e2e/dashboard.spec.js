// Every screen of the real dashboard, in a browser, against the real server.
// A test's [ID] ties it to docs/requirements.yml (scripts/check_requirements.py).
import { test as base, expect } from '@playwright/test';

const TOKEN_SERVER = 'http://127.0.0.1:8792';

// Any console error, uncaught exception or failed request fails the test.
const test = base.extend({
  problems: [async ({ page }, use) => {
    const problems = [];
    page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });
    page.on('pageerror', (e) => problems.push(`page error: ${e.message}`));
    page.on('response', (r) => { if (r.status() >= 400) problems.push(`${r.status()} ${r.url()}`); });
    await use(problems);
    expect(problems).toEqual([]);
  }, { auto: true }],
});

const nav = (page, name) => page.getByRole('navigation').getByText(name, { exact: true }).click();

// Buttons on screen whose label is drawn in the colour of their own background.
const unreadableButtons = (page) => page.evaluate(() => [...document.querySelectorAll('button')]
  .filter((b) => b.offsetParent && b.textContent.trim())
  .filter((b) => { const s = getComputedStyle(b); return s.color === s.backgroundColor; })
  .map((b) => b.textContent.trim()));

test('[UI-SCREENS] every screen opens without an error', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Command Center' })).toBeVisible();
  await nav(page, 'Pipeline Orchestrator');
  await expect(page.getByRole('heading', { name: 'Pipeline Orchestrator' })).toBeVisible();
  await nav(page, 'Run Explorer');
  await expect(page.getByRole('heading', { name: /^Run: / })).toBeVisible();
  await nav(page, 'Pull Requests');
  await expect(page.getByRole('heading', { name: 'Pull Requests' })).toBeVisible();
  await nav(page, 'Settings');
  await expect(page.getByRole('heading', { name: 'Engine Settings & Configuration' })).toBeVisible();
  expect(await unreadableButtons(page)).toEqual([]);
  await nav(page, 'Pipeline Orchestrator');
  expect(await unreadableButtons(page)).toEqual([]);
});

test('[UI-OWN-RUNS] the Command Center lists this directory\'s runs with their outcomes', async ({ page }) => {
  await page.goto('/');
  const rows = page.locator('tbody tr');
  await expect(rows).toHaveCount(3);
  for (const [id, label] of [['e2e-fix', 'Verified fix'], ['e2e-diag', 'Diagnosis only'], ['e2e-flaky', 'Flaky test']]) {
    await expect(rows.filter({ hasText: id })).toContainText(label);
  }
  await expect(page.getByText('37226464198')).toHaveCount(0);  // the sample bundled in the package
});

test('[UI-SCREENS] a run opens in the explorer with its patch, and approval is recorded', async ({ page }) => {
  await page.goto('/');
  await page.locator('tbody tr', { hasText: 'e2e-fix' }).click();
  await expect(page.getByRole('heading', { name: 'Run: e2e-fix' })).toBeVisible();
  await expect(page.getByText('return a + b')).toBeVisible();
  await page.getByRole('button', { name: /Record approval/ }).click();
  await expect(page.getByRole('button', { name: 'Approval recorded' })).toBeDisabled();
});

test('[UI-SCREENS] Pull Requests lists the PR a run opened', async ({ page }) => {
  await page.goto('/');
  await nav(page, 'Pull Requests');
  await expect(page.locator('tbody tr', { hasText: 'acme/calc' })).toContainText('#7');
});

test('[UI-ENV] Settings shows the scratch .env the server runs with', async ({ page }) => {
  await page.goto('/');
  await nav(page, 'Settings');
  await expect(page.getByText('1 of 5 set')).toBeVisible();
  await expect(page.getByText(/0001$/)).toBeVisible();
});

test('[UI-STATIC] the favicon and every file the page loads are served', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Command Center' })).toBeVisible();
  expect((await page.request.get('/favicon.svg')).status()).toBe(200);
});

test('[UI-TOKEN] with a dashboard token, the link carrying it works and a page without it says what to do', async ({ page, browser, problems }) => {
  await page.goto(`${TOKEN_SERVER}/#token=e2e-token`);
  await expect(page.locator('tbody tr')).toHaveCount(3);
  expect(page.url()).not.toContain('token');  // moved out of the address bar
  await nav(page, 'Settings');
  await expect(page.getByText('1 of 5 set')).toBeVisible();

  const stranger = await browser.newPage();
  await stranger.goto(TOKEN_SERVER);
  await expect(stranger.getByRole('alert')).toContainText('needs its access token');
  await expect(stranger.locator('tbody tr', { hasText: 'e2e-' })).toHaveCount(0);
  await stranger.close();
  expect(problems).toEqual([]);  // the stranger's 401s are on its own page, which is not watched
});

test('[UI-MODELS] choosing a model saves it with its endpoint to the server\'s .env', async ({ page }) => {
  await page.goto('/');
  await nav(page, 'Settings');
  await page.getByText('Model Catalog & Routing').click();
  await page.getByRole('button', { name: 'Use this model' }).first().click();  // claude-haiku-4-5
  await expect(page.getByRole('button', { name: '✓ In use' })).toBeVisible();
  const saved = await (await page.request.get('/api/settings')).json();
  expect(saved.models).toMatchObject({ model_fix: 'claude-haiku-4-5', base_url: 'https://api.anthropic.com/v1/' });
});
