<script setup lang="ts">
// Plans de test (migration 43) — troisième couche, purement organisationnelle, au-dessus des
// campagnes déjà listées par « Exécutions » : un Plan REGROUPE des runs existants sous un même
// rapport consolidé (ex. « Recette V3 » = les campagnes fonctionnelle + régression + performance
// de cette version). Créer un plan ne touche à AUCUNE campagne — assigner/retirer un run est un
// geste séparé, posé depuis sa fiche (PlanDetail.vue).
//
// ⚠️ Un plan ne fusionne JAMAIS les runs qu'il contient en un seul chiffre : un run manuel et un
// run automatique gardent chacun leur propre résumé (voir PlanDetail.vue) — un Plan qui
// afficherait « 80 % » sans dire quelle part vient d'un humain mentirait par omission.
//
// Route « plan-new » : même composant que « plans » (router.ts), la création s'ouvre en modale
// par-dessus la liste plutôt que sur un écran à part — un Plan n'a que 3 champs, un écran dédié
// serait vide autour d'eux. L'URL change quand même (deep-linkable, partageable).
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { roleSuffisant } from '../lib/api'
import { useSession } from '../lib/useSession'
import { useProjects } from '../lib/useProjects'
import { usePlans, useCreerPlan } from '../lib/donnees'
import Button from '../components/ui/Button.vue'
import Modal from '../components/ui/Modal.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const { session } = useSession()
const { projectById } = useProjects()
const peutCreer = computed(() => roleSuffisant(projectById(pid.value)?.effective_role || session.value?.role || '', 'testeur'))

const { data: plansData, isLoading, error: erreurPlans, refetch } = usePlans(pid)
const plans = computed(() => plansData.value ?? [])
const loading = computed(() => isLoading.value && !plansData.value)
const error = computed(() => (erreurPlans.value ? 'Impossible de charger les plans de test.' : ''))

function openPlan(id: number) {
  router.push({ name: 'plan-detail', params: { pid: pid.value, id: String(id) } })
}

// ── Création (modale, route « plan-new ») ──────────────────────────────────────────────────
const showCreate = computed(() => route.name === 'plan-new')
function goNew() { router.push({ name: 'plan-new', params: { pid: pid.value } }) }
function closeCreate() { router.push({ name: 'plans', params: { pid: pid.value } }) }

const form = reactive({ name: '', description: '', refs: '' })
const creerPlan = useCreerPlan(pid)
const createError = ref('')
async function submit() {
  if (!form.name.trim()) return
  createError.value = ''
  try {
    const plan = await creerPlan.mutateAsync({
      name: form.name.trim(), description: form.description, refs: form.refs,
    })
    form.name = ''; form.description = ''; form.refs = ''
    router.push({ name: 'plan-detail', params: { pid: pid.value, id: String(plan.id) } })
  } catch (e: any) {
    createError.value = e?.message || 'Création impossible.'
  }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Plans de test</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Regroupez plusieurs campagnes existantes sous un même rapport — purement organisationnel,
          rien n'est relancé ni modifié.
        </p>
      </div>
      <Button v-if="peutCreer" variant="primary" @click="goNew">+ Nouveau plan</Button>
    </div>

    <div v-if="loading" class="mt-6 space-y-2">
      <div v-for="i in 3" :key="i" class="h-16 rounded-md bg-secondary animate-pulse"></div>
    </div>
    <div v-else-if="error" class="mt-8 text-center">
      <p class="text-sm text-muted-foreground">{{ error }}</p>
      <Button variant="secondary" class="mt-3" @click="() => refetch()">Réessayer</Button>
    </div>
    <div v-else-if="!plans.length" class="mt-10 text-center text-sm text-muted-foreground">
      {{ peutCreer ? 'Aucun plan de test pour ce projet. Créez-en un avec « Nouveau plan ».' : 'Aucun plan de test pour ce projet.' }}
    </div>

    <div v-else class="mt-5 divide-y divide-border/40 border-t border-border/40">
      <button v-for="p in plans" :key="p.id" type="button"
              class="w-full text-left flex items-start gap-4 py-4 px-2 -mx-2 hover:bg-accent/30 rounded-md"
              @click="openPlan(p.id)">
        <span class="mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 5h11M9 12h11M9 19h11M4 5h.01M4 12h.01M4 19h.01"/></svg>
        </span>
        <div class="min-w-0 flex-1">
          <div class="text-sm text-primary truncate">{{ p.name }}</div>
          <p v-if="p.description" class="mt-0.5 text-xs text-muted-foreground line-clamp-2">{{ p.description }}</p>
          <p v-if="p.refs" class="mt-1 text-xs text-muted-foreground">Réfs. {{ p.refs }}</p>
        </div>
      </button>
    </div>

    <!-- ════════ Création d'un plan ════════ -->
    <Modal :open="showCreate" title="Nouveau plan de test"
           subtitle="Un conteneur pour regrouper des campagnes existantes — vous y assignerez des runs juste après."
           @close="closeCreate">
      <form id="form-create-plan" class="space-y-4" @submit.prevent="submit">
        <label class="block">
          <span class="text-sm font-medium">Nom <span class="text-destructive">*</span></span>
          <input v-model="form.name" required autofocus
                 class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 text-sm focus:border-primary outline-none" />
          <span class="text-xs text-muted-foreground">Ex. : Recette V3, Sprint 42</span>
        </label>
        <label class="block">
          <span class="text-sm font-medium">Description</span>
          <textarea v-model="form.description" rows="2"
                    class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 text-sm focus:border-primary outline-none"></textarea>
        </label>
        <label class="block">
          <span class="text-sm font-medium">Références</span>
          <input v-model="form.refs" placeholder="JIRA-123, …"
                 class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 text-sm focus:border-primary outline-none" />
        </label>
        <p v-if="createError" class="text-sm text-destructive">{{ createError }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="closeCreate">Annuler</Button>
        <Button type="submit" form="form-create-plan" variant="success"
                :loading="creerPlan.isPending.value" :disabled="!form.name.trim()">
          Créer le plan
        </Button>
      </template>
    </Modal>
  </div>
</template>
