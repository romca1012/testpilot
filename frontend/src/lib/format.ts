// Formatage d'affichage — dates, durée, coût.
import { settingValue } from './useSettings'

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  const timeZone = settingValue('instance_timezone', 'Europe/Paris')
  const format = settingValue('date_format', 'DD/MM/YYYY')
  const base: Intl.DateTimeFormatOptions = {
    timeZone, hour: '2-digit', minute: '2-digit', hour12: false,
    day: '2-digit', month: '2-digit', year: 'numeric',
  }
  const parties = new Intl.DateTimeFormat('fr-FR', base).formatToParts(d)
  const valeur = (type: Intl.DateTimeFormatPartTypes) =>
    parties.find((p) => p.type === type)?.value || ''
  const date = format === 'YYYY-MM-DD'
    ? `${valeur('year')}-${valeur('month')}-${valeur('day')}`
    : format === 'MM/DD/YYYY'
      ? `${valeur('month')}/${valeur('day')}/${valeur('year')}`
      : `${valeur('day')}/${valeur('month')}/${valeur('year')}`
  return `${date} ${valeur('hour')}:${valeur('minute')}`
}

export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '—'
  if (seconds < 60) return `${seconds.toFixed(1)} s`
  const m = Math.floor(seconds / 60)
  return `${m} min ${Math.round(seconds % 60)} s`
}

export function formatCost(usd: number | null | undefined): string {
  if (usd == null) return '—'
  return `$${usd.toFixed(4)}`
}

// ── Regroupement chronologique (fils d'activité et d'historique, 2026-08-05) ──────────────────
// ⚠️ Les clés de regroupement sont calculées en UTC, comme les horodatages que le serveur écrit
// (`now_iso`). Mélanger un jour local et un horodatage UTC ferait basculer un résultat de fin de
// soirée dans le lendemain — un écart d'un jour que personne ne remarque, et qui rend deux écrans
// incohérents entre eux.

/** Clé de JOUR d'un horodatage (`2025-07-01`). Vide si l'horodatage l'est. */
export function cleJour(iso: string | null | undefined): string {
  return (iso || '').slice(0, 10)
}

/** Clé de MOIS d'un horodatage (`2025-07`). */
export function cleMois(iso: string | null | undefined): string {
  return (iso || '').slice(0, 7)
}

/** Libellé lisible d'un jour : « Mardi 1 juillet 2025 ». */
export function jourLong(cle: string): string {
  const d = new Date(`${cle}T00:00:00Z`)
  if (isNaN(d.getTime())) return cle
  const s = d.toLocaleDateString('fr-FR',
    { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' })
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Libellé lisible d'un mois : « Juillet 2025 ». */
export function moisLong(cle: string): string {
  const d = new Date(`${cle}-01T00:00:00Z`)
  if (isNaN(d.getTime())) return cle
  const s = d.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric', timeZone: 'UTC' })
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Les `n` derniers jours (clés UTC), du plus ancien au plus récent, `fin` incluse. */
export function derniersJours(n: number, fin: Date = new Date()): string[] {
  const out: string[] = []
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(fin.getTime() - i * 86400000)
    out.push(d.toISOString().slice(0, 10))
  }
  return out
}
