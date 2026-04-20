function SectionPanel({
  eyebrow,
  title,
  description,
  actions,
  className = '',
  children,
}) {
  return (
    <section className={`section-panel ${className}`.trim()}>
      {(eyebrow || title || description || actions) ? (
        <header className="section-panel-header">
          <div className="section-panel-copy">
            {eyebrow ? <span className="section-panel-eyebrow">{eyebrow}</span> : null}
            {title ? <h3>{title}</h3> : null}
            {description ? <p>{description}</p> : null}
          </div>

          {actions ? <div className="section-panel-actions">{actions}</div> : null}
        </header>
      ) : null}

      {children}
    </section>
  )
}

export default SectionPanel