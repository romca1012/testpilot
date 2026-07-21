/**
 * Garde de NON-RÉGRESSION : le formulaire de création doit S'ARRÊTER à la pause métier.
 *
 * ⚠️ Pourquoi ce fichier existe. La génération se fait désormais en deux passes (décision 0022
 * n°5) : le job passe par `awaiting_metier` et **n'avance plus tout seul**. Un formulaire qui ne
 * connaît que `running` / `done` / `failed` traite cet état comme « en cours » et tourne dans le
 * vide indéfiniment — l'utilisateur voit un spinner pour un travail qui n'arrivera jamais.
 *
 * Ces tests montent la vraie page et vérifient les trois temps : spec → pause éditable → Gherkin.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listModules = vi.fn()
const addCase = vi.fn()
const getGenerationJob = vi.fn()
const validateMetier = vi.fn()
const createModule = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    addCase: (...a: any[]) => addCase(...a),
    getGenerationJob: (...a: any[]) => getGenerationJob(...a),
    validateMetier: (...a: any[]) => validateMetier(...a),
    createModule: (...a: any[]) => createModule(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push }),
}))

import AddTestCase from '../pages/AddTestCase.vue'

const DRAFT = {
  title: 'Réception et délivrance d\'une commande',
  preconditions: 'Un utilisateur connecté.',
  steps: ['Ouvrir le formulaire', 'Envoyer la demande'],
  expected_result: 'La demande est enregistrée.',
  angle: 'nominal',
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  listModules.mockResolvedValue([{ id: 1, name: 'Demande matériel' }])
  addCase.mockResolvedValue({ job_id: 'J1', status: 'running', case_id: null, error: '' })
  createModule.mockResolvedValue({ id: 9, name: 'Nouveau module', project_id: 1, case_count: 0 })
})

/** Monte, saisit une spec, soumet, puis laisse tomber une réponse de job. */
async function jusquAuJob(job: any) {
  const w = mount(AddTestCase)
  await flushPromises()
  await w.find('textarea').setValue('La spécification à tester')
  await w.find('form').trigger('submit')
  await flushPromises()

  getGenerationJob.mockResolvedValue(job)
  await vi.advanceTimersByTimeAsync(2100)
  await flushPromises()
  return w
}

describe('AddTestCase — la pause métier (0022 n°5)', () => {
  it('S\'ARRÊTE sur awaiting_metier et affiche le document ÉDITABLE', async () => {
    const w = await jusquAuJob({ status: 'awaiting_metier', metier: DRAFT, case_id: null, error: '' })

    // Le document est rendu dans des champs, pas en lecture seule : la pause ne sert à rien si
    // on ne peut pas corriger.
    const inputs = w.findAll('input')
    expect(inputs.some((i) => (i.element as HTMLInputElement).value === DRAFT.title)).toBe(true)
    expect(inputs.some((i) => (i.element as HTMLInputElement).value === 'Ouvrir le formulaire')).toBe(true)
    expect(w.text()).toContain('Valider et générer le test')
    expect(push).not.toHaveBeenCalled()
  })

  it('envoie le document CORRIGÉ, pas celui proposé par l\'IA', async () => {
    // Tout l'intérêt de la pause : ce que l'humain écrit fait foi.
    validateMetier.mockResolvedValue({ job_id: 'J1', status: 'running', case_id: null, error: '' })
    const w = await jusquAuJob({ status: 'awaiting_metier', metier: DRAFT, case_id: null, error: '' })

    const titre = w.findAll('input').find(
      (i) => (i.element as HTMLInputElement).value === DRAFT.title)!
    await titre.setValue('MON titre corrigé')
    await w.findAll('button').find((b) => b.text().includes('Valider et générer'))!.trigger('click')
    await flushPromises()

    expect(validateMetier).toHaveBeenCalledWith('J1', expect.objectContaining({
      title: 'MON titre corrigé',
    }))
  })

  it('REFUSE de valider un document amputé de ses étapes', async () => {
    // Titre + étapes + résultat attendu sont obligatoires (0022 n°3.c) : un cas sans eux ne
    // vérifie rien. Le bouton est désactivé plutôt que de laisser le serveur refuser après coup.
    const w = await jusquAuJob({ status: 'awaiting_metier', metier: DRAFT, case_id: null, error: '' })

    // Re-interrogé à chaque tour : après un clic le DOM est re-rendu et les références
    // collectées d'avance pointent sur des nœuds détruits (et les index ont glissé).
    for (let garde = 0; garde < 10; garde++) {
      const croix = w.findAll('button').filter((b) => b.text() === '✕')
      if (!croix.length) break
      await croix[0].trigger('click')
    }

    const valider = w.findAll('button').find((b) => b.text().includes('Valider et générer'))!
    expect(valider.attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('un cas sans eux ne')
  })

  it('emmène au GATE quand le job est terminé, jamais à l\'exécution', async () => {
    await jusquAuJob({ status: 'done', case_id: 42, metier: null, error: '' })

    expect(push).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'case-detail', params: { pid: '1', id: '42' } }))
  })

  it('affiche l\'erreur et rend la main quand la génération échoue', async () => {
    const w = await jusquAuJob({ status: 'failed', case_id: null, metier: null,
                                error: 'le document métier rendu est incomplet' })

    expect(w.text()).toContain('le document métier rendu est incomplet')
    expect(w.find('textarea').exists()).toBe(true) // retour au formulaire, pas un cul-de-sac
  })
})

describe("AddTestCase — un projet NEUF n'est plus un cul-de-sac", () => {
  it("DIT qu'aucun module n'existe au lieu d'offrir une liste vide", async () => {
    // Avant : select vide, `submit()` sortait sur `if (!moduleId) return` — bouton sans effet,
    // aucun message. Un projet fraîchement créé était donc inutilisable, en silence.
    listModules.mockResolvedValue([])
    const w = mount(AddTestCase)
    await flushPromises()

    expect(w.text()).toContain("Ce projet n'a pas encore de module")
    expect(w.find('select').exists()).toBe(false)
  })

  it('CRÉE le module puis enchaîne sur la génération', async () => {
    listModules.mockResolvedValue([])
    const w = mount(AddTestCase)
    await flushPromises()

    const nom = w.findAll('input').find((i) => i.attributes('placeholder')?.includes('Nom du module'))!
    await nom.setValue('Demande de matériel')
    await w.find('textarea').setValue('La spécification')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createModule).toHaveBeenCalledWith('1', 'Demande de matériel')
    expect(addCase).toHaveBeenCalledWith(9, 'La spécification', '')
  })

  it("REMONTE l'erreur de création du module sans lancer de génération payante", async () => {
    // Le module est créé AVANT la génération pour que l'échec (nom déjà pris) soit immédiat,
    // plutôt qu'un job de fond payant qui finit en « failed ».
    listModules.mockResolvedValue([])
    createModule.mockRejectedValue(new Error('ce projet a déjà un module « X »'))
    const w = mount(AddTestCase)
    await flushPromises()

    const nom = w.findAll('input').find((i) => i.attributes('placeholder')?.includes('Nom du module'))!
    await nom.setValue('X')
    await w.find('textarea').setValue('La spécification')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(w.text()).toContain('déjà un module')
    expect(addCase).not.toHaveBeenCalled()
  })

  it('garde le choix normal quand des modules existent', async () => {
    const w = mount(AddTestCase)
    await flushPromises()

    expect(w.find('select').exists()).toBe(true)
    expect(w.text()).toContain('+ Créer un module…')
  })
})
