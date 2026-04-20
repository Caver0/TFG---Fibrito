function AuthCard({
  title,
  subtitle,
  children,
  footer,
  mode = 'login',
}) {
  return (
    <section className={`auth-card auth-card-${mode}`.trim()}>
      <div className="auth-card-accent" aria-hidden="true" />

      <header className="auth-card-header">
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </header>

      <div className="auth-card-body">{children}</div>

      {footer ? <footer className="auth-card-footer">{footer}</footer> : null}
    </section>
  )
}

export default AuthCard