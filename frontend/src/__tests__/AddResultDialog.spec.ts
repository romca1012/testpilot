/**
 * L'écran « Ajouter un résultat » — l'exécution MANUELLE d'un cas, reprise de TestRail.
 *
 * ⚠️ Ce que ces tests gardent, et pourquoi ils existent :
 *
 * 1. **Les statuts sont ceux du SERVEUR, itérés tels quels.** La liste vit déjà en Python et
 *    dans un `CHECK` de la base ; la retaper ici en ferait une troisième version, qui
 *    divergerait un jour sans que personne le voie. Le test passe une liste inhabituelle pour
 *    prouver que l'écran n'en connaît aucune.
 * 2. **Aucun statut n'est pré-sélectionné**, et le bouton reste inactif tant qu'on n'a pas
 *    choisi. Proposer « Passed » d'avance transformerait la saisie en clic distrait — ce qui
 *    vide le mot « testé » de son sens, précisément ce que ce produit combat.
 * 3. **L'avertissement d'honnêteté est affiché.** C'est le contrat passé avec celui qui lira le
 *    rapport ensuite : ce résultat n'a été vérifié par aucune machine.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listResults = vi.fn()
const addResult = vi.fn()
const addAttachments = vi.fn()

vi.mock('../lib/api', () => ({
  API_BASE: '',
  api: {
    listResults: (...a: any[]) => listResults(...a),
    addResult: (...a: any[]) => addResult(...a),
    addAttachments: (...a: any[]) => addAttachments(...a),
  },
}))

import AddResultDialog from '../components/AddResultDialog.vue'

const CAS = {
  id: 84, title: 'Un gestionnaire soumet une demande de lettrage',
  execution_status: 'success', functional_status: 'conforme', execution_id: 119,
  result_mode: 'automatique', statut_manuel: '', comment: '',
  created_by: 'TestPilot', result_at: '2026-08-03T12:54:00+00:00',
  statut: 'passed',
}

// jsdom refuse `input.setValue([file])` de @vue/test-utils sur un `<input type="file">`
// (« may only be programmatically set to the empty string ») : on redéfinit `.files`
// directement, comme le fait un navigateur réel après une sélection, puis on émet l'événement
// que le composant écoute.
function choisirFichier(w: ReturnType<typeof mount>, fichier: File) {
  const input = w.find('input[type="file"]').element as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [fichier], configurable: true })
  input.dispatchEvent(new Event('change'))
}

function monterDialogue(statuts = ['passed', 'failed', 'retest', 'blocked']) {
  return mount(AddResultDialog, {
    props: { open: true, runId: 10, cas: CAS as any, statuts },
    attachTo: document.body,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  listResults.mockResolvedValue([
    { id: 1, mode: 'automatique', statut: 'passed', statut_manuel: '', comment: '',
      created_by: 'TestPilot', created_at: '2026-08-03T12:54:00+00:00',
      execution_id: 119, execution_status: 'success', functional_status: 'conforme' },
  ])
  addResult.mockResolvedValue({ id: 2, mode: 'manuelle', statut: 'blocked' })
  addAttachments.mockResolvedValue([{ id: 5, filename: 'capture.png', content_type: 'image/png', size_bytes: 1024 }])
})

describe('AddResultDialog — l\'exécution manuelle d\'un cas', () => {
  it('n\'affiche QUE les statuts que le serveur autorise', async () => {
    // Une liste volontairement inhabituelle : si l'écran en connaissait une en dur, elle
    // apparaîtrait ici et le test tomberait.
    const w = monterDialogue(['retest', 'blocked'])
    await flushPromises()

    const boutons = w.findAll('button[type="button"]').map((b) => b.text())
    expect(boutons).toContain('Retest')
    expect(boutons).toContain('Blocked')
    expect(boutons).not.toContain('Passed')
    // « Untested » n'est jamais un BOUTON — mais l'écran dit pourquoi il n'est pas proposé.
    // Sans cette phrase, son absence passe pour un oubli de l'outil et on la cherche.
    expect(boutons).not.toContain('Untested')
    expect(w.text()).toContain('« Untested » ne se saisit pas')
  })

  it('n\'en pré-sélectionne AUCUN et refuse de valider tant qu\'on n\'a pas choisi', async () => {
    const w = monterDialogue()
    await flushPromises()

    const valider = w.findAll('button').find((b) => b.text().includes('Ajouter le résultat'))!
    expect(valider.attributes('disabled')).toBeDefined()
    expect(w.findAll('[aria-pressed="true"]')).toHaveLength(0)
  })

  it('envoie le statut CHOISI et son commentaire, puis prévient le parent', async () => {
    const w = monterDialogue()
    await flushPromises()

    await w.findAll('button[type="button"]').find((b) => b.text() === 'Blocked')!.trigger('click')
    await w.find('textarea').setValue('La recette était en cours de restauration.')
    await w.findAll('button').find((b) => b.text().includes('Ajouter le résultat'))!.trigger('click')
    await flushPromises()

    expect(addResult).toHaveBeenCalledWith(10, 84, {
      statut: 'blocked', comment: 'La recette était en cours de restauration.',
    })
    expect(w.emitted('saved')).toBeTruthy()
    expect(w.emitted('close')).toBeTruthy()
  })

  it('avertit que le résultat sera joué MANUELLEMENT, jamais vérifié par une machine', async () => {
    const w = monterDialogue()
    await flushPromises()
    expect(w.text()).toContain('manuellement')
    expect(w.text()).toContain('aucune machine')
  })

  it('affiche l\'historique existant, avec le MODE de chaque résultat', async () => {
    const w = monterDialogue()
    await flushPromises()

    expect(listResults).toHaveBeenCalledWith(10, 84)
    expect(w.text()).toContain('Résultats')
    expect(w.text()).toContain('Automatique')   // le résultat déjà là vient d'une machine
  })

  it('une erreur du serveur s\'affiche sans fermer la fenêtre (la saisie n\'est pas perdue)', async () => {
    addResult.mockRejectedValue(new Error('Cette campagne est archivée (lecture seule)'))
    const w = monterDialogue()
    await flushPromises()

    await w.findAll('button[type="button"]').find((b) => b.text() === 'Passed')!.trigger('click')
    await w.findAll('button').find((b) => b.text().includes('Ajouter le résultat'))!.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('archivée')
    expect(w.emitted('close')).toBeFalsy()
  })

  it('n\'appelle JAMAIS l\'upload quand aucun fichier n\'a été choisi', async () => {
    const w = monterDialogue()
    await flushPromises()

    await w.findAll('button[type="button"]').find((b) => b.text() === 'Passed')!.trigger('click')
    await w.findAll('button').find((b) => b.text().includes('Ajouter le résultat'))!.trigger('click')
    await flushPromises()

    expect(addAttachments).not.toHaveBeenCalled()
    expect(w.emitted('close')).toBeTruthy()
  })

  it('joint les fichiers choisis au résultat CRÉÉ, après addResult', async () => {
    const w = monterDialogue()
    await flushPromises()

    const fichier = new File(['contenu'], 'capture.png', { type: 'image/png' })
    choisirFichier(w, fichier)
    await w.findAll('button[type="button"]').find((b) => b.text() === 'Passed')!.trigger('click')
    await w.findAll('button').find((b) => b.text().includes('Ajouter le résultat'))!.trigger('click')
    await flushPromises()

    // L'id utilisé est celui rendu par `addResult` (2), jamais celui du cas (84) — un résultat
    // manuel peut être le énième du cas, l'id du CAS ne désignerait pas la bonne pièce jointe.
    expect(addAttachments).toHaveBeenCalledWith(2, [fichier])
    expect(w.emitted('close')).toBeTruthy()
  })

  it('un échec d\'upload laisse le résultat ACQUIS et garde la fenêtre ouverte', async () => {
    // ⚠️ Le défaut que ce test empêche : un résultat déjà enregistré qui semblerait avoir
    // disparu parce que l'écran se referme sur une erreur qui ne le concerne pas.
    addAttachments.mockRejectedValue(new Error('« .exe » est refusé pour des raisons de sécurité'))
    const w = monterDialogue()
    await flushPromises()

    const fichier = new File(['x'], 'script.exe', { type: 'application/octet-stream' })
    choisirFichier(w, fichier)
    await w.findAll('button[type="button"]').find((b) => b.text() === 'Passed')!.trigger('click')
    await w.findAll('button').find((b) => b.text().includes('Ajouter le résultat'))!.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('Résultat enregistré')
    expect(w.text()).toContain('refusé pour des raisons de sécurité')
    expect(w.emitted('saved')).toBeTruthy()
    expect(w.emitted('close')).toBeFalsy()

    // Le statut est réinitialisé : recliquer ne doit pas créer un SECOND résultat identique.
    const valider = w.findAll('button').find((b) => b.text().includes('Ajouter le résultat'))!
    expect(valider.attributes('disabled')).toBeDefined()
    expect(addResult).toHaveBeenCalledTimes(1)
  })
})
