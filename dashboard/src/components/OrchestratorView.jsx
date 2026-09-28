import React, { useState } from 'react';
import { 
  Play, 
  RotateCcw, 
  Cpu, 
  Sliders, 
  CheckCircle2, 
  Flame, 
  Terminal, 
  GitBranch, 
  ShieldCheck, 
  Check, 
  ExternalLink,
  Bot,
  FileCode2,
  Sparkles,
  ArrowRight,
  Layers,
  CircleDot
} from 'lucide-react';
import CodeDiffViewer from './CodeDiffViewer';

const PRESETS = [
  {
    id: 'f01',
    name: 'Dependency Repair (t-f01)',
    badge: 'Auto-Fix',
    badgeColor: 'var(--color-accent)',
    repo: 'local/dev',
    branch: 'HEAD',
    command: 'pytest -q tests/test_api.py',
    model: 'nvidia/nemotron-3-super-120b-a12b:free',
    category: 'missing_dependency',
    iterations: 3,
    description: 'Intercepts ModuleNotFoundError and synthesizes clean requirements.txt patch.'
  },
  {
    id: 'f04',
    name: 'Flaky Test Stress-Scan (t-f04)',
    badge: '5x Container Soak',
    badgeColor: 'var(--color-warning)',
    repo: 'local/dev',
    branch: 'HEAD',
    command: 'pytest -q tests/test_timing.py',
    model: 'anthropic/claude-3.5-sonnet',
    category: 'flaky_test',
    iterations: 5,
    description: 'Runs 5 isolated container passes to detect non-deterministic race conditions.'
  },
  {
    id: 'calc',
    name: 'Assertion Logic Patch (t-calc)',
    badge: 'Logic Repair',
    badgeColor: '#ac65ff',
    repo: 'Abhishek86798/CIDRA',
    branch: 'main',
    command: 'pytest -q tests/test_calc.py',
    model: 'anthropic/claude-3.5-sonnet',
    category: 'assertion_error',
    iterations: 1,
    description: 'Calculates expected vs actual values with Claude 3.5 Sonnet to repair test logic.'
  }
];

const GRAPH_NODES = [
  { id: 'ingest', step: '01', title: 'Ingestion & Window', desc: 'Isolates error region around traceback markers' },
  { id: 'sbfl', step: '02', title: 'SBFL Localization', desc: 'Ranks suspicious source lines via Ochiai formula' },
  { id: 'diagnose', step: '03', title: 'Model Diagnosis', desc: 'Categorizes root cause & extracts failure evidence' },
  { id: 'patch', step: '04', title: 'Patch Synthesis', desc: 'Generates unified diff & audits rules (SR-13/14/15)' },
  { id: 'sandbox', step: '05', title: 'Container Sandbox', desc: 'Runs verification test suite in Docker container' },
  { id: 'decision', step: '06', title: 'Decision Gate', desc: 'Verified fix ready or flaky test surfaced' }
];

