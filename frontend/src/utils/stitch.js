export const STITCH_DIET_VISUALS = [
  {
    phase: 'Phase 01',
    label: 'Breakfast',
    imageUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuBV97McYwDNYWDyGsUuvxBrjygsVUXBjVlgpqpMC5WoT-hRZ2qDOxcAPiOB7R7WWyhjXJMs0wFQRzvWgMj7X4zzR8OA1eFh6xo5UrD5DnZ30oQzIubpssI_eyvWh2fDH3_B9QToP7-Ba-G9sNi5uWSrvbbmJsSV1vcN1eBe2eiGKOYdX6iwNmXQ50QtGF5QU5W6WlnOpslILCnUYtNvH76Hmjo3aUJz8DKnRf2ahaaacr1wysIdnl9sZ-B7MFcrloDG0X9-LxYaLno',
  },
  {
    phase: 'Phase 02',
    label: 'Pre-workout',
    imageUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuDAEXQw0p7q1MfKqwHYtz1FLgx7Gi4u4JaGnWaMnLFGRkgW1B5du_SQogH_BLOTMpR4prkuBLkJeCRyr8Lln6EYVhevNXUnSIcZSCcbyuG7CKvwH6DfElVYO5DaGX7rZrNaQ0yKecigPZohpbaxyaxxhoBsfzNB7OcqloM8OHgT6FsAORZEU6mI2_tdKwUGM9LuUfURSH2h7kbFXBAMoR_hkuIjh3dEMdc2W74bPKONbIhEpV8Hy_0-SKfa-uMUAxhZIy9g0lkhzjk',
  },
  {
    phase: 'Phase 03',
    label: 'Post-workout lunch',
    imageUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuCpKMJ-q8WacUhb0kJjrw-mqTcF3UZ1_Gaibb0mk_bO1kHcQXgvJTBGY0igeB2xtVRi5ChQwo0DKNStBcMKFAlbOXHGE47XVP-GbbV_9bmKzFOTC3Z7roftjEA1chb9zrdRo4YXrlm5DSfTNXu51faxU07aSBHenelviKBMIEi07Qf66_SnZyRWCLczGPSnOHJ-9y9FdOZxdF7EYGNx1sVVIp0Ksj8G2nmqN2wKt_uFGexYPxFmiLPUSi7bjf4RL2CQgSJHPwkCB5g',
  },
  {
    phase: 'Phase 04',
    label: 'Dinner',
    imageUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuD68Cvr60cNDb_kQrLJA01Ztsyy-puYpHZ-oeirVIrULHVUpXLxCKv5nuJpkj6R3wn_o6lIT3bQy-479vbs_EbsjFpFYACCRSAtV64h1P7S8DHNeErMuxyytYpnYz-TGjRO-jO8x4wWa95yqjqUxvry-XzwFD7-QGo3h4rp16EyCdp_OVg5njNQBze5fbD1YoFot4tQV0F2-BbjvJFEUa18KNnOEvP5uxkv_9T6EAyL3DBxs0KwtE1pf3vcXECW4QhTLIBHJRv9_eE',
  },
]

export const STITCH_PROFILE_TARGET_BACKGROUND =
  'https://lh3.googleusercontent.com/aida-public/AB6AXuCGw2brtsYaK1cZJ19rRoGmAxDqXPCbCAkHlUyN4frBetqb2gwaW65Y0ATxjctW4YjFQn3okOA1URUiCKcOt9gcb_v_zDgSMegWYsZ4KdbaWm0oTo16rLsIfUxvNu1fTauzFAr01nRoFVZaWNZpe43bsFylNp8zpKqb28AqBLnCTAiFR_efZb_LdaGRFAuSD43cdhUdDP5Oye530msf1P4Zsog_jNcIaFtTeVmdzlFuaIYcaQf77nbBwfD0xnF7U20fd88dLqnbNZ0'

function toFiniteNumber(value) {
  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

export function formatCompactNumber(value, options = {}) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: options.maximumFractionDigits ?? 1,
    minimumFractionDigits: options.minimumFractionDigits ?? 0,
  }).format(numericValue)
}

export function formatMass(value, options = {}) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return `${formatCompactNumber(numericValue, {
    maximumFractionDigits: options.maximumFractionDigits ?? 1,
    minimumFractionDigits: options.minimumFractionDigits ?? 0,
  })} ${options.unit ?? 'kg'}`
}

export function formatSignedMass(value, options = {}) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  const prefix = numericValue > 0 ? '+' : ''
  return `${prefix}${formatMass(numericValue, options)}`
}

