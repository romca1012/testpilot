<script setup lang="ts">
// SHELL UNIQUE : « Cas de test » (disposition TestRail). L'ancien AppShell est retiré (décision
// du porteur 2026-07-20) — sa nav « Gestion des cas / Exécution » est remplacée par la nav TestRail
// (Cas de test / Exécutions et résultats de test / …). La page projets (hors contexte projet) reste
// hors shell : on ne peut pas afficher une barre latérale de projet quand aucun n'est sélectionné.
import { computed, onMounted, ref, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import CasesShell from './components/CasesShell.vue'
import InstanceAdminShell from './components/InstanceAdminShell.vue'
import SimpleShell from './components/SimpleShell.vue'
import LoginScreen from './pages/LoginScreen.vue'
import ForcedPasswordChangeScreen from './pages/ForcedPasswordChangeScreen.vue'
import PaletteCommandes from './components/PaletteCommandes.vue'
import ThemeSwitch from './components/ThemeSwitch.vue'
import { setPasswordChangeRequiredHandler, setUnauthorizedHandler } from './lib/api'
import { ROUTES_SANS_SHELL } from './lib/shell'
import { useSession } from './lib/useSession'
import { useSettings } from './lib/useSettings'

const route = useRoute()
const router = useRouter()
// Routes SANS contexte projet : pas de shell projet. La liste vit dans `lib/shell.ts`, où un
// test la compare aux routes déclarées — en oublier une rend la page entièrement blanche.
const NO_SHELL = ROUTES_SANS_SHELL
const useShell = computed(() => !NO_SHELL.includes(String(route.name)))
const useInstanceAdmin = computed(() =>
  ['admin-projects', 'settings', 'settings-general', 'settings-security', 'utilisateurs', 'utilisateur-detail', 'role-detail'].includes(String(route.name)))

// ⚠️ UN SEUL <RouterView>, enveloppé conditionnellement — jamais deux en parallèle.
// Deux <RouterView> frères (un dans le shell, un hors) se disputaient la même vue pendant une
// transition shell↔hors-shell (ex. …/cases → /projects → …/cases via « Gérer les projets ») :
// le DOM de l'ancienne page restait empilé et CasesShell rendait des liens avec `pid` indéfini
// → « Missing required param "pid" » puis « emitsOptions null », qui corrompait l'interface.
// `<component :is>` déplace la MÊME vue entre le shell et un simple conteneur : plus de doublon.
const layout = computed(() => (useInstanceAdmin.value
  ? InstanceAdminShell
  : useShell.value ? CasesShell : SimpleShell))

// ── Connexion obligatoire — comptes utilisateurs (2026-08-07) ─────────────────
// Trois états, et pas deux : tant que la session n'est pas connue, on n'affiche NI l'application
// NI l'écran de connexion. Afficher l'application « en attendant » la ferait clignoter puis
// disparaître ; afficher le formulaire ferait ressaisir un mot de passe à qui était déjà connecté.
const { session, charger: chargerSession } = useSession()
const { ensureLoaded: chargerReglages, get: getReglage } = useSettings()
const sessionConnue = ref(false)
const doitSeConnecter = ref(false)
// Appropriation obligatoire du mot de passe (audit 2026-09-07) : compte tout juste créé par un
// Admin, ou réinitialisé par lui. Distinct de `doitSeConnecter` — la session EST valide, mais le
// serveur refuse déjà tout le reste (`password_change_required`, voir `api.ts`).
const doitChangerMotDePasse = ref(false)

async function verifierSession() {
  await chargerSession()
  doitSeConnecter.value = !session.value?.authenticated
  doitChangerMotDePasse.value = !!session.value?.must_change_password
  if (session.value?.authenticated && !doitChangerMotDePasse.value) await chargerReglages()
  sessionConnue.value = true
}

onMounted(() => {
  setUnauthorizedHandler(() => { doitSeConnecter.value = true })
  // Peut arriver sur N'IMPORTE QUEL appel après la connexion, pas seulement au login — un Admin
  // a pu réinitialiser ce mot de passe pendant que la session était déjà ouverte ailleurs.
  setPasswordChangeRequiredHandler(() => { doitChangerMotDePasse.value = true })
  verifierSession()
})

async function apresConnexion() {
  doitSeConnecter.value = false
  doitChangerMotDePasse.value = !!session.value?.must_change_password
  if (!doitChangerMotDePasse.value) await chargerReglages(true)
  await router.replace('/projects')
}

async function apresChangementObligatoire() {
  doitChangerMotDePasse.value = false
  await chargerReglages(true)
}

watchEffect(() => {
  document.title = getReglage('instance_name') || 'TestPilot'
  const adminRoutes = ['admin-projects', 'settings', 'settings-general', 'settings-security', 'utilisateurs', 'utilisateur-detail', 'role-detail']
  if (sessionConnue.value && session.value?.authenticated && session.value.role !== 'admin'
      && adminRoutes.includes(String(route.name))) router.replace('/projects')
})
</script>

<template>
  <!-- Sur la connexion il n'existe encore aucun shell. Une fois connecté, chaque shell réserve
       sa propre place au sélecteur pour qu'il ne masque jamais une action de page. -->
  <ThemeSwitch v-if="!sessionConnue || doitSeConnecter || doitChangerMotDePasse"
               class="fixed right-4 top-4 z-40 md:right-6 md:top-5" />
  <LoginScreen v-if="sessionConnue && doitSeConnecter" @connected="apresConnexion" />
  <ForcedPasswordChangeScreen v-else-if="sessionConnue && doitChangerMotDePasse"
                              @changed="apresChangementObligatoire" />
  <template v-else-if="sessionConnue">
    <component :is="layout">
      <RouterView />
    </component>
    <!-- Montée au niveau de l'application : la palette doit répondre à Ctrl+K depuis N'IMPORTE
         quel écran. La poser dans le shell la rendrait muette sur les pages hors shell. -->
    <PaletteCommandes />
  </template>
</template>
