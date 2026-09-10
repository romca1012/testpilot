// Conversion heure LOCALE (saisie/affichée dans le formulaire, fuseau du NAVIGATEUR) <-> heure
// UTC (stockée en base, comparée par `scheduler_service.tick()` côté serveur).
//
// ⚠️ **Le bug que ce fichier corrige** (2026-09-10) : le formulaire demandait juste « Heure »,
// sans dire UTC — un humain y tape naturellement SON heure locale. `tick()` compare pourtant à
// `datetime.now(timezone.utc)`. Une planification à « 14h37 » créée en France l'été (UTC+2) ne
// se déclenchait donc réellement qu'à 16h37 locale, sans qu'aucun message ne le dise.
//
// ⚠️ **Limite assumée, pas cachée** : la conversion se fait UNE FOIS, à la création, avec le
// décalage horaire du jour (heure d'été ou d'hiver). Un changement d'heure d'été/hiver ENTRE la
// création et le déclenchement décale l'heure réelle d'1h, comme partout où une heure « murale »
// récurrente est stockée en UTC sans le nom du fuseau. Corriger ça pour de bon demanderait de
// stocker le fuseau (ex. `Europe/Paris`) et de recalculer le décalage à CHAQUE tick — hors
// périmètre choisi ici (le porteur a préféré la conversion simple à ce coût-là).
//
// Deux conventions de jour de semaine coexistent et ne doivent JAMAIS se mélanger sans passer
// par ces tables : `Date.getDay()` (JS, 0=dimanche) et `datetime.weekday()` (Python, stocké en
// base, 0=lundi).
const JOUR_JS_VERS_PY = [6, 0, 1, 2, 3, 4, 5] // index = JS (0=dim..6=sam) -> valeur Python
const JOUR_PY_VERS_JS = [1, 2, 3, 4, 5, 6, 0] // index = Python (0=lun..6=dim) -> valeur JS

export interface HeurePlanif { hour: number; minute: number; weekday: number | null }

/** Locale (ce que l'utilisateur a tapé) -> UTC (ce qu'on envoie au serveur). */
export function localVersUtc(local: HeurePlanif): HeurePlanif {
  const base = new Date()
  base.setHours(local.hour, local.minute, 0, 0)
  if (local.weekday == null) {
    return { hour: base.getUTCHours(), minute: base.getUTCMinutes(), weekday: null }
  }
  // Recale sur LA MÊME SEMAINE que « maintenant » — seul le jour, pas la date, nous importe ici :
  // ce qu'on convertit est un jour de semaine récurrent, jamais une date précise.
  const decalage = JOUR_PY_VERS_JS[local.weekday] - base.getDay()
  base.setDate(base.getDate() + decalage)
  return {
    hour: base.getUTCHours(), minute: base.getUTCMinutes(),
    weekday: JOUR_JS_VERS_PY[base.getUTCDay()],
  }
}

/** UTC (ce que le serveur a renvoyé) -> locale (ce qu'on affiche). Inverse exacte de la
 *  précédente : même décalage horaire, appliqué dans l'autre sens. */
export function utcVersLocal(utc: HeurePlanif): HeurePlanif {
  const base = new Date()
  base.setUTCHours(utc.hour, utc.minute, 0, 0)
  if (utc.weekday == null) {
    return { hour: base.getHours(), minute: base.getMinutes(), weekday: null }
  }
  const decalage = JOUR_PY_VERS_JS[utc.weekday] - base.getUTCDay()
  base.setUTCDate(base.getUTCDate() + decalage)
  return {
    hour: base.getHours(), minute: base.getMinutes(),
    weekday: JOUR_JS_VERS_PY[base.getDay()],
  }
}
