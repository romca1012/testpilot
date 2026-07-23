// Création d'un module, PARTAGÉE (sans Pinia), sur le patron de `useProjects`.
//
// Pourquoi partagée : plusieurs endroits déclenchent la même action — le « + Ajouter une section »
// de la barre latérale (CasesShell), le bouton d'en-tête et l'état vide de la liste des cas
// (TestCasesList). Une seule MODALE (rendue par CasesShell, toujours présent) évite d'en dupliquer
// trois qui ne partageraient pas leur état. `createdAt` s'incrémente après un succès : les pages
// qui affichent des modules l'observent pour se rafraîchir, sans couplage direct entre composants.
import { ref } from 'vue'

const open = ref(false)
const pid = ref('')
const createdAt = ref(0)  // « horloge » de création : bumpée à chaque module créé

export function useModuleCreate() {
  function openFor(projectId: string | number) {
    pid.value = String(projectId)
    open.value = true
  }
  function close() { open.value = false }
  function markCreated() { createdAt.value++ }
  return { open, pid, createdAt, openFor, close, markCreated }
}
