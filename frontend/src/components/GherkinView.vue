<script setup lang="ts">
// Affichage lisible du .feature (Gherkin) — mise en valeur légère des mots-clés fr.
import { computed } from 'vue'

const props = defineProps<{ content: string }>()

const KEYWORDS = /^(\s*)(Fonctionnalité|Contexte|Scénario|Plan du scénario|Soit|Étant donné|Quand|Alors|Et|Mais)\b/

const lines = computed(() =>
  (props.content || '').split('\n').map((raw) => {
    const m = raw.match(KEYWORDS)
    return { raw, keyword: m ? m[2] : '', indent: m ? m[1] : '' }
  }),
)
</script>

<template>
  <pre class="overflow-x-auto rounded-lg border border-border bg-background p-4 text-xs leading-relaxed font-mono"><template v-for="(l, i) in lines" :key="i"><span v-if="l.keyword"><span>{{ l.indent }}</span><span class="text-primary font-semibold">{{ l.keyword }}</span><span>{{ l.raw.slice(l.indent.length + l.keyword.length) }}</span></span><span v-else :class="l.raw.trim().startsWith('#') ? 'text-muted-foreground' : ''">{{ l.raw }}</span>{{ '\n' }}</template></pre>
</template>
