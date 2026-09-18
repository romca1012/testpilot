/**
 * Garde de NON-RÉGRESSION : le formulaire de création doit S'ARRÊTER à la pause métier.
 *
 * ⚠️ Pourquoi ce fichier existe. La génération se fait désormais en deux passes (décision 0022
 * n°5) : le job passe par `awaiting_metier` et **n'avance plus tout seul**. Un formulaire qui ne
 * connaît que `running` / `done` / `failed` traite cet état comme « en cours » et tourne dans le
 * vide indéfiniment — l'utilisateur voit un spinner pour un travail qui n'arrivera jamais.
 *
 * Ces tests montent la vraie page et vérifient les trois temps : spec → pause éditable → Gherkin.
 *
 * ⚠️ Étendu au §9 (génération MULTI-CAS, 2026-08-05), puis mis À PLAT à l'étape 3 (2026-08-07),
 * puis à l'étape 3bis (même jour, retour du manager du porteur) : la Section se choisit
 * maintenant AVANT la génération, sur l'écran de spécification (même patron obligatoire que le
 * Module) — l'écran de pause n'a donc plus de sélecteur, juste des cas repliés par défaut.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listGroups = vi.fn()
const addCase = vi.fn()
const getGenerationJob = vi.fn()
const validateMetier = vi.fn()
const createModule = vi.fn()
const createGroup = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    addCase: (...a: any[]) => addCase(...a),
    getGenerationJob: (...a: any[]) => getGenerationJob(...a),
    validateMetier: (...a: any[]) => validateMetier(...a),
    createModule: (...a: any[]) => createModule(...a),
    createGroup: (...a: any[]) => createGroup(...a),
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
  user_story: 'Réception et délivrance',
}

const SECTION = { id: 50, module_id: 1, title: 'Connexion', case_count: 0, parent_group_id: null }

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  listModules.mockResolvedValue([{ id: 1, name: 'Demande matériel' }])
  listGroups.mockResolvedValue([SECTION])
  addCase.mockResolvedValue({ job_id: 'J1', status: 'running', case_ids: [], error: '' })
  createModule.mockResolvedValue({ id: 9, name: 'Nouveau module', project_id: 1, case_count: 0 })
})

/** Une proposition à UN cas — le cas le plus simple, suffisant pour la plupart des tests (la
 * multiplicité des cas est couverte côté backend, pas ici). */
function casAvec(draft = DRAFT) {
  return [draft]
}

/** Monte, saisit une spec + choisit la Section obligatoire, soumet, puis laisse tomber une
 * réponse de job. */
async function jusquAuJob(job: any) {
  const w = monter(AddTestCase)
  await flushPromises()
  await w.find('textarea').setValue('La spécification à tester')
  await w.findAll('select')[1].setValue('50')   // [0]=Module, [1]=Section obligatoire (étape 3bis)
  await w.find('form').trigger('submit')
  await flushPromises()

  getGenerationJob.mockResolvedValue(job)
  await vi.advanceTimersByTimeAsync(2100)
  await flushPromises()
  return w
}

