<script setup lang="ts">
// **UN CAS DANS UNE CAMPAGNE** — l'écran qui manquait entièrement (2026-08-05).
//
// ⚠️ **La pièce absente, et pourquoi elle compte.** Cliquer un cas dans une campagne menait
// jusqu'ici soit au rapport technique d'UNE exécution, soit à la fiche du cas dans le
// référentiel — deux écrans qui répondent à d'autres questions. Or le statut, les résultats et
// les commentaires n'appartiennent ni à l'un ni à l'autre : ils appartiennent au COUPLE
// campagne × cas. Sans cet écran, la question « où en est ce cas, ICI ? » n'avait pas d'adresse.
//
// ⚠️ **Deux identités, jamais confondues.** `T{campagne}-{cas}` désigne le test dans cette
// campagne ; `C{cas}` désigne le cas du référentiel. Le bouton « Voir le cas » est la passerelle
// explicite entre les deux — c'est la distinction que TestRail rend par `T7516` / `C7516`, et
// sans laquelle on croit modifier un résultat en modifiant un cas.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, roleSuffisant, type TestDansRun } from '../lib/api'
import { useProjects } from '../lib/useProjects'
import { useSession } from '../lib/useSession'
import { etatView, libelleActeur, priorityView, statutAffiche, testStatusMeta, typeView } from '../lib/status'
import { cleMois, formatDate, moisLong } from '../lib/format'
import ResultHistory from '../components/ResultHistory.vue'
import ResultMode from '../components/ResultMode.vue'
import CourbeResultats from '../components/CourbeResultats.vue'
import AddResultDialog from '../components/AddResultDialog.vue'
import RefsList from '../components/RefsList.vue'
import Button from '../components/ui/Button.vue'
import IconButton from '../components/ui/IconButton.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const runId = computed(() => Number(route.params.id))
const caseId = computed(() => Number(route.params.caseId))
const { session } = useSession()
const { projectById } = useProjects()
const roleProjet = computed(() => projectById(pid.value)?.effective_role || session.value?.role || '')
const peutModifier = computed(() => roleSuffisant(roleProjet.value, 'testeur'))
const peutSupprimer = computed(() => roleSuffisant(roleProjet.value, 'admin'))

const test = ref<TestDansRun | null>(null)
const loading = ref(true)
const error = ref('')
const onglet = ref<'resultats' | 'historique' | 'defauts'>('resultats')

// ⚠️ « Ce cas dans cette campagne » ne porte pas `statuts_manuels` — cette liste n'a de sens que
// pour une campagne MANUELLE, et cet écran sert aussi les campagnes automatiques. On va la
// chercher là où `RunDetail.vue` la lit déjà (`getRun`), jamais retapée ici : c'est le même
// principe que les statuts eux-mêmes dans `AddResultDialog`, appliqué à la source de la donnée.
const statutsManuels = ref<string[]>([])

async function load() {
  loading.value = true; error.value = ''
  try {
    test.value = await api.getTestDansRun(runId.value, caseId.value)
    if (test.value.run_mode === 'manuelle') {
      // Best-effort : son échec ne doit pas empêcher de LIRE le test, seulement d'y saisir.
      try { statutsManuels.value = (await api.getRun(runId.value)).statuts_manuels }
      catch { statutsManuels.value = [] }
    }
  }
  catch { error.value = 'Impossible de charger ce test.' }
  finally { loading.value = false }
}
load()
// Les flèches précédent/suivant changent `caseId` SANS démonter la page : sans ce watch, on
// verrait le test précédent avec le titre du suivant.
watch(caseId, load)

const statut = computed(() => statutAffiche(test.value?.statut || 'untested', test.value?.a_confirmer))

