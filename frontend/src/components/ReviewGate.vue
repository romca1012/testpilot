<script setup lang="ts">
// Gate de relecture ACTIONNABLE depuis l'UI (option a). Montre l'état du gate et permet
// d'approuver / rejeter la version courante — condition pour pouvoir lancer une exécution.
import { ref, watch } from 'vue'
import Button from './ui/Button.vue'
import Hint from './ui/Hint.vue'
import { api, type GateOut } from '../lib/api'

const props = defineProps<{ caseId: number; gate: GateOut | null }>()
const emit = defineEmits<{ (e: 'reviewed'): void }>()

const busy = ref(false)
const error = ref('')

// Le bandeau d'avertissements agrège TROIS familles (0008, 0017, 0021). Sans étiquette, le
// relecteur ne sait pas s'il lit « ton assertion ne peut pas échouer » ou « ce champ n'existe
// pas » — deux problèmes qui n'appellent pas la même décision. Le `kind` vient du serveur ;
// aucune valeur d'enum brute à l'écran (§4.7), d'où cette table.
const FAMILLES: Record<string, string> = {
  // 0008 — l'assertion générée ne peut jamais échouer.
  always_true_constant: 'assertion',
  tautology_negation_in_else: 'assertion',
  then_without_assertion: 'assertion',
  // 0017 — la réparation a touché du code qui marchait.
  step_modifie: 'réparation',
  step_supprime: 'réparation',
  // 0021 — le test référence quelque chose qui n'existe pas dans l'application.
  valeur_option_inexistante: 'donnée',
  champ_inconnu: 'donnée',
}

// Repli explicite : un `kind` inconnu s'affiche quand même. Le taire ferait disparaître un
// avertissement réel parce que le front ignore son étiquette — l'inverse du but.
function familleAvis(kind: string): string {
  return FAMILLES[kind] ?? 'à vérifier'
}

// Budget de réparation autorisé par CETTE approbation (décision 0014, option C). Réparer exige
// d'exécuter, et le gate est le seul à pouvoir autoriser une exécution (§4.3) : c'est donc ici
// que l'autorisation se donne. Pré-rempli au défaut proposé par le serveur — jamais imposé.
const budget = ref<number>(props.gate?.repair_budget_default ?? 2)
watch(() => props.gate, (g) => {
  if (g) budget.value = g.allowed ? g.repair_budget : (g.repair_budget_default ?? 2)
}, { immediate: true })

async function decide(approved: boolean) {
  busy.value = true
  error.value = ''
  try {
    // Le budget n'a de sens qu'à l'approbation : un rejet n'exécute rien, donc ne répare rien.
    await api.reviewCase(props.caseId, approved, '', approved ? budget.value : undefined)
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

    <!-- Avertissements NON-bloquants. Informent le relecteur ; ne désactivent JAMAIS
         l'approbation — le gate reste souverain. Trois familles y arrivent :
           0008 : assertion qui ne peut pas échouer (tautologie)
           0017 : rayon d'explosion d'une réparation (step réécrit / supprimé)
           0021 : champ ou valeur qui n'existe pas dans l'application (smoke-check)
         ⚠️ Le titre disait « Assertions à vérifier — pourraient ne jamais échouer » : vrai pour
         0008 SEUL, faux dès qu'un champ inexistant arrive ici. Un titre qui ment sur son contenu,
         c'est « affiché ≠ réel » (§4.6) — on nomme donc la famille de chaque avis, ligne à ligne. -->
    <div v-if="gate?.lint_warnings?.length"
         class="rounded-lg border border-warning/40 bg-warning/10 p-3 space-y-1.5">
      <p class="flex items-center gap-1.5 text-xs font-medium text-warning">
        <span aria-hidden="true">⚠</span>
        {{ gate.lint_warnings.length }} point{{ gate.lint_warnings.length > 1 ? 's' : '' }} à vérifier avant d'approuver
      </p>
      <ul class="space-y-1">
        <li v-for="(w, i) in gate.lint_warnings" :key="i" class="text-xs text-muted-foreground">
          <span class="mr-1 rounded bg-warning/20 px-1 py-0.5 text-[10px] font-medium text-warning">
            {{ familleAvis(w.kind) }}
          </span>
          <span class="font-mono text-foreground/80">« {{ w.step }} »</span>
          <template v-if="w.line"> (ligne {{ w.line }})</template> — {{ w.message }}
        </li>
      </ul>
      <p class="text-[11px] text-muted-foreground/80">
        Signal indicatif : à vous de juger. L'approbation reste possible.
      </p>
    </div>

    <!-- Budget de réparation — visible AVANT d'approuver : le relecteur doit savoir ce qu'il
         autorise. C'est le gate qui permet la réparation, pas la boucle qui se sert. -->
    <div v-if="!gate?.allowed" class="rounded-lg border border-border bg-surface/40 p-3">
      <label class="flex flex-wrap items-center gap-2 text-xs">
        <span class="inline-flex items-center gap-1.5 text-muted-foreground">
          Autoriser
          <Hint text="Si le test échoue pour une cause technique (sélecteur, navigation, rôle), l'agent peut tenter de le corriger et le rejouer, sans repasser par vous. Il ne touche jamais à l'intention du scénario, et s'arrête net s'il conclut à un bug de l'application. Mettez 0 pour l'interdire." />
        </span>
        <input v-model.number="budget" type="number" min="0" max="10"
               class="w-16 rounded-md border border-border bg-surface px-2 py-1 text-sm" />
        <span class="text-muted-foreground">
          tentative{{ budget > 1 ? 's' : '' }} de réparation automatique
          <span v-if="budget === 0" class="text-warning">— réparation interdite</span>
        </span>
      </label>
    </div>

    <p v-else-if="gate" class="text-xs text-muted-foreground">
      Réparation automatique :
      <span v-if="gate.repair_budget" class="text-foreground">
        {{ gate.repair_budget }} tentative{{ gate.repair_budget > 1 ? 's' : '' }} autorisée{{ gate.repair_budget > 1 ? 's' : '' }}
      </span>
      <span v-else class="text-warning">interdite pour cette version</span>
    </p>

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
