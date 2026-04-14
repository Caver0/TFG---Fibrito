import { useEffect, useState } from 'react'
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

const PROTOCOL_OPTIONS = [
  { value: 'vegetariano', label: 'Vegetarian', icon: 'nutrition' },
  { value: 'vegano', label: 'Vegan protocol', icon: 'eco' },
  { value: 'sin_lactosa', label: 'Lactose-Free', icon: 'water_drop' },
  { value: 'sin_gluten', label: 'Gluten-Free', icon: 'grain' },
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

function ProfilePage() {
  const { refreshUser, replaceUser, token, user } = useAuth()
  const [profileForm, setProfileForm] = useState(buildProfileForm(user))
  const [foodPreferences, setFoodPreferences] = useState(user?.food_preferences ?? null)
  const [preferenceInputs, setPreferenceInputs] = useState(buildPreferenceInputs)
  const [nutrition, setNutrition] = useState(null)
  const [nutritionError, setNutritionError] = useState('')
  const [foodPreferencesError, setFoodPreferencesError] = useState('')
  const [foodPreferencesMessage, setFoodPreferencesMessage] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [saveError, setSaveError] = useState('')
  const [isNutritionLoading, setIsNutritionLoading] = useState(false)
  const [isFoodPreferencesLoading, setIsFoodPreferencesLoading] = useState(false)
  const [isFoodPreferencesSaving, setIsFoodPreferencesSaving] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

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
    setFoodPreferencesError('')
    try {
      const preferences = await userApi.getFoodPreferences(activeToken)
      setFoodPreferences(preferences)
    } catch (error) {
      setFoodPreferences(null)
      setFoodPreferencesError(error.message)
    } finally {
      setIsFoodPreferencesLoading(false)
    }
  }

  useEffect(() => {
    setProfileForm(buildProfileForm(user))
  }, [user])

  useEffect(() => {
    if (!token) return
    loadNutritionSummary(token)
    loadFoodPreferences(token)
  }, [token, user?.age, user?.sex, user?.height, user?.current_weight, user?.training_days_per_week, user?.goal, user?.target_calories])

  function handleProfileChange(event) {
    const { name, value } = event.target
    setProfileForm((current) => ({ ...current, [name]: value }))
  }

  function toggleDietaryRestriction(value) {
    setFoodPreferences((current) => {
      const currentRestrictions = current?.dietary_restrictions ?? []
      const exists = currentRestrictions.includes(value)
      return {
        ...(current ?? {}),
        preferred_foods: current?.preferred_foods ?? [],
        disliked_foods: current?.disliked_foods ?? [],
        allergies: current?.allergies ?? [],
        dietary_restrictions: exists
          ? currentRestrictions.filter((entry) => entry !== value)
          : [...currentRestrictions, value],
      }
    })
  }

  function handlePreferenceInputChange(event) {
    const { name, value } = event.target
    setPreferenceInputs((current) => ({ ...current, [name]: value }))
  }

  function addPreferenceItem(key) {
    const rawValue = preferenceInputs[key]
    const normalizedValue = rawValue.trim()
    if (!normalizedValue) return
    setFoodPreferences((current) => ({
      ...(current ?? {}),
      preferred_foods: current?.preferred_foods ?? [],
      disliked_foods: current?.disliked_foods ?? [],
      dietary_restrictions: current?.dietary_restrictions ?? [],
      allergies: current?.allergies ?? [],
      [key]: [...new Set([...(current?.[key] ?? []), normalizedValue])],
    }))
    setPreferenceInputs((current) => ({ ...current, [key]: '' }))
  }

  function removePreferenceItem(key, value) {
    setFoodPreferences((current) => ({
      ...(current ?? {}),
      preferred_foods: current?.preferred_foods ?? [],
      disliked_foods: current?.disliked_foods ?? [],
      dietary_restrictions: current?.dietary_restrictions ?? [],
      allergies: current?.allergies ?? [],
      [key]: (current?.[key] ?? []).filter((entry) => entry !== value),
    }))
  }

  async function handleSaveProfile() {
    if (!token) return
    setIsSaving(true)
    setSaveMessage('')
    setSaveError('')
    try {
      const updatedUser = await userApi.updateNutritionProfile(token, {
        age: profileForm.age ? Number(profileForm.age) : null,
        sex: profileForm.sex || null,
        height: profileForm.height ? Number(profileForm.height) : null,
        current_weight: profileForm.current_weight ? Number(profileForm.current_weight) : null,
        training_days_per_week: profileForm.training_days_per_week === '' ? null : Number(profileForm.training_days_per_week),
        goal: profileForm.goal || null,
      })
      replaceUser(updatedUser)
      await loadNutritionSummary(token)
      window.dispatchEvent(new CustomEvent('dashboard:refresh'))
      setSaveMessage('Biometric profile updated correctly.')
    } catch (error) {
      setSaveError(error.message)
    } finally {
      setIsSaving(false)
    }
  }

  async function handleSavePreferences() {
    if (!token || !foodPreferences) return
    setIsFoodPreferencesSaving(true)
    setFoodPreferencesError('')
    setFoodPreferencesMessage('')
    try {
      await userApi.updateFoodPreferences(token, foodPreferences)
      await refreshUser(token)
      setFoodPreferencesMessage('Food preferences updated correctly.')
    } catch (error) {
      setFoodPreferencesError(error.message)
    } finally {
      setIsFoodPreferencesSaving(false)
    }
  }

  return (
    <div className="profile-page">
      {(nutritionError || foodPreferencesError || saveError) ? <p className="page-status page-status-error">{nutritionError || foodPreferencesError || saveError}</p> : null}

      <div className="profile-top-layout">
        <SectionPanel eyebrow="Biometric Lab Data" title="Technical precision metrics" className="profile-biometric-panel">
          <div className="profile-biometric-grid">
            <label><span>Weight (kg)</span><input name="current_weight" type="number" step="0.1" value={profileForm.current_weight} onChange={handleProfileChange} /></label>
            <label><span>Height (cm)</span><input name="height" type="number" step="0.1" value={profileForm.height} onChange={handleProfileChange} /></label>
            <label><span>Age</span><input name="age" type="number" min="0" value={profileForm.age} onChange={handleProfileChange} /></label>
            <label><span>Training days</span><input name="training_days_per_week" type="number" min="0" max="7" value={profileForm.training_days_per_week} onChange={handleProfileChange} /></label>
            <div className="profile-biometric-summary-card"><small>Activity level</small><strong>{formatTrainingFrequency(profileForm.training_days_per_week)}</strong></div>
            <div className="profile-sex-toggle">
              <span>Biological sex</span>
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
            <div><small>Target calories</small><strong>{isNutritionLoading ? 'Loading...' : formatCalories(nutrition?.target_calories)}</strong></div>
            <div><small>Protein</small><strong>{nutrition?.protein_grams ? `${nutrition.protein_grams}g` : 'N/A'}</strong></div>
            <div><small>Carbs</small><strong>{nutrition?.carb_grams ? `${nutrition.carb_grams}g` : 'N/A'}</strong></div>
            <div><small>Fats</small><strong>{nutrition?.fat_grams ? `${nutrition.fat_grams}g` : 'N/A'}</strong></div>
          </div>
        </SectionPanel>

        <SectionPanel eyebrow="Performance Target" className="profile-goal-panel">
          <div className="profile-goal-background"><img src={STITCH_PROFILE_TARGET_BACKGROUND} alt="" /></div>
          <div className="profile-goal-stack">
            {[
              { value: 'mantener_peso', label: 'Maintenance' },
              { value: 'perder_grasa', label: 'Shred / Cut' },
              { value: 'ganar_masa', label: 'Hypertrophy / Bulk' },
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
        <SectionPanel title="Dietary Protocols">
          <div className="profile-protocol-list">
            {PROTOCOL_OPTIONS.map((option) => {
              const isActive = (foodPreferences?.dietary_restrictions ?? []).includes(option.value)
              return (
                <button key={option.value} type="button" className={`profile-protocol-row ${isActive ? 'profile-protocol-row-active' : ''}`.trim()} onClick={() => toggleDietaryRestriction(option.value)}>
                  <div><i className="material-symbols-outlined" aria-hidden="true">{option.icon}</i><span>{option.label}</span></div>
                  <i className="material-symbols-outlined" aria-hidden="true">{isActive ? 'toggle_on' : 'toggle_off'}</i>
                </button>
              )
            })}
          </div>
        </SectionPanel>

        <SectionPanel eyebrow="Refined Restriction Engine" title="Excluded compounds" actions={<button type="button" className="protocol-secondary-button" onClick={handleSavePreferences} disabled={isFoodPreferencesSaving || isFoodPreferencesLoading}>{isFoodPreferencesSaving ? 'Saving...' : 'Save Preferences'}</button>}>
          <div className="profile-chip-group">
            <small>Disliked foods</small>
            <div className="profile-chip-list">
              {(foodPreferences?.disliked_foods ?? []).map((item) => (
                <button key={item} type="button" className="profile-chip" onClick={() => removePreferenceItem('disliked_foods', item)}>{item}<span>x</span></button>
              ))}
            </div>
            <div className="profile-chip-input"><input name="disliked_foods" value={preferenceInputs.disliked_foods} onChange={handlePreferenceInputChange} placeholder="Add exclusion" /><button type="button" onClick={() => addPreferenceItem('disliked_foods')}>Add</button></div>
          </div>

          <div className="profile-chip-group">
            <small>Allergies</small>
            <div className="profile-chip-list">
              {(foodPreferences?.allergies ?? []).map((item) => (
                <button key={item} type="button" className="profile-chip profile-chip-danger" onClick={() => removePreferenceItem('allergies', item)}>{item}<span>x</span></button>
              ))}
            </div>
            <div className="profile-chip-input"><input name="allergies" value={preferenceInputs.allergies} onChange={handlePreferenceInputChange} placeholder="Add allergy" /><button type="button" onClick={() => addPreferenceItem('allergies')}>Add</button></div>
          </div>

          <div className="profile-chip-group">
            <small>Preferred foods</small>
            <div className="profile-chip-list">
              {(foodPreferences?.preferred_foods ?? []).map((item) => (
                <button key={item} type="button" className="profile-chip profile-chip-positive" onClick={() => removePreferenceItem('preferred_foods', item)}>{item}<span>x</span></button>
              ))}
            </div>
            <div className="profile-chip-input"><input name="preferred_foods" value={preferenceInputs.preferred_foods} onChange={handlePreferenceInputChange} placeholder="Add preference" /><button type="button" onClick={() => addPreferenceItem('preferred_foods')}>Add</button></div>
          </div>

          <div className="profile-engine-note">
            <strong>Engine note</strong>
            <p>{foodPreferencesMessage || 'Preferences are applied to diet generation, replacement options and compatibility filtering.'}</p>
          </div>
        </SectionPanel>
      </div>

      <SectionPanel className="profile-footer-bar">
        <div>
          <strong>{formatGoalLabel(profileForm.goal)}</strong>
          <span>{nutrition?.target_calories ? `Current target ${formatCalories(nutrition.target_calories)}` : 'Complete the profile to compute calorie targets.'}</span>
        </div>
        <button type="button" className="panel-cta-button" onClick={handleSaveProfile} disabled={isSaving}>{isSaving ? 'Saving profile...' : 'Commit To Profile'}</button>
      </SectionPanel>

      {saveMessage ? <p className="page-status page-status-success">{saveMessage}</p> : null}
      {foodPreferencesMessage && !saveMessage ? <p className="page-status page-status-success">{foodPreferencesMessage}</p> : null}
    </div>
  )
}

export default ProfilePage
