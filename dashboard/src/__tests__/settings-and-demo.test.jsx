// Settings never show what is not there, and the model choice is one that works.
// A test's [ID] ties it to docs/requirements.yml (scripts/check_requirements.py).
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../App';
import SettingsView from '../components/SettingsView';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const SETTINGS = {
  keys: [{ id: 'cidra_api_key', envVar: 'CIDRA_API_KEY', provider: 'openrouter.ai', label: '', masked: 'sk-or••••1234', configured: true }],
  models: { model_analyze: 'old/model', model_fix: 'old/model', base_url: 'https://openrouter.ai/api/v1' },
  flakiness: {}, system: {},
};

describe('settings', () => {
  it('[UI-SETTINGS-HONEST] with no API to read, says so instead of showing sample keys', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) })));
    render(<SettingsView />);
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('cidra dashboard'));
    expect(screen.getByText('Not connected')).toBeTruthy();
    expect(screen.queryByText(/••••/)).toBeNull();
  });

  it('[UI-MODELS] offers the models CIDRA is set up for and saves the model with its endpoint', async () => {
    const posts = [];
    vi.stubGlobal('fetch', vi.fn(async (url, options = {}) => {
      if (options.method === 'POST') posts.push(JSON.parse(options.body));
      return { ok: true, status: 200, json: async () => SETTINGS };
    }));
    render(<SettingsView />);
    fireEvent.click(await screen.findByText('Model Catalog & Routing'));
    expect(screen.getByText('claude-haiku-4-5')).toBeTruthy();
    expect(screen.queryByText(/claude-3\.5|gpt-4o|nemotron/)).toBeNull();
    fireEvent.click(screen.getAllByText('Use this model')[0]);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].models).toEqual({ model_analyze: 'claude-haiku-4-5', model_fix: 'claude-haiku-4-5',
                                      base_url: 'https://api.anthropic.com/v1/' });
  });
});

describe('command center', () => {
  it('[UI-DEMO] the scripted demo is labelled as one', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ stats: {}, runs: [] }) })));
    render(<App />);
    expect(await screen.findByText('Watch demo')).toBeTruthy();
    expect(screen.queryByText('Launch Pipeline')).toBeNull();
  });
});
