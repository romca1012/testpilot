<script setup lang="ts">
// Infobulle discrète : petite icône « i » ; l'explication apparaît au survol.
// Positionnée SOUS l'icône (évite le clipping par les conteneurs au-dessus) et
// alignée à GAUCHE (lisible pour du texte explicatif multi-lignes).
defineProps<{ text: string }>()
</script>

<template>
  <span class="group/hint relative inline-flex align-middle">
    <span
      class="grid h-3.5 w-3.5 cursor-help place-items-center rounded-full border border-border text-[9px] font-semibold leading-none text-muted-foreground"
      tabindex="0"
      aria-label="Aide"
    >i</span>
    <span
      role="tooltip"
      class="pointer-events-none absolute left-0 top-full z-40 mt-1.5 w-max max-w-[15rem] rounded-md border border-border bg-surface-overlay px-2.5 py-1.5 text-left text-xs font-normal normal-case leading-snug text-foreground opacity-0 shadow-xl transition-opacity duration-150 group-hover/hint:opacity-100 group-focus-within/hint:opacity-100"
    >{{ text }}</span>
  </span>
</template>
