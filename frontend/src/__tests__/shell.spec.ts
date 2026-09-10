// ⚠️ **Le défaut que ce fichier empêche : la page entièrement blanche.**
//
// Le shell de projet construit ses liens avec le `pid` de l'URL. Une route déclarée hors de
// `/projects/:pid` mais rendue DANS le shell fait lever « Missing required param "pid" » pendant
// le rendu — et l'écran reste vide, sans message. Rien ne le signale : ni le build, ni les tests
// des pages, qui montent chacune leur composant isolément.
//
// Arrivé le 2026-08-04 en ajoutant l'écran Réglages. Ce test compare la liste des routes
// hors-shell aux routes RÉELLEMENT déclarées : ajouter une route de premier niveau sans
// l'inscrire fait échouer ici, au lieu d'échouer chez l'utilisateur.
import { describe, it, expect } from 'vitest'
import { routes } from '../router'
import { ROUTES_SANS_SHELL } from '../lib/shell'

describe('shell de projet — toute route hors /projects/:pid doit s\'en passer', () => {
  it('ne publie plus de page vide « à venir » dans la navigation V1', () => {
    expect(routes.some((r: any) => r.name === 'cases-soon')).toBe(false)
    // ⚠️ Inversé le 2026-09-10 : les Plans de test sont désormais une fonctionnalité réelle
    // (migration 43), plus une action factice — voir `PlansList.vue`/`PlanDetail.vue`.
    expect(routes.some((r: any) => r.name === 'plan-new')).toBe(true)
  })

  it('aucune route de premier niveau n\'est rendue dans le shell', () => {
    const oubliees = routes
      .filter((r: any) => r.name && !String(r.path).startsWith('/projects/:pid'))
      .map((r: any) => String(r.name))
      .filter((nom: string) => !ROUTES_SANS_SHELL.includes(nom))

    expect(oubliees, 'routes à inscrire dans ROUTES_SANS_SHELL (sinon : page blanche)').toEqual([])
  })

  it('et inversement, la liste ne nomme aucune route fantôme', () => {
    const connues = routes.filter((r: any) => r.name).map((r: any) => String(r.name))
    for (const nom of ROUTES_SANS_SHELL) expect(connues).toContain(nom)
  })
})