// ── Navigation DANS LA CAMPAGNE ───────────────────────────────────────────────
// ⚠️ Les voisins viennent du SERVEUR, bornés à la campagne. Enchaîner les tests d'une session de
// recette n'a rien à voir avec parcourir un module : si les flèches sortaient de la campagne, on
// se retrouverait à noter un cas qui n'y figure pas.
function allerAuTest(id: number | null) {
  if (!id) return
  router.push({ name: 'run-test',
                params: { pid: pid.value, id: String(runId.value), caseId: String(id) } })
}
function voirLeCas() {
  router.push({ name: 'case-detail', params: { pid: pid.value, id: String(caseId.value) } })
}
function retourCampagne() {
  router.push({ name: 'run-detail', params: { pid: pid.value, id: String(runId.value) } })
}
// `window` n'existe pas dans la portée d'un template Vue : la fonction doit vivre ici.
function imprimer() { window.print() }

// ── Saisie manuelle depuis LA PAGE DU TEST — la même fenêtre que `RunDetail.vue`, ouverte
// depuis l'autre endroit où TestRail permet de saisir un résultat : la fiche du test lui-même. ──
// ⚠️ Même garde qu'en liste : absente d'une campagne automatique (rien à saisir, la machine a
// déjà parlé), absente d'une campagne archivée (lecture seule). Le serveur refuse de son côté ;
// l'écran n'est que son porte-parole.
const peutSaisir = computed(() => peutModifier.value && test.value?.run_mode === 'manuelle' && !test.value?.run_archived)
const saisieOuverte = ref(false)
// `AddResultDialog` n'attend que `id` et `title` (voir sa prop `CasMinimal`) : cette page n'a
// jamais eu de `RunCaseResult` complet à lui donner, elle n'a que ces deux champs sur son « test ».
const casPourSaisie = computed(() => ({ id: caseId.value, title: test.value?.title || '' }))
function ouvrirSaisie() { saisieOuverte.value = true }
async function resultatAjoute() {
  saisieOuverte.value = false
  // Recharge : le statut affiché et l'onglet « Résultats et commentaires » (`ResultHistory`)
  // doivent refléter le résultat qu'on vient de poser, pas celui d'avant.
  await load()
}

// ── Onglet « Historique et contexte » : le même cas AILLEURS ──────────────────
// La question à laquelle une campagne seule ne répond pas : « ce cas échoue-t-il partout, ou
// seulement ici ? » — un test rouge sur une seule recette et vert ailleurs ne se diagnostique pas
// comme un test rouge partout.
const ailleurs = computed(() =>
  (test.value?.historique_du_cas || []).filter((r) => r.run_id !== runId.value))

const parMois = computed(() => {
  const groupes = new Map<string, typeof ailleurs.value>()
  for (const r of ailleurs.value) {
    const cle = cleMois(r.created_at)
    if (!groupes.has(cle)) groupes.set(cle, [])
    groupes.get(cle)!.push(r)
  }
  return [...groupes.entries()].map(([cle, lignes]) => ({ cle, titre: moisLong(cle), lignes }))
})
</script>

