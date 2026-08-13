import { createRouter, createWebHistory } from 'vue-router'

// Le PROJET est le contexte de premier niveau, porté par l'URL (§7) : cloisonnement
// structurel et partageable. Les deux onglets Gestion / Exécution vivent SOUS un projet.
//
// « Gestion des cas » se lit comme un explorateur : l'arbre Modules → Cas est rendu par
// `AppShell` dans la barre latérale (sous les onglets), pas par une route layout — deux bandeaux
// de navigation côte à côte gaspillaient l'espace. Les routes restent donc à plat, et AppShell
// n'affiche l'arbre que pour les routes listées dans `CASES_ROUTES` (séparation §8 préservée).
export const routes = [
  // Accueil : auto-sélection si un seul projet, sinon page de gestion des projets.
  { path: '/', name: 'home', component: () => import('./pages/Home.vue') },
  { path: '/projects', name: 'projects', component: () => import('./pages/ProjectsList.vue') },

  // Première vue d'un projet : la LISTE des cas façon TestRail (option (a), 2026-07-20). Le shell
  // « Cas de test » (CasesShell) est choisi par App.vue pour ces routes.
  { path: '/projects/:pid/cases', name: 'cases', component: () => import('./pages/TestCasesList.vue') },
  // « Générer des cas de test » = l'IA depuis une spec (texte ou fichier) → analyse → génération
  // en 2 passes → gate.
  { path: '/projects/:pid/cases/new', name: 'case-new', component: () => import('./pages/AddTestCase.vue') },
  // « Ajouter un cas de test » = saisie MANUELLE (métier, sans IA).
  { path: '/projects/:pid/cases/manual', name: 'case-manual', component: () => import('./pages/AddManualCase.vue') },
  // Onglets de nav non couverts par ce lot (Aperçu, Tâche à faire, Jalons, Rapports) → « à venir ».
  { path: '/projects/:pid/cases/soon', name: 'cases-soon', component: () => import('./pages/CasesSoon.vue') },
  { path: '/projects/:pid/cases/:id', name: 'case-detail', component: () => import('./pages/CaseDetailTR.vue') },
  // La SPÉCIFICATION : le document source, d'où naissent 1 à N cas (décision 0022). Son CRUD
  // existait côté serveur depuis le 2026-07-20 sans qu'aucun écran ne l'appelle — le modèle
  // « une spec → plusieurs cas » était donc inatteignable par l'interface.
  // Chemin `specs/` distinct de `cases/` : sous `cases/`, il serait entré en concurrence avec
  // `cases/:id` (une spécification n'est pas un cas, et l'URL doit le dire).
  { path: '/projects/:pid/specs/:id', name: 'spec-detail', component: () => import('./pages/SpecDetail.vue') },
  // Les RÉGLAGES D'INSTANCE (2026-08-04) : ils valent pour toute l'installation, pas pour un
  // projet. L'URL est donc hors de `/projects/:pid` — la ranger sous un projet laisserait croire
  // qu'un autre projet peut avoir un autre compte de service.
  { path: '/settings', name: 'settings', component: () => import('./pages/Settings.vue') },
  // Gestion des comptes (2026-08-07) — Admin seulement ; le SERVEUR le vérifie (403 sinon), cet
  // écran ne fait qu'éviter de proposer un lien qui serait de toute façon refusé.
  { path: '/utilisateurs', name: 'utilisateurs', component: () => import('./pages/Utilisateurs.vue') },

  // La CORBEILLE (§7) : supprimer masque, restaurer annule, détruire est un geste à part.
  { path: '/projects/:pid/corbeille', name: 'corbeille', component: () => import('./pages/Corbeille.vue') },

  // ── Routes HÉRITÉES, redirigées vers leur équivalent actuel ──────────────────────────────
  // Règle posée le 2026-07-20 : toute route doit être atteignable par un chemin CLAIR depuis
  // l'interface. Ces deux-là ne l'étaient plus (aucun lien nulle part) — les laisser vivantes
  // aurait maintenu deux interfaces concurrentes pour la même chose.
  //   • `cases/all` : la liste plate est désormais LA liste des cas.
  //   • `modules/:mid` : le module se consulte via l'arbre, qui filtre la liste.
  { path: '/projects/:pid/cases/all', redirect: (to: any) => ({ name: 'cases', params: { pid: to.params.pid } }) },
  { path: '/projects/:pid/modules/:mid',
    redirect: (to: any) => ({ name: 'cases', params: { pid: to.params.pid },
                              query: { module: String(to.params.mid) } }) },

  // « Exécutions et résultats de test » — module TestRail (Aperçu / détail run / formulaires).
  { path: '/projects/:pid/executions', name: 'executions', component: () => import('./pages/RunsOverview.vue') },
  { path: '/projects/:pid/executions/new', name: 'run-new', component: () => import('./pages/AddTestRunForm.vue') },
  { path: '/projects/:pid/plans/new', name: 'plan-new', component: () => import('./pages/AddTestPlanForm.vue') },
  { path: '/projects/:pid/runs/:id', name: 'run-detail', component: () => import('./pages/RunDetail.vue') },
  // Les trois vues d'une campagne que TestRail nomme Status / Activity / Progress. Elles sont de
  // VRAIES routes et non un `?tab=` : chacune charge sa propre donnée, et une adresse partagée
  // doit rouvrir exactement l'écran qu'on avait sous les yeux.
  { path: '/projects/:pid/runs/:id/activite', name: 'run-activite', component: () => import('./pages/RunActivite.vue') },
  { path: '/projects/:pid/runs/:id/progression', name: 'run-progression', component: () => import('./pages/RunProgression.vue') },
  // ⚠️ **UN CAS DANS UNE CAMPAGNE** — le « test » (`T…`), distinct du cas (`C…`). L'URL le dit :
  // le test n'existe QUE sous une campagne, alors que `cases/:id` existe seul. C'est cette
  // distinction qui manquait — cliquer un cas dans une campagne menait au rapport technique d'une
  // exécution ou à la fiche du cas, jamais à « ce cas, ici ».
  { path: '/projects/:pid/runs/:id/tests/:caseId', name: 'run-test', component: () => import('./pages/RunTestDetail.vue') },
  { path: '/projects/:pid/executions/:id', name: 'report', component: () => import('./pages/ReportView.vue') },

  // Qualité de génération : l'évolution de l'outil (taux de réussite technique au premier jet),
  // dérivée des vraies exécutions. Onglet de suivi, jamais un chiffre fabriqué.
  { path: '/projects/:pid/quality', name: 'quality', component: () => import('./pages/QualityDashboard.vue') },

  // Rétro-compat : anciens liens sans projet → accueil projets.
  { path: '/cases', redirect: '/projects' },
  { path: '/executions', redirect: '/projects' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
