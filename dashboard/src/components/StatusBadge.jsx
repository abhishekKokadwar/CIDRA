import React from 'react';

export default function StatusBadge({ status }) {
  const styles = {
    success: { bg: 'rgba(23, 201, 100, 0.1)', color: 'var(--color-success)', border: 'rgba(23, 201, 100, 0.2)' },
    error: { bg: 'rgba(243, 18, 96, 0.1)', color: 'var(--color-error)', border: 'rgba(243, 18, 96, 0.2)' },
    active: { bg: 'rgba(0, 112, 243, 0.1)', color: 'var(--color-accent)', border: 'rgba(0, 112, 243, 0.2)' },
    pending: { bg: 'rgba(245, 165, 36, 0.1)', color: 'var(--color-warning)', border: 'rgba(245, 165, 36, 0.2)' }
  };

  const s = styles[status] || styles.pending;

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '0.375rem',
      padding: '0.125rem 0.5rem', borderRadius: '99px',
      fontSize: '0.75rem', fontWeight: '500', letterSpacing: '0.02em',
      background: s.bg, color: s.color, border: `1px solid ${s.border}`
    }}>
      {status === 'active' && (
        <span style={{
          width: 6, height: 6, borderRadius: '50%', background: s.color
        }} />
      )}
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}
