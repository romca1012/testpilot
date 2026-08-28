/**
 * **UN CAS DANS UNE CAMPAGNE** (`RunTestDetail.vue`) — l'écran qui manquait entièrement
 * jusqu'au 2026-08-05, et qui n'avait encore AUCUN test d'interface.
 *
 * Ce que ces tests gardent :
 * - le titre et l'identité `T{campagne}-{cas}` s'affichent, et ne se confondent jamais avec
 *   `C{cas}` (décision 0022 — deux identités pour deux objets différents) ;
 * - un résultat MANUEL ne laisse fuiter aucun des deux axes (déroulement/fonctionnel), qui
 *   n'existent que pour une machine ;
 * - le bouton « Ajouter un résultat » (branché le 2026-08-05, cette page en était dépourvue)
 *   suit EXACTEMENT la même règle que la liste de la campagne : absent d'une campagne
 *   automatique, absent d'une campagne archivée, présent sinon — sans quoi cette page proposerait
 *   un geste que le serveur refuse ;
 * - les flèches précédent/suivant se désactivent quand la campagne n'a pas de voisin à proposer ;
 * - l'onglet « Défauts » dit honnêtement que rien n'est encore modélisé, sans compteur à zéro qui
 *   ferait croire que la question a été posée.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const getTestDansRun = vi.fn()
const getRun = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  API_BASE: '',
  roleSuffisant: () => true,
  api: {
    getTestDansRun: (...a: any[]) => getTestDansRun(...a),
    getRun: (...a: any[]) => getRun(...a),
  },
}))
vi.mock('../lib/useProjects', () => ({
  useProjects: () => ({ projectById: () => ({ effective_role: 'admin' }) }),
}))
vi.mock('../lib/useSession', async () => {
  const { ref } = await import('vue')
  return { useSession: () => ({ session: ref({ role: 'admin' }) }) }
})
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '7', caseId: '12' }, query: {} }),
  useRouter: () => ({ push }),
}))

import RunTestDetail from '../pages/RunTestDetail.vue'

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

function testDto(overrides: Record<string, any> = {}) {
  return {
    run_id: 7, run_name: 'Recette de juillet', run_archived: false, run_mode: 'manuelle',
    case_id: 12, title: 'Un gestionnaire soumet une demande de lettrage',
    type: 'fonctionnel', etat: 'ready', priority: 'medium', estimate: '', refs: '',
    statut: 'blocked',
    results: [] as any[],
    prev_case_id: null, next_case_id: null,
    historique_du_cas: [] as any[],
    ...overrides,
  }
}

function monterEcran() {
  return mount(RunTestDetail, { global: { stubs } })
}

beforeEach(() => {
  vi.clearAllMocks()
  getTestDansRun.mockResolvedValue(testDto())
  getRun.mockResolvedValue({ statuts_manuels: ['passed', 'failed', 'retest', 'blocked'] })
})

describe('RunTestDetail — identité et statut', () => {
  it('affiche le titre du test et l\'identité T{campagne}-{cas}, distincte de C{cas}', async () => {
    const w = monterEcran()
    await flushPromises()

    expect(w.text()).toContain('Un gestionnaire soumet une demande de lettrage')
    expect(w.text()).toContain('T7-12')
    // La distinction n'est PAS un détail cosmétique : « C12 » désignerait le cas du référentiel,
    // pas le test dans cette campagne. Elle ne doit apparaître qu'en infobulle (`title`), jamais
    // dans le texte visible de la page.
    expect(w.text()).not.toContain('C12')
  })

  it('affiche le statut sans exposer les axes bruts d\'un résultat MANUEL', async () => {
    // ⚠️ Un résultat manuel n'a NI déroulement NI verdict fonctionnel mesurés : les deux axes
    // valent `null`. Si l'écran affichait un mot technique venu de ces champs, ce serait le signe
    // qu'il essaie de lire une mesure qui n'existe pas.
    getTestDansRun.mockResolvedValue(testDto({
      statut: 'blocked',
      results: [{
        id: 1, mode: 'manuelle', statut: 'blocked', statut_manuel: 'blocked',
        comment: 'environnement indisponible', created_by: 'Romaric',
        created_at: '2026-08-04T11:00:00+00:00',
        execution_id: null, execution_status: null, functional_status: null, attachments: [],
      }],
    }))
    const w = monterEcran()
    await flushPromises()

    expect(w.text()).toContain('Blocked')
    expect(w.text()).not.toContain('success')
    expect(w.text()).not.toContain('technical_error')
    expect(w.text()).not.toContain('conforme')
  })
})

describe('RunTestDetail — le bouton « Ajouter un résultat »', () => {
  // ⚠️ Avant le branchement (2026-08-05), cette page n'ouvrait AUCUNE fenêtre de saisie : c'était
  // l'unique endroit où TestRail permet de saisir un résultat que TestPilot ne proposait pas.
  it('absent sur une campagne AUTOMATIQUE : rien à saisir, la machine a déjà parlé', async () => {
    getTestDansRun.mockResolvedValue(testDto({ run_mode: 'automatique', run_archived: false }))
    const w = monterEcran()
    await flushPromises()

    expect(w.findAll('button').find((b) => b.text().includes('Ajouter un résultat'))).toBeUndefined()
  })

  it('absent sur une campagne manuelle ARCHIVÉE : lecture seule', async () => {
    getTestDansRun.mockResolvedValue(testDto({ run_mode: 'manuelle', run_archived: true }))
    const w = monterEcran()
    await flushPromises()

    expect(w.findAll('button').find((b) => b.text().includes('Ajouter un résultat'))).toBeUndefined()
  })

  it('présent sur une campagne manuelle NON archivée', async () => {
    getTestDansRun.mockResolvedValue(testDto({ run_mode: 'manuelle', run_archived: false }))
    const w = monterEcran()
    await flushPromises()

    expect(w.findAll('button').find((b) => b.text().includes('Ajouter un résultat'))).toBeDefined()
  })
})

describe('RunTestDetail — navigation DANS la campagne', () => {
  it('désactive les deux flèches quand la campagne n\'a aucun voisin', async () => {
    const w = monterEcran()
    await flushPromises()

    expect(w.find('[aria-label="Test précédent de cette campagne"]').attributes('disabled')).toBeDefined()
    expect(w.find('[aria-label="Test suivant de cette campagne"]').attributes('disabled')).toBeDefined()
  })

  it('active une flèche dès qu\'un voisin existe', async () => {
    getTestDansRun.mockResolvedValue(testDto({ prev_case_id: 5, next_case_id: 20 }))
    const w = monterEcran()
    await flushPromises()

    expect(w.find('[aria-label="Test précédent de cette campagne"]').attributes('disabled')).toBeUndefined()
    expect(w.find('[aria-label="Test suivant de cette campagne"]').attributes('disabled')).toBeUndefined()
  })
})

describe('RunTestDetail — onglet Défauts', () => {
  it('dit honnêtement que rien n\'est encore modélisé, sans compteur trompeur', async () => {
    const w = monterEcran()
    await flushPromises()

    await w.findAll('button').find((b) => b.text() === 'Défauts')!.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('Défauts — à venir.')
    expect(w.text()).toContain('Aucun défaut ne peut encore être rattaché à un résultat')
    // ⚠️ Un panneau de compteurs à zéro laisserait croire que la question a été posée et qu'il
    // n'y a rien : aucun « (0) » ne doit apparaître sur cet onglet.
    expect(w.text()).not.toMatch(/\(0\)/)
  })
})
