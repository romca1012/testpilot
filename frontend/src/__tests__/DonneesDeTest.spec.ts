/**
 * Lot PT-02a — le tableau des données de test (variables × jeux de données), décisions A26 à A32.
 *
 * Ce que ces tests gardent :
 * 1. le tableau montre chaque variable entre doubles accolades, le jeu « Par défaut » en tête, et la valeur héritée d'une
 *    case vide (A27) ;
 * 2. « Enregistrer » n'envoie QUE les cases modifiées, jeu par jeu ;
 * 3. l'écran ne propose pas un geste que le serveur refuserait : un lecteur consulte, un testeur modifie sans supprimer,
 *    l'administrateur du projet supprime (A30) ;
 * 4. avant de supprimer une variable, l'écran montre les tests qui l'utilisent (A31) ;
 * 5. la page du projet ouvre ce tableau aux membres, sans passer par l'administration (A32).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

const getTestData = vi.fn()
const createTestVariable = vi.fn()
const testVariableUsages = vi.fn()
const deleteTestVariable = vi.fn()
const createTestDataset = vi.fn()
const renameTestDataset = vi.fn()
const setDatasetValues = vi.fn()
const deleteTestDataset = vi.fn()
const previewTestDataImport = vi.fn()
const importTestData = vi.fn()
const replace = vi.fn()
const push = vi.fn()
const session = ref<any>({ authenticated: true, role: 'testeur' })
const actifs = ref(true)
const connu = ref(true)
const projets = ref<any[]>([])
const gardes: Array<(to: any) => any> = []

vi.mock('../lib/api', () => ({
  api: {
    getTestData: (...a: any[]) => getTestData(...a),
    createTestVariable: (...a: any[]) => createTestVariable(...a),
    testVariableUsages: (...a: any[]) => testVariableUsages(...a),
    deleteTestVariable: (...a: any[]) => deleteTestVariable(...a),
    createTestDataset: (...a: any[]) => createTestDataset(...a),
    renameTestDataset: (...a: any[]) => renameTestDataset(...a),
    setDatasetValues: (...a: any[]) => setDatasetValues(...a),
    deleteTestDataset: (...a: any[]) => deleteTestDataset(...a),
    exportTestDataUrl: (id: any) => `/api/projects/${id}/donnees-de-test/export`,
    previewTestDataImport: (...a: any[]) => previewTestDataImport(...a),
    importTestData: (...a: any[]) => importTestData(...a),
  },
  roleSuffisant: (role: string, minimum: string) =>
    ['lecture_seule', 'testeur', 'dev', 'admin'].indexOf(role) >= ['lecture_seule', 'testeur', 'dev', 'admin'].indexOf(minimum),
}))
vi.mock('../lib/useSession', () => ({ useSession: () => ({ session }) }))
vi.mock('../lib/parametresDeTest', () => ({ useParametresDeTest: () => ({ actifs, connu }) }))
vi.mock('../lib/useProjects', () => ({
  useProjects: () => ({ ensureLoaded: vi.fn(), projectById: (id: string) => projets.value.find((p) => String(p.id) === String(id)) }),
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push, replace }),
  useRoute: () => ({ params: { pid: '4' } }),
  onBeforeRouteLeave: (g: (to: any) => any) => { gardes.push(g) },
}))

import TableauDonneesDeTest from '../components/parametres/TableauDonneesDeTest.vue'
import ProjectTestData from '../pages/ProjectTestData.vue'

const projet = (role = 'admin') => ({ id: 4, name: 'Boutique', effective_role: role }) as any
const TABLEAU = () => ({
  variables: [{ id: 1, nom: 'client', description: '' }, { id: 2, nom: 'ville', description: '' }],
  jeux: [
    { id: 10, nom: 'Par défaut', est_defaut: true, valeurs: { 1: 'Martin SARL', 2: 'Lyon' } },
    { id: 11, nom: 'Grosse commande', est_defaut: false, valeurs: { 1: 'Durand Industrie' } },
  ],
})
const stubs = {
  Button: { template: '<button v-bind="$attrs"><slot/></button>', inheritAttrs: false },
  Modal: { props: ['open'], template: '<div v-if="open" data-testid="fenetre"><slot/><slot name="footer"/></div>' },
  ConfirmDialog: { props: ['open', 'title', 'message'], emits: ['confirm', 'cancel'],
                   template: '<div v-if="open" data-testid="confirmation"><h2>{{ title }}</h2><p>{{ message }}</p><button data-testid="confirmer" @click="$emit(\'confirm\')">ok</button></div>' },
}
const ouvrir = async (peutModifier = true, peutSupprimer = true) => {
  const w = mount(TableauDonneesDeTest, { props: { projet: projet(), peutModifier, peutSupprimer }, global: { stubs } })
  await flushPromises()
  return w
}
const champ = (w: any, jeu: number, variable: number) => w.get(`[data-testid="case-${jeu}-${variable}"]`)

beforeEach(() => {
  vi.clearAllMocks()
  gardes.length = 0
  actifs.value = true
  session.value = { authenticated: true, role: 'testeur' }
  projets.value = [projet('testeur')]
  getTestData.mockImplementation(() => Promise.resolve(TABLEAU()))
  setDatasetValues.mockImplementation(() => Promise.resolve(TABLEAU()))
  createTestVariable.mockImplementation(() => Promise.resolve(TABLEAU()))
  createTestDataset.mockImplementation(() => Promise.resolve(TABLEAU()))
  renameTestDataset.mockImplementation(() => Promise.resolve(TABLEAU()))
  testVariableUsages.mockResolvedValue([])
  deleteTestVariable.mockResolvedValue(undefined)
  deleteTestDataset.mockResolvedValue(undefined)
})

describe('Données de test — le tableau', () => {
  // A54 (2026-10-16, changement délibéré) : comme le Data Table — les variables en colonnes, une LIGNE par jeu.
  it('montre les variables en colonnes et le jeu « Par défaut » en première ligne', async () => {
    const w = await ouvrir()

    expect(getTestData).toHaveBeenCalledWith(4)
    expect(w.findAll('[data-testid="variable"]').map((c) => c.text())).toEqual([
      expect.stringMatching(/^\{\{client\}\}/), expect.stringMatching(/^\{\{ville\}\}/)])
    expect(w.findAll('tbody th').map((c) => c.text())).toEqual([expect.stringMatching(/^1Par défaut$/), expect.stringMatching(/^2Grosse commande/)])
    // A56 : chaque ligne porte son numéro, celui que « de la ligne X à Y » emploie au lancement.
    expect(w.get('[data-testid="numero-11"]').text()).toBe('2')
    expect((champ(w, 10, 2).element as HTMLInputElement).value).toBe('Lyon')
  })

  it('falsifiable : une case vide montre en gris la valeur qu’elle reprend de « Par défaut » (A27)', async () => {
    const w = await ouvrir()
    const caseVide = champ(w, 11, 2).element as HTMLInputElement

    expect(caseVide.value).toBe('')
    expect(caseVide.placeholder).toBe('Lyon')
    expect((champ(w, 10, 2).element as HTMLInputElement).placeholder).toBe('')
  })

  it('un projet sans variable le dit en deux mots et ne propose pas encore de jeu', async () => {
    getTestData.mockResolvedValue({ variables: [], jeux: [] })
    const w = await ouvrir()

    expect(w.get('[data-testid="aucune-variable"]').text()).toBe('Aucune variable')
    expect(w.find('table').exists()).toBe(false)
    expect(w.find('[data-testid="jeu-ajouter"]').exists()).toBe(false)
    expect(w.find('[data-testid="variable-ajouter"]').exists()).toBe(true)
  })

  it('falsifiable : « Enregistrer » n’envoie que les cases modifiées, jeu par jeu', async () => {
    const w = await ouvrir()
    expect(w.emitted('modifie')!.at(-1)).toEqual([false])
    await champ(w, 11, 2).setValue(' Lille ')
    await champ(w, 11, 1).setValue('')
    expect(w.emitted('modifie')!.at(-1)).toEqual([true])

    await w.get('[data-testid="donnees-enregistrer"]').trigger('click')
    await flushPromises()

    expect(setDatasetValues).toHaveBeenCalledTimes(1)
    expect(setDatasetValues).toHaveBeenCalledWith(4, 11, { 1: '', 2: 'Lille' })
    expect(w.get('[data-testid="enregistre"]').text()).toBe('Enregistré')
  })

  it('« Annuler » revient à ce qui est enregistré', async () => {
    const w = await ouvrir()
    await champ(w, 10, 2).setValue('Paris')
    await w.findAll('button').find((b) => b.text() === 'Annuler')!.trigger('click')

    expect((champ(w, 10, 2).element as HTMLInputElement).value).toBe('Lyon')
    expect(w.emitted('modifie')!.at(-1)).toEqual([false])
  })

  it('le refus du serveur est montré tel quel et la saisie est gardée', async () => {
    setDatasetValues.mockRejectedValue(new Error('une valeur ne contient pas de guillemet double'))
    const w = await ouvrir()
    await champ(w, 10, 1).setValue('Société "Alpha"')
    await w.get('[data-testid="donnees-enregistrer"]').trigger('click')
    await flushPromises()

    expect(w.get('[data-testid="donnees-erreur"]').text()).toContain('guillemet double')
    expect((champ(w, 10, 1).element as HTMLInputElement).value).toBe('Société "Alpha"')
  })

  it('ajoute une variable et un jeu par leurs routes', async () => {
    const w = await ouvrir()
    await w.get('[data-testid="nouvelle-variable"]').setValue(' pays ')
    await w.get('[data-testid="form-variable"]').trigger('submit')
    await flushPromises()
    expect(createTestVariable).toHaveBeenCalledWith(4, { nom: 'pays' })

    await w.get('[data-testid="jeu-ajouter"]').trigger('click')
    await w.get('[data-testid="jeu-nom"]').setValue(' Client étranger ')
    await w.get('[data-testid="jeu-formulaire"]').trigger('submit')
    await flushPromises()
    expect(createTestDataset).toHaveBeenCalledWith(4, { nom: 'Client étranger' })
    expect(w.find('[data-testid="fenetre"]').exists()).toBe(false)
  })

  it('renomme un jeu, jamais « Par défaut »', async () => {
    const w = await ouvrir()

    expect(w.get('[data-testid="jeu-10"]').findAll('button')).toHaveLength(0)
    await w.get('[data-testid="jeu-11"]').findAll('button').find((b) => b.text() === 'Renommer')!.trigger('click')
    expect((w.get('[data-testid="jeu-nom"]').element as HTMLInputElement).value).toBe('Grosse commande')
    await w.get('[data-testid="jeu-nom"]').setValue('Très grosse commande')
    await w.get('[data-testid="jeu-formulaire"]').trigger('submit')
    await flushPromises()

    expect(renameTestDataset).toHaveBeenCalledWith(4, 11, { nom: 'Très grosse commande' })
  })
})

describe('Données de test — supprimer (corbeille, A31)', () => {
  it('falsifiable : montre les tests qui utilisent la variable AVANT de la supprimer', async () => {
    testVariableUsages.mockResolvedValue([{ id: 1, title: 'Commande' }, { id: 2, title: 'Devis' }])
    const w = await ouvrir()
    await w.findAll('[data-testid="variable"]')[1].findAll('button').find((b) => b.text() === 'Supprimer')!.trigger('click')
    await flushPromises()

    expect(testVariableUsages).toHaveBeenCalledWith(4, 2)
    expect(deleteTestVariable).not.toHaveBeenCalled()
    const dialogue = w.get('[data-testid="confirmation"]').text()
    expect(dialogue).toContain('{{ville}}')
    expect(dialogue).toContain('Utilisée par 2 tests : « Commande », « Devis »')
    expect(dialogue).toContain('« bloqué »')

    await w.get('[data-testid="confirmer"]').trigger('click')
    await flushPromises()
    expect(deleteTestVariable).toHaveBeenCalledWith(4, 2)
    expect(getTestData).toHaveBeenCalledTimes(2)
  })

  it('dit quand aucun test ne l’utilise', async () => {
    const w = await ouvrir()
    await w.findAll('[data-testid="variable"]')[0].findAll('button').find((b) => b.text() === 'Supprimer')!.trigger('click')
    await flushPromises()

    expect(w.get('[data-testid="confirmation"]').text()).toContain('Aucun test ne l’utilise'.replace('’', "'"))
  })

  it('supprime un jeu après confirmation', async () => {
    const w = await ouvrir()
    await w.get('[data-testid="jeu-11"]').findAll('button').find((b) => b.text() === 'Supprimer')!.trigger('click')
    expect(deleteTestDataset).not.toHaveBeenCalled()
    await w.get('[data-testid="confirmer"]').trigger('click')
    await flushPromises()

    expect(deleteTestDataset).toHaveBeenCalledWith(4, 11)
  })
})

describe('Données de test — qui peut quoi (A30)', () => {
  it('falsifiable : un testeur modifie le tableau mais ne voit aucun geste de suppression', async () => {
    const w = await ouvrir(true, false)

    expect(w.findAll('button').map((b) => b.text())).not.toContain('Supprimer')
    expect(w.find('[data-testid="variable-ajouter"]').exists()).toBe(true)
    expect((champ(w, 10, 1).element as HTMLInputElement).disabled).toBe(false)
  })

  it('falsifiable : un lecteur consulte, sans aucun geste, et rien ne part', async () => {
    const w = await ouvrir(false, false)

    expect((champ(w, 10, 1).element as HTMLInputElement).disabled).toBe(true)
    expect(w.findAll('button')).toHaveLength(0)
    expect(w.find('[data-testid="form-variable"]').exists()).toBe(false)
  })
})

describe('Page « Données de test » du projet (A32)', () => {
  const ouvrirPage = async () => {
    const w = mount(ProjectTestData, { global: { stubs: { ...stubs, TableauDonneesDeTest: {
      props: ['projet', 'peutModifier', 'peutSupprimer'], emits: ['modifie'],
      template: '<div data-testid="tableau" :data-modifier="String(peutModifier)" :data-supprimer="String(peutSupprimer)"><button data-testid="modifier" @click="$emit(\'modifie\', true)">m</button></div>' } } } })
    await flushPromises()
    return w
  }

  it('ouvre le tableau à une testeuse du projet : elle modifie, elle ne supprime pas', async () => {
    const w = await ouvrirPage()

    expect(w.get('h1').text()).toBe('Données de test')
    expect(w.get('[data-testid="tableau"]').attributes()).toMatchObject({ 'data-modifier': 'true', 'data-supprimer': 'false' })
    expect(replace).not.toHaveBeenCalled()
  })

  it('falsifiable : le rôle sur le projet décide — lecteur en lecture, administrateur du projet avec la suppression', async () => {
    projets.value = [projet('lecture_seule')]
    expect((await ouvrirPage()).get('[data-testid="tableau"]').attributes()).toMatchObject({ 'data-modifier': 'false', 'data-supprimer': 'false' })

    projets.value = [projet('admin')]
    expect((await ouvrirPage()).get('[data-testid="tableau"]').attributes()).toMatchObject({ 'data-modifier': 'true', 'data-supprimer': 'true' })
  })

  it('falsifiable : paramètres de test éteints, l’adresse ramène au projet', async () => {
    actifs.value = false
    await ouvrirPage()

    expect(replace).toHaveBeenCalledWith('/projects/4')
  })

  it('falsifiable : on ne quitte pas un tableau modifié sans confirmation', async () => {
    const w = await ouvrirPage()
    expect(gardes[0]({ fullPath: '/projects/4/cases' })).toBe(true)

    await w.get('[data-testid="modifier"]').trigger('click')
    expect(gardes[0]({ fullPath: '/projects/4/cases' })).toBe(false)
    await flushPromises()
    await w.get('[data-testid="confirmer"]').trigger('click')

    expect(push).toHaveBeenCalledWith('/projects/4/cases')
  })
})


describe('Données de test — Excel (A37)', () => {
  const fichier = new File(['x'], 'donnees.xlsx')
  async function choisir(w: any) {
    const input = w.get('[data-testid="donnees-fichier"]')
    Object.defineProperty(input.element, 'files', { value: [fichier], configurable: true })
    await input.trigger('change')
    await flushPromises()
  }

  it('« Exporter » mène au fichier du tableau', async () => {
    const w = await ouvrir()

    expect(w.get('[data-testid="donnees-exporter"]').attributes('href')).toBe('/api/projects/4/donnees-de-test/export')
  })

  it('falsifiable : l’aperçu montre ce qui change, puis « Importer » enregistre', async () => {
    previewTestDataImport.mockResolvedValue({ nouvelles_variables: ['quantite'], nouveaux_jeux: ['Export'], erreurs: [],
      cases: [{ variable: 'client', jeu: 'Par défaut', avant: 'Martin SARL', apres: 'Durand' }] })
    importTestData.mockImplementation(() => Promise.resolve(TABLEAU()))
    const w = await ouvrir()
    await choisir(w)

    const apercu = w.get('[data-testid="import-apercu"]').text()
    expect(apercu).toContain('{{quantite}}')
    expect(apercu).toContain('Export')
    expect(w.get('[data-testid="import-cases"] tr').findAll('th, td').map((c: any) => c.text().trim()))
      .toEqual(['{{client}}', 'Par défaut', 'Martin SARL Durand'])
    expect(importTestData).not.toHaveBeenCalled()

    await w.get('[data-testid="import-confirmer"]').trigger('click')
    await flushPromises()
    expect(importTestData).toHaveBeenCalledWith(4, fichier)
    expect(w.find('[data-testid="import-apercu"]').exists()).toBe(false)
  })

  it('falsifiable : une erreur dans le fichier, on ne peut pas importer', async () => {
    previewTestDataImport.mockResolvedValue({ nouvelles_variables: [], nouveaux_jeux: [], cases: [],
      erreurs: ['case B2 : une valeur ne contient pas « {{ »'] })
    const w = await ouvrir()
    await choisir(w)

    expect(w.get('[data-testid="import-erreurs"]').text()).toContain('case B2')
    expect(w.get('[data-testid="import-confirmer"]').attributes('disabled')).toBeDefined()
  })

  it('un lecteur ne voit pas « Importer »', async () => {
    const w = await ouvrir(false, false)

    expect(w.find('[data-testid="donnees-importer"]').exists()).toBe(false)
    expect(w.find('[data-testid="donnees-exporter"]').exists()).toBe(true)
  })
})
