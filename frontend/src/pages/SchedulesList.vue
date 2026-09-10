<script setup lang="ts">
// Planifications récurrentes (migration 43) — déclenchent automatiquement une campagne sur une
// horloge (ex. régression nocturne), en réutilisant EXACTEMENT le moteur d'exécution existant
// (voir `scheduler_service.py`). Gardé au-dessus du plancher des campagnes (Dev+, pas Testeur+) :
// une planification tourne sans supervision humaine, avec un coût LLM/navigateur récurrent —
// décision déjà actée avec le porteur.
//
// ⚠️ **Aucun choix de mode ici.** Une planification est TOUJOURS automatique — personne n'est
// présent à 2h du matin pour saisir un résultat manuel. Le formulaire ne propose même pas la
// question, plutôt que de la poser pour la bloquer ensuite (voir la note explicite plus bas).
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, roleSuffisant, type CaseSummary } from '../lib/api'
import { useSession } from '../lib/useSession'
import { useProjects } from '../lib/useProjects'
import { useSchedules, useCreerSchedule, usePatchSchedule, useSupprimerSchedule } from '../lib/donnees'
import { localVersUtc, utcVersLocal } from '../lib/scheduleTime'
import Button from '../components/ui/Button.vue'
import Modal from '../components/ui/Modal.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const { session } = useSession()
const { projectById } = useProjects()
// Lecture : Testeur+ (comme les campagnes). Création/édition/suppression : Dev+ — le serveur
// applique EXACTEMENT le même plancher (`require_project_role(ROLE_DEV)`), ceci n'évite qu'un
// bouton voué à un 403.
const roleProjet = computed(() => projectById(pid.value)?.effective_role || session.value?.role || '')
const peutPlanifier = computed(() => roleSuffisant(roleProjet.value, 'dev'))

const { data: schedulesData, isLoading, error: erreurSchedules, refetch } = useSchedules(pid)
const schedules = computed(() => schedulesData.value ?? [])
const loading = computed(() => isLoading.value && !schedulesData.value)
const error = computed(() => (erreurSchedules.value ? 'Impossible de charger les planifications.' : ''))

const JOURS = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
// ⚠️ `hour`/`minute`/`weekday` sont stockés et comparés en UTC côté serveur (`scheduler_service.
// tick()`) — jamais affichés bruts : reconvertis en heure LOCALE, celle que la personne a tapée
// et reconnaît (voir `lib/scheduleTime.ts` pour la limite assumée autour du changement d'heure).
function frequenceLabel(s: { frequency: string; hour: number; minute: number; weekday: number | null }) {
  const local = utcVersLocal({ hour: s.hour, minute: s.minute, weekday: s.frequency === 'weekly' ? (s.weekday ?? 0) : null })
  const heure = `${String(local.hour).padStart(2, '0')}h${String(local.minute).padStart(2, '0')}`
  if (s.frequency === 'weekly') return `Chaque ${JOURS[local.weekday ?? 0]} à ${heure}`
  return `Chaque jour à ${heure}`
}
function dernierDeclenchement(s: { last_triggered_at: string | null }) {
  if (!s.last_triggered_at) return 'Jamais encore déclenchée'
  return `Dernier déclenchement : ${s.last_triggered_at.slice(0, 16).replace('T', ' à ')}`
}

const toggler = usePatchSchedule(pid)
async function toggleActive(s: { id: number; is_active: boolean }) {
  try {
    await toggler.mutateAsync({ id: s.id, is_active: !s.is_active })
  } catch (e: any) {
    window.alert(e?.message || 'Modification impossible.')
  }
}
const supprimer = useSupprimerSchedule(pid)
async function supprimerSchedule(s: { id: number; name: string }) {
  if (!window.confirm(`Supprimer la planification « ${s.name} » ? Les campagnes déjà lancées par elle restent intactes.`)) return
  try {
    await supprimer.mutateAsync(s.id)
  } catch (e: any) {
    window.alert(e?.message || 'Suppression impossible.')
  }
}

// ── Création (modale, route « schedules », toujours la même liste) ─────────────────────────
const showCreate = ref(false)
// ⚠️ PAS de date dans le nom par défaut : une planification est RÉCURRENTE (elle survit au jour
// de sa création), contrairement au nom par défaut d'un run ponctuel (`AddTestRunForm.vue`).
// `scheduler_service._declencher` ajoute déjà la date du DÉCLENCHEMENT sur chaque run engendré —
// en dater aussi la planification aurait produit des noms doublement datés (et de plus en plus
// faux avec le temps, ex. « Régression nocturne 2026-09-10 — 2026-09-15 »).
const form = reactive({
  name: 'Régression nocturne',
  selection: 'all' as 'all' | 'frozen',
  frequency: 'daily' as 'daily' | 'weekly',
  weekday: 0,
  hour: 2,
  minute: 0,
})
const cases = ref<CaseSummary[]>([])
const selected = ref<number[]>([])
onMounted(async () => {
  try { cases.value = (await api.listCases(pid.value, { limit: 500 })).items } catch { cases.value = [] }
})
const byModule = computed(() => {
  const map = new Map<string, CaseSummary[]>()
  for (const c of cases.value) {
    const k = c.module || 'Sans module'
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(c)
  }
  return [...map.entries()].map(([module, rows]) => ({ module, rows }))
})
function toggleCase(id: number) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((x) => x !== id) : [...selected.value, id]
}
function toggleModule(rows: CaseSummary[]) {
  const ids = rows.map((c) => c.id)
  const tousCoches = ids.every((id) => selected.value.includes(id))
  selected.value = tousCoches
    ? selected.value.filter((id) => !ids.includes(id))
    : [...new Set([...selected.value, ...ids])]
}