export function formatCalories(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return `${formatCompactNumber(Math.round(numericValue), {
    maximumFractionDigits: 0,
  })} kcal`
}

export function formatSignedCalories(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  const roundedValue = Math.round(numericValue)
  const prefix = roundedValue > 0 ? '+' : ''
  return `${prefix}${formatCompactNumber(roundedValue, { maximumFractionDigits: 0 })} kcal`
}

export function formatMacro(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return `${formatCompactNumber(numericValue, {
    maximumFractionDigits: 1,
    minimumFractionDigits: 0,
  })}g`
}

export function formatPercent(value, digits = 1) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'N/A'
  }

  return `${formatCompactNumber(numericValue, {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  })}%`
}

export function formatDateLabel(value, options = {}) {
  if (!value) {
    return 'No date'
  }

  const parsedDate = new Date(value)
  if (Number.isNaN(parsedDate.getTime())) {
    return 'No date'
  }

  return new Intl.DateTimeFormat('en-GB', {
    day: options.day ?? '2-digit',
    month: options.month ?? 'short',
    year: options.year ?? undefined,
  }).format(parsedDate)
}

export function formatDayLabel(value) {
  if (!value) {
    return 'DAY'
  }

  const parsedDate = new Date(value)
  if (Number.isNaN(parsedDate.getTime())) {
    return 'DAY'
  }

  return new Intl.DateTimeFormat('en-US', {
    weekday: 'short',
  })
    .format(parsedDate)
    .toUpperCase()
}

export function formatGoalLabel(goal) {
  if (goal === 'perder_grasa') {
    return 'Shred / Cut'
  }
  if (goal === 'mantener_peso') {
    return 'Maintenance'
  }
  if (goal === 'ganar_masa') {
    return 'Hypertrophy / Bulk'
  }
  return 'Profile setup'
}

export function formatGoalPhase(goal) {
  if (goal === 'perder_grasa') {
    return 'PHASE: RECOMPOSITION'
  }
  if (goal === 'ganar_masa') {
    return 'PHASE: GROWTH'
  }
  if (goal === 'mantener_peso') {
    return 'PHASE: MAINTENANCE'
  }
  return 'PHASE: PROFILE SETUP'
}

export function formatGoalDescription(goal) {
  if (goal === 'perder_grasa') {
    return 'Energy deficit calibrated for body-fat reduction.'
  }
  if (goal === 'ganar_masa') {
    return 'Surplus-focused setup for muscle gain.'
  }
  if (goal === 'mantener_peso') {
    return 'Stable intake to preserve current body composition.'
  }
  return 'Complete the nutrition profile to calibrate targets.'
}

export function formatSexLabel(value) {
  if (value === 'Masculino') {
    return 'Male'
  }
  if (value === 'Femenino') {
    return 'Female'
  }
  return 'Unspecified'
}

export function formatTrainingFrequency(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 'Unspecified'
  }

  if (numericValue === 0) {
    return 'Rest dominant'
  }
  if (numericValue === 1) {
    return '1 day / week'
  }

  return `${numericValue} days / week`
}

export function formatAdherenceLevel(level) {
  if (level === 'alta') {
    return 'Optimal'
  }
  if (level === 'media') {
    return 'Moderate'
  }
  if (level === 'baja') {
    return 'Low'
  }
  return 'Pending'
}

export function formatDataSource(source) {
  if (source === 'spoonacular') {
    return 'Spoonacular'
  }
  if (source === 'cache') {
    return 'Cache'
  }
  if (source === 'mixed') {
    return 'Hybrid'
  }
  return 'Internal'
}

export function getMealVisual(mealNumber) {
  const visual = STITCH_DIET_VISUALS[(Number(mealNumber) - 1) % STITCH_DIET_VISUALS.length]
  return visual ?? {
    phase: `Phase ${String(mealNumber).padStart(2, '0')}`,
    label: `Meal ${mealNumber}`,
    imageUrl: '',
  }
}

export function getInitials(name) {
  return String(name || 'Fibrito')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase()
}

export function clampPercentage(value, fallback = 0) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return fallback
  }

  return Math.min(100, Math.max(0, numericValue))
}

export function toConfidenceScore(value) {
  const numericValue = toFiniteNumber(value)
  if (numericValue === null) {
    return 0
  }

  if (numericValue <= 1) {
    return clampPercentage(numericValue * 100)
  }

  return clampPercentage(numericValue)
}
