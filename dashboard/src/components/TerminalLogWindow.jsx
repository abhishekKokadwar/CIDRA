import React from 'react';
import { Terminal } from 'lucide-react';

export default function TerminalLogWindow({ title, logs }) {
  return (
    <div className="glass-panel" style={{ padding: '0', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      {/* Window Header */}
      <div style={{ 
        display: 'flex', alignItems: 'center', gap: '0.75rem', 
        padding: '0.5rem 1rem', borderBottom: '1px solid var(--border-light)',
        background: 'var(--bg-element)'
      }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--border-focus)' }} />
          <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--border-focus)' }} />
          <div style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--border-focus)' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: '1rem', color: 'var(--text-muted)', fontSize: '0.75rem', fontFamily: 'var(--font-code)' }}>
          <Terminal size={12} />
          {title || 'Terminal'}
        </div>
      </div>
      
      {/* Log Content */}
      <div style={{ padding: '1rem', background: 'var(--bg-dark)', maxHeight: '350px', overflowY: 'auto' }}>
        <pre style={{ background: 'transparent', border: 'none', padding: 0, margin: 0 }}>
          {(() => {
            let parsedLogs = [];
            if (typeof logs === 'string') {
              parsedLogs = logs.split('\n').map(line => {
                const isErr = line.includes('ERROR') || line.includes('FAIL') || line.includes('Error') || line.startsWith('E ') || line.includes('AssertionError');
                const isSuccess = line.includes('PASSED') || line.includes('passed in');
                return { text: line, type: isErr ? 'error' : isSuccess ? 'success' : 'normal' };
              });
            } else if (Array.isArray(logs)) {
              parsedLogs = logs.map(l => typeof l === 'string' ? { text: l, type: 'normal' } : l);
            }

            return parsedLogs.map((log, i) => (
              <div key={i} style={{ 
                color: log.type === 'error' ? 'var(--color-error)' : log.type === 'success' ? 'var(--color-success)' : 'var(--text-main)',
                marginBottom: '0.125rem',
                lineHeight: 1.5,
                fontSize: '0.825rem'
              }}>
                <span style={{ color: 'var(--text-dim)', marginRight: '1rem', userSelect: 'none', display: 'inline-block', width: '28px', textAlign: 'right' }}>
                  {i + 1}
                </span>
                <span>{log.text}</span>
              </div>
            ));
          })()}
        </pre>
      </div>
    </div>
  );
}
