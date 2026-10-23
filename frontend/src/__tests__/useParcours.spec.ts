/**
 * Étape 7b (A109) — le parcours d'un cas joué dans le navigateur en direct :
 * - le jeton du CAS ouvre la WebSocket du parcours ;
 * - clic, « c'est ici que je vérifie », saisie, choix et retrait envoient le bon message ;
 * - une action n'apparaît qu'à l'accusé du serveur ; « enregistré » aussi.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useParcours } from '../lib/useParcours'

const createParcoursSession = vi.fn()

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return {
    ...actual,
    api: { ...actual.api, createParcoursSession: (...a: any[]) => createParcoursSession(...a) },
    parcoursWsUrl: (id: any, token: string) => `wss://test/cas/${id}?token=${token}`,
  }
})

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: any[] = []
  constructor(url: string) { this.url = url; FakeWebSocket.instances.push(this) }
  send(data: string) { this.sent.push(JSON.parse(data)) }
  close() {}
  recevoir(message: object) { this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent) }
}

function monter(caseId: number) {
  let expose: ReturnType<typeof useParcours>
  mount(defineComponent({ setup() { expose = useParcours(caseId); return () => h('div') } }))
  return expose!
}

beforeEach(() => {
  createParcoursSession.mockReset().mockResolvedValue({ token: 'j1', expires_at: '' })
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
})
afterEach(() => vi.unstubAllGlobals())

describe('useParcours', () => {
  it('ouvre la session avec le jeton du cas', async () => {
    const p = monter(12)
    await p.demarrer()
    expect(createParcoursSession).toHaveBeenCalledWith(12)
    expect(FakeWebSocket.instances[0].url).toBe('wss://test/cas/12?token=j1')
  })

  it('envoie chaque geste dans le bon format', async () => {
    const p = monter(12)
    await p.demarrer()
    p.clic(10, 20); p.verifier(30, 40); p.saisir('3'); p.choisir('Azure'); p.retirer(1); p.enregistrer()
    expect(FakeWebSocket.instances[0].sent).toEqual([
      { type: 'clic', x: 10, y: 20 }, { type: 'verifier', x: 30, y: 40 }, { type: 'saisie', valeur: '3' },
      { type: 'choix', valeur: 'Azure' }, { type: 'retirer', rang: 1 }, { type: 'confirmer' },
    ])
    expect(p.statut.value).toBe('connexion')   // rien n'est « enregistré » avant l'accusé du serveur
  })

  it('une action n\'apparaît qu\'à l\'accusé du serveur, et disparaît à son retrait', async () => {
    const p = monter(12)
    await p.demarrer()
    const ws = FakeWebSocket.instances[0]
    ws.recevoir({ type: 'image', data: 'x' })
    ws.recevoir({ type: 'champ_designe', nom: 'Client', secret: false, options: ['Azure'] })
    expect(p.champ.value?.options).toEqual(['Azure'])
    ws.recevoir({ type: 'action_capturee', rang: 0, action: 'choix', role: 'combobox', nom: 'Client', page: '/',
                  champ: 'client', valeur: 'Azure', secret: false })
    expect(p.actions.value).toEqual([{ action: 'choix', role: 'combobox', nom: 'Client', page: '/', champ: 'client',
                                       valeur: 'Azure', secret: false }])
    expect(p.champ.value).toBeNull()
    ws.recevoir({ type: 'action_retiree', rang: 0 })
    expect(p.actions.value).toEqual([])
    ws.recevoir({ type: 'confirme', actions: 0, parcours_id: 3 })
    expect(p.statut.value).toBe('enregistre')
  })

  it('dit une connexion automatique impossible et un geste non retenu', async () => {
    const p = monter(12)
    await p.demarrer()
    const ws = FakeWebSocket.instances[0]
    ws.recevoir({ type: 'connexion_auto', ok: false })
    ws.recevoir({ type: 'clic_ambigu', detail: '…' })
    expect(p.connexionAuto.value).toBe(false)
    expect(p.avertissement.value).toContain('pas été ajoutée')
    ws.recevoir({ type: 'erreur', detail: 'aucun_champ_designe' })
    expect(p.erreur.value).toBe('Cliquez d\'abord sur le champ à remplir.')
  })
})
