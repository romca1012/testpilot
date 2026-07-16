<script setup lang="ts">
/**
 * Arbitrage humain des diagnostics (décision 0013).
 *
 * Un diagnostic est une DÉDUCTION de la machine, jamais un constat : une assertion qui échoue
 * peut venir de l'application, d'un test qui attend la mauvaise chose, ou de l'environnement.
 * Cet écran est le seul endroit où un humain tranche.
 *
 * Il vit sous EXÉCUTION, pas sous Gestion des cas : on juge le résultat d'un run, pas le
 * référentiel (séparation §8, invariant 4.8).
 *
 * ⚠️ Deux choses qu'on ne fait JAMAIS ici : réécrire ce que la machine a déduit (on affiche les
 * deux côte à côte), et recalculer les deux axes du run (§4.2 — un avis ne réécrit pas ce qui
 * s'est passé). L'arbitrage porte sur l'ORIGINE du défaut.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, type RepairOut } from '../lib/api'
import { formatDate } from '../lib/format'
import { defectOriginView, toneClasses } from '../lib/status'
import AxisChip from '../components/AxisChip.vue'
import Card from '../components/ui/Card.vue'
import Chip from '../components/ui/Chip.vue'
import Hint from '../components/ui/Hint.vue'
import Icon from '../components/ui/Icon.vue'
import Button from '../components/ui/Button.vue'

const route = useRoute()
const pid = computed(() => route.params.pid as string)

const items = ref<RepairOut[]>([])
const loading = ref(true)
const error = ref('')
const portee = ref<'pending' | 'all'>('pending')

// Formulaire d'arbitrage, par diagnostic ouvert.
const ouvert = ref<number | null>(null)
const origine = ref('')
const commentaire = ref('')
const relecteur = ref('')
const envoi = ref(false)
const erreurArbitrage = ref('')

const ORIGINES = [
  { code: 'vrai_bug', label: 'Bug dans l\'application' },
  { code: 'test_a_reparer', label: 'Test à corriger' },
  { code: 'indetermine', label: 'Origine à investiguer' },
]

async function load() {
  loading.value = true
  error.value = ''
  try {
    items.value = await api.listRepairs(pid.value, portee.value)
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([pid, portee], load)

function ouvrir(d: RepairOut) {
  ouvert.value = ouvert.value === d.id ? null : d.id
  origine.value = ''
  commentaire.value = ''
  erreurArbitrage.value = ''
}

async function trancher(d: RepairOut, verdict: 'confirmed' | 'overturned') {
  // Infirmer sans dire ce que c'est efface une information sans en produire.
  if (verdict === 'overturned' && !origine.value) {
    erreurArbitrage.value = 'Indiquez l\'origine réelle : dire « ce n\'est pas ça » sans dire ce que c\'est n\'apprend rien.'
    return
  }
  envoi.value = true
  erreurArbitrage.value = ''
  try {
    await api.setRepairVerdict(d.id, {
      verdict,
      origin: verdict === 'overturned' ? origine.value : '',
      comment: commentaire.value,
      reviewer: relecteur.value,
    })
    ouvert.value = null
    await load()
  } catch (e: any) {
    erreurArbitrage.value = e?.message || 'Arbitrage impossible'
  } finally {
    envoi.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="inline-flex items-center gap-1.5 text-2xl font-semibold tracking-tight">
          Confirmations
          <Hint text="Ce que la machine a DÉDUIT de l'échec — pas ce qu'elle a constaté. Confirmez ou infirmez : votre jugement s'ajoute au sien, il ne l'efface pas." />
        </h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Origine des défauts diagnostiqués automatiquement, à trancher par un humain.
        </p>
      </div>
      <div class="inline-flex rounded-md border border-border p-0.5" role="group">
        <button
          v-for="opt in ([{ v: 'pending', label: 'À confirmer' }, { v: 'all', label: 'Tous' }] as const)"
          :key="opt.v" :aria-pressed="portee === opt.v"
          class="rounded px-2.5 py-1 text-xs transition-colors"
          :class="portee === opt.v ? 'bg-primary/15 text-foreground' : 'text-muted-foreground hover:text-foreground'"
          @click="portee = opt.v"
        >{{ opt.label }}</button>
      </div>
    </header>

    <div v-if="loading" class="space-y-3">
      <div v-for="i in 2" :key="i" class="h-24 rounded-xl border border-border bg-card animate-pulse" />
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>

    <div v-else-if="!items.length"
         class="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-5 py-16 text-center">
      <div class="grid h-12 w-12 place-items-center rounded-full border border-border bg-surface text-muted-foreground">
        <Icon name="check" class="h-5 w-5" />
      </div>
      <p class="text-sm text-muted-foreground">
        {{ portee === 'pending' ? 'Aucun diagnostic en attente de confirmation.' : 'Aucun diagnostic à trancher.' }}
      </p>
      <p v-if="portee === 'pending'" class="text-xs text-muted-foreground/70">
        Les diagnostics « bug applicatif » n'exigent pas de confirmation — voyez « Tous » pour les infirmer.
      </p>
    </div>

    <Card v-for="d in items" v-else :key="d.id">
      <div class="space-y-3">
        <!-- Contexte : trancher sans savoir de quel cas il s'agit serait trancher à l'aveugle. -->
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <RouterLink v-if="d.test_case_id" :to="`/projects/${pid}/cases/${d.test_case_id}`"
                        class="font-medium hover:text-primary">{{ d.case_title }}</RouterLink>
            <span v-else class="font-medium text-muted-foreground">Cas supprimé</span>
            <p class="text-xs text-muted-foreground">
              {{ d.module_name }} · exécuté le {{ formatDate(d.executed_at) }}
              · <RouterLink :to="`/projects/${pid}/executions/${d.execution_id}`"
                            class="text-primary hover:underline">voir le rapport</RouterLink>
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <AxisChip kind="execution" :status="d.execution_status" />
            <AxisChip kind="functional" :status="d.functional_status" />
          </div>
        </div>

        <!-- MACHINE vs HUMAIN, côte à côte — jamais l'un à la place de l'autre. -->
        <div class="rounded-lg border border-border bg-surface/40 p-3">
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="text-muted-foreground">La machine a déduit :</span>
            <Chip :icon="defectOriginView(d.defect_origin).icon"
                  :label="defectOriginView(d.defect_origin).label"
                  :cls="toneClasses(defectOriginView(d.defect_origin).tone)" />
            <Hint v-if="defectOriginView(d.defect_origin).hint"
                  :text="defectOriginView(d.defect_origin).hint!" />
            <span class="text-muted-foreground">· cause : {{ d.cause_label }}</span>
          </div>
          <p v-if="d.human_verdict" class="mt-2 text-xs">
            <span class="text-muted-foreground">Tranché par {{ d.confirmed_by }} :</span>
            <span v-if="d.human_verdict === 'confirmed'" class="text-success"> confirmé</span>
            <span v-else class="text-warning">
              infirmé → {{ defectOriginView(d.human_origin).label }}
            </span>
            <span v-if="d.human_comment" class="text-muted-foreground"> — {{ d.human_comment }}</span>
          </p>
        </div>

        <div v-if="!d.human_verdict">
          <Button v-if="ouvert !== d.id" variant="secondary" @click="ouvrir(d)">Trancher…</Button>

          <div v-else class="space-y-3 rounded-lg border border-border p-3">
            <p class="text-xs text-muted-foreground">
              Votre jugement s'ajoute au diagnostic de la machine — il ne le remplace pas.
              Il ne change pas non plus le résultat de l'exécution : ce qui s'est passé reste ce
              qui s'est passé.
            </p>
            <label class="block">
              <span class="text-xs text-muted-foreground">Si vous infirmez, l'origine réelle</span>
              <select v-model="origine"
                      class="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm">
                <option value="">—</option>
                <option v-for="o in ORIGINES" :key="o.code" :value="o.code">{{ o.label }}</option>
              </select>
            </label>
            <label class="block">
              <span class="text-xs text-muted-foreground">Pourquoi (ce qui vaudra encore dans six mois)</span>
              <textarea v-model="commentaire" rows="2"
                        class="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm"
                        placeholder="Ex. : spec périmée — le test ne remplit pas les champs requis ajoutés depuis." />
            </label>
            <label class="block">
              <span class="text-xs text-muted-foreground">Votre nom (champ libre, aucune authentification)</span>
              <input v-model="relecteur"
                     class="mt-1 w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm" />
            </label>
            <p v-if="erreurArbitrage" class="text-xs text-destructive">{{ erreurArbitrage }}</p>
            <div class="flex flex-wrap gap-2">
              <Button :disabled="envoi" @click="trancher(d, 'confirmed')">Confirmer le diagnostic</Button>
              <Button variant="secondary" :disabled="envoi" @click="trancher(d, 'overturned')">
                Infirmer
              </Button>
              <Button variant="ghost" :disabled="envoi" @click="ouvert = null">Annuler</Button>
            </div>
          </div>
        </div>
      </div>
    </Card>
  </div>
</template>
