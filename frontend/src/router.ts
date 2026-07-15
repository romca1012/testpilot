import { createRouter, createWebHistory } from 'vue-router'

// Le PROJET est le contexte de premier niveau, porté par l'URL (§7) : cloisonnement
// structurel et partageable. Les deux onglets Gestion / Exécution vivent SOUS un projet.
const routes = [
  { path: '/', redirect: '/projects' },
  { path: '/projects', name: 'projects', component: () => import('./pages/ProjectsList.vue') },
  { path: '/projects/:pid/cases', name: 'cases', component: () => import('./pages/CasesList.vue') },
  { path: '/projects/:pid/cases/:id', name: 'case-detail', component: () => import('./pages/CaseDetail.vue') },
  { path: '/projects/:pid/executions', name: 'executions', component: () => import('./pages/ExecutionsList.vue') },
  { path: '/projects/:pid/executions/:id', name: 'report', component: () => import('./pages/ReportView.vue') },
  // Rétro-compat : anciens liens sans projet → accueil projets.
  { path: '/cases', redirect: '/projects' },
  { path: '/executions', redirect: '/projects' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
