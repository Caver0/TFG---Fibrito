import { formatGoalPhase, getInitials } from '../utils/stitch'

function AppShell({
  activeView,
  onNavigate,
  onLogout,
  user,
  views,
  viewMeta,
  children,
}) {
  const phaseLabel = viewMeta.phaseLabel || formatGoalPhase(user?.goal)

  return (
    <main className="app-shell">
      <div className="lab-frame app-lab-frame">
        <aside className="lab-sidebar">
          <div className="lab-brand">
            <h1>FIBRIT0</h1>
          </div>

          <nav className="lab-nav" aria-label="Primary">
            {views.map((view) => {
              const isActive = view.id === activeView
              return (
                <button
                  key={view.id}
                  type="button"
                  className={`lab-nav-item ${isActive ? 'lab-nav-item-active' : ''}`.trim()}
                  aria-current={isActive ? 'page' : undefined}
                  onClick={() => onNavigate(view.id)}
                >
                  <i className="material-symbols-outlined" aria-hidden="true">
                    {view.icon}
                  </i>
                  <span>{view.sidebarLabel}</span>
                </button>
              )
            })}
          </nav>

          <div className="lab-operator-card">
            <div className="lab-operator-avatar" aria-hidden="true">
              {getInitials(user?.name)}
            </div>
            <div className="lab-operator-copy">
              <strong>{user?.name ?? 'Perfil Activo'}</strong>
              <span>{phaseLabel.replace('FASE: ', '')}</span>
            </div>
          </div>

          <button type="button" className="lab-logout-button" onClick={onLogout}>
            <i className="material-symbols-outlined" aria-hidden="true">
              logout
            </i>
            <span>Cerrar sesión</span>
          </button>
        </aside>

        <div className="lab-main">
          <header className="lab-topbar">
            <div className="lab-topbar-title">
              <h2>{viewMeta.topbarTitle}</h2>
              <div className="lab-topbar-divider" aria-hidden="true" />
              <p>{viewMeta.topbarContext}</p>
            </div>
          </header>

          <div className="lab-content">{children}</div>
        </div>
      </div>
    </main>
  )
}

export default AppShell
