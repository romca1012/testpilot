<script setup lang="ts">
// Écran de la session en direct (lot « Enregistrement assisté du chemin de connexion »,
// sous-lots B/C/D) : montre l'écran d'un vrai navigateur distant qui pilote l'application du
// projet, laisse cliquer à travers pour franchir un écran de pré-connexion (sélection de pays…),
// puis confirme la séquence — rejouée AUTOMATIQUEMENT à chaque exploration ou run réel ensuite,
// jusqu'à ce que l'application change (échec explicite, jamais un repli silencieux).
//
// Aucune génération, aucune exécution ici : cet écran ne fait qu'ENREGISTRER un chemin de clics.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ProjectSummary } from '../lib/api'
import { useLiveSession } from '../lib/useLiveSession'
import Button from '../components/ui/Button.vue'
import Card from '../components/ui/Card.vue'
import Spinner from '../components/ui/Spinner.vue'
import Chip from '../components/ui/Chip.vue'
import Icon from '../components/ui/Icon.vue'

const route = useRoute()
const router = useRouter()
const pid = route.params.pid as string

const projet = ref<ProjectSummary | null>(null)
const chargement = ref(true)

const {
  statut, image, etapes, erreur, avertissementInactivite, raisonFermeture,
  dernierClicAmbigu, captureArretee, demarrer, clic, confirmer, recommencer, annuler,
} = useLiveSession(pid)

const ecran = ref<HTMLImageElement | null>(null)

// Mise à l'échelle affiché → réel (limite du sous-lot C, jamais traitée avant ce frontend, voir
// son rapport de fin de sous-lot) : le flux transmet la taille RÉELLE du viewport distant
// (`naturalWidth`/`naturalHeight`), mais l'image peut être affichée plus petite pour tenir dans
// l'écran (`getBoundingClientRect`). Sans cette conversion, un clic sur un écran affiché en
// 800×450 pour un viewport réel de 1280×720 atterrirait à 0,625× de sa vraie position — un clic
// qui semble réussir mais capture le MAUVAIS élément (exactement le résultat trompeur que ce
// chantier cherche à exclure).
function surClic(evt: MouseEvent) {
  const el = ecran.value
  if (!el || !el.naturalWidth) return
  const rect = el.getBoundingClientRect()
  const echelleX = el.naturalWidth / rect.width
  const echelleY = el.naturalHeight / rect.height
  const x = (evt.clientX - rect.left) * echelleX
  const y = (evt.clientY - rect.top) * echelleY
  clic(x, y)
}

const RAISONS_FERMETURE: Record<string, string> = {
  inactivite: 'Aucun clic reçu depuis un moment — la session s\'est refermée pour ne pas laisser un navigateur ouvert inutilement.',
  plafond_absolu: 'Cette session a atteint sa durée maximale et s\'est refermée automatiquement.',
  connexion_interrompue: 'La connexion avec le serveur a été interrompue.',
  annulee: 'Session annulée — rien n\'a été enregistré.',
}

const messageFermeture = computed(() =>
  RAISONS_FERMETURE[raisonFermeture.value] || raisonFermeture.value)

async function retourAuProjet() {
  await router.push(`/projects/${pid}/exploration`)
}

onMounted(async () => {
  try {
    const projets = await api.listProjects()
    projet.value = projets.find((p) => String(p.id) === pid) || null
  } catch { /* le nom du projet est un confort d'affichage, jamais bloquant */ }
  chargement.value = false
  await demarrer()
})
</script>

