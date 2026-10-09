<script setup lang="ts">
// D32 (validée par le porteur le 2026-10-09) — « Valeurs refusées à confirmer ».
//
// L'application a refusé une valeur que le MÉTIER d'un cas demande. Ce n'est plus une erreur de nos
// données de test : c'est un bug probable de l'application, ou un métier à corriger. Apprendre ce
// refus d'office ferait éviter la valeur aux tests suivants — le bug disparaîtrait des résultats sans
// avoir été vu. Le refus attend donc ici la décision d'un humain ; tant qu'il attend, rien ne l'apprend.
import { onMounted, ref, watch } from 'vue'
import { api, type DecisionRefus, type RefusAConfirmer } from '../lib/api'

const props = defineProps<{ projectId: string }>()

const refus = ref<RefusAConfirmer[]>([])
const erreur = ref('')
const occupe = ref(false)

async function charger() {
  erreur.value = ''
  try {
    refus.value = await api.refusAConfirmer(props.projectId)
  } catch (e: any) {
    erreur.value = e?.message || 'Chargement des refus impossible.'
  }
}
onMounted(charger)
watch(() => props.projectId, charger)

async function decider(r: RefusAConfirmer, decision: DecisionRefus) {
  occupe.value = true
  erreur.value = ''
  try {
    refus.value = await api.deciderRefus(props.projectId, r, decision)
  } catch (e: any) {
    erreur.value = e?.message || 'Décision non enregistrée.'
  } finally {
    occupe.value = false
  }
}
</script>

<template>
  <section v-if="refus.length || erreur" class="mt-10" aria-labelledby="refus-titre">
    <h2 id="refus-titre" class="text-lg font-semibold tracking-tight">Valeurs refusées à confirmer</h2>
    <p class="mt-1 text-sm text-muted-foreground">
      L'application a refusé une valeur que le <strong class="text-foreground">métier d'un cas demande</strong> :
      c'est un <strong class="text-foreground">bug probable</strong> de l'application, ou un métier à corriger.
      Tant que vous n'avez pas tranché, ce refus n'est <strong class="text-foreground">pas appris</strong> — les
      tests suivants continueront d'essayer cette valeur, et donc de signaler le problème.
    </p>

    <p v-if="erreur" role="alert" class="mt-3 text-sm text-destructive">{{ erreur }}</p>

    <ul class="mt-4 space-y-3">
      <li v-for="r in refus" :key="`${r.route}|${r.champ}|${r.type_contrainte}|${r.valeur_contrainte}|${r.valeur_refusee}`"
          class="rounded-xl border border-border bg-card px-4 py-3 text-sm">
        <p>
          Valeur <strong class="font-mono">« {{ r.valeur_refusee }} »</strong> refusée pour le champ
          <span class="font-mono">{{ r.champ }}</span>, page <span class="font-mono">{{ r.route }}</span>
          <span v-if="r.occurrences > 1" class="text-muted-foreground">({{ r.occurrences }} fois)</span>.
        </p>
        <p v-if="r.preuve" class="mt-1 text-muted-foreground">Message de l'application : « {{ r.preuve }} »</p>
        <div class="mt-3 flex flex-wrap gap-2">
          <button :disabled="occupe"
                  class="min-h-11 rounded-md border border-border px-4 font-medium hover:bg-accent disabled:opacity-50"
                  @click="decider(r, 'confirmee')">
            C'est une règle de l'application — l'apprendre
          </button>
          <button :disabled="occupe"
                  class="min-h-11 rounded-md border border-destructive/30 px-4 font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
                  @click="decider(r, 'rejetee')">
            C'est un bug — ne pas l'apprendre
          </button>
        </div>
      </li>
    </ul>
  </section>
</template>
