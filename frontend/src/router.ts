import { createRouter, createWebHistory } from 'vue-router'

// Le PROJET est le contexte de premier niveau, porté par l'URL (§7) : cloisonnement
// structurel et partageable. Les deux onglets Gestion / Exécution vivent SOUS un projet.
//
// « Gestion des cas » se lit comme un explorateur : l'arbre Modules → Cas est rendu par
// `AppShell` dans la barre latérale (sous les onglets), pas par une route layout — deux bandeaux
// de navigation côte à côte gaspillaient l'espace. Les routes restent donc à plat, et AppShell
// n'affiche l'arbre que pour les routes listées dans `CASES_ROUTES` (séparation §8 préservée).
const routes = [
  // Accueil : auto-sélection si un seul projet, sinon page de gestion des projets.
  { path: '/', name: 'home', component: () => import('./pages/Home.vue') },
  { path: '/projects', name: 'projects', component: () => import('./pages/ProjectsList.vue') },

  // Première vue d'un projet : sa STRUCTURE (les modules), pas un mur de cas.
  { path: '/projects/:pid/cases', name: 'cases', component: () => import('./pages/ModulesOverview.vue') },
  // Vue secondaire, transverse aux modules : le référentiel à plat + ses compteurs.
  // Déclarée avant `cases/:id` par lisibilité (le segment statique l'emporte de toute façon).
  { path: '/projects/:pid/cases/all', name: 'cases-all', component: () => import('./pages/CasesList.vue') },
  { path: '/projects/:pid/cases/:id', name: 'case-detail', component: () => import('./pages/CaseDetail.vue') },
  { path: '/projects/:pid/modules/:mid', name: 'module-detail', component: () => import('./pages/ModuleDetail.vue') },

  { path: '/projects/:pid/executions', name: 'executions', component: () => import('./pages/ExecutionsList.vue') },
  { path: '/projects/:pid/executions/:id', name: 'report', component: () => import('./pages/ReportView.vue') },
  // Arbitrage humain des diagnostics (0013). SOUS Exécution : on juge le résultat d'un run,
  // pas le référentiel — la séparation §8 reste structurelle.
  { path: '/projects/:pid/confirmations', name: 'confirmations', component: () => import('./pages/ConfirmationsList.vue') },

  // Rétro-compat : anciens liens sans projet → accueil projets.
  { path: '/cases', redirect: '/projects' },
  { path: '/executions', redirect: '/projects' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
