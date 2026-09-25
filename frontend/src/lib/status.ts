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
  // Lot 02 (D1) : un PRÉREQUIS d'environnement manque (module non installé, connexion impossible…).
  // Ni un défaut de l'application, ni un test cassé : ne pas le confondre avec « Erreur technique ».
  blocked: { label: 'Bloqué (prérequis)', icon: 'half', tone: 'warning',
    hint: 'Le test n\'a pas pu être joué : un prérequis de l\'environnement n\'est pas rempli (module non '
        + 'installé, connexion impossible, données déjà présentes…). Ce n\'est ni un défaut de '
        + 'l\'application ni un test cassé : il faut préparer l\'environnement, puis relancer.' },
  not_executed: { label: 'Pas lancé', icon: 'circle', tone: 'muted' },
}

// ── Axe FONCTIONNEL : l'application est-elle conforme au besoin ? ─────────────
const FUNCTIONAL: Record<string, StatusView> = {
  conforme: { label: 'Conforme', icon: 'check', tone: 'success' },
  non_conforme: { label: 'Non conforme', icon: 'x', tone: 'destructive' },
  indetermine: { label: 'Indéterminable', icon: 'half', tone: 'warning',
    hint: 'Le test n\'a pas pu juger le comportement de l\'application (il s\'est interrompu avant).' },
  // 4ᵉ verdict (§2bis) : le test a bien tourné, mais SA donnée a été refusée — l'application
  // n'est PAS en cause. On nomme un test à corriger, on n'accuse plus l'application à tort.
  donnee_invalide: { label: 'Donnée du test invalide', icon: 'half', tone: 'warning',
    hint: 'Le test a tourné, mais sa donnée a été refusée (format attendu, champ requis, filtre de saisie…). '
        + 'L\'application n\'est PAS en cause : c\'est le TEST qu\'il faut corriger, pas l\'application.' },
  not_evaluated: { label: 'Non évalué', icon: 'circle', tone: 'muted' },
}

// ── ÉTAT du cas : le cycle de vie du DOCUMENT (New / Design / Ready / Obsolete) ───────────────
// ⚠️ Il remplace l'ancien « statut de validation », qui était DÉRIVÉ des exécutions : on ne
// pouvait ni le poser ni le retirer, et il se donnait des airs de cycle de vie sans en être un.
// Celui-ci n'a AUCUN automatisme — modifier un cas ne le remet pas à zéro. C'est l'humain qui
// le fait avancer, et personne d'autre.
const ETAT: Record<string, StatusView> = {
  new: { label: 'Nouveau', icon: 'circle', tone: 'muted',
    hint: 'Le cas vient d\'être créé. Cet état ne dit RIEN de ses exécutions : c\'est l\'avancement de sa rédaction.' },
  design: { label: 'Conception', icon: 'half', tone: 'warning',
    hint: 'Le cas est en cours de rédaction.' },
  ready: { label: 'Prêt', icon: 'check', tone: 'success',
    hint: 'Le cas est considéré comme rédigé et utilisable.' },
  obsolete: { label: 'Obsolète', icon: 'x', tone: 'muted',
    hint: 'Le cas ne correspond plus à ce que fait l\'application. Il reste consultable.' },
}
export const ETAT_ORDER = ['new', 'design', 'ready', 'obsolete']

// ── TYPE du cas : ce qu'il VÉRIFIE (axe de vérification, jamais une méthode) ──────────────────
// Reprend la coupure réelle de TestRail : Functional/Regression/Acceptance/Smoke d'un côté,
// Performance/Security/Usability/Compatibility de l'autre. « Automated » et « Exploratory » ne
// sont pas ici — ce sont des façons de tester, pas des catégories de vérification.
const TYPE: Record<string, StatusView> = {
  fonctionnel: { label: 'Fonctionnel', icon: 'check', tone: 'muted',
    hint: 'Vérifie que le système fait ce qui est attendu (métier, régression, recette, smoke).' },
  non_fonctionnel: { label: 'Non fonctionnel', icon: 'dot', tone: 'muted',
    hint: 'Évalue une qualité transversale : performance, sécurité, ergonomie, compatibilité.' },
}
export const TYPE_ORDER = ['fonctionnel', 'non_fonctionnel']

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
  // ⚠️ DÉDUCTION, pas constat : une assertion qui échoue peut venir de l'application, d'un test
  // qui attend la mauvaise chose, ou de l'environnement. L'infobulle doit le DIRE — sinon
  // l'écran affirme ce que la machine a seulement supposé (0013).
  vrai_bug: { label: 'Bug dans l\'application', icon: 'x', tone: 'destructive',
    hint: 'Déduit de l\'échec, pas constaté : le test attendait autre chose que ce qu\'il a obtenu. '
        + 'Peut aussi venir d\'un test qui attend la mauvaise chose. À confirmer ou infirmer.' },
  test_a_reparer: { label: 'Test à corriger', icon: 'half', tone: 'warning',
    hint: 'Le défaut vient du test lui-même (parcours, sélecteur, champ…), pas de l\'application.' },
  indetermine: { label: 'Origine à investiguer', icon: 'circle', tone: 'muted' },
}

