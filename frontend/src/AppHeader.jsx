import Icon from './Icon'

export default function AppHeader({ recordingName, busy, canExport, onNew, onExport, sidebarOpen, onToggleSidebar, menuButton }) {
  return <header className="app-header"><div className="header-inner">
    <div className="header-location"><button className="sidebar-toggle" ref={menuButton} onClick={onToggleSidebar} aria-label="Toggle navigation" aria-controls="tweeq-navigation" aria-expanded={sidebarOpen}><Icon name="sidebar" size={24}/></button><span className="desktop-header-title">Recording</span><span className="mobile-header-title">Tweeq</span></div>
    {recordingName && <div className="header-actions"><button className="quiet" disabled={busy} onClick={onNew}>New Recording</button><button className="secondary" disabled={busy || !canExport} onClick={onExport}><Icon name="download"/>Export</button></div>}
  </div></header>
}
