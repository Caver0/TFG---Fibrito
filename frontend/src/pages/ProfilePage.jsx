import { useEffect, useState } from 'react'
import ProfileForm from '../components/ProfileForm'
import NutritionSummary from '../components/NutritionSummary'
import { useAuth } from '../context/AuthContext'
import * as userApi from '../api/userApi'

function ProfilePage() {
  const { replaceUser, token, user } = useAuth()
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

  useEffect(() => {
    if (!token) {
      return
    }

    loadNutritionSummary(token)
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

  return (
    <div className="profile-page">
      <ProfileForm
        user={user}
        isSaving={isSaving}
        saveMessage={saveMessage}
        saveError={saveError}
        onSave={handleSave}
      />
      <NutritionSummary
        nutrition={nutrition}
        error={nutritionError}
        isLoading={isNutritionLoading}
      />
    </div>
  )
}

export default ProfilePage
