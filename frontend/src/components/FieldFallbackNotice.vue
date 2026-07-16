<script setup lang="ts">
/**
 * Replis « libellé → nom technique » d'un run (décision 0007, phase B+).
 *
 * NON-bloquant : informe le lecteur, ne touche jamais au verdict à deux axes — à l'image des
 * `lint_warnings` du gate. Doit s'afficher même quand le run est VERT : Behave n'affiche pas les
 * logs d'un scénario réussi, or c'est précisément le cas où un champ renommé côté application
 * serait retrouvé par son libellé et la régression absorbée sans témoin (verdict 0007 n°2).
 */
defineProps<{ fallbacks: string[] }>()
</script>

<template>
  <div v-if="fallbacks.length"
       class="rounded-lg border border-warning/40 bg-warning/10 p-3 space-y-1.5">
    <p class="flex items-center gap-1.5 text-xs font-medium text-warning">
      <span aria-hidden="true">⚠</span>
      {{ fallbacks.length > 1
         ? `${fallbacks.length} champs ont été résolus par leur libellé`
         : 'Un champ a été résolu par son libellé' }}, pas par son nom technique
    </p>
    <!-- Les DEUX lectures, toujours : n'en donner qu'une orienterait le diagnostic à tort. -->
    <p class="text-xs text-muted-foreground">
      Deux lectures possibles : le step est paramétré avec le libellé affiché au lieu du nom
      technique du champ (à corriger dans le test), ou le champ a réellement été renommé côté
      application (régression à vérifier). Le test a pu continuer dans les deux cas.
    </p>
    <ul class="space-y-1">
      <li v-for="(f, i) in fallbacks" :key="i" class="font-mono text-xs text-foreground/80">
        {{ f }}
      </li>
    </ul>
  </div>
</template>
