<script setup lang="ts">
// Étape 7b (A109) : la personne joue le cas une fois dans le vrai navigateur. Ses actions deviennent les actions du test
// technique (traduites sans IA) ou, pour un cas manuel, son mode opératoire. Ni vidéo ni image gardée ; jamais un mot de
// passe. La vérification n'est qu'un élément désigné : le résultat attendu vient du cas, jamais de l'écran.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ActionParcours } from '../lib/api'
import { useParcours } from '../lib/useParcours'
import Button from '../components/ui/Button.vue'
import Card from '../components/ui/Card.vue'
import Spinner from '../components/ui/Spinner.vue'
import Icon from '../components/ui/Icon.vue'

const route = useRoute()
const router = useRouter()
const pid = route.params.pid as string
const caseId = route.params.id as string

const {
  statut, image, actions, champ, connexionAuto, captureCommencee, avertissement, erreur, avertissementInactivite,
  raisonFermeture, demarrer, clic, verifier, saisir, choisir, retirer, commencer, enregistrer, annuler,
} = useParcours(caseId)

// Le prochain clic sur l'écran : une action, ou « c'est ici que je vérifie » (une fois, puis retour aux actions).
const modeVerifier = ref(false)
const valeur = ref('')

const ecran = ref<HTMLImageElement | null>(null)
let dimensions = { largeur: 0, hauteur: 0 }
function surChargementImage() {
  const el = ecran.value
  if (el && el.naturalWidth) dimensions = { largeur: el.naturalWidth, hauteur: el.naturalHeight }
}

// Même mise à l'échelle que `LiveSession.vue` : l'image affichée peut être plus petite que la page réelle.
function surClic(evt: MouseEvent) {
  const el = ecran.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const largeur = el.naturalWidth || dimensions.largeur
  const hauteur = el.naturalHeight || dimensions.hauteur
  if (!largeur || !hauteur || !rect.width || !rect.height) return
  const x = (evt.clientX - rect.left) * (largeur / rect.width)
  const y = (evt.clientY - rect.top) * (hauteur / rect.height)
  if (modeVerifier.value) {
    verifier(x, y)
    modeVerifier.value = false
  } else {
    clic(x, y)
  }
}

function envoyerValeur() {
  if (!champ.value) return
  saisir(valeur.value)
  valeur.value = ''
}

// Même tableau que `parametres/parcours.py::LIBELLES_DES_ROLES` — jamais un rôle brut à l'écran (§4.7).
const ROLES: Record<string, string> = {
  button: 'bouton', link: 'lien', tab: 'onglet', textbox: 'champ', searchbox: 'champ de recherche',
  spinbutton: 'champ numérique', combobox: 'liste', listbox: 'liste', option: 'option', checkbox: 'case à cocher',
  radio: 'bouton radio', switch: 'interrupteur', slider: 'curseur', menuitem: 'menu', menuitemcheckbox: 'menu',
  menuitemradio: 'menu', summary: 'bloc dépliant', element: 'élément',
}

// Même lecture que `parametres/parcours.py::lire` (le mode opératoire enregistré vient du serveur).
function lire(a: ActionParcours): string {
  const nom = a.nom || a.champ || '?'
  const role = ROLES[a.role] || 'élément'
  if (a.action === 'clic') return `Cliquer sur « ${nom} » (${role})`
  if (a.action === 'choix' || (a.action === 'saisie' && a.relation)) return `Choisir « ${a.valeur} » dans « ${nom} »`
  if (a.action === 'saisie') return `Saisir « ${a.valeur} » dans « ${nom} »`
  return `Vérifier le résultat attendu sur « ${nom} » (${role})`
}

const aUneVerification = computed(() => actions.value.some((a) => a.action === 'verifier'))

const FERMETURES: Record<string, string> = {
  inactivite: 'Aucune action depuis un moment : le navigateur s\'est refermé.',
  plafond_absolu: 'Durée maximale atteinte : le navigateur s\'est refermé.',
  connexion_interrompue: 'La connexion avec le serveur a été interrompue.',
  annulee: 'Annulé — rien n\'a été enregistré.',
}

const retourAuCas = () => router.push(`/projects/${pid}/cases/${caseId}`)

onMounted(demarrer)
</script>

