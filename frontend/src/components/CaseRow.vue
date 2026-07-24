<script setup lang="ts">
// Ligne d'un cas dans un module, repliable sur SES SCÉNARIOS (dernier run).
// Le scénario n'est pas une entité de premier rang : il n'existe qu'au travers d'une
// exécution. On déplie donc la granularité fine là où elle existe vraiment (décision 0006).
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type CaseSummary, type ScenarioResultOut } from '../lib/api'
import { formatDate } from '../lib/format'
import { executionView, functionalView, toneClasses } from '../lib/status'
import Chip from './ui/Chip.vue'
import Icon from './ui/Icon.vue'
import Spinner from './ui/Spinner.vue'
import StatusPair from './StatusPair.vue'
import ValidationBadge from './ValidationBadge.vue'
import PriorityBadge from './PriorityBadge.vue'

const props = defineProps<{ item: CaseSummary; projectId: string }>()
const emit = defineEmits<{ (e: 'changed'): void }>()

const router = useRouter()
const open = ref(false)
const loading = ref(false)
const loaded = ref(false)
const scenarios = ref<ScenarioResultOut[]>([])

async function toggle() {
  open.value = !open.value
  if (!open.value || loaded.value) return
  loading.value = true
  try {
    scenarios.value = await api.getCaseScenarios(props.item.id)
    loaded.value = true
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <!-- Racine <div> et non <li> : c'est la LISTE parente qui porte le <li> (elle y ajoute la
       poignée de réorganisation, décision 0009) — un <li> dans un <li> serait invalide. -->
  <div class="border-t border-border">
    <div class="group flex flex-wrap items-center gap-4 px-5 py-4 transition-colors hover:bg-accent/40">
      <button class="shrink-0 text-muted-foreground/50 hover:text-foreground" @click="toggle"
              :title="open ? 'Replier les scénarios' : 'Déplier les scénarios'" :aria-label="open ? 'Replier les scénarios' : 'Déplier les scénarios'">
        <Icon name="chevron" class="h-4 w-4 transition-transform" :class="open && 'rotate-90'" />
      </button>

      <button class="min-w-0 flex-1 text-left" @click="router.push(`/projects/${projectId}/cases/${item.id}`)">
        <div class="font-medium truncate">{{ item.title }}</div>
        <div class="text-xs text-muted-foreground truncate">
          {{ item.last_executed_at ? formatDate(item.last_executed_at) : 'Jamais exécuté' }}
        </div>
      </button>

      <PriorityBadge :case-id="item.id" :priority="item.priority" editable @updated="emit('changed')" />
      <ValidationBadge :status="item.validation_status" />
      <StatusPair :execution-status="item.last_execution_status" :functional-status="item.last_functional_status" />
    </div>

    <!-- Dépliage : scénarios du dernier run, avec leurs deux axes -->
    <div v-if="open" class="border-t border-border bg-surface/30 px-5 py-3 pl-14">
      <div v-if="loading" class="flex items-center gap-2 text-xs text-muted-foreground">
        <Spinner class="h-3.5 w-3.5" /> Chargement des scénarios…
      </div>
      <p v-else-if="!scenarios.length" class="text-xs text-muted-foreground">
        Aucun scénario : ce cas n'a pas encore été exécuté.
      </p>
      <ul v-else class="space-y-2">
        <li v-for="(s, i) in scenarios" :key="i" class="flex flex-wrap items-center justify-between gap-3">
          <span class="min-w-0 truncate text-sm">{{ s.scenario_name }}</span>
          <span class="flex shrink-0 items-center gap-2">
            <Chip :icon="executionView(s.execution_status).icon" :label="executionView(s.execution_status).label"
                  :cls="toneClasses(executionView(s.execution_status).tone)" />
            <Chip :icon="functionalView(s.functional_status).icon" :label="functionalView(s.functional_status).label"
                  :cls="toneClasses(functionalView(s.functional_status).tone)" />
          </span>
        </li>
      </ul>
    </div>
  </div>
</template>
