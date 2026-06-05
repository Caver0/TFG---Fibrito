import { useState, useEffect } from 'react'
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
  const [menuOpen, setMenuOpen] = useState(false)

  // Cierra el menú al cambiar de vista
  function handleNavigate(viewId) {
    onNavigate(viewId)
    setMenuOpen(false)
  }

  // Bloquea el scroll del body mientras el menú está abierto
  useEffect(() => {
    if (menuOpen) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => {
      document.body.style.overflow = ''
    }
  }, [menuOpen])

  return (
    <main className="app-shell">
      <div className="lab-frame app-lab-frame">

        {/* ── Overlay mobile ────────────────────────────────────── */}
        {menuOpen && (
          <div
            className="lab-mobile-overlay"
            aria-hidden="true"
            onClick={() => setMenuOpen(false)}
          />
        )}

        {/* ── Sidebar desktop / drawer mobile ───────────────────── */}
        <aside className={`lab-sidebar${menuOpen ? ' lab-sidebar-open' : ''}`}>
          <div className="lab-sidebar-inner">
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
                    onClick={() => handleNavigate(view.id)}
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
          </div>
        </aside>

        {/* ── Área principal ────────────────────────────────────── */}
        <div className="lab-main">
          <header className="lab-topbar">
            {/* Botón hamburguesa — sólo visible en mobile */}
            <button
              type="button"
              className="lab-hamburger"
              aria-label={menuOpen ? 'Cerrar menú' : 'Abrir menú'}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((prev) => !prev)}
            >
              <i className="material-symbols-outlined" aria-hidden="true">
                {menuOpen ? 'close' : 'menu'}
              </i>
            </button>

            <div className="lab-topbar-title">
              <h2>{viewMeta.topbarTitle}</h2>
              <div className="lab-topbar-divider" aria-hidden="true" />
              <p>{viewMeta.topbarContext}</p>
            </div>
          </header>

          <div className="lab-content">{children}</div>
        </div>
      </div>

      {/* ── Bottom navigation bar — sólo en mobile ────────────── */}
      <nav className="lab-bottom-nav" aria-label="Navegación principal">
        {views.map((view) => {
          const isActive = view.id === activeView
          return (
            <button
              key={view.id}
              type="button"
              className={`lab-bottom-nav-item${isActive ? ' lab-bottom-nav-item-active' : ''}`}
              aria-current={isActive ? 'page' : undefined}
              onClick={() => handleNavigate(view.id)}
            >
              <i className="material-symbols-outlined" aria-hidden="true">
                {view.icon}
              </i>
              <span>{view.sidebarLabel}</span>
            </button>
          )
        })}
      </nav>
    </main>
  )
}

export default AppShell
