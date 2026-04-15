function AuthShell({ children }) {
  return (
    <main className="auth-shell">
      <div className="lab-frame auth-lab-frame">
        <div className="auth-shell-surface">
          <div className="auth-shell-brand">
            <h1>FIBRIT0</h1>
            <span>LABORATORIO CINÉTICO</span>
          </div>

          <div className="auth-deco auth-deco-left" aria-hidden="true">
            FIB
          </div>
          <div className="auth-deco auth-deco-right" aria-hidden="true">
            RIT0
          </div>

          <div className="auth-shell-polygons" aria-hidden="true">
            <span className="auth-poly auth-poly-a" />
            <span className="auth-poly auth-poly-b" />
            <span className="auth-poly auth-poly-c" />
            <span className="auth-poly auth-poly-d" />
          </div>

          <div className="auth-shell-content">
            {children}
          </div>

          <footer className="auth-shell-footer">
            <div className="auth-footer-block">
              <small>Estado del Sistema</small>
              <strong>
                <span className="auth-footer-dot" aria-hidden="true" />
                EN LÍNEA
              </strong>
            </div>

            <div className="auth-footer-divider" aria-hidden="true" />

            <div className="auth-footer-block">
              <small>Cifrado</small>
              <strong>AES-256</strong>
            </div>

            <span className="auth-footer-version">v2.0.4 // CORE</span>
          </footer>
        </div>
      </div>
    </main>
  )
}

export default AuthShell
