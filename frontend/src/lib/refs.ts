// `refs` (cas, campagnes) est un texte libre style « JIRA-123, JIRA-456 » — jamais découpé nulle
// part jusqu'ici (2026-08-11). Un seul endroit qui sait lire ce format, réutilisé partout.
export function parseRefs(refs: string): string[] {
  return (refs || '').split(',').map((r) => r.trim()).filter(Boolean)
}
