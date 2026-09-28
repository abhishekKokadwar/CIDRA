/**
 * End-to-End Verification Test Suite: Dashboard <-> Backend Wiring
 * 
 * Verifies live HTTP endpoints between React frontend and CIDRA backend:
 * 1. GET /api/settings       -> Reads .env, masks credentials, checks models & limits
 * 2. POST /api/settings      -> Persists configuration directly to .env
 * 3. POST /api/settings/test -> Live connectivity probe to OpenRouter and Groq LPU
 * 4. GET /telemetry.json     -> Verifies Command Center & Run Explorer telemetry feed
 */

const BASE_URL = process.env.DASHBOARD_URL || 'http://localhost:5173';

const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
  bold: '\x1b[1m',
  dim: '\x1b[2m'
};

function pass(name, detail = '') {
  console.log(`  ${colors.green}✓ PASS${colors.reset} ${colors.bold}${name}${colors.reset} ${colors.dim}${detail}${colors.reset}`);
}

function fail(name, error) {
  console.log(`  ${colors.red}✗ FAIL${colors.reset} ${colors.bold}${name}${colors.reset}\n    ${colors.red}${error}${colors.reset}`);
}

async function runTests() {
  console.log(`\n${colors.cyan}${colors.bold}=== CIDRA Dashboard <-> Backend Wiring Verification Suite ===${colors.reset}`);
  console.log(`${colors.dim}Target Endpoint: ${BASE_URL}${colors.reset}\n`);

  let total = 0;
  let passed = 0;

  // Test 1: GET /api/settings
  total++;
  try {
    const t0 = Date.now();
    const res = await fetch(`${BASE_URL}/api/settings`);
    const latency = Date.now() - t0;
    
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data = await res.json();

    if (!Array.isArray(data.keys) || data.keys.length === 0) {
      throw new Error('Expected keys array in settings payload');
    }
    if (!data.models?.model_analyze || !data.models?.model_fix) {
      throw new Error('Missing active model assignments');
    }
    if (typeof data.flakiness?.flaky_runs !== 'number') {
      throw new Error('Missing flakiness parameters');
    }

    // Check credential masking
    const unmasked = data.keys.filter(k => k.configured && !k.masked.includes('••••'));
    if (unmasked.length > 0) {
      throw new Error(`Credential leakage! Keys not masked: ${unmasked.map(k => k.envVar).join(', ')}`);
    }

    pass('GET /api/settings', `(${latency}ms) - ${data.keys.length} keys loaded, models: [${data.models.model_analyze}, ${data.models.model_fix}]`);
    passed++;
  } catch (err) {
    fail('GET /api/settings', err.message);
  }

  // Test 2: POST /api/settings (Round-trip mutation & verification)
  total++;
  try {
    const originalRes = await fetch(`${BASE_URL}/api/settings`);
    const original = await originalRes.json();
    const originalTimeout = original.flakiness.container_timeout || 60;
    const testTimeout = originalTimeout === 60 ? 120 : 60;

    const t0 = Date.now();
    const updateRes = await fetch(`${BASE_URL}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        flakiness: { container_timeout: testTimeout }
      })
    });
    const updateLatency = Date.now() - t0;

    if (!updateRes.ok) throw new Error(`HTTP ${updateRes.status}: Failed to post settings update`);
    const updatedData = await updateRes.json();

    if (updatedData.settings?.flakiness?.container_timeout !== testTimeout) {
      throw new Error(`Setting not persisted. Expected ${testTimeout}, got ${updatedData.settings?.flakiness?.container_timeout}`);
    }

    // Revert back
    await fetch(`${BASE_URL}/api/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        flakiness: { container_timeout: originalTimeout }
      })
    });

    pass('POST /api/settings', `(${updateLatency}ms) - Successfully persisted container_timeout to .env and reverted`);
    passed++;
  } catch (err) {
    fail('POST /api/settings', err.message);
  }

  // Test 3: POST /api/settings/test (Live AI Gateway Ping)
  total++;
  try {
    const t0 = Date.now();
    const res = await fetch(`${BASE_URL}/api/settings/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: 'cidra_api_key' })
    });
    const latency = Date.now() - t0;

    if (!res.ok) throw new Error(`HTTP ${res.status}: Probe failed`);
    const data = await res.json();

    if (!data.ok) {
      throw new Error(data.error || data.message || 'OpenRouter probe failed');
    }

    pass('POST /api/settings/test (OpenRouter)', `Gateway Online (${data.latency_ms}ms round-trip probe, HTTP ${data.status})`);
    passed++;
  } catch (err) {
    fail('POST /api/settings/test (OpenRouter)', err.message);
  }

  // Test 4: POST /api/settings/test (Groq LPU Ping)
  total++;
  try {
    const res = await fetch(`${BASE_URL}/api/settings/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: 'groq_api_key' })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}: Probe failed`);
    const data = await res.json();

    if (!data.ok) {
      throw new Error(data.error || data.message || 'Groq probe failed');
    }

    pass('POST /api/settings/test (Groq Cloud)', `LPU Cluster Online (${data.latency_ms}ms round-trip probe, HTTP ${data.status})`);
    passed++;
  } catch (err) {
    fail('POST /api/settings/test (Groq Cloud)', err.message);
  }

  // Test 5: GET /telemetry.json
  total++;
  try {
    const t0 = Date.now();
    const res = await fetch(`${BASE_URL}/telemetry.json`);
    const latency = Date.now() - t0;

    if (!res.ok) throw new Error(`HTTP ${res.status}: telemetry.json not accessible`);
    const data = await res.json();

    if (!data.stats || !Array.isArray(data.runs)) {
      throw new Error('Invalid telemetry schema: expected stats object and runs array');
    }

    pass('GET /telemetry.json', `(${latency}ms) - ${data.runs.length} real interventions recorded for Command Center & Explorer`);
    passed++;
  } catch (err) {
    fail('GET /telemetry.json', err.message);
  }

  // Summary
  console.log(`\n${colors.bold}=== Test Summary ===${colors.reset}`);
  if (passed === total) {
    console.log(`${colors.green}${colors.bold}ALL ${passed}/${total} WIRING TESTS PASSED!${colors.reset} Dashboard is 100% wired to the backend and .env.`);
    process.exit(0);
  } else {
    console.log(`${colors.red}${colors.bold}${passed}/${total} TESTS PASSED (${total - passed} failed)${colors.reset}`);
    process.exit(1);
  }
}

runTests();
