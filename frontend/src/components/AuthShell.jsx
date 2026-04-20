function AuthShell({ children }) {
  return (
    <main className="auth-shell">
      <div className="lab-frame auth-lab-frame">
        <div className="auth-shell-surface">
          <div className="auth-shell-brand">
            <h1>FIBRIT0</h1>
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
        </div>
      </div>
    </main>
  )
}

export default AuthShell
