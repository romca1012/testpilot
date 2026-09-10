<script setup lang="ts">
// COMMENT un résultat a été obtenu : joué par la machine, ou joué à la main par un humain.
//
// ⚠️ **La raison d'être du composant.** La promesse du produit est de ne jamais dire « ça
// marche » sans pouvoir dire comment on l'a su. Ouvrir l'exécution manuelle ne l'affaiblit qu'à
// une condition : qu'un résultat manuel reste **impossible à confondre** avec un résultat
// automatique. D'où une pastille explicite — mot + icône + ton, jamais la couleur seule
// (invariant 4.7) — et non une simple nuance de gris qu'on cesse de voir au bout de deux jours.
//
// Aucune pastille quand il n'y a pas de résultat : « non testé » se lit déjà dans le statut, et
// une pastille vide laisserait croire à un mode inconnu.
import { computed } from 'vue'
import { libelleActeur, resultModeView, toneClasses } from '../lib/status'
import Icon from './ui/Icon.vue'

const props = defineProps<{
  mode: string
  createdBy?: string
  at?: string
}>()

const view = computed(() => resultModeView(props.mode))

// L'infobulle porte QUI et QUAND — l'information qu'un lecteur cherche en second, après « comment
// ça a été obtenu ». Le nom est une signature déclarée, jamais une identité vérifiée (§8 du brief).
const detail = computed(() => {
  if (!view.value) return ''
  const morceaux = [view.value.hint || '']
  if (props.createdBy) morceaux.push(`Par : ${libelleActeur(props.createdBy)}`)
  if (props.at) morceaux.push(`Le : ${props.at.slice(0, 16).replace('T', ' à ')}`)
  return morceaux.filter(Boolean).join('\n')
})
</script>

<template>
  <span v-if="view" class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium"
        :class="toneClasses(view.tone)" :title="detail">
    <Icon :name="view.icon" class="h-3 w-3" />
    {{ view.label }}
  </span>
</template>
