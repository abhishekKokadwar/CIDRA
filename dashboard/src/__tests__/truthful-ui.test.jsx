// The dashboard shows what is true about a run and the setup.
// A test's [ID] ties it to docs/requirements.yml (scripts/check_requirements.py).
import fs from 'node:fs';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import App from '../App';
import Sidebar from '../components/Sidebar';
import SettingsView from '../components/SettingsView';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function serve(routes) {
  vi.stubGlobal('fetch', vi.fn(async (url) => {
    const body = routes[String(url).split('?')[0]];
    return { ok: body !== undefined, status: body === undefined ? 404 : 200, json: async () => body };
  }));
}

const run = (id, outcome, status) => ({ id, outcome, status, repo: 'o/r', time: 'Oct 04, 19:00', telemetry: {} });

describe('runs', () => {
  it('[UI-OUTCOME] labels each run by its outcome, never a finished diagnosis as pending', async () => {
    serve({ '/telemetry.json': { stats: {}, runs: [
      run('r1', 'diagnosis_only', 'pending'), run('r2', 'verified_fix', 'success'),
      run('r3', 'flaky_detected', 'pending'), run('r4', 'failed', 'error'),
    ] } });
    render(<App />);
    expect(await screen.findByText('Diagnosis only')).toBeTruthy();
    for (const label of ['Verified fix', 'Flaky test', 'Failed']) expect(screen.getByText(label)).toBeTruthy();
    expect(screen.queryByText('Pending')).toBeNull();
  });
});

describe('settings', () => {
  it('[UI-KEYS] counts the keys that are set, not the rows', async () => {
    const key = (envVar, configured) => ({ id: envVar, envVar, provider: envVar, label: '', masked: '', configured });
    serve({ '/api/settings': { keys: [key('CIDRA_API_KEY', true), key('GEMINI_API_KEY', false), key('CIDRA_GITHUB_TOKEN', false)],
                               models: {}, flakiness: {}, system: {} } });
    render(<SettingsView />);
    expect(await screen.findByText('1 of 3 set')).toBeTruthy();
  });
});

describe('sidebar', () => {
  it('[UI-VERSION] shows the version of the package it ships in', () => {
    const version = fs.readFileSync('../pyproject.toml', 'utf-8').match(/^version = "(.+)"/m)[1];
    for (const collapsed of [false, true]) {
      const { unmount } = render(<Sidebar activeTab="overview" setActiveTab={() => {}} collapsed={collapsed} onToggleCollapse={() => {}} />);
      expect(screen.getByText(`v${version}`)).toBeTruthy();
      unmount();
    }
  });
});
