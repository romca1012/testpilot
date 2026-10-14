<script setup lang="ts">
// « Données de test » d'un projet, pour ses MEMBRES (lot PT-02a, décision A32 du porteur, 2026-10-13).
//
// Le tableau des données de test se modifie comme les tests (testeurs et plus, A30), mais la page « Paramètres de test »
// vit dans l'administration, fermée à qui n'administre pas l'installation. Cette page montre donc le MÊME tableau dans le
// projet. Aucune entrée n'est ajoutée au menu du projet : on y arrive par un lien, là où l'on en a besoin (création d'une
// exécution, fiche d'un test).
import { computed, ref, watchEffect } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { useParametresDeTest } from '../lib/parametresDeTest'
import { useProjects } from '../lib/useProjects'
import { useSession } from '../lib/useSession'
import { roleSuffisant } from '../lib/api'
import TableauDonneesDeTest from '../components/parametres/TableauDonneesDeTest.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
const { session } = useSession()
const { projectById, ensureLoaded } = useProjects()
const { actifs, connu } = useParametresDeTest()
const pid = computed(() => String(route.params.pid || ''))
// La page n'existe que si l'installation a allumé les paramètres de test : éteinte, son adresse ramène au projet.
watchEffect(() => { if (connu?.value && !actifs.value) router.replace(`/projects/${pid.value}`) })
ensureLoaded()

const projet = computed(() => projectById(pid.value) || null)
// Le serveur tranche (403) ; l'écran ne propose pas un geste qu'il refuserait.
const role = computed(() => projet.value?.effective_role || session.value?.role || '')
const peutModifier = computed(() => roleSuffisant(role.value, 'testeur'))
const peutSupprimer = computed(() => role.value === 'admin')

// Ne rien perdre par mégarde : on confirme avant de quitter un tableau modifié et non enregistré.
const modifie = ref(false)
const destination = ref<string | null>(null)
onBeforeRouteLeave((to) => {
  if (!modifie.value) return true
  destination.value = to.fullPath
  return false
})
function quitter() {
  const vers = destination.value
  modifie.value = false
  destination.value = null
  if (vers) router.push(vers)
}
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-6 sm:px-6">
    <h1 class="text-2xl font-semibold tracking-tight">Données de test</h1>
    <div v-if="projet" class="mt-5">
      <TableauDonneesDeTest :projet="projet" :peut-modifier="peutModifier" :peut-supprimer="peutSupprimer" @modifie="modifie = $event" />
    </div>
    <ConfirmDialog :open="destination !== null" title="Quitter sans enregistrer ?"
                   message="Les modifications du tableau ne sont pas enregistrées."
                   confirm-label="Quitter" @confirm="quitter" @cancel="destination = null" />
  </div>
</template>
