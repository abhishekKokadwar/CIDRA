import React from 'react';
import { 
  LayoutDashboard, 
  Search, 
  GitPullRequest, 
  Settings, 
  Workflow, 
  PanelLeftClose, 
  PanelLeftOpen 
} from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab, collapsed, onToggleCollapse }) {
  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      {/* Top Header: Logo + Title + Collapse Toggle */}
      <div style={{ 
        display: 'flex', 
        flexDirection: collapsed ? 'column' : 'row',
        alignItems: 'center', 
        justifyContent: collapsed ? 'center' : 'space-between',
        gap: collapsed ? '0.75rem' : '0',
        padding: collapsed ? '0' : '0 0.5rem',
        marginBottom: '1.25rem',
        width: '100%'
      }}>
        {/* Logo and Brand Title */}
        <div 
          onClick={collapsed ? onToggleCollapse : undefined}
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: collapsed ? 'center' : 'flex-start',
            gap: '0.75rem',
            cursor: collapsed ? 'pointer' : 'default',
            userSelect: 'none',
            width: collapsed ? '100%' : 'auto'
          }}
          title={collapsed ? 'Click to expand sidebar' : undefined}
        >
          <div style={{
            background: 'transparent',
            width: '36px',
            height: '36px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            margin: collapsed ? '0 auto' : '0'
          }}>
            <img 
              src="/cidra_icon.png" 
              alt="CIDRA" 
              style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }}
            />
          </div>
          
          {!collapsed && (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ 
                fontSize: '1.25rem', 
                fontWeight: 800, 
                letterSpacing: '-0.02em', 
                color: 'var(--text-main)',
                lineHeight: 1.1,
                display: 'inline-block'
              }}>
                CIDRA
              </span>
              <span style={{
                fontSize: '0.65rem',
                fontFamily: 'var(--font-code)',
                color: 'var(--color-accent)',
                letterSpacing: '0.08em',
                fontWeight: 600,
                marginTop: '2px'
              }}>
                AUTONOMOUS CI
              </span>
            </div>
          )}
        </div>

        {/* Toggle Collapse/Expand Button */}
        <button
          onClick={onToggleCollapse}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          style={{
            background: 'transparent',
            border: 'none',
            color: 'var(--text-dim)',
            cursor: 'pointer',
            padding: '0.45rem',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'color 0.15s ease, background 0.15s ease',
            margin: collapsed ? '0 auto' : '0'
          }}
          onMouseOver={(e) => {
            e.currentTarget.style.color = 'var(--text-main)';
            e.currentTarget.style.background = 'var(--bg-element)';
          }}
          onMouseOut={(e) => {
            e.currentTarget.style.color = 'var(--text-dim)';
            e.currentTarget.style.background = 'transparent';
          }}
        >
          {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
        </button>
      </div>

      {/* Navigation Items */}
      <nav style={{ 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '0.35rem', 
        marginTop: '0.5rem',
        width: '100%'
      }}>
        <NavItem 
          icon={<LayoutDashboard size={18} />} 
          label="Command Center" 
          active={activeTab === 'overview'} 
          collapsed={collapsed}
          onClick={() => setActiveTab('overview')} 
        />
        <NavItem 
          icon={<Workflow size={18} />} 
          label="Pipeline Orchestrator" 
          active={activeTab === 'orchestrator'} 
          collapsed={collapsed}
          onClick={() => setActiveTab('orchestrator')} 
        />
        <NavItem 
          icon={<Search size={18} />} 
          label="Run Explorer" 
          active={activeTab === 'explorer'} 
          collapsed={collapsed}
          onClick={() => setActiveTab('explorer')} 
        />
        <NavItem 
          icon={<GitPullRequest size={18} />} 
          label="Pull Requests" 
          active={activeTab === 'prs'} 
          collapsed={collapsed}
          onClick={() => setActiveTab('prs')} 
        />
        <NavItem 
          icon={<Settings size={18} />} 
          label="Settings" 
          active={activeTab === 'settings'} 
          collapsed={collapsed}
          onClick={() => setActiveTab('settings')} 
        />
      </nav>
      
      {/* Bottom Footer */}
      <div style={{ 
        marginTop: 'auto', 
        padding: collapsed ? '0' : '0 0.75rem', 
        fontSize: '0.75rem', 
        color: 'var(--text-dim)',
        textAlign: collapsed ? 'center' : 'left',
        width: '100%'
      }}>
        {collapsed ? (
          <span title="CIDRA Engine v0.2.0" style={{ fontFamily: 'var(--font-code)', fontSize: '0.7rem', display: 'block', margin: '0 auto' }}>
            v1.0
          </span>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
            <span style={{ fontWeight: 500, color: 'var(--text-muted)' }}>CIDRA Engine</span>
            <span style={{ fontFamily: 'var(--font-code)', fontSize: '0.7rem' }}>v0.2.0</span>
          </div>
        )}
      </div>
    </aside>
  );
}

function NavItem({ icon, label, active, collapsed, onClick }) {
  return (
    <div 
      className={`nav-link ${active ? 'active' : ''}`}
      onClick={onClick}
      title={collapsed ? label : undefined}
      style={{
        position: 'relative',
        justifyContent: collapsed ? 'center' : 'flex-start',
        width: collapsed ? '40px' : '100%',
        height: collapsed ? '40px' : 'auto',
        margin: collapsed ? '0 auto' : '0',
        padding: collapsed ? '0' : '0.5rem 0.75rem',
        borderRadius: '6px'
      }}
    >
      <span style={{ 
        color: active ? 'var(--color-accent)' : 'var(--text-muted)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        {icon}
      </span>
      {!collapsed && (
        <span style={{ 
          color: active ? 'var(--text-main)' : 'var(--text-muted)',
          fontWeight: active ? 600 : 500
        }}>
          {label}
        </span>
      )}
    </div>
  );
}