// ── CAUSE d'un échec (`cause_category`) — jamais brute à l'écran (§4.7) ───────────────────────
// ⚠️ Miroir de `LABELS` dans `src/testpilot/verdict/defect_taxonomy.py` : un test Python compare les
// deux tables, une cause ajoutée d'un seul côté fait échouer la suite.
const CAUSE: Record<string, string> = {
  precondition_non_remplie: 'Prérequis non rempli (environnement)',
  erreur_serveur_5xx: 'Erreur interne du serveur (HTTP 5xx)',
  missing_server_context: 'Contexte serveur manquant',
  donnee_refusee: 'Donnée du test refusée (à corriger)',
  broken_test_code: 'Erreur dans le code du test',
  wrong_navigation: 'Navigation erronée',
  wrong_field_name: 'Champ/sélecteur introuvable',
  missing_role: 'Rôle/permission manquant',
  assertion_mismatch: 'Assertion métier en échec',
  resolveur_incomplet: 'Test non automatisable (résolveur)',
  refus_non_explique: 'Refus non expliqué (à instruire)',
  aucun_constat: 'Aucune vérification exécutée',
  unknown: 'Indéterminé',
}
/** Libellé français d'une cause ; une cause inconnue du front reste lisible (« à instruire »). */
export function causeLabel(code: string | null | undefined): string {
  return (code && CAUSE[code]) || 'Cause à instruire'
}

export function executionView(code: string | null | undefined): StatusView {
  return (code && EXECUTION[code]) || EXECUTION.not_executed
}
export function functionalView(code: string | null | undefined): StatusView {
  return (code && FUNCTIONAL[code]) || FUNCTIONAL.not_evaluated
}
export function etatView(code: string | null | undefined): StatusView {
  return (code && ETAT[code]) || ETAT.new
}
export function typeView(code: string | null | undefined): StatusView {
  return (code && TYPE[code]) || UNKNOWN
}
export function defectOriginView(code: string | null | undefined): StatusView {
  return (code && DEFECT_ORIGIN[code]) || DEFECT_ORIGIN.indetermine
}

// ⚠️ `angleLabel` A ÉTÉ SUPPRIMÉE le 2026-08-04, avec le champ `angle` lui-même (migration 26).
// **TestRail n'a pas de champ « Angle »**, et le cap produit est la parité. Ce que l'angle
// prétendait dire est porté par le `Type` ci-dessus et par le TITRE, qui est une phrase métier.
// La génération multi-cas ne s'appuiera pas dessus non plus : elle découpe par user story.

// ── Statut de test « façon TestRail » — DÉRIVÉ des DEUX axes, pas une fusion ─────────────────
// Passed / Failed / Retest / Blocked / Untested. ⚠️ Ce n'est PAS un badge « OK/KO » qui cache les
// axes (§4.1) : c'est un RÉSUMÉ pour la vue run/liste, tandis que le détail à deux axes reste
// visible dans l'onglet Tests & Résultats du cas. Dérivation documentée (déroulement + fonctionnel),
// jamais devinée — « Untested » par défaut quand l'info ne permet pas de trancher.
export type TestStatusCode = 'passed' | 'failed' | 'retest' | 'blocked' | 'untested'

const TEST_STATUS: Record<TestStatusCode, { label: string; color: string; badge: string }> = {
  passed:   { label: 'Passed',   color: 'var(--success)',         badge: 'bg-success/15 text-success' },
  failed:   { label: 'Failed',   color: 'var(--destructive)',     badge: 'bg-destructive/15 text-destructive' },
  retest:   { label: 'Retest',   color: 'var(--warning)',         badge: 'bg-warning/15 text-warning' },
  blocked:  { label: 'Blocked',  color: 'var(--muted-foreground)', badge: 'bg-secondary text-muted-foreground' },
  untested: { label: 'Untested', color: 'var(--untested)',        badge: 'bg-[hsl(var(--untested)/0.15)] text-[hsl(var(--untested))]' },
}
// Ordre canonique (légende du donut, colonnes de filtre).
export const TEST_STATUS_ORDER: TestStatusCode[] = ['passed', 'blocked', 'retest', 'failed', 'untested']

// ⚠️ `testStatusCode` A ÉTÉ SUPPRIMÉE le 2026-07-24. La projection des deux axes en une
// étiquette vivait ICI, en TypeScript. Filtrer une liste par statut côté serveur — ce qu'exige
// la pagination — aurait obligé à la réécrire en SQL : deux implémentations de la même règle,
// qui divergent le jour où l'une évolue, et dont l'écart est invisible (les deux « marchent »).
//
// La règle vit désormais dans `verdict/status.py`, le serveur la calcule, et l'API expose
// `statut` sur les cas, les exécutions, les scénarios et les cas d'une campagne. Ce module ne
// garde que la PRÉSENTATION : quel libellé, quelle couleur pour un statut donné.

