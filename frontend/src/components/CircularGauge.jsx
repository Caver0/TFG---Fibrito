function CircularGauge({
  value = 0,
  label,
  caption,
  size = 212,
  strokeWidth = 10,
  className = '',
  accentClassName = '',
}) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const safeValue = Math.min(100, Math.max(0, Number(value) || 0))
  const dashOffset = circumference * (1 - safeValue / 100)

  return (
    <div className={`circular-gauge ${className}`.trim()}>
      <svg
        aria-hidden="true"
        className="circular-gauge-ring"
        viewBox={`0 0 ${size} ${size}`}
      >
        <circle
          className="circular-gauge-track"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
        />
        <circle
          className={`circular-gauge-progress ${accentClassName}`.trim()}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
        />
      </svg>

      <div className="circular-gauge-center">
        <strong>{Math.round(safeValue)}%</strong>
        {label ? <span>{label}</span> : null}
        {caption ? <small>{caption}</small> : null}
      </div>
    </div>
  )
}

export default CircularGauge
