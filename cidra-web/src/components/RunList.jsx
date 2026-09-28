import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle, XCircle, AlertTriangle, Clock } from 'lucide-react';

const RunList = () => {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetch('http://localhost:8000/api/runs')
      .then(res => res.json())
      .then(data => {
        setRuns(data);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  const getOutcomeBadge = (outcome) => {
    switch(outcome) {
      case 'verified_fix': return <span className="badge success"><CheckCircle size={14}/> Verified Fix</span>;
      case 'failed': return <span className="badge error"><XCircle size={14}/> Failed</span>;
      case 'flaky_detected': return <span className="badge warning"><AlertTriangle size={14}/> Flaky</span>;
      case 'diagnosis_only': return <span className="badge info"><Clock size={14}/> Diagnosis Only</span>;
      default: return <span className="badge info">{outcome}</span>;
    }
  };

  if (loading) return <div className="glass-panel text-secondary">Loading runs...</div>;

  return (
    <div className="glass-panel">
      <h2 style={{ marginBottom: '1.5rem', fontWeight: 600 }}>Recent Executions</h2>
      <div className="table-container">
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Repository</th>
              <th>Category</th>
              <th>Flaky Score</th>
              <th>Outcome</th>
              <th>Timestamp</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 ? (
              <tr><td colSpan="6" className="text-secondary" style={{ textAlign: 'center' }}>No runs recorded yet.</td></tr>
            ) : runs.map((run, idx) => (
              <tr key={idx} onClick={() => navigate(`/run/${run.run_id}`)}>
                <td style={{ fontFamily: 'monospace' }}>{run.run_id.slice(0,8)}...</td>
                <td>{run.repo} <span className="text-secondary">@{run.commit_sha}</span></td>
                <td>{run.category || 'N/A'}</td>
                <td>
                  {run.flaky_score !== null ? (
                    <span className={`badge ${run.flaky_score > 0 ? 'warning' : 'success'}`}>
                      {run.flaky_score}
                    </span>
                  ) : '-'}
                </td>
                <td>{getOutcomeBadge(run.outcome)}</td>
                <td className="text-secondary">
                  {new Date(run.ts * 1000).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default RunList;
