import React from 'react';
import { Check, Loader2, X, Circle } from 'lucide-react';

export default function TimelineNode({ title, description, status, icon, isLast, children }) {
  const isSuccess = status === 'success';
  const isActive = status === 'active';
  const isError = status === 'error';
  
  const getIcon = () => {
    if (icon) return icon;
    if (isSuccess) return <Check size={14} />;
    if (isError) return <X size={14} />;
    if (isActive) return <Loader2 size={14} className="lucide-spin" />;
    return <Circle size={14} />;
  };
  
  const getColor = () => {
    if (isSuccess) return 'var(--color-success)';
    if (isError) return 'var(--color-error)';
    if (isActive) return 'var(--color-accent)';
    return 'var(--text-dim)';
  };

  return (
    <div style={{ display: 'flex', gap: '1.5rem', position: 'relative' }}>
      {/* Line */}
      {!isLast && (
        <div style={{
          position: 'absolute',
          left: '11px',
          top: '24px',
          bottom: '-8px',
          width: '2px',
          background: isSuccess ? 'var(--color-success)' : 'var(--border-light)',
          zIndex: 0
        }} />
      )}
      
      {/* Node Icon */}
      <div style={{
        width: '24px',
        height: '24px',
        borderRadius: '50%',
        background: 'var(--bg-dark)',
        border: `2px solid ${getColor()}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: getColor(),
        zIndex: 1,
        flexShrink: 0
      }}>
        {getIcon()}
      </div>
      
      {/* Content */}
      <div style={{ flex: 1, paddingBottom: '2.5rem' }}>
        <h3 style={{ color: isActive ? 'var(--text-main)' : 'var(--text-main)', fontSize: '1rem', marginBottom: '0.25rem' }}>{title}</h3>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '1rem', maxWidth: '800px' }}>{description}</p>
        
        {children && (
          <div className="animate-in">
            {children}
          </div>
        )}
      </div>
    </div>
  );
}
