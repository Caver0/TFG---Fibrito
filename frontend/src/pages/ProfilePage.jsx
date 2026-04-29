import { useEffect, useRef, useState } from 'react'
import SectionPanel from '../components/SectionPanel'
import { useAuth } from '../context/AuthContext'
import * as userApi from '../api/userApi'
import {
  STITCH_PROFILE_TARGET_BACKGROUND,
  formatCalories,
  formatGoalDescription,
  formatGoalLabel,
  formatSexLabel,
  formatTrainingFrequency,
} from '../utils/stitch'

const AUTOSAVE_DELAY_MS = 700
const PROTOCOL_OPTIONS = [
  { value: 'vegetariano', label: 'Vegetariano', icon: 'nutrition' },
  { value: 'vegano', label: 'Vegano', icon: 'eco' },
  { value: 'sin_lactosa', label: 'Sin lactosa', icon: 'water_drop' },
  { value: 'sin_gluten', label: 'Sin gluten', icon: 'grain' },
]

function buildProfileForm(user) {
  return {
    age: user?.age ?? '',
    sex: user?.sex ?? '',
    height: user?.height ?? '',
    current_weight: user?.current_weight ?? '',
    training_days_per_week: user?.training_days_per_week ?? '',
    goal: user?.goal ?? 'mantener_peso',
  }
}

function buildPreferenceInputs() {
  return {
    preferred_foods: '',
    disliked_foods: '',
    allergies: '',
  }
}

function normalizePreferenceList(values) {
  return [...new Set((values ?? []).map((value) => String(value).trim()).filter(Boolean))]
}

function normalizeFoodPreferences(preferences) {
  return {
    preferred_foods: normalizePreferenceList(preferences?.preferred_foods),
    disliked_foods: normalizePreferenceList(preferences?.disliked_foods),
    dietary_restrictions: normalizePreferenceList(preferences?.dietary_restrictions),
    allergies: normalizePreferenceList(preferences?.allergies),
  }
}

function buildProfilePayload(profileForm) {
  return {
    age: profileForm.age ? Number(profileForm.age) : null,
    sex: profileForm.sex || null,
    height: profileForm.height ? Number(profileForm.height) : null,
    current_weight: profileForm.current_weight ? Number(profileForm.current_weight) : null,
    training_days_per_week: profileForm.training_days_per_week === '' ? null : Number(profileForm.training_days_per_week),
    goal: profileForm.goal || null,
  }
}

function buildProfileSignature(profileForm) {
  return JSON.stringify(buildProfilePayload(profileForm))
}

function buildFoodPreferencesSignature(preferences) {
  return JSON.stringify(normalizeFoodPreferences(preferences))
}

function resolveAutosaveMessage(saveState) {
  if (saveState.status === 'saving') return 'Guardando...'
  if (saveState.status === 'saved') return 'Guardado ✓'
  if (saveState.status === 'error') return 'Error al guardar'
  return 'Autosave activo'
}

function mergeAutosaveStates(saveStates) {
  if (saveStates.some((state) => state.status === 'saving')) {
    return { status: 'saving' }
  }
  if (saveStates.some((state) => state.status === 'error')) {
    return { status: 'error' }
  }
  if (saveStates.some((state) => state.status === 'saved')) {
    return { status: 'saved' }
  }
  return { status: 'idle' }
}

function AutosaveIndicator({ label, saveState }) {
  return (
    <div className={`autosave-indicator autosave-indicator-${saveState.status}`.trim()}>
      <small>{label}</small>
      <strong>{resolveAutosaveMessage(saveState)}</strong>
    </div>
  )
}

