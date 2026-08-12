<script setup lang="ts">
// Bouton-icône à zone de clic fixe (audit DA 2026-08-12) : avant, chaque écran choisissait son
// propre padding pour une icône cliquable (chevron, tri, colonnes…) — p-1, p-0.5, p-1.5 selon le
// fichier, donc une zone de clic qui variait de 24px à 32px+ pour un rôle identique.
withDefaults(defineProps<{
  label: string // aria-label obligatoire : un bouton-icône seul n'a pas de nom accessible sinon
  variant?: 'ghost' | 'secondary' | 'danger'
  // `md` (32px, défaut) pour une icône isolée. `sm` (24px) pour une RANGÉE dense où plusieurs
  // boutons-icônes se répètent à côté d'un libellé (ex. l'arbre Module → Section) : à 32px, 3-4
  // icônes côte à côte grignotaient trop de largeur et tronquaient le nom (repéré le 2026-08-12,
  // « Mutation payeur » devenait « Mutatio… »).
  size?: 'sm' | 'md'
  disabled?: boolean
}>(), { variant: 'ghost', size: 'md', disabled: false })

const VARIANTS = {
  ghost: 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-accent/50',
  secondary: 'bg-surface-raised text-foreground hover:bg-accent border border-border',
  // Action destructive (ex. supprimer) : discret au repos, alerte seulement au survol/focus.
  danger: 'bg-transparent text-muted-foreground hover:text-destructive hover:bg-destructive/10',
}

const SIZES = { sm: 'h-6 w-6', md: 'h-8 w-8' }
</script>

<template>
  <button
    :aria-label="label"
    :title="label"
    :disabled="disabled"
    class="inline-flex items-center justify-center rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    :class="[VARIANTS[variant], SIZES[size]]"
  >
    <slot />
  </button>
</template>
