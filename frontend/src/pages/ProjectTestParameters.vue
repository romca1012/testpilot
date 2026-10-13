<script setup lang="ts">
// LES PARAMÈTRES DE TEST D'UN PROJET (lot PT-01a, 2026-10-13) — ce qu'on règle pour jouer ses tests : le navigateur, les
// comptes, l'état de départ. Ces réglages vivaient au bas de la longue fenêtre « Identité et application » ; ils se lisent et
// s'enregistrent ICI par les MÊMES routes du serveur, sur les MÊMES données : rien n'est copié, rien n'est à ressaisir
// (décisions A16 et A17 du dossier de cadrage).
//
// Une PAGE et non une fenêtre : chaque onglet a sa propre adresse (un lien ouvre le bon onglet, le retour arrière ramène
// d'où l'on vient), et l'écran reste sobre — libellés, valeurs, boutons, aucune phrase d'explication (décision A15).
import { computed, onMounted, ref, watch, watchEffect } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { api, type ProjectSummary } from '../lib/api'
import { useSession } from '../lib/useSession'
import { useParametresDeTest } from '../lib/parametresDeTest'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import OngletConfigurations from '../components/parametres/OngletConfigurations.vue'
import OngletComptes from '../components/parametres/OngletComptes.vue'
import OngletEtatDeDepart from '../components/parametres/OngletEtatDeDepart.vue'
import OngletValeursAttendues from '../components/parametres/OngletValeursAttendues.vue'

const ONGLETS = [
  { cle: 'configurations', libelle: 'Configurations' },
  { cle: 'comptes', libelle: 'Comptes' },
  { cle: 'etat-de-depart', libelle: 'État de départ' },
  { cle: 'valeurs-attendues', libelle: 'Valeurs attendues' },
] as const
type CleOnglet = typeof ONGLETS[number]['cle']

const route = useRoute()
const router = useRouter()
const { session } = useSession()
// La page n'existe que si l'installation a allumé la nouvelle organisation : éteinte, son adresse ramène aux projets
// (revue du 2026-10-13 : seul le bouton était derrière l'interrupteur, pas la page).
const { actifs, connu } = useParametresDeTest()
watchEffect(() => { if (connu?.value && !actifs.value) router.replace('/admin/projects') })

const projet = ref<ProjectSummary | null>(null)
const chargement = ref(true)
const erreur = ref('')
const pid = computed(() => String(route.params.pid || ''))
const onglet = computed<CleOnglet>(() => {
  const demande = String(route.params.onglet || '')
  return (ONGLETS.find((o) => o.cle === demande)?.cle || 'configurations') as CleOnglet
})
// Le serveur tranche (403) ; l'écran ne propose pas un geste qu'il refuserait. Le rôle sur CE projet prime sur le rôle global.
const role = computed(() => projet.value?.effective_role || session.value?.role || '')
const peutRegler = computed(() => role.value === 'admin')
const peutGererComptes = computed(() => ['admin', 'dev'].includes(role.value))

async function charger() {
  chargement.value = true
  erreur.value = ''
  try {
    const projets = await (session.value?.role === 'admin' ? api.listAdminProjects() : api.listProjects())
    projet.value = projets.find((p) => String(p.id) === pid.value) || null
    if (!projet.value) erreur.value = 'Projet introuvable.'
  } catch (e: any) {
    erreur.value = e?.message || 'Chargement impossible.'
  } finally {
    chargement.value = false
  }
}

// ── Ne rien perdre par mégarde : on confirme avant de quitter un onglet modifié et non enregistré ──────────────────────
const modifie = ref(false)
const destination = ref<RouteLocationRaw | null>(null)
let sortieConfirmee = false

function garder(to: RouteLocationRaw) {
  if (!modifie.value || sortieConfirmee) { sortieConfirmee = false; return true }
  destination.value = to
  return false
}
onBeforeRouteLeave((to) => garder(to.fullPath))
onBeforeRouteUpdate((to) => garder(to.fullPath))

function quitterSansEnregistrer() {
  const cible = destination.value
  destination.value = null
  modifie.value = false
  sortieConfirmee = true
  if (cible) router.push(cible)
}

watch(onglet, () => { modifie.value = false })
onMounted(charger)
</script>

<template>
  <div class="mx-auto max-w-5xl px-4 py-6 sm:px-6 md:py-8">
    <nav aria-label="Fil d'Ariane" class="text-sm text-muted-foreground">
      <RouterLink to="/admin/projects" class="hover:text-foreground">Projets</RouterLink>
      <span aria-hidden="true"> › </span>
      <span class="font-medium text-foreground" data-testid="nom-du-projet">{{ projet?.name || '…' }}</span>
    </nav>
    <h1 class="mt-1 text-2xl font-semibold tracking-tight">Paramètres de test</h1>

    <p v-if="erreur" role="alert" class="mt-5 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{{ erreur }}</p>
    <p v-if="chargement" class="mt-6 text-sm text-muted-foreground" aria-live="polite">Chargement…</p>

    <template v-if="projet">
      <div role="tablist" aria-label="Paramètres de test" class="mt-5 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-border">
        <RouterLink v-for="o in ONGLETS" :key="o.cle" role="tab"
                    :to="{ name: 'project-test-params', params: { pid, onglet: o.cle } }"
                    :id="`onglet-${o.cle}`" :aria-selected="onglet === o.cle" :data-testid="`onglet-${o.cle}`"
                    class="-mb-px inline-flex min-h-11 shrink-0 items-center border-b-2 px-3 text-sm font-medium"
                    :class="onglet === o.cle ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'">
          {{ o.libelle }}
        </RouterLink>
      </div>

      <div role="tabpanel" :aria-labelledby="`onglet-${onglet}`" class="mt-5">
        <OngletConfigurations v-if="onglet === 'configurations'" :projet="projet" :peut-regler="peutRegler"
                              @enregistre="projet = $event" @modifie="modifie = $event" />
        <OngletComptes v-else-if="onglet === 'comptes'" :projet="projet" :peut-gerer="peutGererComptes" :peut-regler="peutRegler"
                       @enregistre="projet = $event" />
        <OngletEtatDeDepart v-else-if="onglet === 'etat-de-depart'" :projet="projet" :peut-regler="peutRegler"
                            @enregistre="projet = $event" @modifie="modifie = $event" />
        <OngletValeursAttendues v-else :projet="projet" :peut-regler="peutRegler"
                                @enregistre="projet = $event" @modifie="modifie = $event" />
      </div>
    </template>

    <ConfirmDialog :open="destination !== null" title="Quitter sans enregistrer ?"
                   message="Les modifications de cet onglet ne sont pas enregistrées."
                   confirm-label="Quitter" @confirm="quitterSansEnregistrer" @cancel="destination = null" />
  </div>
</template>
