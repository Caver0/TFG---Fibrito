import { useEffect, useState } from 'react'
import FoodPreferencesForm from '../components/FoodPreferencesForm'
import ProfileForm from '../components/ProfileForm'
import NutritionSummary from '../components/NutritionSummary'
import { useAuth } from '../context/AuthContext'
import * as userApi from '../api/userApi'

function ProfilePage() {
  const { refreshUser, replaceUser, token, user } = useAuth()
  const [foodPreferences, setFoodPreferences] = useState(user?.food_preferences ?? null)
  const [foodPreferencesError, setFoodPreferencesError] = useState('')
  const [foodPreferencesMessage, setFoodPreferencesMessage] = useState('')
  const [isFoodPreferencesLoading, setIsFoodPreferencesLoading] = useState(false)
  const [isFoodPreferencesSaving, setIsFoodPreferencesSaving] = useState(false)
  const [nutrition, setNutrition] = useState(null)
  const [nutritionError, setNutritionError] = useState('')
  const [isNutritionLoading, setIsNutritionLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState('')
  const [saveError, setSaveError] = useState('')

  async function loadNutritionSummary(activeToken = token) {
    if (!activeToken) {
      return
    }

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
    if (!activeToken) {
      return
    }

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
    if (!token) {
      return
    }

    loadNutritionSummary(token)
    loadFoodPreferences(token)
  }, [
    token,
    user?.age,
    user?.sex,
    user?.height,
    user?.current_weight,
    user?.training_days_per_week,
    user?.goal,
    user?.target_calories,
  ])

  useEffect(() => {
    setFoodPreferences(user?.food_preferences ?? null)
  }, [user?.food_preferences])

  async function handleSave(profilePayload) {
    if (!token) {
      return
    }

    setIsSaving(true)
    setSaveMessage('')
    setSaveError('')

    try {
      const updatedUser = await userApi.updateNutritionProfile(token, profilePayload)
      replaceUser(updatedUser)
      await loadNutritionSummary(token)
      setSaveMessage('Perfil nutricional actualizado correctamente.')
    } catch (error) {
      setSaveError(error.message)
    } finally {
      setIsSaving(false)
    }
  }

  async function handleSaveFoodPreferences(preferencesPayload) {
    if (!token) {
      return
    }

    setIsFoodPreferencesSaving(true)
    setFoodPreferencesError('')
    setFoodPreferencesMessage('')

    try {
      const updatedPreferences = await userApi.updateFoodPreferences(token, preferencesPayload)
      setFoodPreferences(updatedPreferences)
      await refreshUser(token)
      setFoodPreferencesMessage('Preferencias alimentarias actualizadas correctamente.')
    } catch (error) {
      setFoodPreferencesError(error.message)
    } finally {
      setIsFoodPreferencesSaving(false)
    }
  }

  return (
    <div className="profile-page">
      <div className="progress-page">
        <ProfileForm
          user={user}
          isSaving={isSaving}
          saveMessage={saveMessage}
          saveError={saveError}
          onSave={handleSave}
        />
        <FoodPreferencesForm
          preferences={foodPreferences}
          isLoading={isFoodPreferencesLoading}
          isSaving={isFoodPreferencesSaving}
          saveMessage={foodPreferencesMessage}
          saveError={foodPreferencesError}
          onSave={handleSaveFoodPreferences}
        />
      </div>
      <NutritionSummary
        nutrition={nutrition}
        error={nutritionError}
        isLoading={isNutritionLoading}
      />
    </div>
  )
}

export default ProfilePage
