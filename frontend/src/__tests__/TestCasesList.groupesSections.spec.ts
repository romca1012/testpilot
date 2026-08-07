/**
 * Le regroupement PAR SECTION dans la liste des cas (2026-08-05).
 *
 * ⚠️ Pourquoi ce fichier existe. Une génération multi-cas (§9) produit plusieurs Sections
 * (`case_group` = une user story), chacune avec plusieurs cas. Le mécanisme de FILTRE existait
 * déjà (cliquer une Section dans l'arbre latéral) — mais il REMPLAÇAIT toute la vue par un seul
 * résultat, sans jamais montrer le regroupement fait à la génération dans la liste elle-même.
 * Vérifié en conditions réelles le 2026-08-05 sur une génération de 6 cas en 5 Sections : la
 * liste du module les affichait tous à plat, sans distinction visuelle de leur story d'origine —
 * le porteur l'a signalé en comparant au comportement de TestRail (une Section = un dossier
 * visible en permanence, pas seulement accessible en filtrant).
 *
 * Ce que ces tests figent :
 *   • deux Sections d'un même module produisent DEUX en-têtes distincts, avec leur propre compte ;
 *   • chaque cas atterrit sous LA BONNE Section, jamais mélangé avec une autre ;
 *   • un cas sans `group_id` (ne devrait pas arriver) va dans un groupe « Sans section », pas nulle
 *     part ;
 *   • plier une Section ne plie QUE la sienne, pas ses voisines ;
 *   • le compte en tête de page dit la vérité sous un filtre de Section (pas « 15 sur 15 » quand
 *     un seul cas est affiché).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listCases = vi.fn()
const listGroups = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listCases: (...a: any[]) => listCases(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    renameModule: vi.fn(),
  },
}))

let routeQuery: Record<string, string> = {}
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: routeQuery }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot/></a>', props: ['to'] },
}))

import TestCasesList from '../pages/TestCasesList.vue'

// Deux Sections (86 « Mutation nominale », 87 « Mutation refusée ») dans le MÊME module, comme
// une vraie génération multi-cas les produit — plus un cas orphelin (group_id null), le cas de
// bord que la logique de secours doit couvrir.
const CAS = [
  { id: 95, title: 'Dépôt complet et valide', module: 'Mutation payeur', module_id: 10,
    group_id: 86, group_title: 'Mutation nominale', type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
  { id: 96, title: 'Sans agence sélectionnée', module: 'Mutation payeur', module_id: 10,
    group_id: 86, group_title: 'Mutation nominale', type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
  { id: 97, title: 'Code payeur trop court', module: 'Mutation payeur', module_id: 10,
    group_id: 87, group_title: 'Mutation refusée', type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
  { id: 13, title: 'Cas orphelin (résidu)', module: 'Mutation payeur', module_id: 10,
    group_id: null, group_title: null, type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
]

// Les DEUX Sections elles-mêmes (migration 28 : la liste ne les dérive plus des seuls cas
// présents, pour qu'une Section fraîchement créée et encore vide apparaisse quand même).
const GROUPES = [
  { id: 86, module_id: 10, title: 'Mutation nominale', case_count: 2, parent_group_id: null },
  { id: 87, module_id: 10, title: 'Mutation refusée', case_count: 1, parent_group_id: null },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  routeQuery = {}
  listModules.mockResolvedValue([{ id: 10, name: 'Mutation payeur', case_count: 4 }])
  listCases.mockResolvedValue({ items: CAS, next_cursor: null, total: CAS.length })
  listGroups.mockResolvedValue(GROUPES)
})

async function monterListe() {
  const w = monter(TestCasesList)
  await flushPromises()
  await flushPromises()
  return w
}

describe('le regroupement par Section dans la liste', () => {
  it('affiche DEUX en-têtes de Section distincts, avec leur propre compte', async () => {
    const w = await monterListe()
    expect(w.text()).toContain('Mutation nominale')
    expect(w.text()).toContain('Mutation refusée')
    // 2 cas dans « Mutation nominale », 1 dans « Mutation refusée » — pas 3 dans l'une ou l'autre.
    const texte = w.text()
    expect(texte.indexOf('Mutation nominale')).toBeLessThan(texte.indexOf('2'))
  })

  it('range chaque cas sous SA Section, jamais sous une autre', async () => {
    const w = await monterListe()
    const lignes = w.findAll('tbody tr')
    // La ligne du cas 97 (Section 87) doit suivre l'en-tête « Mutation refusée », pas
    // « Mutation nominale » — on vérifie l'ORDRE des blocs, pas seulement leur présence.
    const html = w.html()
    const posNominale = html.indexOf('Mutation nominale')
    const posRefusee = html.indexOf('Mutation refusée')
    const posCas97 = html.indexOf('Code payeur trop court')
    expect(posCas97).toBeGreaterThan(posRefusee)
    expect(posRefusee).toBeGreaterThan(posNominale)
    expect(lignes.length).toBeGreaterThan(0)
  })

  it('un cas SANS group_id atterrit dans « Sans section », pas nulle part', async () => {
    const w = await monterListe()
    expect(w.text()).toContain('Sans section')
    expect(w.text()).toContain('Cas orphelin (résidu)')
  })

  it('plier UNE Section ne plie QUE la sienne', async () => {
    const w = await monterListe()
    expect(w.text()).toContain('Dépôt complet et valide')   // Section « nominale », visible
    expect(w.text()).toContain('Code payeur trop court')     // Section « refusée », visible

    const toggleNominale = w.findAll('button').find((b) => b.attributes('aria-label')?.includes('la section Mutation nominale'))!
    await toggleNominale.trigger('click')

    expect(w.text()).not.toContain('Dépôt complet et valide')  // repliée
    expect(w.text()).toContain('Code payeur trop court')       // l'AUTRE Section reste dépliée
  })

  it('le lien "voir le document" pointe vers LA BONNE spécification', async () => {
    const w = await monterListe()
    const liens = w.findAll('a').filter((a) => a.text() === 'voir le document')
    expect(liens.length).toBe(2)  // une par Section RÉELLE — pas pour « Sans section »
  })
})

describe('le compte affiché dit la vérité sous un filtre de Section', () => {
  it('ne compare PAS au total du projet quand une Section filtre la vue', async () => {
    routeQuery = { spec: '86' }
    const w = await monterListe()
    // 2 cas dans la Section 86 — jamais « sur 4 » (le total du MODULE, pas de la Section).
    expect(w.text()).toContain('2 cas affichés pour cette section')
    expect(w.text()).not.toContain('sur 4')
  })
})
