// Cœur de la représentation des statuts — mapping PUR des codes vers un affichage
// {label, icône, ton}. Principe (repris de l'ancien front, porté aux DEUX AXES) :
// jamais la couleur seule — toujours icône + mot + couleur. Les deux axes du §5
// (exécution / fonctionnel) ne sont JAMAIS fusionnés : ce sont deux mappings distincts.

export type Tone = 'success' | 'destructive' | 'warning' | 'muted' | 'primary'

export interface StatusView {
  label: string
  icon: string
  tone: Tone
}

const UNKNOWN: StatusView = { label: 'Inconnu', icon: '?', tone: 'muted' }

// ── Axe EXÉCUTION : le test a-t-il pu tourner techniquement ? ─────────────────
const EXECUTION: Record<string, StatusView> = {
  success: { label: 'Exécuté', icon: '✓', tone: 'success' },
  technical_error: { label: 'Erreur technique', icon: '✗', tone: 'destructive' },
  not_executed: { label: 'Non exécuté', icon: '○', tone: 'muted' },
}

// ── Axe FONCTIONNEL : l'application est-elle conforme au besoin ? ─────────────
const FUNCTIONAL: Record<string, StatusView> = {
  conforme: { label: 'Conforme', icon: '✓', tone: 'success' },
  non_conforme: { label: 'Non conforme', icon: '✗', tone: 'destructive' },
  indetermine: { label: 'Indéterminé', icon: '◐', tone: 'warning' },
  not_evaluated: { label: 'Non évalué', icon: '○', tone: 'muted' },
}

// ── Statut de VALIDATION du cas (cycle de vie) ────────────────────────────────
const VALIDATION: Record<string, StatusView> = {
  never_executed: { label: 'Jamais exécuté', icon: '○', tone: 'muted' },
  validated: { label: 'Validé', icon: '✓', tone: 'success' },
  to_review: { label: 'À relire', icon: '◐', tone: 'warning' },
}

export function executionView(code: string | null | undefined): StatusView {
  return (code && EXECUTION[code]) || EXECUTION.not_executed
}
export function functionalView(code: string | null | undefined): StatusView {
  return (code && FUNCTIONAL[code]) || FUNCTIONAL.not_evaluated
}
export function validationView(code: string | null | undefined): StatusView {
  return (code && VALIDATION[code]) || UNKNOWN
}

// Classes Tailwind par ton — bordure + fond léger + texte (jamais fond plein « OK/KO »).
const TONE_CLASSES: Record<Tone, string> = {
  success: 'border-success/30 bg-success/15 text-success',
  destructive: 'border-destructive/30 bg-destructive/15 text-destructive',
  warning: 'border-warning/40 bg-warning/15 text-warning',
  muted: 'border-border bg-secondary text-muted-foreground',
  primary: 'border-primary/40 bg-primary/10 text-primary',
}

export function toneClasses(tone: Tone): string {
  return TONE_CLASSES[tone]
}
