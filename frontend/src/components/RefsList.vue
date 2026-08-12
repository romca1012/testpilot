<script setup lang="ts">
// Références d'un cas/d'une campagne, rendues CLIQUABLES si un gabarit d'URL est réglé
// (Réglages d'instance) — sinon du texte brut, comme avant ce chantier (2026-08-11).
//
// N'affiche RIEN pour une liste vide : chaque appelant garde son propre texte de repli
// (« Aucune », ligne masquée…), déjà en place avant ce composant — pas de comportement dupliqué.
import { computed, onMounted } from 'vue'
import { parseRefs } from '../lib/refs'
import { useSettings } from '../lib/useSettings'

const props = defineProps<{ refs: string }>()
const { get, ensureLoaded } = useSettings()
onMounted(() => ensureLoaded())

// Un gabarit qui ne mène pas à une vraie URL http(s) (mal saisi, ou juste du texte) ne doit
// jamais produire un lien cassé ou dangereux — repli sur le texte brut, en silence.
const items = computed(() => {
  const gabarit = get('reference_url_template')
  return parseRefs(props.refs).map((texte) => {
    if (!gabarit) return { texte, href: null as string | null }
    const href = gabarit.replace('{ref}', encodeURIComponent(texte))
    return { texte, href: /^https?:\/\//i.test(href) ? href : null }
  })
})
</script>

<template>
  <span class="inline-flex flex-wrap items-baseline gap-x-2 gap-y-1">
    <template v-for="(it, i) in items" :key="i">
      <a v-if="it.href" :href="it.href" target="_blank" rel="noopener noreferrer"
         class="text-primary hover:underline" @click.stop>{{ it.texte }}</a>
      <span v-else>{{ it.texte }}</span>
    </template>
  </span>
</template>
