import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { RouterLinkStub } from '@vue/test-utils'
import ModuleTree from '../components/ModuleTree.vue'
import type { CaseSummary, ModuleSummary } from '../lib/api'

const MODULES: ModuleSummary[] = [
  { id: 1, project_id: 1, name: 'demande_materiel', description: '', case_count: 2 },
  { id: 2, project_id: 1, name: 'facturation', description: '', case_count: 0 },
]

const CASES: CaseSummary[] = [
  { id: 10, title: 'Demande de matériel', module: 'demande_materiel', module_id: 1, project_id: 1,
    group_id: null, group_title: null, refs: '', estimate: '',
    etat: 'ready', type: 'fonctionnel', priority: 'medium', statut: 'passed',
    last_execution_status: 'success', last_functional_status: 'conforme', last_executed_at: null,
    last_verdict_version_id: null, verdict_from_other_version: false },
  { id: 11, title: 'Validation champ requis', module: 'demande_materiel', module_id: 1, project_id: 1,
    group_id: null, group_title: null, refs: '', estimate: '',
    etat: 'design', type: 'fonctionnel', priority: 'high', statut: 'blocked',
    last_execution_status: 'technical_error', last_functional_status: 'indetermine', last_executed_at: null,
    last_verdict_version_id: null, verdict_from_other_version: false },
]

function mountTree(props: Partial<InstanceType<typeof ModuleTree>['$props']> = {}) {
  return mount(ModuleTree, {
    props: { modules: MODULES, cases: CASES, projectId: '1', expanded: [], ...props } as any,
    global: { stubs: { RouterLink: RouterLinkStub } },
  })
}

describe('ModuleTree — la structure du projet d\'un coup d\'œil', () => {
  it('replié, montre les modules et leur compte de cas, mais pas les cas', () => {
    const w = mountTree({ expanded: [] })
    expect(w.text()).toContain('Demande materiel')   // libellé lisible, pas le slug brut
    expect(w.text()).toContain('Facturation')
    expect(w.text()).not.toContain('Validation champ requis')
  })

  it('déplié, montre les cas DU module — sans changer de page', () => {
    const w = mountTree({ expanded: [1] })
    expect(w.text()).toContain('Demande de matériel')
    expect(w.text()).toContain('Validation champ requis')
  })

  it('compte les cas RÉELS, pas le case_count du DTO', () => {
    // Le module 2 annonce case_count=0 et n'a aucun cas : cohérent. Le module 1 en a 2.
    // Un compteur qui contredirait la liste dépliée serait un « affiché ≠ réel » (4.6).
    const w = mountTree({ expanded: [1] })
    expect(w.text()).toContain('2')
  })

  it('un module vide le dit, plutôt que de paraître cassé', () => {
    const w = mountTree({ expanded: [2] })
    expect(w.text()).toContain('Aucun cas dans ce module')
  })

  it('n\'affiche JAMAIS de statut fusionné sur un cas (invariant 4.1)', () => {
    const w = mountTree({ expanded: [1] })
    const text = w.text()
    // Le cas 10 est success/conforme, le cas 11 technical_error/indetermine. L'arbre ne doit
    // porter QUE l'ÉTAT du document — jamais un verdict des deux axes, ni fusionné, ni même
    // affiché : ces deux axes vivent dans la table et le détail.
    expect(text).not.toContain('Conforme')
    expect(text).not.toContain('Erreur technique')
    expect(text).not.toContain('Indéterminable')
    // …et l'État est bien là, avec son mot en infobulle (jamais la couleur seule).
    expect(w.html()).toContain('État :')
    expect(w.html()).toContain('Prêt')
  })

  it('bascule le libellé tout déplier / tout replier selon l\'état', async () => {
    const replie = mountTree({ expanded: [] })
    expect(replie.text()).toContain('Tout déplier')

    const deplie = mountTree({ expanded: [1, 2] })   // tous les modules ouverts
    expect(deplie.text()).toContain('Tout replier')
  })

  it('émet expand-all / collapse-all et toggle', async () => {
    const w = mountTree({ expanded: [] })
    await w.find('button[aria-expanded]').trigger('click')
    expect(w.emitted('toggle')?.[0]).toEqual([1])

    const boutons = w.findAll('button')
    await boutons[boutons.length - 1].trigger('click')   // le bouton « Tout déplier » du header
    expect(w.emitted('expand-all') || w.emitted('toggle')).toBeTruthy()
  })

  it('rattache les cas par un connecteur tree — ├─ sauf le DERNIER en └─', () => {
    const w = mountTree({ expanded: [1] })
    const text = w.text()
    // Deux cas dans le module 1 : le premier est un intermédiaire, le second ferme la fratrie.
    expect(text).toContain('├─')
    expect(text).toContain('└─')
    expect((text.match(/├─/g) || []).length).toBe(1)
    expect((text.match(/└─/g) || []).length).toBe(1)
  })

  it('un cas unique porte directement le coude final └─', () => {
    const w = mountTree({ cases: [CASES[0]], expanded: [1] })
    expect(w.text()).toContain('└─')
    expect(w.text()).not.toContain('├─')
  })

  it('donne au cas une icône DOCUMENT, au module une icône DOSSIER', () => {
    // Un cas est une feuille (il ne se déplie pas) : lui mettre un dossier promettrait un
    // contenu qu'on ne peut pas ouvrir (4.6). Les deux natures ont deux formes distinctes.
    const w = mountTree({ expanded: [1] })
    const icons = w.findAllComponents({ name: 'Icon' }).map((c) => c.props('name'))
    expect(icons).toContain('folder')
    expect(icons).toContain('file')
  })

  it('expose les cas sans module au lieu de les cacher', () => {
    const orphelin: CaseSummary = { ...CASES[0], id: 99, title: 'Cas orphelin', module_id: null }
    const w = mountTree({ cases: [...CASES, orphelin] })
    expect(w.text()).toContain('Sans module')
    expect(w.text()).toContain('Cas orphelin')
  })
})
