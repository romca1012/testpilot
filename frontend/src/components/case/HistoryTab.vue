<script setup lang="ts">
// Onglet « Historique » — vraies données : la timeline des VERSIONS du cas (test_case_version).
// Création = v1 ; Mise à jour = versions suivantes (dont les réparations `repair-agent`, 0014).
// Groupé par date. Pas de bandeau commercial (retiré, comme demandé).
import { computed } from 'vue'
import type { VersionOut } from '../../lib/api'

const props = defineProps<{ versions: VersionOut[] }>()
const emit = defineEmits<{ 'voir-script': [id: number] }>()

function fmtDay(iso: string) {
  const s = new Date(iso).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
  return s.charAt(0).toUpperCase() + s.slice(1)
}
function fmtDateTime(iso: string) {
  const d = new Date(iso)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function dayKey(iso: string) { return new Date(iso).toISOString().slice(0, 10) }

// Versions triées (récentes d'abord), enrichies du type d'action.
const entries = computed(() =>
  [...props.versions]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .map((v) => ({
      ...v,
      isCreation: v.version_number === 1,
      byRepair: v.created_by === 'repair-agent',
    })))

// Groupées par jour.
const groups = computed(() => {
  const map = new Map<string, typeof entries.value>()
  for (const e of entries.value) {
    const k = dayKey(e.created_at)
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(e)
  }
  return [...map.entries()].map(([k, rows]) => ({ day: fmtDay(rows[0].created_at), key: k, rows }))
})
</script>

<template>
  <div class="space-y-8">
    <div v-for="g in groups" :key="g.key">
      <div class="text-sm font-medium text-muted-foreground border-b border-border/60 pb-1">{{ g.day }}</div>

      <div v-for="v in g.rows" :key="v.id" class="mt-4 rounded-lg border border-border bg-surface-raised/40 p-4">
        <div class="flex items-center gap-3 flex-wrap">
          <span v-if="v.isCreation" class="rounded-md bg-success/20 text-success text-xs font-semibold px-2.5 py-1">Création</span>
          <span v-else class="rounded-md bg-secondary text-secondary-foreground text-xs font-semibold px-2.5 py-1">Mise à jour</span>
          <span class="text-sm font-medium">Version : {{ v.version_number }}</span>
          <span class="text-xs text-muted-foreground tabular-nums">{{ fmtDateTime(v.created_at) }}</span>
          <span class="text-xs text-muted-foreground">· {{ v.byRepair ? 'Réparation automatique' : (v.created_by || 'auteur inconnu') }}</span>
          <button v-if="(v.feature_content || '').trim()" class="ml-auto text-xs text-primary hover:underline"
                  @click="emit('voir-script', v.id)">
            Voir le script →
          </button>
        </div>

        <!-- Création : pas de diff, texte explicatif -->
        <p v-if="v.isCreation" class="mt-3 text-sm text-muted-foreground">
          Ce cas de test a été créé. Les modifications apportées ensuite sont affichées ci-dessus,
          séparément pour chaque mise à jour.
        </p>

        <!-- Mise à jour : ce qui a changé (résumé porté par la version) -->
        <div v-else-if="v.change_summary" class="mt-3 overflow-x-auto">
          <table class="w-full text-sm border-collapse">
            <tbody>
              <tr class="border-t border-border/60">
                <td class="py-2 pr-4 align-top text-muted-foreground font-medium whitespace-nowrap">Modification</td>
                <td class="py-2 text-foreground/90">{{ v.change_summary }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="mt-3 text-sm text-muted-foreground italic">Version enregistrée (aucun résumé de modification).</p>
      </div>
    </div>

    <p v-if="!groups.length" class="py-10 text-center text-sm text-muted-foreground">Aucun historique pour ce cas.</p>
  </div>
</template>
