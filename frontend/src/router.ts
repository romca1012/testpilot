import { createRouter, createWebHistory } from 'vue-router'

// Deux sections de premier niveau — la séparation §8 Gestion / Exécution est structurelle.
const routes = [
  { path: '/', redirect: '/cases' },
  { path: '/cases', name: 'cases', component: () => import('./pages/CasesList.vue') },
  { path: '/cases/:id', name: 'case-detail', component: () => import('./pages/CaseDetail.vue') },
  { path: '/executions', name: 'executions', component: () => import('./pages/ExecutionsList.vue') },
  { path: '/executions/:id', name: 'report', component: () => import('./pages/ReportView.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