const canSubmit = computed(() =>
  !!form.name.trim() && (form.selection === 'all' || selected.value.length > 0))
const creerSchedule = useCreerSchedule(pid)
const createError = ref('')
function resetForm() {
  form.name = 'Régression nocturne'
  form.selection = 'all'; form.frequency = 'daily'; form.weekday = 0; form.hour = 2; form.minute = 0
  selected.value = []
  createError.value = ''
}
function openCreate() { resetForm(); showCreate.value = true }
async function submit() {
  if (!canSubmit.value) return
  createError.value = ''
  try {
    // Le formulaire recueille l'heure LOCALE (celle que la personne connaît) — jamais envoyée
    // telle quelle : le serveur compare en UTC (`scheduler_service.tick()`), voir scheduleTime.ts.
    const utc = localVersUtc({
      hour: form.hour, minute: form.minute,
      weekday: form.frequency === 'weekly' ? form.weekday : null,
    })
    await creerSchedule.mutateAsync({
      name: form.name.trim(),
      selection_mode: form.selection,
      case_ids: form.selection === 'frozen' ? selected.value : [],
      frequency: form.frequency,
      hour: utc.hour,
      minute: utc.minute,
      weekday: utc.weekday,
    })
    showCreate.value = false
  } catch (e: any) {
    createError.value = e?.message || 'Création impossible.'
  }
}
function goBack() { router.push({ name: 'executions', params: { pid: pid.value } }) }
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Planifications</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Déclenche automatiquement une campagne sur une horloge — toujours en mode
          <strong class="text-foreground">automatique</strong>, jamais manuel.
        </p>
      </div>
      <Button v-if="peutPlanifier" variant="primary" @click="openCreate">+ Nouvelle planification</Button>
    </div>

    <div v-if="loading" class="mt-6 space-y-2">
      <div v-for="i in 3" :key="i" class="h-16 rounded-md bg-secondary animate-pulse"></div>
    </div>
    <div v-else-if="error" class="mt-8 text-center">
      <p class="text-sm text-muted-foreground">{{ error }}</p>
      <Button variant="secondary" class="mt-3" @click="() => refetch()">Réessayer</Button>
    </div>
    <p v-else-if="!schedules.length" class="mt-10 text-center text-sm text-muted-foreground">
      {{ peutPlanifier ? 'Aucune planification pour ce projet. Créez-en une avec « Nouvelle planification ».'
                        : 'Aucune planification pour ce projet.' }}
    </p>

    <div v-else class="mt-5 divide-y divide-border/40 border-t border-border/40">
      <div v-for="s in schedules" :key="s.id" class="flex items-center gap-4 py-3.5 px-2 -mx-2"
           :class="s.is_active ? '' : 'opacity-60'">
        <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-medium border border-success/30 bg-success/15 text-success shrink-0">
          Automatique
        </span>
        <div class="min-w-0 flex-1">
          <div class="text-sm font-medium truncate">{{ s.name }}</div>
          <div class="text-xs text-muted-foreground mt-0.5">
            {{ frequenceLabel(s) }} · {{ s.selection_mode === 'all' ? 'tous les cas' : 'sélection figée' }}
          </div>
          <div class="text-xs text-muted-foreground/70 mt-0.5">{{ dernierDeclenchement(s) }}</div>
        </div>
        <span class="text-xs shrink-0" :class="s.is_active ? 'text-success' : 'text-muted-foreground'">
          {{ s.is_active ? 'Active' : 'En pause' }}
        </span>
        <Button v-if="peutPlanifier" variant="secondary" size="sm" class="shrink-0" @click="toggleActive(s)">
          {{ s.is_active ? 'Mettre en pause' : 'Réactiver' }}
        </Button>
        <Button v-if="peutPlanifier" variant="ghost" size="sm" class="shrink-0 text-destructive" @click="supprimerSchedule(s)">
          Supprimer
        </Button>
      </div>
    </div>

    <button class="mt-8 text-sm text-muted-foreground hover:text-foreground flex items-center gap-1" @click="goBack">
      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
      Retour aux exécutions
    </button>

    <!-- ════════ Création d'une planification ════════ -->
    <Modal :open="showCreate" title="Nouvelle planification" max-width="max-w-2xl"
           subtitle="Lance automatiquement une campagne à l'heure choisie — toujours en mode automatique."
           @close="showCreate = false">
      <form id="form-create-schedule" class="space-y-5" @submit.prevent="submit">
        <label class="block">
          <span class="text-sm font-medium">Nom <span class="text-destructive">*</span></span>
          <input v-model="form.name" required autofocus
                 class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 text-sm focus:border-primary outline-none" />
        </label>

        <!-- Pas de choix de mode : une note plutôt qu'une question posée pour être bloquée. -->
        <p class="rounded-md border border-border bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
          Une planification s'exécute toujours en mode <strong class="text-foreground">automatique</strong> —
          un résultat manuel demande une présence humaine, incompatible avec un déclenchement nocturne.
        </p>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block">
            <span class="text-sm font-medium">Fréquence</span>
            <select v-model="form.frequency"
                    class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 text-sm focus:border-primary outline-none">
              <option value="daily">Quotidienne</option>
              <option value="weekly">Hebdomadaire</option>
            </select>
          </label>
          <label v-if="form.frequency === 'weekly'" class="block">
            <span class="text-sm font-medium">Jour</span>
            <select v-model.number="form.weekday"
                    class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 text-sm focus:border-primary outline-none">
              <option v-for="(j, i) in JOURS" :key="i" :value="i">{{ j.charAt(0).toUpperCase() + j.slice(1) }}</option>
            </select>
          </label>
          <label class="block">
            <span class="text-sm font-medium">Heure <span class="font-normal text-xs text-muted-foreground">(votre heure locale)</span></span>
            <div class="mt-1 flex items-center gap-2">
              <input v-model.number="form.hour" type="number" min="0" max="23"
                     class="w-20 rounded-md bg-surface-raised border border-border px-3 py-2 text-sm focus:border-primary outline-none" />
              <span class="text-muted-foreground">h</span>
              <input v-model.number="form.minute" type="number" min="0" max="59"
                     class="w-20 rounded-md bg-surface-raised border border-border px-3 py-2 text-sm focus:border-primary outline-none" />
            </div>
          </label>
        </div>

        <div>
          <span class="text-sm font-medium">Sélection des cas de test <span class="text-destructive">*</span></span>
          <div class="mt-2 space-y-2">
            <label class="flex gap-3 rounded-md border p-3 cursor-pointer transition-colors"
                   :class="form.selection === 'all' ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'">
              <input type="radio" value="all" v-model="form.selection" class="mt-1 accent-[hsl(var(--primary))]" />
              <div>
                <div class="text-sm font-medium">Inclure tous les cas de test</div>
                <p class="text-xs text-muted-foreground mt-0.5">
                  Sélection vivante : les cas créés après coup rejoignent chaque déclenchement. ({{ cases.length }} cas aujourd'hui.)
                </p>
              </div>
            </label>
            <label class="flex gap-3 rounded-md border p-3 cursor-pointer transition-colors"
                   :class="form.selection === 'frozen' ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'">
              <input type="radio" value="frozen" v-model="form.selection" class="mt-1 accent-[hsl(var(--primary))]" />
              <div class="min-w-0 flex-1">
                <div class="text-sm font-medium">Sélectionner des cas de test spécifiques</div>
                <p class="text-xs text-muted-foreground mt-0.5">Sélection figée : aucun ajout automatique ensuite.</p>

                <div v-if="form.selection === 'frozen'" class="mt-3">
                  <span class="text-xs text-muted-foreground">{{ selected.length }} sélectionné(s)</span>
                  <div v-if="!cases.length" class="mt-2 text-xs text-muted-foreground">Aucun cas de test dans ce projet.</div>
                  <div v-else class="mt-2 max-h-56 overflow-y-auto rounded-md border border-border">
                    <div v-for="m in byModule" :key="m.module">
                      <button type="button"
                              class="w-full flex items-center gap-2 bg-surface-raised/70 px-3 py-1.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground border-b border-border/60"
                              @click="toggleModule(m.rows)">
                        {{ m.module }}
                        <span class="ml-auto font-normal normal-case">{{ m.rows.length }} cas — tout (dé)cocher</span>
                      </button>
                      <label v-for="c in m.rows" :key="c.id"
                             class="flex items-center gap-2 pl-6 pr-3 py-2 text-sm hover:bg-accent/30 cursor-pointer border-b border-border/40">
                        <input type="checkbox" :checked="selected.includes(c.id)" @change="toggleCase(c.id)"
                               class="accent-[hsl(var(--primary))]" />
                        <span class="text-muted-foreground tabular-nums text-xs">C{{ c.id }}</span>
                        <span class="truncate">{{ c.title }}</span>
                      </label>
                    </div>
                  </div>
                </div>
              </div>
            </label>
          </div>
        </div>

        <p v-if="createError" class="text-sm text-destructive">{{ createError }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="showCreate = false">Annuler</Button>
        <Button type="submit" form="form-create-schedule" variant="success"
                :loading="creerSchedule.isPending.value" :disabled="!canSubmit">
          Créer la planification
        </Button>
      </template>
    </Modal>
  </div>
</template>
