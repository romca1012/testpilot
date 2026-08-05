<script setup lang="ts">
// Jeu d'icônes SVG cohérent (remplace les glyphes unicode ✓✗○◐, qui font « brut »).
defineProps<{ name: string; class?: string }>()

// Icônes de contour (stroke=currentColor) sauf 'half' qui remplit un demi-disque.
const STROKE = new Set(['check', 'x', 'circle', 'chevron', 'folder', 'file', 'plus', 'image'])
</script>

<template>
  <svg viewBox="0 0 24 24" :class="$props.class" fill="none" aria-hidden="true"
       :stroke="STROKE.has(name) ? 'currentColor' : 'none'" stroke-width="2.2"
       stroke-linecap="round" stroke-linejoin="round">
    <template v-if="name === 'check'"><path d="M5 12.5l4.2 4.2L19 6.8" /></template>
    <template v-else-if="name === 'x'"><path d="M7 7l10 10M17 7L7 17" /></template>
    <template v-else-if="name === 'circle'"><circle cx="12" cy="12" r="7.5" /></template>
    <template v-else-if="name === 'chevron'"><path d="M9 6l6 6-6 6" /></template>
    <template v-else-if="name === 'half'">
      <circle cx="12" cy="12" r="7.5" stroke="currentColor" stroke-width="2.2" />
      <path d="M12 4.5a7.5 7.5 0 0 1 0 15z" fill="currentColor" />
    </template>
    <template v-else-if="name === 'dot'"><circle cx="12" cy="12" r="4" fill="currentColor" /></template>
    <template v-else-if="name === 'plus'"><path d="M12 5v14M5 12h14" /></template>
    <!-- 'folder' = conteneur (un module contient des cas). 'file' = feuille (un cas ne se
         déplie pas dans l'arbre) : deux formes distinctes, parce que la nature diffère. -->
    <template v-else-if="name === 'folder'">
      <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </template>
    <template v-else-if="name === 'file'">
      <path d="M13 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V9m-6-6l6 6m-6-6v6h6" />
    </template>
    <!-- 'image' distingue une pièce jointe VISIBLE d'un coup d'œil (capture d'écran) d'un
         document quelconque ('file') — utile dans la liste des pièces jointes d'un résultat. -->
    <template v-else-if="name === 'image'">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9.5" r="1.4" fill="currentColor" stroke="none" />
      <path d="M3 16l5-5 4 4 5-6 4 5" />
    </template>
  </svg>
</template>
