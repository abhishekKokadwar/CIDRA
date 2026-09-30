import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const envPath = path.resolve(__dirname, '../.env');

function maskSecret(secret) {
  if (!secret) return '';
  if (secret.length <= 8) return '••••••••';
  return `${secret.slice(0, 7)}••••••••${secret.slice(-4)}`;
}

function parseEnv() {
  if (!fs.existsSync(envPath)) return {};
  const content = fs.readFileSync(envPath, 'utf-8');
  const env = {};
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const idx = trimmed.indexOf('=');
    if (idx !== -1) {
      const k = trimmed.slice(0, idx).trim();
      const v = trimmed.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '');
      env[k] = v;
    }
  }
  return env;
}

function writeEnv(updates) {
  let content = fs.existsSync(envPath) ? fs.readFileSync(envPath, 'utf-8') : '';
  let lines = content.split('\n');
  const updatedKeys = new Set();
  const newLines = lines.map((line) => {
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('#') && trimmed.includes('=')) {
      const k = trimmed.slice(0, trimmed.indexOf('=')).trim();
      if (k in updates) {
        updatedKeys.add(k);
        return `${k}=${updates[k]}`;
      }
    }
    return line;
  });

  for (const [k, v] of Object.entries(updates)) {
    if (!updatedKeys.has(k) && v !== undefined && v !== null) {
      newLines.push(`${k}=${v}`);
    }
  }

  fs.writeFileSync(envPath, newLines.join('\n'), 'utf-8');
}

function getSettingsPayload() {
  const env = parseEnv();
  return {
    keys: [
      {
        id: 'cidra_api_key',
        provider: 'OpenRouter',
        label: 'Primary LLM Inference Gateway',
        envVar: 'CIDRA_API_KEY',
        masked: maskSecret(env.CIDRA_API_KEY),
        configured: Boolean(env.CIDRA_API_KEY),
        canTest: true,
        baseUrl: env.CIDRA_BASE_URL || 'https://openrouter.ai/api/v1'
      },
      {
        id: 'nvidia_kimi',
        provider: 'NVIDIA NIM (Kimi)',
        label: 'Fast Fallback Tier 1',
        envVar: 'NVIDIA_API_KEY_KIMI',
        masked: maskSecret(env.NVIDIA_API_KEY_KIMI),
        configured: Boolean(env.NVIDIA_API_KEY_KIMI),
        canTest: true,
        baseUrl: 'https://integrate.api.nvidia.com/v1'
      },
      {
        id: 'nvidia_glm',
        provider: 'NVIDIA NIM (GLM)',
        label: 'Fast Fallback Tier 2',
        envVar: 'NVIDIA_API_KEY_GLM',
        masked: maskSecret(env.NVIDIA_API_KEY_GLM),
        configured: Boolean(env.NVIDIA_API_KEY_GLM),
        canTest: true,
        baseUrl: 'https://integrate.api.nvidia.com/v1'
      },
      {
        id: 'groq_api_key',
        provider: 'Groq Cloud',
        label: 'Ultra-Fast LPU Inference',
        envVar: 'GROQ_API_KEY',
        masked: maskSecret(env.GROQ_API_KEY),
        configured: Boolean(env.GROQ_API_KEY),
        canTest: true,
        baseUrl: 'https://api.groq.com/openai/v1'
      },
      {
        id: 'github_token',
        provider: 'GitHub PAT (Read/Write)',
        label: 'Automated Pull Requests & Branches',
        envVar: 'CIDRA_GITHUB_TOKEN',
        masked: maskSecret(env.CIDRA_GITHUB_TOKEN),
        configured: Boolean(env.CIDRA_GITHUB_TOKEN),
        canTest: true,
        baseUrl: 'https://api.github.com'
      },
      {
        id: 'github_token_ro',
        provider: 'GitHub PAT (Read-Only)',
        label: 'Safe CI Log & Metadata Fetching',
        envVar: 'CIDRA_GITHUB_TOKEN_RO',
        masked: maskSecret(env.CIDRA_GITHUB_TOKEN_RO),
        configured: Boolean(env.CIDRA_GITHUB_TOKEN_RO),
        canTest: true,
        baseUrl: 'https://api.github.com'
      },
      {
        id: 'webhook_secret',
        provider: 'Webhook HMAC Secret',
        label: 'GitHub Webhook Delivery Verification',
        envVar: 'CIDRA_WEBHOOK_SECRET',
        masked: maskSecret(env.CIDRA_WEBHOOK_SECRET),
        configured: Boolean(env.CIDRA_WEBHOOK_SECRET),
        canTest: false,
        baseUrl: ''
      }
    ],
    models: {
      model_analyze: env.CIDRA_MODEL_ANALYZE || 'anthropic/claude-3.5-sonnet',
      model_fix: env.CIDRA_MODEL_FIX || 'anthropic/claude-3.5-sonnet',
      base_url: env.CIDRA_BASE_URL || 'https://openrouter.ai/api/v1',
      nvidia_base_url: 'https://integrate.api.nvidia.com/v1',
      groq_base_url: 'https://api.groq.com/openai/v1'
    },
    flakiness: {
      flaky_runs: parseInt(env.FLAKY_RUNS || '5', 10),
      flaky_score_threshold: parseInt(env.FLAKY_SCORE_THRESHOLD || '1', 10),
      max_fix_attempts: parseInt(env.MAX_FIX_ATTEMPTS || '3', 10),
      container_timeout: parseInt(env.CONTAINER_TIMEOUT || '60', 10),
      enable_pr_creation: (env.CIDRA_ENABLE_PR_CREATION || 'false').toLowerCase() === 'true',
      practice_repo: env.CIDRA_PRACTICE_REPO_SLUG || 'helpmecode69/cidra-practice'
    },
    system: {
      python_version: '3.11.0',
      framework: 'LangGraph Core',
      idempotency_db: 'cidra_idempotency.db',
      worktree_root: 'worktrees',
      fix_cache_path: 'cidra_fix_cache.json',
      run_history_path: 'cidra_run_history.jsonl',
      status: 'operational',
      env_file: envPath
    }
  };
}

