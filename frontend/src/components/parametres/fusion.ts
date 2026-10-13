// Le projet tel que le serveur vient de l'enregistrer — SANS perdre le rôle de l'utilisateur sur ce projet.
//
// Revue du 2026-10-13, reproduit : `PATCH /api/projects/:id` rend `effective_role: ''` (la route ne recalcule pas le rôle).
// Fusionner sa réponse telle quelle effaçait donc le rôle connu, l'écran retombait sur le rôle global, et un administrateur DU
// PROJET (sans être administrateur de l'installation) voyait ses onglets passer en lecture seule après le premier
// enregistrement — alors que le serveur acceptait toujours ses modifications.
import type { ProjectSummary } from '../../lib/api'

export function projetEnregistre(avant: ProjectSummary, rendu: Partial<ProjectSummary> | null | undefined): ProjectSummary {
  return { ...avant, ...(rendu || {}), effective_role: avant.effective_role }
}
