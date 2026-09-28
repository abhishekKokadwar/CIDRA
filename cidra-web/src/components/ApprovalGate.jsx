import React from 'react';
import { Check, X } from 'lucide-react';

const ApprovalGate = ({ runId, outcome, prUrl }) => {
  const [status, setStatus] = React.useState('pending');

  const handleApprove = async () => {
    setStatus('approving');
    try {
      const res = await fetch(`http://localhost:8000/api/runs/${runId}/approve`, {
        method: 'POST'
      });
      if (res.ok) {
        setStatus('approved');
      } else {
        setStatus('error');
      }
    } catch (err) {
      console.error(err);
      setStatus('error');
    }
  };

  if (outcome !== 'verified_fix' && outcome !== 'diagnosis_only') {
    return (
      <div className="glass-panel mt-4" style={{ borderLeft: '4px solid var(--text-secondary)' }}>
        <h3 style={{ marginBottom: '0.5rem' }}>No Action Required</h3>
        <p className="text-secondary" style={{ fontSize: '0.875rem' }}>
          This run ended in <strong>{outcome}</strong>. The pipeline safely terminated without proposing a patch.
        </p>
      </div>
    );
  }

  return (
    <div className="glass-panel mt-4" style={{ borderLeft: '4px solid var(--accent)' }}>
      <h3 style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        Human-in-the-Loop Gate
      </h3>
      <p className="text-secondary mb-4" style={{ fontSize: '0.875rem' }}>
        A verified fix has been drafted. Please review the patch and analysis above before merging.
        {prUrl && <span> You can view the full draft PR <a href={prUrl} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>here</a>.</span>}
      </p>

      {status === 'pending' && (
        <div style={{ display: 'flex', gap: '1rem' }}>
          <button className="btn btn-success" onClick={handleApprove}>
            <Check size={18} /> Approve & Merge
          </button>
          <button className="btn" style={{ background: 'var(--panel-bg)', border: '1px solid var(--error)', color: 'var(--error)' }}>
            <X size={18} /> Reject
          </button>
        </div>
      )}
      
      {status === 'approving' && <div className="text-secondary">Processing approval...</div>}
      
      {status === 'approved' && (
        <div className="badge success" style={{ fontSize: '1rem', padding: '0.75rem 1rem' }}>
          <Check size={18} /> Patch Approved & Merged
        </div>
      )}

      {status === 'error' && (
        <div className="badge error" style={{ fontSize: '1rem', padding: '0.75rem 1rem' }}>
          <X size={18} /> Error processing approval
        </div>
      )}
    </div>
  );
};

export default ApprovalGate;