function cidraSettingsPlugin() {
  return {
    name: 'cidra-settings-api',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = req.url ? req.url.split('?')[0] : '';
        if (url === '/api/settings' && req.method === 'GET') {
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify(getSettingsPayload()));
          return;
        }

        if (url === '/api/settings' && req.method === 'POST') {
          let body = '';
          req.on('data', chunk => { body += chunk; });
          req.on('end', () => {
            try {
              const data = JSON.parse(body || '{}');
              const updates = {};

              if (data.keys && typeof data.keys === 'object') {
                for (const [k, v] of Object.entries(data.keys)) {
                  if (v && !v.includes('••••')) {
                    updates[k] = v;
                  }
                }
              }

              if (data.models) {
                if (data.models.model_analyze) updates['CIDRA_MODEL_ANALYZE'] = data.models.model_analyze;
                if (data.models.model_fix) updates['CIDRA_MODEL_FIX'] = data.models.model_fix;
                if (data.models.base_url) updates['CIDRA_BASE_URL'] = data.models.base_url;
              }

              if (data.flakiness) {
                if (data.flakiness.flaky_runs !== undefined) updates['FLAKY_RUNS'] = String(data.flakiness.flaky_runs);
                if (data.flakiness.flaky_score_threshold !== undefined) updates['FLAKY_SCORE_THRESHOLD'] = String(data.flakiness.flaky_score_threshold);
                if (data.flakiness.max_fix_attempts !== undefined) updates['MAX_FIX_ATTEMPTS'] = String(data.flakiness.max_fix_attempts);
                if (data.flakiness.container_timeout !== undefined) updates['CONTAINER_TIMEOUT'] = String(data.flakiness.container_timeout);
                if (data.flakiness.enable_pr_creation !== undefined) updates['CIDRA_ENABLE_PR_CREATION'] = String(data.flakiness.enable_pr_creation);
                if (data.flakiness.practice_repo) updates['CIDRA_PRACTICE_REPO_SLUG'] = String(data.flakiness.practice_repo);
              }

              if (Object.keys(updates).length > 0) {
                writeEnv(updates);
              }

              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify({ ok: true, message: 'Settings saved to .env', settings: getSettingsPayload() }));
            } catch (err) {
              res.statusCode = 500;
              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify({ ok: false, error: err.message }));
            }
          });
          return;
        }

        if (url === '/api/settings/test' && req.method === 'POST') {
          let body = '';
          req.on('data', chunk => { body += chunk; });
          req.on('end', async () => {
            try {
              const { provider_id } = JSON.parse(body || '{}');
              const env = parseEnv();
              const start = Date.now();

              if (provider_id === 'cidra_api_key') {
                const key = env.CIDRA_API_KEY;
                if (!key) throw new Error('No OpenRouter key configured in .env');
                const resp = await fetch('https://openrouter.ai/api/v1/auth/key', {
                  headers: { Authorization: `Bearer ${key}` }
                });
                const elapsed = Date.now() - start;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ ok: resp.ok, status: resp.status, latency_ms: elapsed, message: resp.ok ? 'OpenRouter Gateway Online' : 'Invalid or expired key' }));
                return;
              }

              if (provider_id === 'groq_api_key') {
                const key = env.GROQ_API_KEY;
                if (!key) throw new Error('No Groq key configured in .env');
                const resp = await fetch('https://api.groq.com/openai/v1/models', {
                  headers: { Authorization: `Bearer ${key}` }
                });
                const elapsed = Date.now() - start;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ ok: resp.ok, status: resp.status, latency_ms: elapsed, message: resp.ok ? 'Groq LPU Engine Online' : 'Invalid or expired key' }));
                return;
              }

              if (provider_id === 'nvidia_kimi' || provider_id === 'nvidia_glm') {
                const key = provider_id === 'nvidia_kimi' ? env.NVIDIA_API_KEY_KIMI : env.NVIDIA_API_KEY_GLM;
                if (!key) throw new Error('No NVIDIA NIM key configured in .env');
                const resp = await fetch('https://integrate.api.nvidia.com/v1/models', {
                  headers: { Authorization: `Bearer ${key}` }
                });
                const elapsed = Date.now() - start;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ ok: resp.ok, status: resp.status, latency_ms: elapsed, message: resp.ok ? 'NVIDIA NIM Cluster Online' : 'Invalid or expired key' }));
                return;
              }

              if (provider_id === 'github_token' || provider_id === 'github_token_ro') {
                const token = provider_id === 'github_token' ? env.CIDRA_GITHUB_TOKEN : env.CIDRA_GITHUB_TOKEN_RO;
                if (!token) throw new Error('No GitHub token configured in .env');
                const resp = await fetch('https://api.github.com/user', {
                  headers: { 
                    Authorization: `Bearer ${token}`,
                    'User-Agent': 'CIDRA-Engine/1.0',
                    Accept: 'application/vnd.github+json'
                  }
                });
                const elapsed = Date.now() - start;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ ok: resp.ok, status: resp.status, latency_ms: elapsed, message: resp.ok ? 'GitHub PAT Verified' : 'Authentication failed' }));
                return;
              }

              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify({ ok: false, error: `Testing not supported for ${provider_id}` }));
            } catch (err) {
              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify({ ok: false, error: err.message }));
            }
          });
          return;
        }

        next();
      });
    }
  };
}

function syncToPythonStatic() {
  return {
    name: 'sync-to-python-static',
    closeBundle() {
      try {
        const distDir = path.resolve(__dirname, 'dist');
        const staticDir = path.resolve(__dirname, '../cidra/static');
        if (fs.existsSync(distDir)) {
          fs.cpSync(distDir, staticDir, { recursive: true });
          console.log('[CIDRA] Successfully mirrored dist -> cidra/static');
        }
      } catch (e) {
        console.error('[CIDRA] Warning: could not mirror to cidra/static:', e.message);
      }
    }
  };
}

export default defineConfig({
  plugins: [tailwindcss(), react(), cidraSettingsPlugin(), syncToPythonStatic()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
