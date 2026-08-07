// Création d'une Section ou d'une Sous-section, PARTAGÉE (sans Pinia), sur le patron de
// `useModuleCreate.ts`.
//
// Pourquoi partagée : c'est la liste des cas (TestCasesList) qui déclenche ce geste — inline,
// sous chaque module/Section, comme TestRail le place — mais c'est CasesShell (toujours présent)
// qui rend la modale unique. `parentGroupId` distingue les deux cas : `null` = Section de premier
// niveau, un id = Sous-section de cette Section (migration 28, une seule profondeur).
import { ref } from 'vue'

const open = ref(false)
const moduleId = ref<number | null>(null)
const parentGroupId = ref<number | null>(null)
const createdAt = ref(0)  // « horloge » de création : bumpée à chaque section créée

export function useSectionCreate() {
  function openFor(mid: number, parentId: number | null = null) {
    moduleId.value = mid
    parentGroupId.value = parentId
    open.value = true
  }
  function close() {
    open.value = false
    moduleId.value = null
    parentGroupId.value = null
  }
  function markCreated() { createdAt.value++ }
  return { open, moduleId, parentGroupId, createdAt, openFor, close, markCreated }
}
