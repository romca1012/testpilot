<script setup lang="ts">
/**
 * Le dernier verdict a-t-il été produit par une AUTRE version que la version courante ?
 * (décision 0016, option (iii)).
 *
 * Pourquoi ça arrive : les `last_*` du cas sont écrits à CHAQUE run — y compris la tentative
 * d'une réparation qui n'est finalement pas adoptée. Le disque et la base reviennent alors à la
 * version de référence, mais le verdict affiché, lui, décrit la tentative. Il reste VRAI du run
 * qui l'a produit (§4.2) — il est simplement orphelin de la version qui l'a produit.
 *
 * Depuis 0016, `A` referme le cas dangereux : une version qui TOURNE est adoptée, donc le
 * verdict affiché ne peut plus être meilleur que ce que la version courante délivre. Ce qui
 * reste est signalé ici plutôt que corrigé en silence — la ligne du projet depuis 0007 (B+),
 * 0008 (lint) et 0013 (arbitrage humain). On ne recalcule PAS le verdict depuis la version
 * courante : ce serait masquer un run réel.
 */
defineProps<{
  show: boolean
  verdictVersionId: number | null
  currentVersionId: number | null
}>()
</script>

<template>
  <div v-if="show"
       class="rounded-lg border border-warning/40 bg-warning/10 p-3 space-y-1.5">
    <p class="flex items-center gap-1.5 text-xs font-medium text-warning">
      <span aria-hidden="true">⚠</span>
      Ce verdict a été produit par la version v{{ verdictVersionId }}, pas par la version
      courante v{{ currentVersionId }}
    </p>
    <p class="text-xs text-muted-foreground">
      Une réparation a été tentée puis écartée : la référence est revenue à v{{ currentVersionId }}.
      Le verdict ci-dessus reste vrai du run qui l'a produit, mais il ne décrit pas ce que la
      version courante ferait aujourd'hui. Relancez le cas pour un verdict sur v{{ currentVersionId }}.
    </p>
  </div>
</template>
