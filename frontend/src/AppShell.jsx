import { useRef, useState } from 'react'
import AppHeader from './AppHeader'
import Icon from './Icon'

export function UsageNotice({ usage, onCheck }) {
  return <section className="usage-notice" aria-label="Free AI usage" role="status">
    <strong>{usage.unavailable ? 'Public AI temporarily unavailable' : `${usage.remaining} free AI uses remaining`}</strong>
    {!usage.unavailable && <p>{usage.global_remaining} public AI uses left in total. {usage.remaining === 0 && 'Your free allowance has been reached. Playback, Undo/Redo and export remain available.'}</p>}
    <details className="usage-details"><summary>Usage details</summary><p>{usage.message}</p>
    <small>Anonymous sessions and network limits reduce abuse; they do not identify individual people.</small></details>
    {usage.unavailable && <button className="secondary" onClick={onCheck}>Check availability</button>}
  </section>
}

export default function AppShell({ session, busy, canExport, onNew, onExport, usagePanel, children }) {
  const [sidebarOpen, setSidebarOpen] = useState(() => window.matchMedia?.('(min-width: 901px)').matches ?? true)
  const menuButton = useRef(null)
  function closeSidebar() { setSidebarOpen(false); menuButton.current?.focus() }
  function reveal(selector) {
    const target = document.querySelector(selector)
    if (target?.tagName === 'DETAILS') target.open = true
    if (target?.id === 'recording-workspace') target.scrollTo?.({ top: 0, behavior: 'smooth' })
    else target?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
    if (window.matchMedia?.('(max-width: 900px)').matches) closeSidebar()
  }
  return <div className={`app-shell stage-one-shell ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`} onKeyDown={event => { if (event.key === 'Escape' && sidebarOpen) closeSidebar() }}>
    <aside className="app-sidebar" id="tweeq-navigation" aria-label="Tweeq navigation" aria-hidden={!sidebarOpen} inert={!sidebarOpen}>
      <div className="sidebar-brand brand-block"><a className="brand" href="/" aria-label="Tweeq home"><Icon name="waveform" size={36}/><span>Tweeq</span></a><p>One mistake shouldn't mean another take.</p></div>
      <div className="sidebar-context"><Icon name="folder" size={24}/><span>Audio editor</span></div>
      <nav className="sidebar-navigation" aria-label="Workspace">
        <span className="sidebar-group-label">Workspace</span>
        <a href="#recording-workspace" className="sidebar-link selected" aria-current="page" onClick={event => { event.preventDefault(); reveal('#recording-workspace') }}><Icon name="home" size={24}/>Recording</a>
        {!!session?.quality?.warnings?.length && <button className="sidebar-link" onClick={() => reveal('.quality-notice')}><Icon name="shield" size={24}/>Recording quality</button>}
        {!!session?.edit_history?.length && <button className="sidebar-link" onClick={() => reveal('.history-disclosure')}><Icon name="history" size={24}/>Edit History</button>}
      </nav>
      <div className="sidebar-bottom">{usagePanel}<footer className="sidebar-footer"><span>Tweeq <span className="muted">/ One mistake shouldn't mean another take.</span></span><span className="muted">Local editing. Your voice, with permission.</span></footer></div>
    </aside>
    <button className="sidebar-scrim" hidden={!sidebarOpen} onClick={closeSidebar} aria-label="Close navigation"/>
    <AppHeader recordingName={session?.name} busy={busy} canExport={canExport} onNew={onNew} onExport={onExport}
      sidebarOpen={sidebarOpen} onToggleSidebar={() => setSidebarOpen(value => !value)} menuButton={menuButton}/>
    <main className={session ? 'editor-stage' : 'upload-stage'} id="recording-workspace">{children}</main>
  </div>
}