describe('AddTestCase — la pause métier (0022 n°5, étendue au §9, à PLAT et repliée depuis l\'étape 3bis)', () => {
  it('S\'ARRÊTE sur awaiting_metier et affiche les cas, REPLIÉS par défaut', async () => {
    const w = await jusquAuJob({ status: 'awaiting_metier', cases: casAvec(), case_ids: [], error: '' })

    // Replié : le champ Titre du CAS n'est PAS visible tant qu'on ne l'a pas déplié — seul le
    // titre en lecture apparaît dans l'en-tête.
    expect(w.text()).toContain(DRAFT.title)
    expect(w.text()).toContain('Issu de : Réception et délivrance')  // repère de LECTURE
    const inputs = w.findAll('input')
    expect(inputs.some((i) => (i.element as HTMLInputElement).value === DRAFT.title)).toBe(false)
    expect(w.text()).toContain('Valider 1 cas et générer les tests')
    expect(push).not.toHaveBeenCalled()
  })

  it('déplier un cas révèle ses champs ÉDITABLES', async () => {
    const w = await jusquAuJob({ status: 'awaiting_metier', cases: casAvec(), case_ids: [], error: '' })

    await w.find('[aria-expanded="false"]').trigger('click')

    const inputs = w.findAll('input')
    expect(inputs.some((i) => (i.element as HTMLInputElement).value === DRAFT.title)).toBe(true)
    expect(inputs.some((i) => (i.element as HTMLInputElement).value === 'Ouvrir le formulaire')).toBe(true)
  })

  it('envoie l\'ensemble CORRIGÉ, pas celui proposé par l\'IA', async () => {
    // Tout l'intérêt de la pause : ce que l'humain écrit fait foi.
    validateMetier.mockResolvedValue({ job_id: 'J1', status: 'running', case_ids: [], error: '' })
    const w = await jusquAuJob({ status: 'awaiting_metier', cases: casAvec(), case_ids: [], error: '' })
    await w.find('[aria-expanded="false"]').trigger('click')

    const titre = w.findAll('input').find(
      (i) => (i.element as HTMLInputElement).value === DRAFT.title)!
    await titre.setValue('MON titre corrigé')
    await w.findAll('button').find((b) => b.text().includes('Valider'))!.trigger('click')
    await flushPromises()

    expect(validateMetier).toHaveBeenCalledWith('J1', [
      expect.objectContaining({ title: 'MON titre corrigé' }),
    ])
  })

  it('REFUSE de valider un cas amputé de ses étapes', async () => {
    // Titre + étapes + résultat attendu sont obligatoires (0022 n°3.c) : un cas sans eux ne
    // vérifie rien. Le bouton est désactivé plutôt que de laisser le serveur refuser après coup.
    const w = await jusquAuJob({ status: 'awaiting_metier', cases: casAvec(), case_ids: [], error: '' })
    await w.find('[aria-expanded="false"]').trigger('click')

    for (let garde = 0; garde < 10; garde++) {
      const croix = w.findAll('button').filter((b) => b.attributes('title') === 'Supprimer')
      if (!croix.length) break
      await croix[0].trigger('click')
    }

    const valider = w.findAll('button').find((b) => b.text().includes('Valider'))!
    expect(valider.attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('incomplet')   // repère visible même replié
  })

  it('retourne à la LISTE quand le job est terminé, jamais directement à l\'exécution', async () => {
    // N cas générés : plus de redirection vers UN cas précis, qui n'aurait plus de sens dès
    // qu'il y en a plusieurs (§9).
    await jusquAuJob({ status: 'done', case_ids: [42, 43], cases: null, error: '' })

    expect(push).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'cases', params: { pid: '1' }, query: { module: '1' } }))
  })

  it('un succès PARTIEL (des cas en échec) ne redirige JAMAIS en silence', async () => {
    // ⚠️ Bug réel constaté sur SauceDemo (2026-09-13) : `resume_generation` peut rendre
    // `status: "done"` avec des cas réussis ET un `error` listant ceux qui ont échoué
    // (`dry_run_stalled`) — avant ce correctif, cet écran redirigeait vers la liste SANS jamais
    // lire `job.error` sur ce chemin, laissant croire à un succès total.
    const w = await jusquAuJob({
      status: 'done', case_ids: [1, 2, 3], cases: null,
      error: '« Cas A » : dry_run_stalled; « Cas B » : dry_run_stalled',
    })

    expect(push).not.toHaveBeenCalled()
    expect(w.text()).toContain('3 cas')
    expect(w.text()).toContain('Cas A')
    expect(w.text()).toContain('Cas B')

    await w.findAll('button').find((b) => b.text().includes('Voir les'))!.trigger('click')
    expect(push).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'cases', params: { pid: '1' }, query: { module: '1' } }))
  })

  it('affiche l\'erreur et rend la main quand la génération échoue', async () => {
    const w = await jusquAuJob({ status: 'failed', case_ids: [], cases: null,
                                error: 'le document métier rendu est incomplet' })

    expect(w.text()).toContain('le document métier rendu est incomplet')
    expect(w.find('textarea').exists()).toBe(true) // retour au formulaire, pas un cul-de-sac
  })
})

describe('AddTestCase — un projet NEUF n\'est plus un cul-de-sac', () => {
  it("DIT qu'aucun module n'existe au lieu d'offrir une liste vide", async () => {
    // Avant : select vide, `submit()` sortait sur `if (!moduleId) return` — bouton sans effet,
    // aucun message. Un projet fraîchement créé était donc inutilisable, en silence.
    listModules.mockResolvedValue([])
    const w = monter(AddTestCase)
    await flushPromises()

    expect(w.text()).toContain("Ce projet n'a pas encore de module")
    expect(w.find('select').exists()).toBe(false)
  })

  it('CRÉE le module ET la section puis enchaîne sur la génération', async () => {
    listModules.mockResolvedValue([])
    listGroups.mockResolvedValue([])
    createModule.mockResolvedValue({ id: 9, name: 'Demande de matériel', project_id: 1, case_count: 0 })
    createGroup.mockResolvedValue({ id: 60, module_id: 9, title: 'Connexion', case_count: 0 })
    const w = monter(AddTestCase)
    await flushPromises()

    const nom = w.findAll('input').find((i) => i.attributes('placeholder')?.includes('Nom du module'))!
    await nom.setValue('Demande de matériel')
    await flushPromises()
    const nomSection = w.findAll('input').find((i) => i.attributes('placeholder')?.includes('Nom de la section'))!
    await nomSection.setValue('Connexion')
    await w.find('textarea').setValue('La spécification')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createModule).toHaveBeenCalledWith('1', 'Demande de matériel')
    expect(createGroup).toHaveBeenCalledWith(9, { title: 'Connexion', spec_content: 'La spécification' })
    expect(addCase).toHaveBeenCalledWith(9, 'La spécification', '', 60)
  })

  it("REMONTE l'erreur de création du module sans lancer de génération payante", async () => {
    // Le module est créé AVANT la génération pour que l'échec (nom déjà pris) soit immédiat,
    // plutôt qu'un job de fond payant qui finit en « failed ».
    listModules.mockResolvedValue([])
    createModule.mockRejectedValue(new Error('ce projet a déjà un module « X »'))
    const w = monter(AddTestCase)
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
    const w = monter(AddTestCase)
    await flushPromises()

    expect(w.find('select').exists()).toBe(true)
    expect(w.text()).toContain('+ Créer un module…')
  })
})
