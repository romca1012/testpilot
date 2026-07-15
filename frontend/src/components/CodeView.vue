<script setup lang="ts">
// Coloration syntaxique MAISON (zéro dépendance) pour les fichiers générés :
// Gherkin (.feature) et Python (_steps.py). Scroll interne, hauteur bornée.
import { computed } from 'vue'

const props = withDefaults(defineProps<{ content: string; lang: 'gherkin' | 'python' }>(),
  { lang: 'gherkin' })

const GHERKIN_KW = /^(\s*)(Fonctionnalité|Contexte|Scénario|Plan du scénario|Exemples|Soit|Étant donné|Quand|Alors|Et|Mais)\b/
const PY_DECORATOR = /^(\s*)(@[\w.]+)/
const PY_KW = /\b(from|import|def|return|if|elif|else|for|while|in|not|and|or|is|None|True|False|assert|with|as|try|except|finally|raise|class|lambda|yield|pass|continue|break|global)\b/g

function escape(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// Colore les chaînes ; hors chaînes, applique un coloriseur passé en argument.
function withStrings(s: string, outside: (seg: string) => string): string {
  return s.split(/("[^"]*"|'[^']*')/g).map((p) =>
    (p.startsWith('"') || p.startsWith("'"))
      ? `<span class="text-success">${escape(p)}</span>`
      : outside(p),
  ).join('')
}

function renderGherkin(raw: string): string {
  const m = raw.match(GHERKIN_KW)
  if (m) {
    const rest = raw.slice(m[1].length + m[2].length)
    return `${m[1]}<span class="text-primary font-semibold">${escape(m[2])}</span>${withStrings(rest, escape)}`
  }
  if (raw.trim().startsWith('#')) return `<span class="text-muted-foreground">${escape(raw)}</span>`
  return withStrings(raw, escape)
}

function renderPython(raw: string): string {
  if (raw.trim().startsWith('#')) return `<span class="text-muted-foreground">${escape(raw)}</span>`
  const dec = raw.match(PY_DECORATOR)
  if (dec) {
    const rest = raw.slice(dec[1].length + dec[2].length)
    return `${dec[1]}<span class="text-warning">${escape(dec[2])}</span>${withStrings(rest, escape)}`
  }
  // Hors chaînes : surligne les mots-clés (sur texte déjà échappé).
  return withStrings(raw, (seg) => escape(seg).replace(PY_KW, '<span class="text-primary">$1</span>'))
}

const html = computed(() => {
  const render = props.lang === 'python' ? renderPython : renderGherkin
  return (props.content || '').split('\n').map(render).join('\n')
})
</script>

<template>
  <pre class="max-h-[28rem] overflow-auto rounded-lg border border-border bg-background p-4 text-xs leading-relaxed font-mono"><code v-html="html" /></pre>
</template>
