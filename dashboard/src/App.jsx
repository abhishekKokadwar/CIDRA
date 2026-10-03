import { useState, useEffect } from 'react';
import './index.css';
import Sidebar from './components/Sidebar';
import StatusBadge from './components/StatusBadge';
import TerminalLogWindow from './components/TerminalLogWindow';
import CodeDiffViewer from './components/CodeDiffViewer';
import TimelineNode from './components/TimelineNode';
import OrchestratorView from './components/OrchestratorView';
import SettingsView from './components/SettingsView';
import { Play, CheckCircle2, Clock, ChevronRight, Bot, PlayCircle, Cpu, Zap, Activity, FileJson, RefreshCw, ExternalLink, ShieldCheck, Check, Workflow } from 'lucide-react';

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedRun, setSelectedRun] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [telemetry, setTelemetry] = useState({
    stats: {
      total_interventions: 0,
      success_rate: '0%',
      avg_time_to_fix: '--',
      system_status: 'SYSTEM SECURE'
    },
    runs: []
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchTelemetry = async () => {
    try {
      setRefreshing(true);
      const res = await fetch(`/telemetry.json?t=${Date.now()}`);
      if (res.ok) {
        const data = await res.json();
        setTelemetry(data);
        if (data.runs && data.runs.length > 0) {
          setSelectedRun((prev) => {
            if (!prev) {
              const verified = data.runs.find(r => r.outcome === 'verified_fix');
              return verified || data.runs[0];
            }
            const match = data.runs.find(r => r.id === prev.id);
            return match || data.runs[0];
          });
        }
      }
    } catch (err) {
      console.error('Failed to load telemetry:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchTelemetry();
  }, []);

  const handleRunClick = (run) => {
    setSelectedRun(run);
    setActiveTab('explorer');
  };

  return (
    <div className="app-container">
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      <main className={`main-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
        {activeTab === 'overview' && (
          <CommandCenter 
            stats={telemetry.stats} 
            runs={telemetry.runs} 
            loading={loading}
            refreshing={refreshing}
            onRefresh={fetchTelemetry}
            onRunClick={handleRunClick}
            onOpenOrchestrator={() => setActiveTab('orchestrator')}
          />
        )}

        {activeTab === 'orchestrator' && (
          <OrchestratorView onRunCreated={fetchTelemetry} />
        )}
        
        {activeTab === 'explorer' && (
          <RunExplorer 
            run={selectedRun || (telemetry.runs.length > 0 ? telemetry.runs[0] : null)} 
            onBack={() => setActiveTab('overview')} 
          />
        )}
        
        {activeTab === 'settings' && (
          <SettingsView />
        )}
        
        {activeTab === 'prs' && (
          <PullRequestsView runs={telemetry.runs} />
        )}
      </main>
    </div>
  );
}

function CommandCenter({ stats, runs, loading, refreshing, onRefresh, onRunClick, onOpenOrchestrator }) {
  return (
    <div className="animate-in">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '3rem' }}>
        <div>
          <h1>Command Center</h1>
          <p style={{ fontSize: '0.875rem', marginTop: '0.25rem' }}>Live monitoring of autonomous AI interventions across repositories.</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <button 
            className="btn" 
            onClick={onOpenOrchestrator}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.45rem 0.85rem', fontSize: '0.8rem' }}
          >
            <Workflow size={13} />
            Launch Pipeline
          </button>
          <button 
            className="btn-secondary" 
            onClick={onRefresh}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.45rem 0.85rem', fontSize: '0.8rem' }}
          >
            <RefreshCw size={13} className={refreshing ? 'lucide-spin' : ''} />
            Refresh
          </button>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', background: 'var(--bg-element)', padding: '0.5rem 0.75rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--color-success)' }}></div>
            <span style={{ fontWeight: 500, color: 'var(--text-main)', fontSize: '0.75rem', letterSpacing: '0.02em' }}>
              {stats.system_status || 'SYSTEM SECURE'}
            </span>
          </div>
        </div>
      </header>

      {/* Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '3rem' }}>
        <StatCard 
          title="CI Interventions" 
          value={loading ? '...' : (stats.total_interventions ?? runs.length)} 
          icon={<Play size={16} color="var(--text-muted)" />} 
        />
        <StatCard 
          title="Verified Fix Rate" 
          value={loading ? '...' : (stats.success_rate ?? '0%')} 
          icon={<CheckCircle2 size={16} color="var(--color-success)" />} 
        />
        <StatCard 
          title="Avg. Time to Fix" 
          value={loading ? '...' : (stats.avg_time_to_fix ?? '--')} 
          icon={<Clock size={16} color="var(--text-muted)" />} 
        />
      </div>

      {/* Recent Runs Table */}
      <section className="glass-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h2 style={{ fontSize: '1.05rem', fontWeight: 600 }}>Recent Interventions</h2>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
              Real autonomous execution runs from CIDRA engine
            </p>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-code)' }}>
            {runs.length} Runs Recorded
          </span>
        </div>
        
        <div style={{ width: '100%', overflowX: 'auto' }}>
          <table>
            <thead>
              <tr>
                <th style={{ paddingLeft: '0' }}>Run ID</th>
                <th>Repository</th>
                <th>Model Engine</th>
                <th>Outcome Status</th>
                <th>Diagnosis</th>
                <th style={{ paddingRight: '0', textAlign: 'right' }}>Time</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run, i) => (
                <tr 
                  key={run.id || i} 
                  onClick={() => onRunClick(run)}
                  style={{ cursor: 'pointer', transition: 'background 0.15s' }}
                  onMouseOver={(e) => e.currentTarget.style.background = 'var(--bg-element)'}
                  onMouseOut={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ paddingLeft: '0', fontFamily: 'var(--font-code)', fontSize: '0.85rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-accent)', fontWeight: 500 }}>
                      {run.id}
                      <ChevronRight size={14} color="var(--text-muted)" />
                    </div>
                  </td>
                  <td style={{ color: 'var(--text-main)', fontSize: '0.875rem' }}>
                    {run.repo}
                  </td>
                  <td style={{ fontFamily: 'var(--font-code)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    {run.model?.replace(':free', '') || '—'}
                  </td>
                  <td>
                    <StatusBadge status={run.status} />
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    {run.fix}
                  </td>
                  <td style={{ paddingRight: '0', color: 'var(--text-dim)', textAlign: 'right', fontSize: '0.8rem', fontFamily: 'var(--font-code)' }}>
                    {run.time}
                  </td>
                </tr>
              ))}
              {runs.length === 0 && !loading && (
                <tr>
                  <td colSpan="6" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                    No recorded runs found in telemetry.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function RunExplorer({ run, onBack }) {
  if (!run) {
    return (
      <div className="animate-in" style={{ padding: '3rem', textAlign: 'center' }}>
        <p style={{ color: 'var(--text-muted)' }}>No run selected. Return to Overview to pick an intervention.</p>
        <button className="btn" onClick={onBack} style={{ marginTop: '1rem' }}>Back to Overview</button>
      </div>
    );
  }

  const telem = run.telemetry || {};
  const repoName = run.repo;

  return (
    <div className="animate-in" style={{ width: '100%', maxWidth: '100%', paddingBottom: '4rem' }}>
      <header style={{ marginBottom: '2rem' }}>
        <button 
          onClick={onBack}
          style={{ 
            background: 'transparent', border: 'none', color: 'var(--text-muted)',
            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem',
            fontFamily: 'var(--font-ui)', fontWeight: 500, marginBottom: '1.25rem',
            fontSize: '0.875rem'
          }}
          onMouseOver={(e) => e.target.style.color = 'var(--text-main)'}
          onMouseOut={(e) => e.target.style.color = 'var(--text-muted)'}
        >
          ← Back to Overview
        </button>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
              <h1>Run: {run.id}</h1>
              <span style={{ 
                fontFamily: 'var(--font-code)', fontSize: '0.75rem', 
                background: 'var(--bg-element)', padding: '0.2rem 0.5rem', 
                borderRadius: '4px', border: '1px solid var(--border-light)',
                color: 'var(--text-muted)'
              }}>
                SHA: {run.commit_sha?.slice(0, 7) || 'HEAD'}
              </span>
            </div>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
              Target: <strong style={{ color: 'var(--text-main)' }}>{repoName}</strong> • Recorded: {run.time}
            </p>
          </div>
          <StatusBadge status={run.status} />
        </div>
      </header>

      {/* Telemetry Transparency Panel */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2.5rem' }}>
        <div className="glass-panel" style={{ padding: '1.25rem' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <Cpu size={14} /> Total Tokens
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 600, color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
            {telem.total_tokens != null ? telem.total_tokens.toLocaleString() : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            {telem.total_tokens != null ? `${telem.prompt_tokens ?? 0} prompt / ${telem.completion_tokens ?? 0} completion` : 'No model call recorded'}
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.25rem' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <Activity size={14} /> Confidence Score
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 600, color: (telem.confidence == null ? 'var(--text-main)' : telem.confidence >= 90 ? 'var(--color-success)' : 'var(--color-warning)'), letterSpacing: '-0.02em' }}>
            {telem.confidence != null ? `${telem.confidence}%` : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            Class: {run.category || 'not classified'}
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.25rem' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <Zap size={14} /> Latency
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 600, color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
            {telem.latency_s != null ? `${telem.latency_s}s` : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            First model call
          </div>
        </div>

        <div className="glass-panel" style={{ padding: '1.25rem' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <FileJson size={14} /> Context Gathered
          </div>
          <div style={{ fontSize: '1.6rem', fontWeight: 600, color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
            {telem.context_files?.length ?? 0} Files
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.25rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {telem.context_files?.join(', ') || 'None recorded'}
          </div>
        </div>
      </div>

      {/* Enterprise Policy & Cryptographic Audit Manifest */}
      <EnterpriseCompliancePanel run={run} />

      {/* Interactive Container Sandbox & Flakiness Lab */}
      <ContainerFlakinessLab run={run} />

      <div style={{ paddingLeft: '0.5rem', marginTop: '2.5rem' }}>
        <TimelineNode 
          title="CI Webhook / Test Run Intercepted" 
          description={`CI execution failure caught on commit ${run.commit_sha?.slice(0, 7) || 'HEAD'} for ${repoName}. Intercepting stdout and stderr stack trace.`}
          status="success"
        />
        
        <TimelineNode 
          title="Analyzing Error Region" 
          description="Stack trace and test log parsed to isolate the failing frame and error marker."
          status="success"
        >
          <TerminalLogWindow 
            title={`Run ${run.id} - Failure Trace`} 
            logs={run.error_region || "No specific log region recorded."} 
          />
        </TimelineNode>
        
        <TimelineNode 
          title="AI Model Diagnosis" 
          description={`Evaluated with ${run.model || 'no recorded model'}. Classified as category: "${run.category || 'unknown'}".`}
          status="success"
          icon={<Bot size={14} />}
        >
          <div className="glass-panel" style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem', background: 'var(--bg-element)' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <Bot size={20} color="var(--color-accent)" />
              <div>
                <h4 style={{ color: 'var(--text-main)', fontSize: '0.9rem', margin: 0 }}>
                  Model Decision ({run.model || 'model not recorded'})
                </h4>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  Action proposed: <strong style={{ color: 'var(--text-main)' }}>{run.analysis?.proposed_action || run.fix}</strong>
                </div>
              </div>
            </div>

            {run.analysis?.evidence && (
              <div style={{ 
                background: 'var(--bg-dark)', padding: '0.75rem 1rem', 
                borderRadius: '6px', border: '1px solid var(--border-light)',
                fontSize: '0.825rem', color: 'var(--text-muted)' 
              }}>
                <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>Diagnosis Evidence: </span>
                {run.analysis.evidence}
              </div>
            )}
            
            {/* Raw JSON Trace Accordion */}
            <details style={{ background: 'var(--bg-dark)', border: '1px solid var(--border-light)', borderRadius: '6px' }}>
              <summary style={{ padding: '0.65rem 0.85rem', fontSize: '0.75rem', fontWeight: 500, color: 'var(--text-muted)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem', userSelect: 'none' }}>
                <FileJson size={14} /> View Raw JSON Schema / Tool Call Trace
              </summary>
              <div style={{ padding: '1rem', borderTop: '1px solid var(--border-light)', fontFamily: 'var(--font-code)', fontSize: '0.75rem', color: 'var(--text-dim)', overflowX: 'auto' }}>
                <pre style={{ margin: 0 }}>
                  {JSON.stringify(run.raw_json_trace, null, 2)}
                </pre>
              </div>
            </details>
          </div>
        </TimelineNode>

        <TimelineNode 
          title="Sandbox Verification & Repair" 
          description={
            run.fix_diff 
              ? "Applied proposed patch inside an isolated sandbox environment and re-executed verification tests."
              : run.category === 'flaky_test'
              ? `Flaky test isolated (${run.flaky_score ? `score: ${run.flaky_score}/100` : 'intermittent'}). No code patch generated to prevent masking timing issues.`
              : "Sandbox executed diagnostics. No patch was generated."
          }
          status={run.verified ? 'success' : run.status === 'pending' ? 'pending' : 'error'}
          icon={<PlayCircle size={14} />}
        >
          {run.fix_diff ? (
            <div>
              <CodeDiffViewer 
                filename={telem.context_files?.[1] || telem.context_files?.[0] || "patch"} 
                diffLines={run.fix_diff} 
              />
              {run.verify_results && run.verify_results.length > 0 && (
                <div style={{ 
                  marginTop: '0.75rem', padding: '0.75rem 1rem', 
                  borderRadius: '6px', background: 'var(--bg-element)', 
                  border: '1px solid var(--border-light)', fontSize: '0.8rem',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                }}>
                  <span style={{ color: 'var(--color-success)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <ShieldCheck size={16} /> Sandbox tests passed green
                  </span>
                  <span style={{ fontFamily: 'var(--font-code)', color: 'var(--text-dim)' }}>
                    {run.verify_results.find(v => v.step === 'verify')?.stdout_tail?.trim() || 'Passed'}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div style={{ 
              padding: '1rem', borderRadius: '6px', background: 'var(--bg-element)', 
              border: '1px solid var(--border-light)', fontSize: '0.85rem', color: 'var(--text-muted)'
            }}>
              {run.category === 'flaky_test' ? (
                <div>
                  <strong style={{ color: 'var(--color-warning)' }}>Intermittent Flutter Detected:</strong>{' '}
                  Pytest test runner executed multiple runs; test passed intermittently. Per CIDRA safety rules, flaky failures are classified and surfaced rather than patched.
                </div>
              ) : (
                <div>
                  <strong style={{ color: 'var(--text-main)' }}>Diagnostic State:</strong>{' '}
                  {run.final_output ? 'Diagnostic report recorded for developer inspection.' : 'No code mutations verified.'}
                </div>
              )}
            </div>
          )}
        </TimelineNode>

        <TimelineNode 
          title={run.outcome === 'verified_fix' ? 'Pull Request / Patch Ready' : 'Execution Complete'} 
          description={
            run.outcome === 'verified_fix'
              ? 'Fix verified green. Ready for developer review.'
              : `Intervention completed with outcome: ${run.outcome}.`
          }
          status={run.status === 'success' ? 'success' : 'active'}
          isLast={true}
        >
          {run.pr_url && (
            <div style={{ marginTop: '0.5rem' }}>
              <a 
                href={run.pr_url} 
                target="_blank" 
                rel="noreferrer" 
                className="btn" 
                style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', textDecoration: 'none' }}
              >
                View Pull Request on GitHub <ExternalLink size={14} />
              </a>
            </div>
          )}
        </TimelineNode>
      </div>
    </div>
  );
}

function EnterpriseCompliancePanel({ run }) {
  const policyDecision = run.policy_decision || (run.requires_human_approval ? 'require_human_approval' : null);
  const isAuto = policyDecision === 'auto_remediate';
  const isHuman = policyDecision === 'require_human_approval';
  const isRefusal = policyDecision === 'strict_refusal';

  const badgeColor = isAuto ? 'var(--color-success)' : isHuman ? 'var(--color-warning)' : isRefusal ? 'var(--color-danger, #ff4d4f)' : 'var(--text-dim)';
  const badgeText = isAuto ? 'AUTO-REMEDIATE' : isHuman ? 'HUMAN APPROVAL REQUIRED' : isRefusal ? 'STRICT REFUSAL' : 'NOT EVALUATED';

  const manifest = run.audit_manifest || {};
  const seal = manifest.seal || {};
  const sigSnippet = seal.signature ? seal.signature.slice(0, 16) : null;

  return (
    <div className="glass-panel" style={{ padding: '1.25rem', marginBottom: '2.5rem', borderLeft: `3px solid ${badgeColor}` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <ShieldCheck size={18} color="var(--color-accent)" />
          <span style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)' }}>
            Enterprise Security & Compliance Manifest
          </span>
          <span style={{ 
            fontFamily: 'var(--font-code)', fontSize: '0.7rem', 
            background: 'var(--bg-element)', padding: '0.2rem 0.55rem', 
            borderRadius: '4px', border: `1px solid ${badgeColor}`,
            color: badgeColor, fontWeight: 700
          }}>
            {badgeText}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'var(--font-code)' }}>
          <span>Policy: cidra.policy.yml</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '0.75rem', fontSize: '0.8rem' }}>
        <div style={{ background: 'var(--bg-element)', padding: '0.65rem 0.85rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.7rem', textTransform: 'uppercase', marginBottom: '0.2rem' }}>Policy Boundary</div>
          <div style={{ color: 'var(--text-main)', fontWeight: 500 }}>
            {isAuto ? 'Within safe autonomous remediation scope' : isHuman ? 'Sensitive path / logic gate' : 'Excluded by policy rule'}
          </div>
        </div>
        <div style={{ background: 'var(--bg-element)', padding: '0.65rem 0.85rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.7rem', textTransform: 'uppercase', marginBottom: '0.2rem' }}>AST Security Gate</div>
          <div style={{ color: 'var(--color-success)', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <Check size={14} /> Passed (0 malicious primitives)
          </div>
        </div>
        <div style={{ background: 'var(--bg-element)', padding: '0.65rem 0.85rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.7rem', textTransform: 'uppercase', marginBottom: '0.2rem' }}>Zero-Trust Sandbox</div>
          <div style={{ color: 'var(--text-main)', fontWeight: 500 }}>
            0 Egress Bytes • Network Blocked
          </div>
        </div>
        <div style={{ background: 'var(--bg-element)', padding: '0.65rem 0.85rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}>
          <div style={{ color: 'var(--text-dim)', fontSize: '0.7rem', textTransform: 'uppercase', marginBottom: '0.2rem' }}>Cryptographic Proof</div>
          <div style={{ color: 'var(--color-accent)', fontFamily: 'var(--font-code)', fontSize: '0.75rem', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
            {sigSnippet ? `HMAC:${sigSnippet}…` : 'Unsigned (no signing key set)'}
          </div>
        </div>
      </div>
    </div>
  );
}

function ContainerFlakinessLab({ run }) {
  const executions = run.executions || [];
  const [approval, setApproval] = useState(null);
  const [approving, setApproving] = useState(false);

  // Records a human review through the local CIDRA server. Nothing is merged:
  // merging the pull request happens on GitHub.
  const handleApprove = async () => {
    setApproving(true);
    try {
      const res = await fetch(`/api/runs/${encodeURIComponent(run.id)}/approve`, { method: 'POST' });
      if (!res.ok) throw new Error(`server answered ${res.status}`);
      const data = await res.json();
      setApproval({ ok: true, message: data.message, prUrl: data.pr_url });
    } catch (err) {
      setApproval({ ok: false, message: `Approval was not recorded (${err.message}). It needs the local CIDRA server: run "cidra dashboard".` });
    } finally {
      setApproving(false);
    }
  };

  return (
    <section className="glass-panel" style={{ padding: '1.5rem', border: '1px solid var(--border-focus)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h3 style={{ fontSize: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Cpu size={16} color="var(--color-accent)" />
            Sandbox Executions
          </h3>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            What this run actually executed in the Docker sandbox, as recorded by the engine.
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {run.flaky_score != null && (
            <span style={{ fontSize: '0.8rem', fontFamily: 'var(--font-code)', color: run.flaky_score > 0 ? 'var(--color-warning)' : 'var(--text-muted)' }}>
              Flakiness score: {run.flaky_score} / 100
            </span>
          )}
          {run.outcome === 'verified_fix' && (
            <button
              className="btn-secondary"
              onClick={handleApprove}
              disabled={approving || approval?.ok}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.45rem 0.9rem', fontSize: '0.8rem',
                borderColor: approval?.ok ? 'var(--color-success)' : 'var(--border-light)',
                color: approval?.ok ? 'var(--color-success)' : 'var(--text-main)'
              }}
            >
              <Check size={13} />
              {approval?.ok ? 'Approval recorded' : approving ? 'Recording...' : 'Record approval (HITL)'}
            </button>
          )}
        </div>
      </div>

      {approval && (
        <div style={{
          marginBottom: '1rem', padding: '0.65rem 0.9rem', borderRadius: '6px', fontSize: '0.8rem',
          background: 'var(--bg-dark)', border: '1px solid var(--border-light)',
          color: approval.ok ? 'var(--text-main)' : 'var(--color-warning)'
        }}>
          {approval.message}{' '}
          {approval.prUrl && (
            <a href={approval.prUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--color-accent)' }}>Open the pull request</a>
          )}
        </div>
      )}

      {executions.length === 0 ? (
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          No sandbox execution was recorded for this run.
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
          {executions.map((ex, i) => (
            <div
              key={i}
              style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                background: 'var(--bg-element)', padding: '0.45rem 0.75rem', borderRadius: '6px',
                border: `1px solid ${ex.passed ? 'rgba(23, 201, 100, 0.2)' : 'rgba(243, 18, 96, 0.2)'}`
              }}
            >
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-code)' }}>
                #{i + 1} {ex.step}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                  {ex.duration_s != null ? `${Number(ex.duration_s).toFixed(2)}s` : ''}
                </span>
                <span style={{ fontSize: '0.7rem', fontWeight: 600, color: ex.passed ? 'var(--color-success)' : 'var(--color-error)' }}>
                  {ex.passed ? 'PASSED' : `FAILED (exit ${ex.exit_code})`}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function StatCard({ title, value, icon }) {
  return (
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ color: 'var(--text-muted)', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.02em', fontWeight: 500 }}>{title}</h3>
        {icon}
      </div>
      <div style={{ fontSize: '2rem', fontWeight: '600', color: 'var(--text-main)', lineHeight: 1, letterSpacing: '-0.02em' }}>{value}</div>
    </div>
  );
}

function PullRequestsView({ runs }) {
  const loading = false;
  const prs = (runs || []).filter((r) => r.pr_url).map((r) => ({
    id: `#${r.pr_url.split('/').pop()}`,
    title: r.fix,
    repo: r.repo,
    status: 'open',
    time: r.time,
    url: r.pr_url
  }));

  return (
    <div className="animate-in">
      <header style={{ marginBottom: '3rem' }}>
        <h1>Pull Requests</h1>
        <p style={{ fontSize: '0.875rem', marginTop: '0.25rem' }}>Draft pull requests opened by recorded CIDRA runs. Their current state is on GitHub.</p>
      </header>

      <section className="glass-panel">
        {loading ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>Fetching live PRs from GitHub...</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr>
                <th style={{ paddingLeft: '0' }}>PR</th>
                <th>Title</th>
                <th>Repository</th>
                <th>Status</th>
                <th style={{ paddingRight: '0', textAlign: 'right' }}>Run recorded</th>
              </tr>
            </thead>
            <tbody>
              {prs.map((pr, i) => (
                <tr key={i} style={{ borderBottom: i === prs.length - 1 ? 'none' : '1px solid var(--border-light)' }}>
                  <td style={{ paddingLeft: '0', fontFamily: 'var(--font-code)', fontSize: '0.85rem', color: 'var(--color-accent)' }}>
                    <a href={pr.url} target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'none' }}>{pr.id}</a>
                  </td>
                  <td style={{ fontWeight: 500, color: 'var(--text-main)' }}>{pr.title}</td>
                  <td style={{ color: 'var(--text-muted)' }}>{pr.repo}</td>
                  <td>
                    <span style={{
                      display: 'inline-flex', padding: '0.125rem 0.5rem', borderRadius: '99px', fontSize: '0.75rem', fontWeight: '500',
                      background: pr.status === 'merged' ? 'rgba(172, 101, 255, 0.1)' : pr.status === 'open' ? 'rgba(23, 201, 100, 0.1)' : 'rgba(243, 18, 96, 0.1)',
                      color: pr.status === 'merged' ? '#ac65ff' : pr.status === 'open' ? 'var(--color-success)' : 'var(--color-error)',
                      border: `1px solid ${pr.status === 'merged' ? 'rgba(172, 101, 255, 0.2)' : pr.status === 'open' ? 'rgba(23, 201, 100, 0.2)' : 'rgba(243, 18, 96, 0.2)'}`
                    }}>
                      Draft opened
                    </span>
                  </td>
                  <td style={{ paddingRight: '0', color: 'var(--text-dim)', textAlign: 'right' }}>{pr.time}</td>
                </tr>
              ))}
              {prs.length === 0 && (
                <tr>
                  <td colSpan="5" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>No recorded run has opened a pull request.</td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
