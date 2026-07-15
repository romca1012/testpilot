<script setup lang="ts">
// Gate de relecture ACTIONNABLE depuis l'UI (option a). Montre l'état du gate et permet
// d'approuver / rejeter la version courante — condition pour pouvoir lancer une exécution.
import { ref } from 'vue'
import Button from './ui/Button.vue'
import { api, type GateOut } from '../lib/api'

const props = defineProps<{ caseId: number; gate: GateOut | null }>()
const emit = defineEmits<{ (e: 'reviewed'): void }>()

const busy = ref(false)
const error = ref('')

async function decide(approved: boolean) {
  busy.value = true
  error.value = ''
  try {
    await api.reviewCase(props.caseId, approved)
    emit('reviewed')
  } catch (e: any) {
    error.value = e?.message || 'Échec de la relecture'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-start gap-2">
      <span
        class="mt-0.5 inline-flex h-5 items-center rounded-full border px-2 text-xs font-medium"
        :class="gate?.allowed
          ? 'border-success/30 bg-success/15 text-success'
          : 'border-warning/40 bg-warning/15 text-warning'"
      >
        {{ gate?.allowed ? 'Approuvé' : 'Relecture requise' }}
      </span>
      <p class="text-sm text-muted-foreground">{{ gate?.reason }}</p>
    </div>

    <!-- Avertissements NON-bloquants sur les assertions générées (décision 0008). Informent le
         relecteur ; ne désactivent jamais l'approbation — le gate reste souverain. -->
    <div v-if="gate?.lint_warnings?.length"
         class="rounded-lg border border-warning/40 bg-warning/10 p-3 space-y-1.5">
      <p class="flex items-center gap-1.5 text-xs font-medium text-warning">
        <span aria-hidden="true">⚠</span>
        Assertion{{ gate.lint_warnings.length > 1 ? 's' : '' }} à vérifier — pourrai{{ gate.lint_warnings.length > 1 ? 'ent' : 't' }} ne jamais échouer
      </p>
      <ul class="space-y-1">
        <li v-for="(w, i) in gate.lint_warnings" :key="i" class="text-xs text-muted-foreground">
          <span class="font-mono text-foreground/80">« {{ w.step }} »</span>
          (ligne {{ w.line }}) — {{ w.message }}
        </li>
      </ul>
      <p class="text-[11px] text-muted-foreground/80">
        Signal indicatif : à vous de juger. L'approbation reste possible.
      </p>
    </div>

    <div v-if="!gate?.allowed" class="flex gap-2">
      <Button variant="primary" :loading="busy" @click="decide(true)">Approuver la version</Button>
      <Button variant="danger" :disabled="busy" @click="decide(false)">Rejeter</Button>
    </div>
    <div v-else class="flex gap-2">
      <Button variant="danger" :disabled="busy" @click="decide(false)">Révoquer / rejeter</Button>
    </div>

    <p v-if="error" class="text-xs text-destructive">{{ error }}</p>
  </div>
</template>
