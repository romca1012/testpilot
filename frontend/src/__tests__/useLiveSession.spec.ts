/**
 * Composable de la session en direct — ce que ces tests gardent :
 * - le jeton est demandé au serveur puis utilisé pour ouvrir la WebSocket (jamais deviné) ;
 * - chaque type de message serveur produit exactement l'effet attendu sur l'état réactif ;
 * - confirmer/recommencer/annuler envoient le message attendu, dans le bon format.
 *
 * `WebSocket` global remplacé par une doublure contrôlable : jsdom fournit un `WebSocket` qui
 * tente une VRAIE connexion réseau, inutilisable en test unitaire.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { useLiveSession } from '../lib/useLiveSession'

const createLiveSession = vi.fn()

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return {
    ...actual,
    api: { ...actual.api, createLiveSession: (...a: any[]) => createLiveSession(...a) },
    liveSessionWsUrl: (id: any, token: string) => `wss://test/ws/${id}?token=${token}`,
  }
})

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  onmessage: ((e: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []
  closed = false

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string) { this.sent.push(data) }
  close() { this.closed = true }

  // Aide de test : simule un message reçu du serveur.
  recevoir(message: object) {
    this.onmessage?.({ data: JSON.stringify(message) } as MessageEvent)
  }
}

// Le composable utilise `onUnmounted` — il doit donc être instancié dans un composant hôte
// monté, pas appelé nu dans le corps du test (Vue lève sinon un avertissement et le hook n'a
// aucun effet).
function monterComposable(projectId: string | number) {
  let expose: ReturnType<typeof useLiveSession>
  const Hote = defineComponent({
    setup() {
      expose = useLiveSession(projectId)
      return () => h('div')
    },
  })
  const wrapper = mount(Hote)
  return { wrapper, session: expose! }
}

beforeEach(() => {
  createLiveSession.mockReset()
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useLiveSession', () => {
  it('demande un jeton puis ouvre la WebSocket avec ce jeton, jamais un autre', async () => {
    createLiveSession.mockResolvedValue({ token: 'abc123', expires_at: '2026-09-30T12:00:00Z' })
    const { session } = monterComposable(7)

    await session.demarrer()

    expect(createLiveSession).toHaveBeenCalledWith(7)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toBe('wss://test/ws/7?token=abc123')
  })

  it('passe en direct et porte l\'image à la première frame reçue', async () => {
    createLiveSession.mockResolvedValue({ token: 't', expires_at: '' })
    const { session } = monterComposable(7)
    await session.demarrer()

    expect(session.statut.value).toBe('connexion')
    FakeWebSocket.instances[0].recevoir({ type: 'image', data: 'BASE64==' })

    expect(session.statut.value).toBe('en_direct')
    expect(session.image.value).toBe('BASE64==')
  })

  it('accumule les étapes capturées dans l\'ordre de réception', async () => {
    createLiveSession.mockResolvedValue({ token: 't', expires_at: '' })
    const { session } = monterComposable(7)
    await session.demarrer()
    const ws = FakeWebSocket.instances[0]

    ws.recevoir({ type: 'etape_capturee', role: 'button', name: 'France' })
    ws.recevoir({ type: 'etape_capturee', role: 'button', name: 'Continuer' })

    expect(session.etapes.value).toEqual([
      { role: 'button', name: 'France' },
      { role: 'button', name: 'Continuer' },
    ])
  })

  it('clic() envoie les coordonnées reçues telles quelles, sans les retoucher', async () => {
    createLiveSession.mockResolvedValue({ token: 't', expires_at: '' })
    const { session } = monterComposable(7)
    await session.demarrer()

    session.clic(123.4, 56.7)

    const envoye = JSON.parse(FakeWebSocket.instances[0].sent[0])
    expect(envoye).toEqual({ type: 'clic', x: 123.4, y: 56.7 })
  })

  it('confirmer() envoie le message et passe le statut à confirmee', async () => {
    createLiveSession.mockResolvedValue({ token: 't', expires_at: '' })
    const { session } = monterComposable(7)
    await session.demarrer()

    session.confirmer()

    expect(JSON.parse(FakeWebSocket.instances[0].sent[0])).toEqual({ type: 'confirmer' })
    expect(session.statut.value).toBe('confirmee')
  })

  it('recommencer() vide les étapes localement ET envoie le message', async () => {
    createLiveSession.mockResolvedValue({ token: 't', expires_at: '' })
    const { session } = monterComposable(7)
    await session.demarrer()
    FakeWebSocket.instances[0].recevoir({ type: 'etape_capturee', role: 'button', name: 'France' })
    expect(session.etapes.value).toHaveLength(1)

    session.recommencer()

    expect(session.etapes.value).toEqual([])
    expect(JSON.parse(FakeWebSocket.instances[0].sent[0])).toEqual({ type: 'recommencer' })
  })

  it('annuler() ferme la WebSocket et ne se dit jamais confirmee', async () => {
    createLiveSession.mockResolvedValue({ token: 't', expires_at: '' })
    const { session } = monterComposable(7)
    await session.demarrer()

    session.annuler()

    expect(FakeWebSocket.instances[0].closed).toBe(true)
    expect(session.statut.value).toBe('fermee')
    expect(session.raisonFermeture.value).toBe('annulee')
  })

  it('une fermeture serveur (timeout) porte la raison et clôt proprement', async () => {
    createLiveSession.mockResolvedValue({ token: 't', expires_at: '' })
    const { session } = monterComposable(7)
    await session.demarrer()

    FakeWebSocket.instances[0].recevoir({ type: 'fermeture', raison: 'plafond_absolu' })

    expect(session.statut.value).toBe('fermee')
    expect(session.raisonFermeture.value).toBe('plafond_absolu')
  })

  it('falsifiable — un clic ambigu ne s\'ajoute PAS au chemin capturé', async () => {
    createLiveSession.mockResolvedValue({ token: 't', expires_at: '' })
    const { session } = monterComposable(7)
    await session.demarrer()

    FakeWebSocket.instances[0].recevoir({ type: 'clic_ambigu', detail: 'ambigu : 2 éléments' })

    expect(session.etapes.value).toEqual([])
    expect(session.dernierClicAmbigu.value).toBe('ambigu : 2 éléments')
  })

  it('un jeton refusé par le serveur porte le statut erreur, jamais une WebSocket ouverte', async () => {
    createLiveSession.mockRejectedValue(new Error('403'))
    const { session } = monterComposable(7)

    await session.demarrer()

    expect(session.statut.value).toBe('erreur')
    expect(FakeWebSocket.instances).toHaveLength(0)
  })
})