<template>
  <div class="space-y-6">
    <RouterLink :to="`/projects/${pid}/cases/${caseId}`"
                class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <Icon name="chevron" class="h-3.5 w-3.5 rotate-180" /> Retour au cas
    </RouterLink>

    <div>
      <h1 class="text-2xl font-semibold tracking-tight">Enregistrer le parcours</h1>
      <p class="mt-1 max-w-2xl text-sm text-subtle-foreground">
        Jouez le cas une fois, comme d'habitude. Puis cliquez « C'est ici que je vérifie » et montrez où le résultat
        se lit. Aucune image n'est gardée, jamais un mot de passe.
      </p>
    </div>

    <div class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <Card :dense="true" class="overflow-hidden">
        <div v-if="connexionAuto === false && !captureCommencee" class="mb-3 flex items-center justify-between gap-3 text-xs text-warning"
             data-testid="connexion-auto-ko">
          <span>Connexion automatique impossible : connectez-vous ici. Rien n'est enregistré pendant ce temps.</span>
          <Button size="sm" variant="secondary" :disabled="statut !== 'en_direct'" @click="commencer">Je suis connecté</Button>
        </div>

        <div v-if="statut === 'connexion'"
             class="flex aspect-video items-center justify-center rounded-lg border border-dashed border-border bg-surface-raised">
          <div class="flex items-center gap-2 text-sm text-muted-foreground">
            <Spinner class="h-4 w-4" /> Ouverture du navigateur et connexion…
          </div>
        </div>

        <div v-else-if="statut === 'erreur'"
             class="flex aspect-video items-center justify-center rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
          <p class="text-sm text-destructive">{{ erreur }}</p>
        </div>

        <div v-else-if="statut === 'fermee'"
             class="flex aspect-video flex-col items-center justify-center gap-3 rounded-lg border border-border bg-surface-raised p-6 text-center">
          <p class="text-sm text-muted-foreground">{{ FERMETURES[raisonFermeture] || raisonFermeture }}</p>
          <div class="flex gap-2">
            <Button size="sm" @click="demarrer">Recommencer</Button>
            <Button size="sm" variant="ghost" @click="retourAuCas">Retour au cas</Button>
          </div>
        </div>

        <div v-else-if="statut === 'enregistre'"
             class="flex aspect-video flex-col items-center justify-center gap-3 rounded-lg border border-success/30 bg-success/5 p-6 text-center"
             data-testid="parcours-enregistre">
          <Icon name="check" class="h-6 w-6 text-success" />
          <p class="text-sm text-foreground">Parcours enregistré ({{ actions.length }} actions).</p>
          <Button size="sm" @click="retourAuCas">Retour au cas</Button>
        </div>

        <button v-else type="button"
                class="relative block w-full overflow-hidden rounded-lg border bg-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                :class="modeVerifier ? 'cursor-crosshair border-primary ring-2 ring-primary' : 'cursor-default border-border'"
                aria-label="Écran du navigateur — cliquez pour agir" @click="surClic">
          <img ref="ecran" :src="`data:image/jpeg;base64,${image}`" alt="Écran du navigateur"
               class="block w-full select-none" draggable="false" @load="surChargementImage" />
        </button>
      </Card>

      <Card title="Parcours" :dense="true" class="flex flex-col">
        <Button variant="secondary" size="sm" :disabled="statut !== 'en_direct'" data-testid="je-verifie"
                :class="modeVerifier ? 'ring-2 ring-primary' : ''" @click="modeVerifier = !modeVerifier">
          {{ modeVerifier ? 'Cliquez sur l\'élément à vérifier…' : 'C\'est ici que je vérifie' }}
        </Button>

        <!-- Le champ désigné : la valeur à saisir, ou le choix dans la liste. -->
        <div v-if="champ" class="mt-3 rounded-lg border border-border bg-surface-raised p-3" data-testid="champ-designe">
          <p class="text-xs font-medium text-foreground">{{ champ.nom }}</p>
          <div v-if="champ.options.length" class="mt-2 flex flex-wrap gap-1">
            <Button v-for="o in champ.options" :key="o" size="sm" variant="ghost" @click="choisir(o)">{{ o }}</Button>
          </div>
          <form v-else class="mt-2 flex gap-2" @submit.prevent="envoyerValeur">
            <input v-model="valeur" :type="champ.secret ? 'password' : 'text'" autocomplete="off"
                   class="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm"
                   :aria-label="`Valeur de ${champ.nom}`" />
            <Button size="sm" type="submit">Saisir</Button>
          </form>
          <p v-if="champ.secret" class="mt-1 text-xs text-subtle-foreground">Mot de passe : saisi, mais jamais enregistré.</p>
        </div>

        <p v-if="!actions.length" class="mt-3 text-xs text-subtle-foreground">
          Aucune action encore — cliquez sur l'écran.
        </p>
        <ol v-else class="mt-3 space-y-1.5" data-testid="actions">
          <li v-for="(a, i) in actions" :key="i" class="flex items-start gap-2 text-xs">
            <span class="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
              {{ i + 1 }}
            </span>
            <span class="flex-1 text-foreground">{{ lire(a) }}</span>
            <button type="button" class="text-muted-foreground hover:text-destructive" :aria-label="`Retirer l'action ${i + 1}`"
                    @click="retirer(i)">
              <Icon name="x" class="h-3.5 w-3.5" />
            </button>
          </li>
        </ol>

        <p v-if="avertissement" class="mt-3 text-xs text-warning">{{ avertissement }}</p>
        <p v-if="erreur && statut === 'en_direct'" class="mt-3 text-xs text-destructive">{{ erreur }}</p>
        <p v-if="avertissementInactivite !== null" class="mt-3 text-xs text-warning">
          Sans action, fermeture dans {{ avertissementInactivite }} s.
        </p>
        <p v-if="actions.length && !aUneVerification" class="mt-3 text-xs text-subtle-foreground">
          Montrez aussi où vous vérifiez le résultat (« C'est ici que je vérifie »).
        </p>

        <div class="mt-auto flex flex-col gap-2 pt-4">
          <Button variant="success" :disabled="statut !== 'en_direct' || !actions.length" @click="enregistrer">
            Enregistrer ({{ actions.length }})
          </Button>
          <Button variant="ghost" size="sm" :disabled="statut !== 'en_direct'" @click="annuler">Annuler</Button>
        </div>
      </Card>
    </div>
  </div>
</template>
