// Montage de test partagé — depuis que les écrans lisent la COUCHE DE DONNÉES (lot A,
// 2026-07-24), un composant monté sans elle plante au `setup()`.
//
// ⚠️ La configuration de test n'est PAS celle de production, et c'est délibéré :
//   • `retry: false`      — un test qui échoue doit échouer TOUT DE SUITE. Avec les tentatives
//                           de production, une erreur attendue mettrait des secondes à remonter
//                           et le test passerait son temps à attendre.
//   • `gcTime: 0`         — aucun cache ne survit d'un test à l'autre. Un cache partagé rendrait
//                           l'ordre des tests significatif : le pire défaut d'une suite, parce
//                           qu'il ne se voit qu'au moment où on en ajoute un.
//   • un client NEUF par montage, pour la même raison.
import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

export function monter(composant: any, options: any = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return mount(composant, {
    ...options,
    global: {
      ...(options.global || {}),
      plugins: [...(options.global?.plugins || []), [VueQueryPlugin, { queryClient: client }]],
    },
  })
}