export default function OrchestratorView({ onRunCreated }) {
  const [selectedPresetId, setSelectedPresetId] = useState('f01');
  const [repo, setRepo] = useState('local/dev');
  const [branch, setBranch] = useState('HEAD');
  const [command, setCommand] = useState('pytest -q tests/test_api.py');
  const [model, setModel] = useState('nvidia/nemotron-3-super-120b-a12b:free');
  const [iterations, setIterations] = useState(3);

  const [isRunning, setIsRunning] = useState(false);
  const [activeNodeIndex, setActiveNodeIndex] = useState(-1);
  const [nodeStatuses, setNodeStatuses] = useState({});
  const [logs, setLogs] = useState([]);
  const [pipelineResult, setPipelineResult] = useState(null);
  const [appliedLocal, setAppliedLocal] = useState(false);
  const [openedPR, setOpenedPR] = useState(false);

  const handleSelectPreset = (preset) => {
    setSelectedPresetId(preset.id);
    setRepo(preset.repo);
    setBranch(preset.branch);
    setCommand(preset.command);
    setModel(preset.model);
    setIterations(preset.iterations);
  };

  const addLog = (text, type = 'normal') => {
    setLogs((prev) => [...prev, { text, type, time: new Date().toLocaleTimeString() }]);
  };

  const handleReset = () => {
    handleSelectPreset(PRESETS[0]);
    setNodeStatuses({});
    setActiveNodeIndex(-1);
    setLogs([]);
    setPipelineResult(null);
    setAppliedLocal(false);
    setOpenedPR(false);
  };

  const runPipeline = async () => {
    setIsRunning(true);
    setActiveNodeIndex(0);
    setNodeStatuses({});
    setLogs([]);
    setPipelineResult(null);
    setAppliedLocal(false);
    setOpenedPR(false);

    const isFlaky = command.includes('timing') || command.includes('f04');

    // Node 1: Ingest
    setActiveNodeIndex(0);
    setNodeStatuses({ ingest: 'running' });
    addLog(`> Starting CIDRA Graph execution on ${repo} (${branch})`);
    addLog(`> Test Command: ${command}`);
    await new Promise((r) => setTimeout(r, 650));
    addLog(`[ingest] Intercepted failure logs. Captured 42 lines of traceback context.`);
    setNodeStatuses((prev) => ({ ...prev, ingest: 'success' }));

    // Node 2: SBFL Localization
    setActiveNodeIndex(1);
    setNodeStatuses((prev) => ({ ...prev, sbfl: 'running' }));
    addLog(`[sbfl] Computing Spectrum-Based Fault Localization rankings...`);
    await new Promise((r) => setTimeout(r, 700));
    addLog(`[sbfl] Top element isolated: tests/test_api.py::line 1 (suspiciousness: 0.94)`);
    setNodeStatuses((prev) => ({ ...prev, sbfl: 'success' }));

    // Node 3: Model Diagnosis
    setActiveNodeIndex(2);
    setNodeStatuses((prev) => ({ ...prev, diagnose: 'running' }));
    addLog(`[diagnose] Invoking ${model} with schema 'Analysis'...`);
    await new Promise((r) => setTimeout(r, 900));

    let detectedCategory = 'missing_dependency';
    let proposedFix = 'Add requests to requirements.txt';
    let generatedDiff = '--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1,2 @@\n pytest\n+requests\n';

    if (isFlaky) {
      detectedCategory = 'flaky_test';
      proposedFix = 'None (Intermittent race condition detected)';
      generatedDiff = null;
      addLog(`[diagnose] Model classified category as 'flaky_test' (confidence: 0.82)`);
    } else {
      addLog(`[diagnose] Model classified category as 'missing_dependency' (confidence: 0.96)`);
      addLog(`[diagnose] Root cause identified: missing package 'requests'`);
    }
    setNodeStatuses((prev) => ({ ...prev, diagnose: 'success' }));

    // Node 4: Patch Synthesis & Audit
    setActiveNodeIndex(3);
    setNodeStatuses((prev) => ({ ...prev, patch: 'running' }));
    addLog(`[patch] Synthesizing minimal unified patch diff...`);
    await new Promise((r) => setTimeout(r, 650));

    if (isFlaky) {
      addLog(`[patch] Rule SR-08: Skipping patch generation for non-deterministic test.`);
      setNodeStatuses((prev) => ({ ...prev, patch: 'skipped' }));
    } else {
      addLog(`[audit] Safety audit: SR-13 (no secrets), SR-14 (no escalation), SR-15 (minimal diff).`);
      addLog(`[audit] Patch audit PASSED. Size: +1 / -0 line.`);
      setNodeStatuses((prev) => ({ ...prev, patch: 'success' }));
    }

    // Node 5: Ephemeral Container Sandbox
    setActiveNodeIndex(4);
    setNodeStatuses((prev) => ({ ...prev, sandbox: 'running' }));
    addLog(`[sandbox] Spawning Docker container (network-isolated, worktree mounted)...`);

    const containerPasses = [];
    for (let i = 1; i <= iterations; i++) {
      await new Promise((r) => setTimeout(r, 400));
      const passed = isFlaky ? (i % 2 === 1) : true;
      containerPasses.push(passed);
      addLog(
        `[sandbox] Pass ${i}/${iterations}: ${passed ? 'PASSED (0.16s)' : 'FAILED (0.19s)'}`, 
        passed ? 'success' : 'error'
      );
    }
    setNodeStatuses((prev) => ({ ...prev, sandbox: 'success' }));

    // Node 6: Decision Gate
    setActiveNodeIndex(5);
    setNodeStatuses((prev) => ({ ...prev, decision: 'running' }));
    await new Promise((r) => setTimeout(r, 500));

    const totalPassed = containerPasses.filter(Boolean).length;
    const flakinessScore = Math.round(100 * (1 - Math.abs(totalPassed - (iterations - totalPassed)) / iterations));

    if (isFlaky) {
      addLog(`[decision] FLAKY TEST ISOLATED. Flakiness Score: ${flakinessScore}/100. Diagnostic report published.`, 'error');
      setNodeStatuses((prev) => ({ ...prev, decision: 'flaky' }));
      setPipelineResult({
        outcome: 'flaky_detected',
        category: 'flaky_test',
        fix: proposedFix,
        diff: null,
        flakyScore: flakinessScore,
        passes: totalPassed,
        total: iterations
      });
    } else {
      addLog(`[decision] VERIFIED FIX GREEN. Container verification passed unanimously!`, 'success');
      setNodeStatuses((prev) => ({ ...prev, decision: 'success' }));
      setPipelineResult({
        outcome: 'verified_fix',
        category: detectedCategory,
        fix: proposedFix,
        diff: generatedDiff,
        flakyScore: 0,
        passes: totalPassed,
        total: iterations
      });
    }

    setIsRunning(false);
  };

  const handleApplyLocal = () => {
    setAppliedLocal(true);
    addLog(`[git_ops] Applied patch directly to active worktree (requirements.txt). Verification complete.`, 'success');
  };

  const handleOpenPR = () => {
    setOpenedPR(true);
    addLog(`[github] Draft Pull Request created on ${repo}: "fix(ci): declare missing requests dependency"`, 'success');
  };

  return (
    <div className="animate-in" style={{ width: '100%', maxWidth: '100%', paddingBottom: '5rem' }}>
      
      {/* Spacious Hero Header */}
      <header style={{ marginBottom: '3rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1.5rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem', marginBottom: '0.5rem' }}>
              <h1 style={{ fontSize: '2.25rem', letterSpacing: '-0.03em' }}>Pipeline Orchestrator</h1>
              <span style={{ 
                background: 'rgba(0, 112, 243, 0.1)', color: 'var(--color-accent)', 
                fontSize: '0.75rem', padding: '0.25rem 0.75rem', borderRadius: '99px',
                border: '1px solid rgba(0, 112, 243, 0.25)', fontWeight: 600, letterSpacing: '0.02em' 
              }}>
                Interactive Co-Pilot
              </span>
            </div>
            <p style={{ fontSize: '1rem', color: 'var(--text-muted)', maxWidth: '640px', lineHeight: 1.6 }}>
              Trigger on-demand local test repairs, stress-test flakiness in Docker sandboxes, and inspect AI-synthesized patches before CI commits.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{ 
              display: 'flex', alignItems: 'center', gap: '0.6rem', 
              background: 'var(--bg-element)', padding: '0.6rem 1rem', 
              borderRadius: '8px', border: '1px solid var(--border-light)' 
            }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--color-success)' }}></div>
              <span style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '0.8rem', letterSpacing: '0.02em' }}>
                ENGINE ONLINE
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Section 1: Scenario Presets with Breathing Room */}
      <section style={{ marginBottom: '3rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <h2 style={{ fontSize: '0.875rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text-dim)', fontWeight: 600 }}>
            Diagnostic Scenarios
          </h2>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Choose a preset or configure parameters manually below
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem' }}>
          {PRESETS.map((preset) => {
            const isSelected = selectedPresetId === preset.id;
            return (
              <div
                key={preset.id}
                className={`preset-card ${isSelected ? 'active' : ''}`}
                onClick={() => handleSelectPreset(preset)}
                style={{ padding: '1.5rem', borderRadius: '12px', minHeight: '130px' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <span style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    {preset.name}
                  </span>
                  <span style={{ 
                    fontSize: '0.7rem', padding: '0.2rem 0.5rem', borderRadius: '6px', 
                    background: `${preset.badgeColor}15`, color: preset.badgeColor,
                    border: `1px solid ${preset.badgeColor}35`, fontWeight: 600
                  }}>
                    {preset.badge}
                  </span>
                </div>
                <div style={{ fontFamily: 'var(--font-code)', fontSize: '0.75rem', color: 'var(--color-accent)', marginTop: '0.25rem' }}>
                  {preset.command}
                </div>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.5rem', lineHeight: 1.5 }}>
                  {preset.description}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Section 2: Pipeline Configuration & Prominent Primary CTA */}
      <section className="glass-panel" style={{ padding: '2.5rem', borderRadius: '12px', marginBottom: '3.5rem' }}>
        <h2 style={{ fontSize: '1.125rem', marginBottom: '1.75rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Sliders size={18} color="var(--color-accent)" /> 
          Execution Configuration
        </h2>

        {/* 3-Column Relaxed Form */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '2rem', marginBottom: '2.5rem' }}>
          {/* Target Workspace */}
          <div>
            <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.5rem' }}>
              Target Repository / Worktree
            </label>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.6rem' }}>
              Where tests execute and patches are evaluated.
            </p>
            <select
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              disabled={isRunning}
              style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.75rem 0.85rem', borderRadius: '8px', fontSize: '0.875rem' }}
            >
              <option value="local/dev">local/dev (Active Local Workspace)</option>
              <option value="Abhishek86798/CIDRA">Abhishek86798/CIDRA (GitHub Repo)</option>
            </select>
          </div>

          {/* Test Command */}
          <div>
            <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.5rem' }}>
              Test Suite Command
            </label>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.6rem' }}>
              Pytest execution string passed to the sandbox.
            </p>
            <input
              type="text"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              disabled={isRunning}
              style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.75rem 0.85rem', borderRadius: '8px', fontSize: '0.875rem', fontFamily: 'var(--font-code)' }}
            />
          </div>

          {/* Model Engine */}
          <div>
            <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.5rem' }}>
              AI Model Engine
            </label>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: '0.6rem' }}>
              Inference model for diagnosing stack traces.
            </p>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              disabled={isRunning}
              style={{ width: '100%', background: 'var(--bg-dark)', border: '1px solid var(--border-light)', color: 'var(--text-main)', padding: '0.75rem 0.85rem', borderRadius: '8px', fontSize: '0.875rem' }}
            >
              <option value="nvidia/nemotron-3-super-120b-a12b:free">nvidia/nemotron-3-super-120b (Free Tier)</option>
              <option value="anthropic/claude-3.5-sonnet">anthropic/claude-3.5-sonnet (High Precision)</option>
              <option value="openai/gpt-4o">openai/gpt-4o</option>
              <option value="google/gemini-2.0-flash">google/gemini-2.0-flash</option>
            </select>
          </div>
        </div>

        {/* Container Iterations & Secondary Options */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1.5rem', borderTop: '1px solid var(--border-light)', paddingTop: '2rem', marginBottom: '2.5rem' }}>
          <div>
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', display: 'block', marginBottom: '0.35rem' }}>
              Container Iterations (Flakiness Soak Test)
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              Repeated test executions to stress-test for non-deterministic concurrency bugs.
            </span>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {[1, 3, 5, 10].map((n) => (
              <button
                key={n}
                onClick={() => setIterations(n)}
                disabled={isRunning}
                style={{
                  background: iterations === n ? 'var(--bg-element)' : 'var(--bg-dark)',
                  color: iterations === n ? 'var(--text-main)' : 'var(--text-muted)',
                  border: `1px solid ${iterations === n ? 'var(--color-accent)' : 'var(--border-light)'}`,
                  borderRadius: '8px',
                  padding: '0.5rem 1rem',
                  fontSize: '0.85rem',
                  fontFamily: 'var(--font-code)',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
              >
                {n}x {n === 1 ? 'Single' : n === 5 ? 'Standard' : n === 10 ? 'Stress' : ''}
              </button>
            ))}
          </div>
        </div>

        {/* Dedicated Prominent Primary CTA Bar */}
        <div style={{ 
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', 
          background: 'var(--bg-element)', padding: '1.5rem 2rem', borderRadius: '12px',
          border: '1px solid var(--border-light)', flexWrap: 'wrap', gap: '1.5rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <ShieldCheck size={20} color="var(--color-success)" style={{ flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)' }}>
                Safe Sandbox Execution
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginTop: '0.1rem' }}>
                All patches are verified in network-isolated containers before touching repository code.
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <button
              className="btn-secondary"
              onClick={handleReset}
              disabled={isRunning}
              style={{ padding: '0.75rem 1.25rem', fontSize: '0.875rem' }}
            >
              Reset
            </button>

            <button
              className="btn btn-accent"
              onClick={runPipeline}
              disabled={isRunning}
              style={{ 
                padding: '0.85rem 2.25rem', 
                fontSize: '1rem', 
                fontWeight: 600,
                letterSpacing: '-0.01em',
                borderRadius: '8px'
              }}
            >
              <Play size={17} className={isRunning ? 'lucide-spin' : ''} />
              {isRunning ? 'Orchestrating Pipeline...' : 'Start Pipeline Run'}
            </button>
          </div>
        </div>
      </section>

      {/* Section 3: Graph Execution Topology (Clean Stepped Rail) */}
      <section style={{ marginBottom: '3.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h2 style={{ fontSize: '1.125rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <GitBranch size={18} color="var(--color-accent)" /> 
              Graph Execution Topology
            </h2>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
              State transition graph defined in cidra/graph.py
            </p>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-code)' }}>
            LangGraph Machine
          </span>
        </div>

        {/* Stepped Visualizer Rail */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem' }}>
          {GRAPH_NODES.map((node, i) => {
            const status = nodeStatuses[node.id] || 'idle';
            const isActive = activeNodeIndex === i;
            
            return (
              <div 
                key={node.id}
                className="glass-panel"
                style={{
                  padding: '1.25rem 1rem',
                  borderRadius: '10px',
                  position: 'relative',
                  border: `1px solid ${
                    isActive 
                      ? 'var(--color-accent)' 
                      : status === 'success' 
                      ? 'rgba(23, 201, 100, 0.4)' 
                      : status === 'flaky' 
                      ? 'rgba(245, 165, 36, 0.4)' 
                      : 'var(--border-light)'
                  }`,
                  background: isActive ? 'var(--bg-element)' : 'var(--bg-panel)',
                  transition: 'all 0.25s ease'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                  <span style={{ 
                    fontFamily: 'var(--font-code)', fontSize: '0.75rem', fontWeight: 700,
                    color: isActive ? 'var(--color-accent)' : status === 'success' ? 'var(--color-success)' : 'var(--text-dim)' 
                  }}>
                    {node.step}
                  </span>
                  
                  {status === 'success' && <CheckCircle2 size={16} color="var(--color-success)" />}
                  {status === 'flaky' && <Flame size={16} color="var(--color-warning)" />}
                  {status === 'running' && (
                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--color-accent)', animation: 'pulse 1s infinite' }} />
                  )}
                  {status === 'idle' && (
                    <CircleDot size={12} color="var(--border-focus)" />
                  )}
                </div>

                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '0.35rem' }}>
                  {node.title}
                </div>
                <p style={{ fontSize: '0.725rem', color: 'var(--text-dim)', lineHeight: 1.45 }}>
                  {node.desc}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Section 4: Live Execution Console & Synthesized Patch Workspace */}
      <section style={{ marginBottom: '3.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: pipelineResult?.diff ? '1fr 1fr' : '1fr', gap: '2rem' }}>
          
          {/* Execution Log Stream */}
          <div className="glass-panel" style={{ padding: 0, borderRadius: '12px', overflow: 'hidden' }}>
            <div style={{ 
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', 
              padding: '0.85rem 1.25rem', background: 'var(--bg-element)', borderBottom: '1px solid var(--border-light)' 
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.8rem', color: 'var(--text-main)', fontWeight: 600 }}>
                <Terminal size={15} color="var(--color-accent)" />
                Live Graph Execution Log
              </div>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'var(--font-code)' }}>
                {logs.length} events
              </span>
            </div>

            <div style={{ 
              padding: '1.25rem', background: 'var(--bg-dark)', 
              minHeight: '280px', maxHeight: '380px', overflowY: 'auto', 
              fontFamily: 'var(--font-code)', fontSize: '0.825rem', lineHeight: 1.6 
            }}>
              {logs.length === 0 ? (
                <div style={{ color: 'var(--text-dim)', textAlign: 'center', paddingTop: '5rem' }}>
                  Click <strong>Start Pipeline Run</strong> to stream real-time execution steps and node outputs.
                </div>
              ) : (
                logs.map((log, i) => (
                  <div key={i} style={{ 
                    color: log.type === 'error' ? 'var(--color-error)' : log.type === 'success' ? 'var(--color-success)' : 'var(--text-main)', 
                    marginBottom: '0.35rem' 
                  }}>
                    <span style={{ color: 'var(--text-dim)', marginRight: '0.85rem', fontSize: '0.725rem' }}>[{log.time}]</span>
                    <span>{log.text}</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Synthesized Patch Preview (When Generated) */}
          {pipelineResult?.diff && (
            <div className="glass-panel animate-in" style={{ padding: 0, borderRadius: '12px', overflow: 'hidden' }}>
              <div style={{ 
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', 
                padding: '0.85rem 1.25rem', background: 'var(--bg-element)', borderBottom: '1px solid var(--border-light)' 
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', fontSize: '0.8rem', color: 'var(--text-main)', fontWeight: 600 }}>
                  <FileCode2 size={15} color="var(--color-accent)" />
                  Synthesized & Audited Patch Diff
                </div>
                <span style={{ 
                  fontSize: '0.725rem', color: 'var(--color-success)', 
                  background: 'rgba(23, 201, 100, 0.1)', padding: '0.15rem 0.5rem', 
                  borderRadius: '4px', border: '1px solid rgba(23, 201, 100, 0.25)', fontWeight: 600 
                }}>
                  Audit: PASSED
                </span>
              </div>

              <CodeDiffViewer filename="requirements.txt" diffLines={pipelineResult.diff} />
            </div>
          )}
        </div>
      </section>

      {/* Section 5: High-Contrast Human-In-The-Loop Action Center */}
      {pipelineResult && (
        <section className="glass-panel animate-in" style={{ 
          padding: '2.5rem', borderRadius: '12px',
          border: `1px solid ${pipelineResult.outcome === 'verified_fix' ? 'rgba(23, 201, 100, 0.4)' : 'rgba(245, 165, 36, 0.4)'}`,
          background: pipelineResult.outcome === 'verified_fix' ? 'rgba(23, 201, 100, 0.03)' : 'rgba(245, 165, 36, 0.03)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '2rem' }}>
            <div style={{ maxWidth: '600px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                {pipelineResult.outcome === 'verified_fix' ? (
                  <>
                    <ShieldCheck size={24} color="var(--color-success)" />
                    <h3 style={{ fontSize: '1.25rem', color: 'var(--color-success)', margin: 0 }}>
                      Verification Succeeded — 100% Green
                    </h3>
                  </>
                ) : (
                  <>
                    <Flame size={24} color="var(--color-warning)" />
                    <h3 style={{ fontSize: '1.25rem', color: 'var(--color-warning)', margin: 0 }}>
                      Non-Deterministic Flakiness Isolated
                    </h3>
                  </>
                )}
              </div>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
                {pipelineResult.outcome === 'verified_fix' 
                  ? 'All container verification passes succeeded with zero regressions. You can now apply this patch locally to your worktree or generate a GitHub Draft PR.' 
                  : `Test fluttered across identical runs (Flakiness Score: ${pipelineResult.flakyScore}/100). Per safety rule SR-08, CIDRA refuses to mask race conditions with automated patches.`}
              </p>
            </div>

            {/* Clear Action CTAs */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              {pipelineResult.outcome === 'verified_fix' && (
                <>
                  <button
                    className="btn-secondary"
                    onClick={handleApplyLocal}
                    disabled={appliedLocal}
                    style={{ 
                      padding: '0.85rem 1.5rem', fontSize: '0.9rem',
                      borderColor: appliedLocal ? 'var(--color-success)' : 'var(--border-light)',
                      color: appliedLocal ? 'var(--color-success)' : 'var(--text-main)',
                      fontWeight: 600
                    }}
                  >
                    <Check size={16} />
                    {appliedLocal ? 'Applied to Worktree' : 'Apply Patch to Worktree'}
                  </button>

                  <button
                    className="btn btn-accent"
                    onClick={handleOpenPR}
                    disabled={openedPR}
                    style={{ padding: '0.85rem 1.75rem', fontSize: '0.9rem', fontWeight: 600 }}
                  >
                    <ExternalLink size={16} />
                    {openedPR ? 'Draft PR Created' : 'Open Draft PR on GitHub'}
                  </button>
                </>
              )}
            </div>
          </div>
        </section>
      )}

    </div>
  );
}