function ProfilePage() {
  const { refreshUser, replaceUser, token, user } = useAuth()
  const [profileForm, setProfileForm] = useState(buildProfileForm(user))
  const [foodPreferences, setFoodPreferences] = useState(normalizeFoodPreferences(user?.food_preferences))
  const [preferenceInputs, setPreferenceInputs] = useState(buildPreferenceInputs)
  const [nutrition, setNutrition] = useState(null)
  const [nutritionError, setNutritionError] = useState('')
  const [foodPreferencesLoadError, setFoodPreferencesLoadError] = useState('')
  const [profileSaveError, setProfileSaveError] = useState('')
  const [preferencesSaveError, setPreferencesSaveError] = useState('')
  const [isNutritionLoading, setIsNutritionLoading] = useState(false)
  const [isFoodPreferencesLoading, setIsFoodPreferencesLoading] = useState(false)
  const [profileSaveState, setProfileSaveState] = useState({ status: 'idle' })
  const [preferencesSaveState, setPreferencesSaveState] = useState({ status: 'idle' })

  const profileSignature = buildProfileSignature(profileForm)
  const preferencesSignature = buildFoodPreferencesSignature(foodPreferences)
  const combinedAutosaveState = mergeAutosaveStates([profileSaveState, preferencesSaveState])
  const pageError = nutritionError || foodPreferencesLoadError || profileSaveError || preferencesSaveError

  const lastSavedProfileSignatureRef = useRef(profileSignature)
  const latestProfileSignatureRef = useRef(profileSignature)
  const profileSaveCycleRef = useRef(0)
  const lastSavedPreferencesSignatureRef = useRef(preferencesSignature)
  const latestPreferencesSignatureRef = useRef(preferencesSignature)
  const preferencesSaveCycleRef = useRef(0)
  const arePreferencesReadyRef = useRef(false)

  async function loadNutritionSummary(activeToken = token) {
    if (!activeToken) return
    setIsNutritionLoading(true)
    setNutritionError('')
    try {
      const summary = await userApi.getNutritionSummary(activeToken)
      setNutrition(summary)
    } catch (error) {
      setNutrition(null)
      setNutritionError(error.message)
    } finally {
      setIsNutritionLoading(false)
    }
  }

  async function loadFoodPreferences(activeToken = token) {
    if (!activeToken) return
    setIsFoodPreferencesLoading(true)
    setFoodPreferencesLoadError('')
    try {
      const preferences = normalizeFoodPreferences(await userApi.getFoodPreferences(activeToken))
      const signature = buildFoodPreferencesSignature(preferences)
      arePreferencesReadyRef.current = true
      lastSavedPreferencesSignatureRef.current = signature
      latestPreferencesSignatureRef.current = signature
      setFoodPreferences(preferences)
      setPreferencesSaveState({ status: 'idle' })
      setPreferencesSaveError('')
    } catch (error) {
      const emptyPreferences = normalizeFoodPreferences(null)
      const signature = buildFoodPreferencesSignature(emptyPreferences)
      arePreferencesReadyRef.current = true
      lastSavedPreferencesSignatureRef.current = signature
      latestPreferencesSignatureRef.current = signature
      setFoodPreferences(emptyPreferences)
      setFoodPreferencesLoadError(error.message)
    } finally {
      setIsFoodPreferencesLoading(false)
    }
  }

  useEffect(() => {
    const nextForm = buildProfileForm(user)
    const nextSignature = buildProfileSignature(nextForm)
    setProfileForm(nextForm)
    lastSavedProfileSignatureRef.current = nextSignature
    latestProfileSignatureRef.current = nextSignature
  }, [user])

  useEffect(() => {
    if (!token) return
    loadNutritionSummary(token)
  }, [token, user?.age, user?.sex, user?.height, user?.current_weight, user?.training_days_per_week, user?.goal, user?.target_calories])

  useEffect(() => {
    if (!token) return
    loadFoodPreferences(token)
  }, [token])

  useEffect(() => {
    latestProfileSignatureRef.current = profileSignature
  }, [profileSignature])

  useEffect(() => {
    latestPreferencesSignatureRef.current = preferencesSignature
  }, [preferencesSignature])

  useEffect(() => {
    if (!token || !user?.id) return undefined
    if (profileSignature === lastSavedProfileSignatureRef.current) return undefined

    const cycle = profileSaveCycleRef.current + 1
    profileSaveCycleRef.current = cycle

    const timeoutId = window.setTimeout(async () => {
      setProfileSaveState({ status: 'saving' })
      setProfileSaveError('')

      try {
        const updatedUser = await userApi.updateNutritionProfile(token, buildProfilePayload(profileForm))
        if (
          profileSaveCycleRef.current !== cycle
          || latestProfileSignatureRef.current !== profileSignature
        ) {
          return
        }

        lastSavedProfileSignatureRef.current = profileSignature
        replaceUser(updatedUser)
        await loadNutritionSummary(token)
        window.dispatchEvent(new CustomEvent('dashboard:refresh'))
        setProfileSaveState({ status: 'saved' })
      } catch (error) {
        if (profileSaveCycleRef.current !== cycle) return
        setProfileSaveError(error.message)
        setProfileSaveState({ status: 'error' })
      }
    }, AUTOSAVE_DELAY_MS)

    return () => window.clearTimeout(timeoutId)
  }, [profileForm, profileSignature, replaceUser, token, user?.id])

  useEffect(() => {
    if (!token || !arePreferencesReadyRef.current) return undefined
    if (preferencesSignature === lastSavedPreferencesSignatureRef.current) return undefined

    const cycle = preferencesSaveCycleRef.current + 1
    preferencesSaveCycleRef.current = cycle

    const timeoutId = window.setTimeout(async () => {
      setPreferencesSaveState({ status: 'saving' })
      setPreferencesSaveError('')
      setFoodPreferencesLoadError('')

      try {
        await userApi.updateFoodPreferences(token, normalizeFoodPreferences(foodPreferences))
        if (
          preferencesSaveCycleRef.current !== cycle
          || latestPreferencesSignatureRef.current !== preferencesSignature
        ) {
          return
        }

        lastSavedPreferencesSignatureRef.current = preferencesSignature
        await refreshUser(token)
        setPreferencesSaveState({ status: 'saved' })
      } catch (error) {
        if (preferencesSaveCycleRef.current !== cycle) return
        setPreferencesSaveError(error.message)
        setPreferencesSaveState({ status: 'error' })
      }
    }, AUTOSAVE_DELAY_MS)

    return () => window.clearTimeout(timeoutId)
  }, [foodPreferences, preferencesSignature, refreshUser, token])

  function handleProfileChange(event) {
    const { name, value } = event.target
    setProfileForm((current) => ({ ...current, [name]: value }))
  }

  function toggleDietaryRestriction(value) {
    setFoodPreferences((current) => {
      const currentRestrictions = current.dietary_restrictions ?? []
      const exists = currentRestrictions.includes(value)
      return normalizeFoodPreferences({
        ...current,
        dietary_restrictions: exists
          ? currentRestrictions.filter((entry) => entry !== value)
          : [...currentRestrictions, value],
      })
    })
  }

  function handlePreferenceInputChange(event) {
    const { name, value } = event.target
    setPreferenceInputs((current) => ({ ...current, [name]: value }))
  }

  function addPreferenceItem(key) {
    const normalizedValue = preferenceInputs[key].trim()
    if (!normalizedValue) return

    setFoodPreferences((current) => normalizeFoodPreferences({
      ...current,
      [key]: [...(current[key] ?? []), normalizedValue],
    }))
    setPreferenceInputs((current) => ({ ...current, [key]: '' }))
  }

  function removePreferenceItem(key, value) {
    setFoodPreferences((current) => normalizeFoodPreferences({
      ...current,
      [key]: (current[key] ?? []).filter((entry) => entry !== value),
    }))
  }

  return (
    <div className="profile-page">
      {pageError ? <p className="page-status page-status-error">{pageError}</p> : null}

      <div className="profile-top-layout">
        <SectionPanel
          eyebrow="Datos personales"
          title="Perfil y metricas"
          className="profile-biometric-panel"
          actions={<AutosaveIndicator label="Perfil" saveState={profileSaveState} />}
        >
          <div className="profile-biometric-grid">
            <label><span>Peso (kg)</span><input name="current_weight" type="number" step="0.1" value={profileForm.current_weight} onChange={handleProfileChange} /></label>
            <label><span>Altura (cm)</span><input name="height" type="number" step="0.1" value={profileForm.height} onChange={handleProfileChange} /></label>
            <label><span>Edad</span><input name="age" type="number" min="0" value={profileForm.age} onChange={handleProfileChange} /></label>
            <label><span>Dias de entreno</span><input name="training_days_per_week" type="number" min="0" max="7" value={profileForm.training_days_per_week} onChange={handleProfileChange} /></label>
            <div className="profile-biometric-summary-card"><small>Nivel de actividad</small><strong>{formatTrainingFrequency(profileForm.training_days_per_week)}</strong></div>
            <div className="profile-sex-toggle">
              <span>Sexo</span>
              <div>
                {['Masculino', 'Femenino'].map((sex) => (
                  <button key={sex} type="button" className={profileForm.sex === sex ? 'profile-toggle-active' : ''} onClick={() => setProfileForm((current) => ({ ...current, sex }))}>
                    {formatSexLabel(sex)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="profile-calibration-strip">
            <div><small>Calorias objetivo</small><strong>{isNutritionLoading ? 'Cargando...' : formatCalories(nutrition?.target_calories)}</strong></div>
            <div><small>Proteina</small><strong>{nutrition?.protein_grams ? `${nutrition.protein_grams}g` : 'N/A'}</strong></div>
            <div><small>Carbohidratos</small><strong>{nutrition?.carb_grams ? `${nutrition.carb_grams}g` : 'N/A'}</strong></div>
            <div><small>Grasas</small><strong>{nutrition?.fat_grams ? `${nutrition.fat_grams}g` : 'N/A'}</strong></div>
          </div>
        </SectionPanel>

        <SectionPanel eyebrow="Objetivo" className="profile-goal-panel">
          <div className="profile-goal-background"><img src={STITCH_PROFILE_TARGET_BACKGROUND} alt="" /></div>
          <div className="profile-goal-stack">
            {[
              { value: 'mantener_peso', label: 'Mantenimiento' },
              { value: 'perder_grasa', label: 'Definicion / Perdida' },
              { value: 'ganar_masa', label: 'Hipertrofia / Volumen' },
            ].map((goalOption) => (
              <button
                key={goalOption.value}
                type="button"
                className={`profile-goal-option ${profileForm.goal === goalOption.value ? 'profile-goal-option-active' : ''}`.trim()}
                onClick={() => setProfileForm((current) => ({ ...current, goal: goalOption.value }))}
              >
                <span>{goalOption.label}</span>
              </button>
            ))}
          </div>
          <p>{formatGoalDescription(profileForm.goal)}</p>
        </SectionPanel>
      </div>

      <div className="profile-bottom-layout">
        <SectionPanel
          title="Restricciones dieteticas"
          className="profile-restrictions-panel"
          actions={<AutosaveIndicator label="Preferencias" saveState={preferencesSaveState} />}
        >
          <div className="profile-protocol-list profile-protocol-grid">
            {PROTOCOL_OPTIONS.map((option) => {
              const isActive = foodPreferences.dietary_restrictions.includes(option.value)
              return (
                <button key={option.value} type="button" className={`profile-protocol-row ${isActive ? 'profile-protocol-row-active' : ''}`.trim()} onClick={() => toggleDietaryRestriction(option.value)}>
                  <div className="profile-protocol-copy">
                    <div>
                      <i className="material-symbols-outlined" aria-hidden="true">{option.icon}</i>
                      <span>{option.label}</span>
                    </div>
                    <small>{isActive ? 'Activo' : 'Inactivo'}</small>
                  </div>
                  <span className={`profile-visual-switch ${isActive ? 'profile-visual-switch-active' : ''}`.trim()} aria-hidden="true">
                    <span className="profile-visual-switch-thumb" />
                  </span>
                </button>
              )
            })}
          </div>
        </SectionPanel>

        <SectionPanel
          eyebrow="Preferencias"
          title="Alimentos y alergias"
          actions={<AutosaveIndicator label="Listado" saveState={preferencesSaveState} />}
        >
          <div className="profile-chip-group">
            <small>Alimentos no deseados</small>
            <div className="profile-chip-list">
              {foodPreferences.disliked_foods.map((item) => (
                <button key={item} type="button" className="profile-chip" onClick={() => removePreferenceItem('disliked_foods', item)}>{item}<span>x</span></button>
              ))}
            </div>
            <div className="profile-chip-input"><input name="disliked_foods" value={preferenceInputs.disliked_foods} onChange={handlePreferenceInputChange} placeholder="Anadir alimento" /><button type="button" onClick={() => addPreferenceItem('disliked_foods')}>Anadir</button></div>
          </div>

          <div className="profile-chip-group">
            <small>Alergias</small>
            <div className="profile-chip-list">
              {foodPreferences.allergies.map((item) => (
                <button key={item} type="button" className="profile-chip profile-chip-danger" onClick={() => removePreferenceItem('allergies', item)}>{item}<span>x</span></button>
              ))}
            </div>
            <div className="profile-chip-input"><input name="allergies" value={preferenceInputs.allergies} onChange={handlePreferenceInputChange} placeholder="Anadir alergia" /><button type="button" onClick={() => addPreferenceItem('allergies')}>Anadir</button></div>
          </div>

          <div className="profile-chip-group">
            <small>Alimentos preferidos</small>
            <div className="profile-chip-list">
              {foodPreferences.preferred_foods.map((item) => (
                <button key={item} type="button" className="profile-chip profile-chip-positive" onClick={() => removePreferenceItem('preferred_foods', item)}>{item}<span>x</span></button>
              ))}
            </div>
            <div className="profile-chip-input"><input name="preferred_foods" value={preferenceInputs.preferred_foods} onChange={handlePreferenceInputChange} placeholder="Anadir preferencia" /><button type="button" onClick={() => addPreferenceItem('preferred_foods')}>Anadir</button></div>
          </div>

          <div className="profile-engine-note">
            <strong>Autosave nutricional</strong>
            <p>Las preferencias se aplican automaticamente a la generacion de dieta, sustituciones y filtros de compatibilidad.</p>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel className="profile-footer-bar">
        <div>
          <strong>{formatGoalLabel(profileForm.goal)}</strong>
          <span>{nutrition?.target_calories ? `Objetivo actual ${formatCalories(nutrition.target_calories)}` : 'Completa el perfil para calcular objetivos caloricos.'}</span>
        </div>
        <AutosaveIndicator label="Sincronizacion" saveState={combinedAutosaveState} />
      </SectionPanel>
    </div>
  )
}

export default ProfilePage
