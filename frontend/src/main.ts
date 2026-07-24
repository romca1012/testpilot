import { createApp } from 'vue'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { router } from './router'
import App from './App.vue'
import './assets/css/main.css'

// La couche de données (lot A, 2026-07-24) — la règle est dans `lib/donnees.ts`.
//
// `staleTime` à 30 s : une donnée fraîche de moins de 30 secondes n'est pas rechargée. C'est ce
// qui supprime les doubles chargements shell + page à chaque navigation, sans figer l'écran — un
// run en cours, lui, se rafraîchit par son propre intervalle, pas par ce défaut.
//
// `refetchOnWindowFocus` désactivé : l'outil pilote de vrais navigateurs et de vraies campagnes,
// on passe donc son temps à changer de fenêtre. Recharger à chaque retour ferait clignoter les
// écrans sans rien apprendre — la revalidation qui compte est celle qui suit une MUTATION, et
// elle est explicite dans chaque mutation.
createApp(App)
  .use(router)
  .use(VueQueryPlugin, {
    queryClientConfig: {
      defaultOptions: {
        queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: 1 },
      },
    },
  })
  .mount('#app')
