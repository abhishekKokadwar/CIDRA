import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
// The UI shows the version of the package it ships in.
const cidraVersion = fs.readFileSync(path.resolve(__dirname, '../pyproject.toml'), 'utf-8')
  .match(/^version = "(.+)"/m)[1];

function syncToPythonStatic() {
  return {
    name: 'sync-to-python-static',
    apply: 'build',  // not on dev or test runs: they would copy a stale dist
    closeBundle() {
      try {
        const distDir = path.resolve(__dirname, 'dist');
        const staticDir = path.resolve(__dirname, '../cidra/static');
        if (fs.existsSync(distDir)) {
          // Replace the hashed bundles, or every build leaves the old one behind
          fs.rmSync(path.join(staticDir, 'assets'), { recursive: true, force: true });
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
  plugins: [tailwindcss(), react(), syncToPythonStatic()],
  // `npm run dev` talks to the real backend (`cidra dashboard`, port 8000), so it
  // gets the same API, guard and .env handling as users do: no second copy here.
  server: {
    proxy: Object.fromEntries(['/api', '/telemetry.json'].map((p) => [p, 'http://127.0.0.1:8000'])),
  },
  define: { __CIDRA_VERSION__: JSON.stringify(cidraVersion) },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{js,jsx}'],
    // Floors at the measured level: raise them when coverage rises, never lower them
    // to get a change through. The browser tests (e2e/) are not counted here.
    coverage: {
      enabled: true,
      provider: 'v8',
      include: ['src/**'],
      exclude: ['src/__tests__/**', 'src/main.jsx'],
      reporter: ['text-summary'],
      thresholds: { statements: 27, branches: 35, functions: 20, lines: 30 },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
