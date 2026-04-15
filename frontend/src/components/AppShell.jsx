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
            <span>KINETIC LAB</span>
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
            <div>
              <strong>{user?.name ?? 'Perfil Activo'}</strong>
              <span>{phaseLabel.replace('PHASE: ', '')}</span>
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

            <div className="lab-topbar-actions">
              <label className="lab-search" aria-label="Decorative search field">
                <i className="material-symbols-outlined" aria-hidden="true">
                  search
                </i>
                <input placeholder={viewMeta.searchPlaceholder} type="text" />
              </label>

              <button type="button" className="lab-icon-button" aria-label="Notifications">
                <i className="material-symbols-outlined" aria-hidden="true">
                  notifications
                </i>
              </button>

              <button type="button" className="lab-icon-button" aria-label="Settings">
                <i className="material-symbols-outlined" aria-hidden="true">
                  settings
                </i>
              </button>
            </div>
          </header>

          <div className="lab-content">{children}</div>
        </div>
      </div>
    </main>
  )
}

export default AppShell
