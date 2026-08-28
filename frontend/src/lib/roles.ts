import type { Role } from './api'

export interface PermissionLigne {
  groupe: string
  action: string
  minimum: Role
  description: string
}

// Miroir documentaire de la hiérarchie réellement appliquée par le serveur. Cette matrice ne
// décide jamais un droit : elle explique les contrôles access.require_role/require_project_role.
export const PERMISSIONS_ROLES: PermissionLigne[] = [
  { groupe: 'Projets', action: 'Consulter les projets autorisés', minimum: 'lecture_seule', description: 'Voir les cas, campagnes et résultats des projets dont le compte est membre.' },
  { groupe: 'Structure', action: 'Créer et renommer modules et sections', minimum: 'testeur', description: 'Organiser le référentiel sans supprimer son historique.' },
  { groupe: 'Cas de test', action: 'Créer, déplacer et modifier les cas', minimum: 'testeur', description: 'Créer, organiser et mettre à jour le référentiel de tests.' },
  { groupe: 'Structure', action: 'Supprimer modules, sections et cas', minimum: 'admin', description: 'Placer à la corbeille des ressources et leur historique ; action réservée aux administrateurs du projet.' },
  { groupe: 'Exécutions', action: 'Créer des campagnes et saisir des résultats', minimum: 'testeur', description: 'Préparer une campagne, exécuter les tests et enregistrer leurs résultats.' },
  { groupe: 'Exécutions', action: 'Clôturer et rouvrir une campagne', minimum: 'testeur', description: 'Figer temporairement une campagne sans supprimer son historique.' },
  { groupe: 'Résultats', action: 'Retirer une pièce jointe', minimum: 'admin', description: 'Retirer un fichier justificatif sans modifier le résultat signé auquel il appartenait.' },
  { groupe: 'Automatisation', action: 'Générer et modifier les scripts', minimum: 'dev', description: 'Automatiser un cas, modifier le Gherkin/Python et accéder aux outils de qualité.' },
  { groupe: 'Administration', action: 'Gérer les projets et leurs accès', minimum: 'admin', description: 'Créer les projets et administrer leurs membres.' },
  { groupe: 'Administration', action: 'Gérer les utilisateurs et les réglages', minimum: 'admin', description: 'Créer, désactiver et administrer les comptes et les paramètres de l’instance.' },
]

export const DESCRIPTION_ROLE: Record<Role, string> = {
  lecture_seule: 'Consulter les projets autorisés, sans aucune modification.',
  testeur: 'Créer et modifier les cas, campagnes et résultats dans les projets autorisés.',
  dev: 'Droits Testeur, avec accès aux scripts automatisés et à la qualité de génération.',
  admin: 'Administrer l’instance, les utilisateurs, les projets et leurs accès.',
}
