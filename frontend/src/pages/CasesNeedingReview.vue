<script setup lang="ts">
// « Cas à relire » — amendement §4.3-bis (2026-09-15).
//
// Un cas généré n'est plus approuvé automatiquement s'il porte un point de vigilance réel
// (assertion infalsifiable, réparation à risque, champ/valeur absent du domaine mesuré) : il faut
// alors un humain. Cet écran est ce qui rend ces cas TROUVABLES — sans lui, resserrer
// l'approbation automatique aurait juste déplacé le bug qu'on corrige (cas 82 : bloqué, et
// invisible) plutôt que de le régler.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseARelire } from '../lib/api'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)

const cas = ref<CaseARelire[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    cas.value = await api.casesNeedingReview(pid.value)
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(pid, load)

function ouvrirCas(caseId: number) {
  router.push({ name: 'case-detail', params: { pid: pid.value, id: String(caseId) } })
}
</script>

<template>
  <div class="p-6 md:p-8 max-w-4xl">
    <header>
      <h1 class="text-2xl font-semibold tracking-tight">Cas à relire</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Ces cas ont un <strong class="text-foreground">point de vigilance réel</strong> relevé à la
        génération (assertion qui ne peut jamais échouer, réparation à risque, champ ou valeur
        absent de l'application mesurée) : ils ne sont donc <strong class="text-foreground">pas
        approuvés automatiquement</strong> et ne peuvent pas être lancés depuis un run tant qu'un
        humain n'a pas tranché. Ouvrez un cas pour voir le détail et approuver ou rejeter sa
        version.
      </p>
    </header>

    <div v-if="loading" class="mt-8 space-y-2">
      <div v-for="i in 3" :key="i" class="h-12 rounded-md bg-secondary animate-pulse"></div>
    </div>

    <div v-else-if="error" role="alert"
         class="mt-8 flex flex-wrap items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
      <span>{{ error }}</span>
      <button class="min-h-11 rounded-md border border-destructive/30 px-4 font-medium hover:bg-destructive/10" @click="load">
        Réessayer
      </button>
    </div>

    <div v-else-if="!cas.length" class="mt-8 rounded-xl border border-border bg-card px-5 py-10 text-center">
      <p class="text-sm text-muted-foreground">
        Aucun cas à relire pour l'instant — tous les cas générés sont soit approuvés automatiquement
        (aucun point de vigilance), soit pas encore générés.
      </p>
    </div>

    <table v-else class="mt-6 w-full border-collapse text-sm">
      <thead>
        <tr class="text-xs uppercase tracking-wider text-muted-foreground">
          <th class="text-left font-semibold py-2 px-2.5">Cas</th>
          <th class="text-left font-semibold py-2 px-2.5">Module</th>
          <th class="text-left font-semibold py-2 px-2.5">Pourquoi</th>
          <th class="text-right font-semibold py-2 px-2.5">Points de vigilance</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in cas" :key="c.case_id"
            class="group border-t border-border/60 hover:bg-accent/30 cursor-pointer"
            @click="ouvrirCas(c.case_id)">
          <td class="py-2.5 px-2.5 text-primary group-hover:underline">C{{ c.case_id }} — {{ c.title }}</td>
          <td class="py-2.5 px-2.5 text-muted-foreground">{{ c.module_name || '—' }}</td>
          <td class="py-2.5 px-2.5 text-muted-foreground">{{ c.reason }}</td>
          <td class="py-2.5 px-2.5 text-right tabular-nums">
            <span class="rounded-full bg-warning/15 text-warning text-xs font-semibold px-2 py-0.5">
              {{ c.lint_warnings_count }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