/** Libellé + couleur d'un statut rendu par le serveur. Un statut inconnu retombe sur
 *  « untested » plutôt que de casser l'affichage sur une valeur brute. */
export function testStatusMeta(code: string) {
  return TEST_STATUS[(code as TestStatusCode)] || TEST_STATUS.untested
}

export function testStatusView(statut: string) {
  return TEST_STATUS[(statut as TestStatusCode)] || TEST_STATUS.untested
}

// ── CONFIANCE du verdict (lot 05, D5) ─────────────────────────────────────────────────────────────────────────
// Un vert n'a pas toujours la même valeur : obtenu par la cascade déterministe (nominale), par un repli adaptatif
// (un LLM a retrouvé un élément renommé) ou au second essai après un timeout. Ce n'est NI un statut NI un axe : le
// statut de lecture reste `passed`, le serveur calcule `a_confirmer` et l'écran l'affiche — il ne redérive rien.
// Les libellés sont DUPLIQUÉS dans `verdict/status.py::LIBELLES_CONFIANCE` (test d'accord).
export const A_CONFIRMER_LABEL = 'Réussi — à confirmer'

const CONFIANCE_LABEL: Record<string, string> = {
  nominale: 'Nominale',
  auto_resolue: 'Résolue automatiquement',
  apres_retry: 'Obtenue au second essai',
}

/** Libellé français d'une confiance ; une valeur inconnue retombe sur « Nominale », jamais sur la valeur brute. */
export function confianceLabel(code: string | undefined): string {
  return CONFIANCE_LABEL[code || 'nominale'] || CONFIANCE_LABEL.nominale
}

/** Le libellé et le badge d'un statut, avec la réserve « à confirmer » d'un vert non nominal. Seul un `passed` la porte :
 *  un échec obtenu par repli reste un échec. */
export function statutAffiche(statut: string, aConfirmer = false) {
  const meta = testStatusMeta(statut)
  if (statut === 'passed' && aConfirmer) {
    return { ...meta, label: A_CONFIRMER_LABEL, badge: 'bg-warning/15 text-warning' }
  }
  return meta
}

// ── MODE D'EXÉCUTION : la machine a joué le test, ou un humain l'a joué à la main ─────────────
// ⚠️ **C'est l'étiquette qui empêche le statut de mentir.** Dans la plupart des outils de test
// management, « Passed » est une case qu'un humain coche : rien ne dit si quoi que ce soit a
// tourné. Ici, les deux façons d'exécuter existent — et on ne les confond jamais, parce que le
// mode est STOCKÉ en base avec le résultat, pas deviné à l'affichage.
//
// ⚠️ **« Manuelle » et non « Déclaré »** (vocabulaire arrêté le 2026-08-04). « Déclaré » traitait
// en aveu ce qui est un vrai travail de test : un humain a suivi les étapes contre la vraie
// application. Le mot poussait à cacher la moitié manuelle de la recette plutôt qu'à la tenir.
const RESULT_MODE: Record<string, StatusView> = {
  automatique: { label: 'Automatique', icon: 'check', tone: 'success',
    hint: 'Un test a tourné tout seul contre l\'application. La trace complète est consultable.' },
  manuelle: { label: 'Manuelle', icon: 'half', tone: 'warning',
    hint: 'Un humain a joué ce test à la main, en suivant ses étapes. Aucune trace machine : '
        + 'le statut vaut ce que vaut la personne qui l\'a constaté.' },
}
/** Rend `null` quand il n'y a AUCUN résultat — l'écran n'affiche alors pas de pastille du tout.
 *  Une pastille « inconnu » laisserait croire qu'un résultat existe mais qu'on ignore son mode. */
export function resultModeView(code: string | null | undefined): StatusView | null {
  return (code && RESULT_MODE[code]) || null
}

// Un « auteur » de résultat ou de campagne peut être un acteur NON HUMAIN — jamais son nom
// technique brut à l'écran (même invariant que le mode : mot + sens, pas un identifiant système).
// Deux figures à ce jour : la réparation automatique d'un cas (`repair-agent`, 2026-08) et, depuis
// la migration 43, une campagne lancée par une planification récurrente (`scheduler:<nom>`).
export function libelleActeur(createdBy: string | null | undefined): string {
  if (!createdBy) return '—'
  if (createdBy === 'repair-agent') return 'réparation automatique'
  if (createdBy.startsWith('scheduler:')) return `Lancement planifié — ${createdBy.slice('scheduler:'.length)}`
  return createdBy
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
