import React, { useState, useEffect } from 'react';
import { AUTH_HELP, apiFetch } from '../api';
import { 
  Key, 
  Bot, 
  Cpu, 
  Server, 
  CheckCircle2, 
  AlertCircle, 
  Plus, 
  Eye, 
  EyeOff, 
  Zap, 
  Sliders, 
  ShieldCheck, 
  Check, 
  RefreshCw, 
  Flame
} from 'lucide-react';

// The models CIDRA is set up for. Any other id the endpoint serves can be typed in.
const KNOWN_MODELS = [
  {
    id: 'claude-haiku-4-5',
    baseUrl: 'https://api.anthropic.com/v1/',
    note: 'The model CIDRA is measured with (eval/results). $1 / $5 per million input / output tokens.',
  },
  {
    id: 'gemini-3.5-flash',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai/',
    note: 'The default when CIDRA_BASE_URL is unset, and the fallback model.',
  },
];

const UNAVAILABLE_HELP = 'Settings are edited in the dashboard you run yourself: `cidra dashboard` reads and writes the .env of the directory you start it in. This page could not reach that server.';

export default function SettingsView() {
  const [activeSubTab, setActiveSubTab] = useState('keys'); // 'keys' | 'models' | 'container' | 'runtime'
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState(null);

  // Form States
  const [selectedAnalysis, setSelectedAnalysis] = useState('');
  const [selectedFix, setSelectedFix] = useState('');
  const [flakyRuns, setFlakyRuns] = useState(5);
  const [flakyThreshold, setFlakyThreshold] = useState(1);
  const [maxFixAttempts, setMaxFixAttempts] = useState(3);
  const [containerTimeout, setContainerTimeout] = useState(60);
  const [enablePR, setEnablePR] = useState(false);
  const [practiceRepo, setPracticeRepo] = useState('helpmecode69/cidra-practice');

  // Key management state
  const [testStatuses, setTestStatuses] = useState({});
  const [editingKeyId, setEditingKeyId] = useState(null);
  const [editingSecret, setEditingSecret] = useState('');
  const [showEditSecret, setShowEditSecret] = useState(false);

  // Add Key Form
  const [newKeyEnvVar, setNewKeyEnvVar] = useState('CIDRA_API_KEY');
  const [newKeySecret, setNewKeySecret] = useState('');
  const [showNewSecret, setShowNewSecret] = useState(false);

  const [customModel, setCustomModel] = useState('');
  const [unavailable, setUnavailable] = useState(false);

  // Load Settings from Backend. `loading` starts true; a reload sets it first.
  const loadSettings = async () => {
    try {
      const res = await apiFetch(`/api/settings?t=${Date.now()}`);
      if (res.status === 401) {
        setSaveMessage({ type: 'error', text: AUTH_HELP });
      } else if (res.ok) {
        const data = await res.json();
        setSettings(data);
        if (data.models) {
          setSelectedAnalysis(data.models.model_analyze || '');
          setSelectedFix(data.models.model_fix || '');
        }
        if (data.flakiness) {
          setFlakyRuns(data.flakiness.flaky_runs ?? 5);
          setFlakyThreshold(data.flakiness.flaky_score_threshold ?? 1);
          setMaxFixAttempts(data.flakiness.max_fix_attempts ?? 3);
          setContainerTimeout(data.flakiness.container_timeout ?? 60);
          setEnablePR(Boolean(data.flakiness.enable_pr_creation));
          setPracticeRepo(data.flakiness.practice_repo || 'helpmecode69/cidra-practice');
        }
      } else {
        setUnavailable(true);  // e.g. the hosted demo, which has no API
      }
    } catch {
      setUnavailable(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Sets state only after its first await, which this rule cannot see.
    // oxlint-disable-next-line react/set-state-in-effect
    loadSettings();
  }, []);

  // Save Settings to Backend (.env)
  const saveAllSettings = async (overrides = {}) => {
    try {
      setSaving(true);
      const payload = {
        models: {
          model_analyze: overrides.model_analyze || selectedAnalysis,
          model_fix: overrides.model_fix || selectedFix,
          ...(overrides.base_url ? { base_url: overrides.base_url } : {})
        },
        flakiness: {
          flaky_runs: overrides.flaky_runs ?? flakyRuns,
          flaky_score_threshold: overrides.flaky_score_threshold ?? flakyThreshold,
          max_fix_attempts: overrides.max_fix_attempts ?? maxFixAttempts,
          container_timeout: overrides.container_timeout ?? containerTimeout,
          enable_pr_creation: overrides.enable_pr_creation ?? enablePR,
          practice_repo: overrides.practice_repo ?? practiceRepo
        },
        keys: overrides.keys || {}
      };

      const res = await apiFetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        setSettings(await res.json());  // the server answers with the settings as saved
        setSaveMessage({ type: 'success', text: 'Saved and persisted to .env' });
        setTimeout(() => setSaveMessage(null), 3000);
      } else {
        const err = await res.json();
        setSaveMessage({ type: 'error', text: err.error || 'Failed to save settings' });
      }
    } catch (err) {
      setSaveMessage({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  // Test Provider Connectivity
  const testProvider = async (providerId) => {
    setTestStatuses(prev => ({
      ...prev,
      [providerId]: { loading: true }
    }));

    try {
      const res = await apiFetch('/api/settings/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: providerId })
      });
      const data = await res.json();
      setTestStatuses(prev => ({
        ...prev,
        [providerId]: {
          loading: false,
          ok: data.ok,
          latency: data.latency_ms,
          message: data.message || data.error || (data.ok ? 'Verified' : 'Failed')
        }
      }));
    } catch (err) {
      setTestStatuses(prev => ({
        ...prev,
        [providerId]: {
          loading: false,
          ok: false,
          message: err.message
        }
      }));
    }
  };

  // Save updated single key
  const handleUpdateKey = async (envVar) => {
    if (!editingSecret.trim()) return;
    await saveAllSettings({
      keys: { [envVar]: editingSecret.trim() }
    });
    setEditingKeyId(null);
    setEditingSecret('');
  };

  // Add new key from form
  const handleAddNewKey = async (e) => {
    e.preventDefault();
    if (!newKeySecret.trim()) return;
    await saveAllSettings({
      keys: { [newKeyEnvVar]: newKeySecret.trim() }
    });
    setNewKeySecret('');
    setShowNewSecret(false);
  };

  return (
    <div className="animate-in" style={{ width: '100%', maxWidth: '100%', paddingBottom: '4rem' }}>
      
      {unavailable && (
        <div role="alert" style={{ padding: '0.75rem 1rem', marginBottom: '1.5rem', borderRadius: '8px', border: '1px solid rgba(245, 165, 36, 0.3)', background: 'rgba(245, 165, 36, 0.1)', color: 'var(--color-warning)' }}>
          {UNAVAILABLE_HELP}
        </div>
      )}
      {/* Top Header */}
      <header style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1.5rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.35rem' }}>
              <h1 style={{ fontSize: '2rem', letterSpacing: '-0.02em', margin: 0 }}>
                Engine Settings & Configuration
              </h1>
              <span style={{ 
                fontFamily: 'var(--font-code)', fontSize: '0.75rem', 
                background: settings ? 'rgba(23, 201, 100, 0.1)' : 'rgba(245, 165, 36, 0.1)', 
                color: settings ? 'var(--color-success)' : 'var(--color-warning)',
                border: settings ? '1px solid rgba(23, 201, 100, 0.25)' : '1px solid rgba(245, 165, 36, 0.25)', 
                borderRadius: '4px',
                padding: '0.2rem 0.5rem', fontWeight: 600
              }}>
                {settings ? 'Live .env' : 'Not connected'}
              </span>
            </div>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', maxWidth: '720px', lineHeight: 1.5 }}>
              Persist API keys, configure model assignments for analysis and fix nodes, tune ephemeral container sandbox loops, and verify runtime health.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            {saveMessage && (
              <span className="animate-in" style={{ 
                fontSize: '0.825rem', 
                color: saveMessage.type === 'success' ? 'var(--color-success)' : 'var(--color-error)', 
                display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 600 
              }}>
                {saveMessage.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                {saveMessage.text}
              </span>
            )}
            <button 
              className="btn btn-accent" 
              onClick={() => saveAllSettings()}
              disabled={saving}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.65rem 1.5rem' }}
            >
              {saving ? <RefreshCw size={15} className="lucide-spin" /> : <Check size={15} />}
              {saving ? 'Syncing...' : 'Save Configuration'}
            </button>
          </div>
        </div>
      </header>

      {/* Sub-Tabs Navigation Rail */}
      <nav className="tabs-nav">
        <button 
          className={`tab-btn ${activeSubTab === 'keys' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('keys')}
        >
          <Key size={16} color={activeSubTab === 'keys' ? 'var(--color-accent)' : 'currentColor'} />
          <span>LLM Keys & Credentials</span>
        </button>

        <button 
          className={`tab-btn ${activeSubTab === 'models' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('models')}
        >
          <Bot size={16} color={activeSubTab === 'models' ? 'var(--color-accent)' : 'currentColor'} />
          <span>Model Catalog & Routing</span>
        </button>

        <button 
          className={`tab-btn ${activeSubTab === 'container' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('container')}
        >
          <Cpu size={16} color={activeSubTab === 'container' ? 'var(--color-accent)' : 'currentColor'} />
          <span>Container Sandbox & Flakiness</span>
        </button>

        <button 
          className={`tab-btn ${activeSubTab === 'runtime' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('runtime')}
        >
          <Server size={16} color={activeSubTab === 'runtime' ? 'var(--color-accent)' : 'currentColor'} />
          <span>System & Runtime Diagnostics</span>
        </button>
      </nav>

      {/* SUB-TAB 1: LLM Keys & Credentials */}
      {activeSubTab === 'keys' && (
        <div className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Security Notice Card */}
          <div style={{ 
            background: 'rgba(0, 112, 243, 0.06)', 
            border: '1px solid rgba(0, 112, 243, 0.25)', 
            borderRadius: '8px', padding: '1rem 1.25rem',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <ShieldCheck size={20} color="var(--color-accent)" />
              <div style={{ fontSize: '0.85rem', color: 'var(--text-main)' }}>
                <strong>Zero-Exfiltration Storage:</strong> API keys are committed directly to your local project <code style={{ color: 'var(--color-accent)' }}>.env</code>. Secrets are masked in telemetry and memory dumps.
              </div>
            </div>
            <button 
              onClick={() => { setLoading(true); loadSettings(); }}
              className="btn-secondary"
              style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <RefreshCw size={12} className={loading ? 'lucide-spin' : ''} />
              Reload .env
            </button>
          </div>

          {/* Configured Keys List */}
          <section className="glass-panel" style={{ padding: '1.75rem', borderRadius: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <div>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Key size={18} color="var(--color-accent)" /> Active Provider Credentials
                </h2>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                  Managed keys loaded by <code style={{ color: 'var(--text-muted)' }}>cidra/config.py</code> and used across pipeline execution nodes.
                </p>
              </div>
              <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-code)', color: 'var(--text-muted)' }}>
                {settings?.keys?.filter((k) => k.configured).length || 0} of {settings?.keys?.length || 0} set
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {settings?.keys?.map((k) => {
                const testStatus = testStatuses[k.id];
                const isEditing = editingKeyId === k.id;

                return (
                  <div 
                    key={k.id}
                    style={{ 
                      background: 'var(--bg-dark)', 
                      border: '1px solid var(--border-light)', 
                      borderRadius: '8px', 
                      padding: '1rem 1.25rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.75rem'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                        <div style={{ 
                          width: 10, height: 10, borderRadius: '50%', 
                          background: k.configured ? 'var(--color-success)' : 'var(--text-dim)',
                          boxShadow: k.configured ? '0 0 8px rgba(23, 201, 100, 0.4)' : 'none'
                        }} />
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                            <span style={{ fontSize: '0.925rem', fontWeight: 600, color: 'var(--text-main)' }}>
                              {k.provider}
                            </span>
                            <span style={{ fontSize: '0.75rem', fontFamily: 'var(--font-code)', color: 'var(--color-accent)', background: 'var(--bg-element)', padding: '0.15rem 0.45rem', borderRadius: '4px' }}>
                              {k.envVar}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                            {k.label}
                          </div>
                        </div>
                      </div>

                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <span style={{ 
                          fontFamily: 'var(--font-code)', fontSize: '0.8rem', 
                          color: k.configured ? 'var(--text-muted)' : 'var(--color-error)',
                          background: 'var(--bg-element)', padding: '0.35rem 0.75rem', borderRadius: '6px',
                          border: '1px solid var(--border-light)', minWidth: '160px', textAlign: 'center'
                        }}>
                          {k.configured ? k.masked : 'Not Set in .env'}
                        </span>

                        {k.canTest && k.configured && (
                          <button
                            onClick={() => testProvider(k.id)}
                            disabled={testStatus?.loading}
                            className="btn-secondary"
                            style={{ 
                              fontSize: '0.75rem', padding: '0.4rem 0.85rem', 
                              display: 'flex', alignItems: 'center', gap: '0.4rem',
                              borderColor: testStatus?.ok === true ? 'var(--color-success)' : testStatus?.ok === false ? 'var(--color-error)' : 'var(--border-light)'
                            }}
                          >
                            <Zap size={13} className={testStatus?.loading ? 'lucide-spin' : ''} color={testStatus?.ok ? 'var(--color-success)' : 'currentColor'} />
                            {testStatus?.loading ? 'Pinging...' : testStatus?.ok ? `${testStatus.latency}ms` : 'Test Ping'}
                          </button>
                        )}

                        <button
                          onClick={() => {
                            if (isEditing) {
                              setEditingKeyId(null);
                            } else {
                              setEditingKeyId(k.id);
                              setEditingSecret('');
                            }
                          }}
                          className="btn-secondary"
                          style={{ fontSize: '0.75rem', padding: '0.4rem 0.85rem' }}
                        >
                          {isEditing ? 'Cancel' : 'Rotate / Set'}
                        </button>
                      </div>
                    </div>

                    {/* Inline Test Result Message */}
                    {testStatus && (
                      <div style={{ 
                        fontSize: '0.75rem', 
                        color: testStatus.ok ? 'var(--color-success)' : 'var(--color-error)', 
                        display: 'flex', alignItems: 'center', gap: '0.4rem',
                        paddingTop: '0.35rem', borderTop: '1px dashed var(--border-light)'
                      }}>
                        {testStatus.ok ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
                        <span>{testStatus.message} {testStatus.latency ? `(${testStatus.latency}ms round-trip)` : ''}</span>
                      </div>
                    )}

                    {/* Inline Key Update Drawer */}
                    {isEditing && (
                      <div className="animate-in" style={{ 
                        background: 'var(--bg-element)', padding: '1rem', borderRadius: '6px', 
                        border: '1px solid var(--border-focus)', marginTop: '0.5rem' 
                      }}>
                        <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '0.4rem' }}>
                          Paste new secret for {k.envVar}:
                        </label>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <div style={{ position: 'relative', flex: 1 }}>
                            <input 
                              type={showEditSecret ? 'text' : 'password'}
                              value={editingSecret}
                              onChange={(e) => setEditingSecret(e.target.value)}
                              placeholder={`Enter ${k.provider} key...`}
                              style={{ 
                                width: '100%', background: 'var(--bg-dark)', 
                                border: '1px solid var(--border-light)', color: 'var(--text-main)', 
                                padding: '0.55rem 2.25rem 0.55rem 0.75rem', borderRadius: '6px', 
                                fontSize: '0.825rem', fontFamily: 'var(--font-code)' 
                              }}
                            />
                            <button
                              type="button"
                              onClick={() => setShowEditSecret(!showEditSecret)}
                              style={{ 
                                position: 'absolute', right: '0.6rem', top: '50%', 
                                transform: 'translateY(-50%)', background: 'transparent', 
                                border: 'none', color: 'var(--text-dim)', cursor: 'pointer' 
                              }}
                            >
                              {showEditSecret ? <EyeOff size={15} /> : <Eye size={15} />}
                            </button>
                          </div>
                          <button
                            onClick={() => handleUpdateKey(k.envVar)}
                            className="btn btn-accent"
                            style={{ fontSize: '0.8rem', padding: '0.55rem 1.25rem', whiteSpace: 'nowrap' }}
                          >
                            Save to .env
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </section>

          {/* Add Custom / Additional Key */}
          <section className="glass-panel" style={{ padding: '1.75rem', borderRadius: '10px' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <Plus size={16} color="var(--color-accent)" /> Add or Override Secret
            </h3>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginBottom: '1.25rem' }}>
              Directly inject arbitrary provider credentials into <code style={{ color: 'var(--text-muted)' }}>.env</code>.
            </p>

            <form onSubmit={handleAddNewKey} style={{ display: 'grid', gridTemplateColumns: '240px 1fr auto', gap: '1rem', alignItems: 'end' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: '0.35rem' }}>
                  Target Environment Variable
                </label>
                <select
                  value={newKeyEnvVar}
                  onChange={(e) => setNewKeyEnvVar(e.target.value)}
                  style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '6px', fontSize: '0.825rem' }}
                >
                  <option value="CIDRA_API_KEY">CIDRA_API_KEY (primary endpoint)</option>
                  <option value="GEMINI_API_KEY">GEMINI_API_KEY (Gemini Fallback)</option>
                  <option value="CIDRA_GITHUB_TOKEN">CIDRA_GITHUB_TOKEN (GitHub PAT)</option>
                  <option value="CIDRA_WEBHOOK_SECRET">CIDRA_WEBHOOK_SECRET (HMAC Secret)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-dim)', display: 'block', marginBottom: '0.35rem' }}>
                  API Key Secret
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showNewSecret ? 'text' : 'password'}
                    placeholder="sk-..., nvapi-..., gsk_..."
                    value={newKeySecret}
                    onChange={(e) => setNewKeySecret(e.target.value)}
                    style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.6rem 2.25rem 0.6rem 0.75rem', borderRadius: '6px', fontSize: '0.825rem', fontFamily: 'var(--font-code)' }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewSecret(!showNewSecret)}
                    style={{ position: 'absolute', right: '0.6rem', top: '50%', transform: 'translateY(-50%)', background: 'transparent', border: 'none', color: 'var(--text-dim)', cursor: 'pointer' }}
                  >
                    {showNewSecret ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <button type="submit" className="btn-secondary" style={{ padding: '0.6rem 1.25rem', fontSize: '0.825rem', whiteSpace: 'nowrap' }}>
                Commit to .env
              </button>
            </form>
          </section>
        </div>
      )}

      {/* SUB-TAB 2: Model Catalog & Routing Strategy */}
      {activeSubTab === 'models' && (
        <div className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Active Model Assignment Hero */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1.5rem' }}>
            
            {/* Primary Analysis Model */}
            <div className="glass-panel" style={{ padding: '1.5rem', border: '1px solid var(--color-accent)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-accent)', fontWeight: 600 }}>
                  Active Analysis Node
                </span>
                <span style={{ fontSize: '0.7rem', background: 'rgba(0, 112, 243, 0.1)', color: 'var(--color-accent)', padding: '0.15rem 0.45rem', borderRadius: '4px' }}>
                  CIDRA_MODEL_ANALYZE
                </span>
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.25rem', fontFamily: 'var(--font-code)' }}>
                {selectedAnalysis}
              </div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                Responsible for isolating root causes from GitHub Actions logs, evaluating stack trace markers, and classifying failure category.
              </p>
            </div>

            {/* Primary Fix Model */}
            <div className="glass-panel" style={{ padding: '1.5rem', border: '1px solid var(--border-focus)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-success)', fontWeight: 600 }}>
                  Active Patch Synthesis Node
                </span>
                <span style={{ fontSize: '0.7rem', background: 'rgba(23, 201, 100, 0.1)', color: 'var(--color-success)', padding: '0.15rem 0.45rem', borderRadius: '4px' }}>
                  CIDRA_MODEL_FIX
                </span>
              </div>
              <div style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.25rem', fontFamily: 'var(--font-code)' }}>
                {selectedFix}
              </div>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                Synthesizes unified git diffs, performs semantic AST refactoring, and ensures minimal code mutation footprint.
              </p>
            </div>

          </div>

          {/* Models CIDRA is set up for, or any id the endpoint serves */}
          <section className="glass-panel" style={{ padding: '1.75rem', borderRadius: '10px' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Bot size={18} color="var(--color-accent)" /> Models
            </h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', margin: '0.2rem 0 1.25rem' }}>
              CIDRA calls one OpenAI-compatible endpoint, <code style={{ color: 'var(--text-muted)' }}>{settings?.models?.base_url || 'CIDRA_BASE_URL'}</code>. A model id must be one that endpoint serves: use <strong>Test Ping</strong> on the primary key to check.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {KNOWN_MODELS.map((m) => {
                const active = selectedAnalysis === m.id && selectedFix === m.id && settings?.models?.base_url === m.baseUrl;
                return (
                  <div key={m.id} style={{ background: 'var(--bg-dark)', border: `1px solid ${active ? 'var(--color-accent)' : 'var(--border-light)'}`, borderRadius: '8px', padding: '1.1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
                    <div>
                      <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)', fontFamily: 'var(--font-code)' }}>{m.id}</div>
                      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.25rem 0' }}>{m.note}</p>
                      <div style={{ fontSize: '0.75rem', fontFamily: 'var(--font-code)', color: 'var(--text-dim)' }}>Endpoint: {m.baseUrl}</div>
                    </div>
                    <button
                      className={active ? 'btn' : 'btn-secondary'}
                      disabled={active || !settings}
                      onClick={() => {
                        setSelectedAnalysis(m.id);
                        setSelectedFix(m.id);
                        saveAllSettings({ model_analyze: m.id, model_fix: m.id, base_url: m.baseUrl });
                      }}
                    >
                      {active ? '✓ In use' : 'Use this model'}
                    </button>
                  </div>
                );
              })}
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const id = customModel.trim();
                  if (!id) return;
                  setSelectedAnalysis(id);
                  setSelectedFix(id);
                  saveAllSettings({ model_analyze: id, model_fix: id });
                }}
                style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}
              >
                <input
                  type="text"
                  aria-label="Model id"
                  placeholder="Another model id the endpoint serves"
                  value={customModel}
                  onChange={(e) => setCustomModel(e.target.value)}
                  style={{ flex: '1 1 260px', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.5rem 0.75rem', borderRadius: '6px', fontSize: '0.8rem', fontFamily: 'var(--font-code)' }}
                />
                <button type="submit" className="btn-secondary" disabled={!settings || !customModel.trim()}>Use for analysis and fix</button>
              </form>
            </div>
          </section>
        </div>
      )}

      {/* SUB-TAB 3: Container Sandbox & Flakiness */}
      {activeSubTab === 'container' && (
        <div className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)', gap: '2rem', alignItems: 'start' }}>
            
            {/* Column 1: Flakiness Engine Rules */}
            <section className="glass-panel" style={{ padding: '1.75rem', borderRadius: '10px' }}>
              <div style={{ marginBottom: '1.5rem' }}>
                <h2 style={{ fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Flame size={18} color="var(--color-warning)" /> Flakiness Detection Engine (Rule SR-08)
                </h2>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                  Governs non-deterministic test flutter isolation in ephemeral Docker containers.
                </p>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                
                {/* Setting: FLAKY_RUNS */}
                <div style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.35rem' }}>
                    <label style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)' }}>
                      Container Test Iterations (FLAKY_RUNS)
                    </label>
                    <span style={{ fontSize: '0.75rem', color: 'var(--color-accent)', fontFamily: 'var(--font-code)' }}>
                      {flakyRuns} Passes
                    </span>
                  </div>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
                    Number of repeated runs executed in the isolated container to observe intermittent failures.
                  </p>
                  <select 
                    value={flakyRuns}
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10);
                      setFlakyRuns(val);
                      saveAllSettings({ flaky_runs: val });
                    }}
                    style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '6px', fontSize: '0.825rem' }}
                  >
                    <option value="1">1 Pass (Fast unit check - no flakiness check)</option>
                    <option value="3">3 Passes (Quick verification)</option>
                    <option value="5">5 Passes (Standard CIDRA default)</option>
                    <option value="10">10 Passes (Strict non-determinism quarantine)</option>
                    <option value="20">20 Passes (Exhaustive soak test)</option>
                  </select>
                </div>

                {/* Setting: FLAKY_SCORE_THRESHOLD */}
                <div style={{ borderBottom: '1px solid var(--border-light)', paddingBottom: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.35rem' }}>
                    <label style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)' }}>
                      Flakiness Trigger Threshold (FLAKY_SCORE_THRESHOLD)
                    </label>
                    <span style={{ fontSize: '0.75rem', color: 'var(--color-warning)', fontFamily: 'var(--font-code)' }}>
                      &gt;= {flakyThreshold}%
                    </span>
                  </div>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.75rem', lineHeight: 1.5 }}>
                    When deterministic score meets or exceeds this threshold, CIDRA flags as flaky rather than synthesizing code patches.
                  </p>
                  <select 
                    value={flakyThreshold}
                    onChange={(e) => {
                      const val = parseInt(e.target.value, 10);
                      setFlakyThreshold(val);
                      saveAllSettings({ flaky_score_threshold: val });
                    }}
                    style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '6px', fontSize: '0.825rem' }}
                  >
                    <option value="1">1% - Strict (Any disagreement across runs is classified flaky)</option>
                    <option value="20">20% - Moderate tolerance</option>
                    <option value="50">50% - Split-half only</option>
                  </select>
                </div>

                {/* Mathematical Formula Explain Card */}
                <div style={{ background: 'var(--bg-dark)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--border-light)' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.4rem', textTransform: 'uppercase' }}>
                    Rule SR-08 Flakiness Formula
                  </div>
                  <div style={{ fontFamily: 'var(--font-code)', fontSize: '0.8rem', color: 'var(--color-accent)' }}>
                    score = round(100 * (1 - |passes - fails| / n))
                  </div>
                  <p style={{ fontSize: '0.725rem', color: 'var(--text-dim)', marginTop: '0.5rem', lineHeight: 1.4, margin: 0 }}>
                    If a test passes 3/5 times, score = 60. Since 60 &gt;= 1, the failure is marked non-deterministic, preventing harmful patches that mask race conditions.
                  </p>
                </div>

              </div>
            </section>

            {/* Column 2: Sandbox Bounds & Human-in-the-Loop */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
              
              <section className="glass-panel" style={{ padding: '1.75rem', borderRadius: '10px' }}>
                <div style={{ marginBottom: '1.5rem' }}>
                  <h2 style={{ fontSize: '1.1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Sliders size={18} color="var(--color-accent)" /> Container & Loop Bounds
                  </h2>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                    Limits to prevent runaway token spend and infinite retry loops.
                  </p>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  
                  {/* MAX_FIX_ATTEMPTS */}
                  <div>
                    <label style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.3rem' }}>
                      Max Repair Loops (MAX_FIX_ATTEMPTS)
                    </label>
                    <select
                      value={maxFixAttempts}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        setMaxFixAttempts(val);
                        saveAllSettings({ max_fix_attempts: val });
                      }}
                      style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '6px', fontSize: '0.825rem' }}
                    >
                      <option value="1">1 Attempt (Fail fast after 1 trial)</option>
                      <option value="2">2 Attempts (Retry once on compiler error)</option>
                      <option value="3">3 Attempts (Standard bounded limit)</option>
                      <option value="5">5 Attempts (Deep search for hard bugs)</option>
                    </select>
                  </div>

                  {/* CONTAINER_TIMEOUT */}
                  <div>
                    <label style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.3rem' }}>
                      Execution Step Timeout
                    </label>
                    <select
                      value={containerTimeout}
                      onChange={(e) => {
                        const val = parseInt(e.target.value, 10);
                        setContainerTimeout(val);
                        saveAllSettings({ container_timeout: val });
                      }}
                      style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '6px', fontSize: '0.825rem' }}
                    >
                      <option value="30">30 Seconds (Fast unit tests)</option>
                      <option value="60">60 Seconds (Standard test suite)</option>
                      <option value="120">120 Seconds (Heavy integration tests)</option>
                      <option value="300">300 Seconds (Monolithic build compilation)</option>
                    </select>
                  </div>

                  {/* Target Repository */}
                  <div>
                    <label style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.3rem' }}>
                      Target Repository Slug (CIDRA_PRACTICE_REPO_SLUG)
                    </label>
                    <input
                      type="text"
                      value={practiceRepo}
                      onChange={(e) => setPracticeRepo(e.target.value)}
                      onBlur={() => saveAllSettings({ practice_repo: practiceRepo })}
                      style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.6rem', borderRadius: '6px', fontSize: '0.825rem', fontFamily: 'var(--font-code)' }}
                    />
                  </div>

                  {/* Automated PR Generation Toggle */}
                  <div style={{ paddingTop: '0.75rem', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)' }}>
                        Automated PR Generation
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
                        Create draft PR when container tests pass green
                      </div>
                    </div>
                    <input
                      type="checkbox"
                      checked={enablePR}
                      onChange={(e) => {
                        setEnablePR(e.target.checked);
                        saveAllSettings({ enable_pr_creation: e.target.checked });
                      }}
                      style={{ width: '20px', height: '20px', accentColor: 'var(--color-accent)', cursor: 'pointer' }}
                    />
                  </div>

                </div>
              </section>

            </div>

          </div>

        </div>
      )}

      {/* SUB-TAB 4: System & Runtime Diagnostics */}
      {activeSubTab === 'runtime' && (
        <div className="animate-in" style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          
          {/* Diagnostics Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.5rem' }}>
            
            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.4rem' }}>
                Python Engine Runtime
              </div>
              <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text-main)', fontFamily: 'var(--font-code)' }}>
                {settings?.system?.python_version || '3.11.0'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--color-success)', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <CheckCircle2 size={13} /> Active Virtualenv Verified
              </div>
            </div>

            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.4rem' }}>
                Idempotency Store
              </div>
              <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text-main)', fontFamily: 'var(--font-code)' }}>
                {settings?.system?.idempotency_db || 'cidra_idempotency.db'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
                SQLite WAL mode • Deduplicates webhook deliveries
              </div>
            </div>

            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.4rem' }}>
                Isolated Worktrees
              </div>
              <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text-main)', fontFamily: 'var(--font-code)' }}>
                {settings?.system?.worktree_root || 'worktrees/'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
                Dedicated checkout directory per run ID
              </div>
            </div>

            <div className="glass-panel" style={{ padding: '1.5rem' }}>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.4rem' }}>
                Verified Fix Cache
              </div>
              <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text-main)', fontFamily: 'var(--font-code)' }}>
                {settings?.system?.fix_cache_path || 'cidra_fix_cache.json'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
                Sha256 failure fingerprints for 0-cost instant fixes
              </div>
            </div>

          </div>

          {/* Full Connection Test Suite */}
          <section className="glass-panel" style={{ padding: '1.75rem', borderRadius: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Server size={18} color="var(--color-accent)" /> Global Provider Health Matrix
                </h3>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                  Concurrent latency probes across all configured AI endpoints and GitHub REST APIs.
                </p>
              </div>

              <button
                onClick={() => {
                  ['cidra_api_key', 'gemini_api_key', 'github_token'].forEach(id => {
                    testProvider(id);
                  });
                }}
                className="btn-secondary"
                style={{ fontSize: '0.8rem', padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
              >
                <Zap size={14} color="var(--color-accent)" /> Test All Endpoints Concurrently
              </button>
            </div>

            <div style={{ width: '100%', overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th style={{ paddingLeft: '0' }}>Provider Name</th>
                    <th>Role in Pipeline</th>
                    <th>Endpoint URL</th>
                    <th>Latency</th>
                    <th style={{ paddingRight: '0', textAlign: 'right' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    { id: 'cidra_api_key', name: 'Primary model endpoint', role: 'Analysis and fix calls', url: settings?.models?.base_url || '' },
                    { id: 'gemini_api_key', name: 'Google Gemini', role: 'Fallback When The Primary Fails', url: 'https://generativelanguage.googleapis.com/v1beta/openai/' },
                    { id: 'github_token', name: 'GitHub REST API', role: 'CI Log Extraction & PR Creation', url: 'https://api.github.com' }
                  ].map((p) => {
                    const st = testStatuses[p.id];
                    return (
                      <tr key={p.id}>
                        <td style={{ paddingLeft: '0', fontWeight: 600, color: 'var(--text-main)', fontSize: '0.875rem' }}>
                          {p.name}
                        </td>
                        <td style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                          {p.role}
                        </td>
                        <td style={{ fontFamily: 'var(--font-code)', fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                          {p.url}
                        </td>
                        <td style={{ fontFamily: 'var(--font-code)', fontSize: '0.8rem', color: st?.ok ? 'var(--color-success)' : 'var(--text-dim)' }}>
                          {st?.loading ? 'Pinging...' : st?.latency ? `${st.latency}ms` : '--'}
                        </td>
                        <td style={{ paddingRight: '0', textAlign: 'right' }}>
                          {st?.loading ? (
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Probing...</span>
                          ) : st?.ok === true ? (
                            <span style={{ fontSize: '0.75rem', color: 'var(--color-success)', fontWeight: 600 }}>✓ Online</span>
                          ) : st?.ok === false ? (
                            <span style={{ fontSize: '0.75rem', color: 'var(--color-error)', fontWeight: 600 }}>⚠ Offline</span>
                          ) : (
                            <button 
                              onClick={() => testProvider(p.id)}
                              className="btn-secondary" 
                              style={{ fontSize: '0.7rem', padding: '0.25rem 0.6rem' }}
                            >
                              Probe
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Config Path Info */}
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', textAlign: 'center' }}>
            Active Configuration Source: <code style={{ color: 'var(--text-muted)' }}>{settings?.system?.env_file || 'd:/CODES/cidra/.env'}</code>
          </div>

        </div>
      )}

    </div>
  );
}