<template>
  <div class="space-y-6">
    <RouterLink :to="`/projects/${pid}/exploration`"
                class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <Icon name="chevron" class="h-3.5 w-3.5 rotate-180" /> Cartographie explorée
    </RouterLink>

    <div>
      <h1 class="text-2xl font-semibold tracking-tight">
        Enregistrer le chemin de connexion{{ projet ? ' — ' + projet.name : '' }}
      </h1>
      <p class="mt-1 max-w-2xl text-sm text-subtle-foreground">
        Montrez, une seule fois, comment franchir un écran de pré-connexion (sélection de pays,
        bandeau de consentement…) — cliquez ci-dessous exactement comme vous le feriez, puis
        confirmez. Ce chemin sera rejoué automatiquement à chaque exploration ou exécution
        ultérieure sur ce projet, jusqu'à ce que l'application change.
      </p>
    </div>

    <div v-if="chargement" class="flex items-center gap-2 text-muted-foreground text-sm">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>

    <template v-else>
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <!-- ── Écran distant ────────────────────────────────────────────────────────────── -->
        <Card :dense="true" class="overflow-hidden">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div class="flex items-center gap-2 text-sm font-medium">
              <span class="relative flex h-2.5 w-2.5">
                <span v-if="statut === 'en_direct'"
                      class="absolute inline-flex h-full w-full animate-ping rounded-full bg-destructive/60" />
                <span class="relative inline-flex h-2.5 w-2.5 rounded-full"
                      :class="statut === 'en_direct' ? 'bg-destructive' : 'bg-muted-foreground/40'" />
              </span>
              {{ statut === 'en_direct' ? 'En direct' : statut === 'connexion' ? 'Connexion…' : 'Session terminée' }}
            </div>
            <span v-if="captureArretee" class="text-xs text-warning">
              Capture arrêtée — un champ mot de passe est visible
            </span>
          </div>

          <div v-if="statut === 'connexion'"
               class="flex aspect-video items-center justify-center rounded-lg border border-dashed border-border bg-surface-raised">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <Spinner class="h-4 w-4" /> Ouverture du navigateur distant…
            </div>
          </div>

          <div v-else-if="statut === 'erreur'"
               class="flex aspect-video flex-col items-center justify-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center">
            <Icon name="x" class="h-6 w-6 text-destructive" />
            <p class="text-sm text-destructive">{{ erreur }}</p>
          </div>

          <div v-else-if="statut === 'fermee'"
               class="flex aspect-video flex-col items-center justify-center gap-3 rounded-lg border border-border bg-surface-raised p-6 text-center">
            <p class="text-sm text-muted-foreground">{{ messageFermeture }}</p>
            <div class="flex gap-2">
              <Button size="sm" @click="demarrer">Recommencer une session</Button>
              <Button size="sm" variant="ghost" @click="retourAuProjet">Revenir au projet</Button>
            </div>
          </div>

          <div v-else-if="statut === 'confirmee'"
               class="flex aspect-video flex-col items-center justify-center gap-3 rounded-lg border border-success/30 bg-success/5 p-6 text-center">
            <Icon name="check" class="h-6 w-6 text-success" />
            <p class="text-sm text-foreground">
              Chemin de connexion enregistré ({{ etapes.length }}
              étape{{ etapes.length > 1 ? 's' : '' }}) — il sera rejoué automatiquement désormais.
            </p>
            <Button size="sm" @click="retourAuProjet">Revenir au projet</Button>
          </div>

          <button v-else type="button"
                  class="block w-full cursor-crosshair overflow-hidden rounded-lg border border-border bg-overlay focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="Écran du navigateur distant — cliquez pour reproduire votre geste"
                  @click="surClic">
            <img ref="ecran" :src="`data:image/jpeg;base64,${image}`" alt="Écran du navigateur distant"
                 class="block w-full select-none" draggable="false" />
          </button>
        </Card>

        <!-- ── Chemin capturé ───────────────────────────────────────────────────────────── -->
        <Card title="Chemin capturé" :dense="true" class="flex flex-col">
          <p v-if="!etapes.length" class="text-xs text-subtle-foreground">
            Aucune étape encore — cliquez sur l'écran ci-contre comme vous le feriez normalement.
          </p>
          <ol v-else class="space-y-1.5">
            <li v-for="(e, i) in etapes" :key="i" class="flex items-center gap-2">
              <span class="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
                {{ i + 1 }}
              </span>
              <Chip icon="dot" :label="e.name || `(sans nom, ${e.role})`"
                    cls="border-border bg-surface-raised text-foreground" />
            </li>
          </ol>

          <p v-if="dernierClicAmbigu" class="mt-3 text-xs text-warning">
            Ce clic touche plusieurs éléments identiques — il n'a pas été ajouté. Cliquez sur un
            élément qui se distingue seul.
          </p>
          <p v-if="erreur && statut === 'en_direct'" class="mt-3 text-xs text-destructive">{{ erreur }}</p>
          <p v-if="avertissementInactivite !== null" class="mt-3 text-xs text-warning">
            Session inactive — fermeture dans {{ avertissementInactivite }} s sans nouveau clic.
          </p>

          <div class="mt-auto flex flex-col gap-2 pt-4">
            <Button variant="success" :disabled="statut !== 'en_direct'" @click="confirmer">
              Confirmer ({{ etapes.length }})
            </Button>
            <Button variant="secondary" size="sm" :disabled="statut !== 'en_direct' || !etapes.length"
                    @click="recommencer">
              Recommencer
            </Button>
            <Button variant="ghost" size="sm" :disabled="statut !== 'en_direct'" @click="annuler">
              Annuler
            </Button>
          </div>
        </Card>
      </div>
    </template>
  </div>
</template>
