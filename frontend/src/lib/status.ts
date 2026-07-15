// Cœur de la représentation des statuts — mapping PUR des codes techniques vers un
// affichage UTILISATEUR {label court, icône, ton, hint?}. Règles :
//  - jamais la couleur seule (icône + mot + couleur) ;
//  - jamais une valeur d'enum brute à l'écran — tout passe par ces mappings ;
//  - les explications longues vont dans `hint` (infobulle « i »), pas en libellé.
// Les deux axes du §5 (exécution / fonctionnel) restent DEUX mappings distincts.

export type Tone = 'success' | 'destructive' | 'warning' | 'muted' | 'primary'

export interface StatusView {
  label: string
  icon: string // nom d'icône SVG (voir ui/Icon.vue)
  tone: Tone
  hint?: string // explication longue → infobulle
}

const UNKNOWN: StatusView = { label: 'Inconnu', icon: 'circle', tone: 'muted' }

// Étiquettes des DEUX AXES (compréhensibles sans connaître le brief) + leur aide.
export const AXIS = {
  execution: { label: 'Déroulement du test', hint: 'Le test a-t-il pu s\'exécuter techniquement (sans crash, timeout ni erreur d\'environnement) ?' },
  functional: { label: 'Résultat fonctionnel', hint: 'L\'application s\'est-elle comportée comme attendu par le besoin ?' },
}

// ── Axe EXÉCUTION : le test a-t-il pu tourner techniquement ? ─────────────────
const EXECUTION: Record<string, StatusView> = {
  success: { label: 'A tourné', icon: 'check', tone: 'success' },
  technical_error: { label: 'Erreur technique', icon: 'x', tone: 'destructive' },
  not_executed: { label: 'Pas lancé', icon: 'circle', tone: 'muted' },
}

// ── Axe FONCTIONNEL : l'application est-elle conforme au besoin ? ─────────────
const FUNCTIONAL: Record<string, StatusView> = {
  conforme: { label: 'Conforme', icon: 'check', tone: 'success' },
  non_conforme: { label: 'Non conforme', icon: 'x', tone: 'destructive' },
  indetermine: { label: 'Indéterminable', icon: 'half', tone: 'warning',
    hint: 'Le test n\'a pas pu juger le comportement de l\'application (il s\'est interrompu avant).' },
  not_evaluated: { label: 'Non évalué', icon: 'circle', tone: 'muted' },
}

// ── Statut de VALIDATION du cas (cycle de vie) ────────────────────────────────
const VALIDATION: Record<string, StatusView> = {
  // « Non validé » et non « Jamais lancé » : un cas peut avoir été lancé mais échoué
  // techniquement — il reste non validé sans pour autant n'avoir jamais tourné (§5).
  never_executed: { label: 'Non validé', icon: 'circle', tone: 'muted',
    hint: 'Aucune exécution réussie n\'a encore validé ce cas (jamais lancé, ou lancé sans succès).' },
  validated: { label: 'Validé', icon: 'check', tone: 'success',
    hint: 'Le test a été exécuté au moins une fois en entier, sans interruption technique.' },
  to_review: { label: 'À relire', icon: 'half', tone: 'warning' },
}

// ── Priorité de LECTURE d'un cas — surtout pas un ordre d'exécution ───────────
const PRIORITY: Record<string, StatusView> = {
  high: { label: 'Haute', icon: 'dot', tone: 'destructive' },
  medium: { label: 'Moyenne', icon: 'dot', tone: 'muted' },
  low: { label: 'Basse', icon: 'dot', tone: 'muted' },
}
const PRIORITY_HINT =
  "Priorité de lecture et de traitement. Elle n'impose AUCUN ordre d'exécution : " +
  "l'ordre réel des scénarios est celui du fichier .feature."

export function priorityView(code: string | null | undefined): StatusView {
  return { ...((code && PRIORITY[code]) || PRIORITY.medium), hint: PRIORITY_HINT }
}

// ── Origine d'un défaut (defect_origin) — jamais brut à l'écran ────────────────
const DEFECT_ORIGIN: Record<string, StatusView> = {
  vrai_bug: { label: 'Bug dans l\'application', icon: 'x', tone: 'destructive' },
  test_a_reparer: { label: 'Test à corriger', icon: 'half', tone: 'warning',
    hint: 'Le défaut vient du test lui-même (parcours, sélecteur, champ…), pas de l\'application.' },
  indetermine: { label: 'Origine à investiguer', icon: 'circle', tone: 'muted' },
}

// ── Statut de confirmation (confirmation_status) — not_required → masqué ───────
const CONFIRMATION: Record<string, StatusView | null> = {
  pending_human: { label: 'En attente de validation humaine', icon: 'half', tone: 'warning' },
  confirmed: { label: 'Validé par un humain', icon: 'check', tone: 'success' },
  rejected: { label: 'Écarté après revue', icon: 'x', tone: 'muted' },
  not_required: null, // ne rien afficher
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
export function defectOriginView(code: string | null | undefined): StatusView {
  return (code && DEFECT_ORIGIN[code]) || DEFECT_ORIGIN.indetermine
}
export function confirmationView(code: string | null | undefined): StatusView | null {
  return code ? (CONFIRMATION[code] ?? null) : null
}

// Provenance du coût, en clair.
export function costSourceLabel(code: string | null | undefined): string {
  if (code === 'anthropic_api') return 'mesuré via l\'API'
  return 'estimé'
}

// Slug de module → libellé lisible ('demande_materiel' → 'Demande materiel').
export function prettyModule(slug: string | null | undefined): string {
  if (!slug) return ''
  const s = slug.replace(/[_-]+/g, ' ').trim()
  return s.charAt(0).toUpperCase() + s.slice(1)
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