<template>
  <div v-if="loading" class="space-y-3">
    <div class="h-8 w-72 rounded bg-secondary animate-pulse"></div>
    <div class="h-40 rounded bg-secondary animate-pulse"></div>
  </div>

  <div v-else-if="error" class="text-center py-10">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <Button variant="secondary" class="mt-3" @click="load">Réessayer</Button>
  </div>

  <div v-else-if="test">
    <!-- ══ EN-TÊTE ══ -->
    <div class="flex items-center gap-3 flex-wrap">
      <!-- Pastille de statut — jamais SEULE : le mot est répété dans le badge de droite et dans
           chaque résultat. La couleur accompagne, elle n'informe pas à elle seule (invariant 4.7). -->
      <span class="h-3.5 w-3.5 rounded-full shrink-0" :style="{ background: `hsl(${statut.color})` }"
            :title="`Statut : ${statut.label}`"></span>
      <!-- L'identité du TEST, distincte de celle du cas. L'infobulle le dit en toutes lettres :
           sans elle, « T7-12 » ressemblerait à une variante décorative de « C12 ». -->
      <span class="rounded-full bg-accent-id text-accent-id-foreground text-sm font-semibold px-3 py-1 tabular-nums"
            :title="`Ce test = le cas C${test.case_id} dans la campagne R${test.run_id}. Le cas, lui, vit dans le référentiel et sert à toutes les campagnes.`">
        T{{ test.run_id }}-{{ test.case_id }}
      </span>
      <h1 class="text-2xl font-semibold tracking-tight truncate">{{ test.title }}</h1>
      <span v-if="test.run_archived" class="text-sm text-muted-foreground">(archivé)</span>
      <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold"
            :class="statut.badge">{{ statut.label }}</span>

      <div class="ml-auto flex items-center gap-1.5">
        <IconButton label="Test précédent de cette campagne"
                    :disabled="!test.prev_case_id" @click="allerAuTest(test.prev_case_id)">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 6l-6 6 6 6"/></svg>
        </IconButton>
        <IconButton label="Test suivant de cette campagne"
                    :disabled="!test.next_case_id" @click="allerAuTest(test.next_case_id)">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>
        </IconButton>
        <IconButton label="Imprimer ce test" @click="imprimer">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9V3h12v6M6 18H4a1 1 0 01-1-1v-5a2 2 0 012-2h14a2 2 0 012 2v5a1 1 0 01-1 1h-2M6 14h12v7H6z"/></svg>
        </IconButton>
        <!-- Le geste central de TestRail, offert ici comme dans la liste de la campagne : la
             fiche du test est L'AUTRE endroit d'où on saisit un résultat. -->
        <Button v-if="peutSaisir" variant="primary"
                title="Ajouter un résultat pour ce test" @click="ouvrirSaisie">Ajouter un résultat</Button>
        <!-- ⚠️ Le geste qui empêche les deux identités de se confondre : d'ici, on va au CAS —
             le document du référentiel, partagé par toutes les campagnes. -->
        <Button variant="secondary"
                title="Ouvrir le cas dans le référentiel (partagé par toutes les campagnes)"
                @click="voirLeCas">Voir le cas</Button>
      </div>
    </div>

    <!-- Fil d'Ariane vers la campagne -->
    <button class="mt-1 text-primary text-sm hover:underline" @click="retourCampagne">{{ test.run_name }}</button>

    <!-- ══ MÉTADONNÉES — lues sur le cas, jamais réinventées ici ══ -->
    <div class="mt-4 rounded-lg border border-border bg-primary/5 p-4 grid grid-cols-2 md:grid-cols-5 gap-y-4 gap-x-6 text-sm">
      <div>
        <div class="text-xs font-semibold text-muted-foreground">Type</div>
        <div class="mt-0.5" :title="typeView(test.type).hint">{{ typeView(test.type).label }}</div>
      </div>
      <div>
        <div class="text-xs font-semibold text-muted-foreground">Priorité</div>
        <div class="mt-0.5" :title="priorityView(test.priority).hint">{{ priorityView(test.priority).label }}</div>
      </div>
      <div>
        <div class="text-xs font-semibold text-muted-foreground">Estimation</div>
        <div class="mt-0.5" :class="!test.estimate && 'text-subtle-foreground italic'">{{ test.estimate || 'Non renseignée' }}</div>
      </div>
      <div>
        <div class="text-xs font-semibold text-muted-foreground">Références</div>
        <div class="mt-0.5" :class="!test.refs && 'text-subtle-foreground italic'">
          <RefsList v-if="test.refs" :refs="test.refs" />
          <template v-else>Aucune</template>
        </div>
      </div>
      <div>
        <div class="text-xs font-semibold text-muted-foreground">État</div>
        <div class="mt-0.5" :title="etatView(test.etat).hint">{{ etatView(test.etat).label }}</div>
      </div>
    </div>
    <!-- ⚠️ Ces valeurs sont celles du cas AUJOURD'HUI : il n'y a pas de photo des cas à la
         clôture d'une campagne (`RunRepo.archive`). Écart connu et assumé — on le dit plutôt que
         de laisser croire que la campagne a figé ce qu'elle affiche. -->
    <p class="mt-1.5 text-xs text-muted-foreground">
      Métadonnées lues sur le cas dans son état actuel — une campagne ne fige pas le contenu des cas.
    </p>

    <!-- ══ ONGLETS ══ -->
    <div class="mt-6 flex items-center gap-1 border-b border-border">
      <button v-for="o in [
                { key: 'resultats', label: 'Résultats et commentaires' },
                { key: 'historique', label: 'Historique et contexte' },
                { key: 'defauts', label: 'Défauts' }]" :key="o.key"
              class="px-3 py-2 text-sm -mb-px border-b-2 transition-colors"
              :class="onglet === o.key ? 'border-primary text-foreground font-medium'
                                       : 'border-transparent text-muted-foreground hover:text-foreground'"
              @click="onglet = (o.key as any)">{{ o.label }}</button>
    </div>

    <!-- ── Résultats et commentaires ─────────────────────────────────────────
         `ResultHistory` porte déjà cette liste (mode d'exécution, statut, auteur, date,
         commentaire) : la réécrire ici en ferait deux versions du même affichage. -->
    <div v-if="onglet === 'resultats'" class="mt-5">
      <ResultHistory :results="test.results" :can-delete-attachments="peutSupprimer"
                     @attachment-removed="load" />
    </div>

    <!-- ── Historique et contexte ─────────────────────────────────────────── -->
    <div v-else-if="onglet === 'historique'" class="mt-5 space-y-6">
      <div>
        <h3 class="text-sm font-semibold">Résultats de ce cas sur 30 jours</h3>
        <p class="mt-1 text-xs text-muted-foreground">
          Toutes campagnes confondues — c'est la vue qui distingue un test rouge PARTOUT d'un test
          rouge seulement ici.
        </p>
        <CourbeResultats class="mt-2" :events="test.historique_du_cas" :jours="30" />
      </div>

      <div>
        <h3 class="text-sm font-semibold">Ce cas dans les autres campagnes</h3>
        <p v-if="!ailleurs.length" class="mt-2 text-sm text-muted-foreground italic">
          Ce cas n'a été joué dans aucune autre campagne.
        </p>
        <div v-for="mois in parMois" :key="mois.cle" class="mt-4">
          <h4 class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{{ mois.titre }}</h4>
          <ul class="mt-2 divide-y divide-border/40 rounded-lg border border-border">
            <li v-for="(r, i) in mois.lignes" :key="i" class="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
              <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold shrink-0"
                    :class="statutAffiche(r.statut, r.a_confirmer).badge">{{ statutAffiche(r.statut, r.a_confirmer).label }}</span>
              <!-- ⚠️ Le MODE reste visible ici aussi : un « Passed » manuel dans une autre
                   campagne ne vaut pas un « Passed » automatique, et l'écran ne doit jamais
                   laisser croire le contraire. -->
              <ResultMode :mode="r.mode" :created-by="r.created_by" :at="r.created_at" />
              <RouterLink :to="{ name: 'run-test', params: { pid, id: String(r.run_id), caseId: String(test.case_id) } }"
                          class="text-primary hover:underline truncate">{{ r.run_name }}</RouterLink>
              <span class="ml-auto text-xs text-muted-foreground shrink-0">
                Testé par {{ libelleActeur(r.created_by) }} · {{ formatDate(r.created_at) }}
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <!-- ── Défauts ────────────────────────────────────────────────────────────
         Honnête plutôt que décoratif : TestPilot ne modélise pas encore de défaut rattaché à un
         résultat. Un panneau de compteurs à zéro laisserait croire que la question a été posée
         et qu'il n'y a rien — alors qu'elle n'a pas encore de réponse ici. -->
    <div v-else class="mt-5 rounded-lg border border-border bg-surface/60 p-6 text-sm text-muted-foreground">
      <p class="text-foreground font-medium">Défauts — à venir.</p>
      <p class="mt-2 max-w-xl">
        Aucun défaut ne peut encore être rattaché à un résultat. Ce que TestPilot sait dire
        aujourd'hui, c'est l'ORIGINE probable d'un échec automatique (application / test /
        environnement) : elle est lisible sur le rapport de l'exécution concernée, depuis l'onglet
        « Résultats et commentaires ».
      </p>
    </div>

    <AddResultDialog :open="saisieOuverte" :run-id="runId" :cas="casPourSaisie"
                     :statuts="statutsManuels"
                     @close="saisieOuverte = false" @saved="resultatAjoute" />
  </div>

  <div v-else class="text-sm text-muted-foreground">Test introuvable dans cette campagne.</div>
</template>
