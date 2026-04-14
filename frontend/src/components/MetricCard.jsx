function MetricCard({
  title,
  value,
  suffix,
  note,
  noteTone = 'accent',
  icon = 'neurology',
  highlight = false,
}) {
  return (
    <article className={`metric-card ${highlight ? 'metric-card-highlight' : ''}`.trim()}>
      <div className="metric-card-head">
        <span>{title}</span>
        <i className="material-symbols-outlined" aria-hidden="true">
          {icon}
        </i>
      </div>

      <div className="metric-card-body">
        <strong>{value}</strong>
        {suffix ? <em>{suffix}</em> : null}
      </div>

      {note ? <small className={`metric-card-note metric-card-note-${noteTone}`}>{note}</small> : null}
    </article>
  )
}

export default MetricCard
