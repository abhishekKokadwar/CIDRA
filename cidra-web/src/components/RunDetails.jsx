import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import ApprovalGate from './ApprovalGate';
import { ArrowLeft, GitCommit, PlayCircle, Code, ShieldCheck } from 'lucide-react';

const RunDetails = () => {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`http://localhost:8000/api/runs/${runId}`)
      .then(res => res.json())
      .then(data => {
        setState(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [runId]);

  if (loading) return <div className="glass-panel text-secondary">Loading details...</div>;
  if (!state) return <div className="glass-panel text-secondary">Run not found.</div>;

  return (
    <div>
      <button className="btn mb-4" onClick={() => navigate('/')} style={{ background: 'transparent', border: '1px solid var(--glass-border)', color: 'var(--text-secondary)' }}>
        <ArrowLeft size={16} /> Back to Runs
      </button>

      <div className="glass-panel mb-4">
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <GitCommit size={24} color="var(--accent)" />
          {state.repo} <span className="text-secondary" style={{ fontWeight: 400 }}>@{state.commit_sha?.slice(0, 7)}</span>
        </h2>
        <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
          <div className="badge info">Outcome: {state.outcome}</div>
          {state.cache_hit && <div className="badge success">Cache Hit (0 LLM Calls)</div>}
          <div className="badge warning">Flaky Score: {state.flaky_score ?? 'N/A'}</div>
        </div>
      </div>

      <div className="grid-2">
        {/* Decision Tree / Analysis */}
        <div className="glass-panel">
          <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <PlayCircle size={18} /> LangGraph Decision Tree
          </h3>
          
          <div className="tree-node">
            <strong>Log Ingestion</strong>
            <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Isolated {state.log_markers?.length || 0} error markers</div>
          </div>
          
          {state.analysis && (
            <div className="tree-node">
              <strong>LLM Root Cause Analysis</strong>
              <div className="text-secondary" style={{ fontSize: '0.875rem' }}>Category: <span style={{ color: 'var(--accent)' }}>{state.analysis.category}</span></div>
              <div className="log-block" style={{ marginTop: '0.5rem' }}>
                {state.analysis.evidence}
                <br/><br/>
                Action: {state.analysis.proposed_action}
              </div>
            </div>
          )}

          {state.patch_audit_reasons && state.patch_audit_reasons.length > 0 && (
            <div className="tree-node">
              <strong>Static AST Audit</strong>
              <div className="badge error" style={{ marginTop: '0.5rem' }}>Rejected: {state.patch_audit_reasons[0]}</div>
            </div>
          )}

          {state.fix_diff && (
            <div className="tree-node">
              <strong>Patch Generation</strong>
              <div className="log-block">{state.fix_diff}</div>
            </div>
          )}

          <div className="tree-node" style={{ borderLeft: 'none' }}>
            <strong>Terminal State: {state.outcome}</strong>
          </div>
        </div>

        {/* Container Logs */}
        <div className="glass-panel">
          <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <ShieldCheck size={18} /> Sandbox Container Execution
          </h3>
          
          {state.repro_results?.map((res, i) => (
            <div key={`repro-${i}`} className="mb-4">
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong>Step: {res.step} (Reproduction)</strong>
                <span className={`badge ${res.exit_code === 0 ? 'success' : 'error'}`}>Exit: {res.exit_code}</span>
              </div>
              <div className="log-block">
                {res.stderr_tail || res.stdout_tail || 'No output'}
              </div>
            </div>
          ))}

          {state.verify_results?.map((res, i) => (
            <div key={`verify-${i}`} className="mb-4">
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <strong>Step: {res.step} (Verification)</strong>
                <span className={`badge ${res.exit_code === 0 ? 'success' : 'error'}`}>Exit: {res.exit_code}</span>
              </div>
              <div className="log-block">
                {res.stderr_tail || res.stdout_tail || 'No output'}
              </div>
            </div>
          ))}

          {(!state.repro_results?.length && !state.verify_results?.length) && (
            <div className="text-secondary">No container executions recorded for this run.</div>
          )}
        </div>
      </div>

      <ApprovalGate 
        runId={state.run_id} 
        outcome={state.outcome} 
        prUrl={state.pr_url}
      />
    </div>
  );
};

export default RunDetails;
