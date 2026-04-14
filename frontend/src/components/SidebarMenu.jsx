function SidebarMenu({ activeView, onLogout, onNavigate, user, views }) {
  return (
    <aside className="sidebar-menu">
      <div className="sidebar-menu-panel">
        <div className="sidebar-menu-heading">
          <span className="eyebrow">Workspace</span>
          <h2>FIBRIT0</h2>
          <p>Un panel mas ordenado para moverte entre seguimiento, dieta, progreso y perfil sin recorrer una pagina infinita.</p>
        </div>

        <div className="sidebar-menu-user">
          <span className="sidebar-menu-user-label">Sesion activa</span>
          <strong>{user?.name ?? 'Perfil'}</strong>
          <small>{user?.email ?? 'Sin email disponible'}</small>
        </div>

        <nav className="sidebar-menu-links" aria-label="Vistas principales">
          {views.map((view, index) => (
            <button
              key={view.id}
              type="button"
              className={`sidebar-menu-link ${activeView === view.id ? 'sidebar-menu-link-active' : ''}`}
              aria-current={activeView === view.id ? 'page' : undefined}
              onClick={() => onNavigate(view.id)}
            >
              <span className="sidebar-menu-link-line" aria-hidden="true">
                {String(index + 1).padStart(2, '0')}
              </span>
              <span className="sidebar-menu-link-copy">
                <strong>{view.label}</strong>
                <small>{view.note}</small>
              </span>
            </button>
          ))}
        </nav>

        <div className="sidebar-menu-footer">
          <p>Diseno oscuro, limpio y preparado para aprovechar mejor el ancho de trabajo.</p>
          <button type="button" className="secondary-button sidebar-menu-logout" onClick={onLogout}>
            Cerrar sesion
          </button>
        </div>
      </div>
    </aside>
  )
}

export default SidebarMenu
