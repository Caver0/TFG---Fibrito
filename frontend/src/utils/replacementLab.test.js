import test from 'node:test'
import assert from 'node:assert/strict'

import {
  getReplacementOptionsForDisplay,
  inferDominantMacroFromFood,
  mergeReplacementOptions,
  resolveCurrentMacroDominante,
} from './replacementLab.js'

test('inferDominantMacroFromFood clasifica frutos secos mixtos como grasa', () => {
  assert.equal(
    inferDominantMacroFromFood({
      name: 'Frutos secos',
      category: 'grasas',
      protein_grams: 20,
      fat_grams: 54,
      carb_grams: 21,
    }),
    'fat',
  )
})

test('resolveCurrentMacroDominante usa el valor del backend o un fallback local estable', () => {
  assert.equal(resolveCurrentMacroDominante({ name: 'Platano', category: 'frutas', carb_grams: 27 }, 'carb'), 'carb')
  assert.equal(
    resolveCurrentMacroDominante({
      name: 'Yogur griego',
      category: 'lacteos',
      protein_grams: 12,
      fat_grams: 0.5,
      carb_grams: 6,
    }),
    'protein',
  )
})

test('mergeReplacementOptions y getReplacementOptionsForDisplay mantienen la lista renderizable', () => {
  const automaticOption = { food_code: 'banana', name: 'Banana' }
  const manualOption = { food_code: 'cornflakes', name: 'Cornflakes' }
  const duplicateOption = { food_code: 'banana', name: 'Banana duplicada' }

  assert.deepEqual(
    mergeReplacementOptions([manualOption], [automaticOption, duplicateOption]).map((option) => option.food_code),
    ['cornflakes', 'banana'],
  )

  assert.deepEqual(
    getReplacementOptionsForDisplay({
      manualOptions: [manualOption],
      options: [automaticOption, duplicateOption],
    }).map((option) => option.food_code),
    ['cornflakes', 'banana'],
  )
})
