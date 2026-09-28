import React from 'react';
import { FileCode2 } from 'lucide-react';

export default function CodeDiffViewer({ filename, diffLines }) {
  return (
    <div className="glass-panel" style={{ padding: '0', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div style={{ 
        display: 'flex', alignItems: 'center', gap: '0.5rem', 
        padding: '0.75rem 1rem', borderBottom: '1px solid var(--border-light)',
        background: 'var(--bg-element)'
      }}>
        <FileCode2 size={14} color="var(--text-muted)" />
        <span style={{ fontFamily: 'var(--font-code)', fontSize: '0.75rem', color: 'var(--text-main)' }}>{filename}</span>
      </div>
      
      <div style={{ background: 'var(--bg-dark)', overflowX: 'auto' }}>
        <pre style={{ background: 'transparent', border: 'none', padding: '0.5rem 0', margin: 0, fontSize: '0.85rem' }}>
          {(() => {
            const lines = typeof diffLines === 'string' ? diffLines.split('\n') : Array.isArray(diffLines) ? diffLines : [];
            return lines.map((line, i) => {
              const isAdd = line.startsWith('+');
              const isRemove = line.startsWith('-');
              const isHeader = line.startsWith('---') || line.startsWith('+++') || line.startsWith('@@');
              const bgColor = isAdd ? 'rgba(23, 201, 100, 0.1)' : isRemove ? 'rgba(243, 18, 96, 0.1)' : 'transparent';
              const color = isAdd ? 'var(--color-success)' : isRemove ? 'var(--color-error)' : isHeader ? 'var(--color-accent)' : 'var(--text-muted)';
              
              return (
                <div key={i} style={{ 
                  background: bgColor, color: color, padding: '0 1rem',
                  display: 'flex', gap: '1rem', lineHeight: '1.5'
                }}>
                  <span style={{ color: 'var(--text-dim)', userSelect: 'none', width: '24px', textAlign: 'right', fontSize: '0.75rem' }}>{i + 1}</span>
                  <span style={{ whiteSpace: 'pre-wrap' }}>{line}</span>
                </div>
              );
            });
          })()}
        </pre>
      </div>
    </div>
  );
}
