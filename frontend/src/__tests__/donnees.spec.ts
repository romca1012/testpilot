/**
 * LA COUCHE DE DONNÉES (lot A, 2026-07-24) — et la preuve de ce qu'elle apporte.
 *
 * Sans ces tests, le lot A ne serait qu'une réécriture : « on a mis une bibliothèque ». Ce qui
 * suit vérifie les trois promesses qui justifiaient le chantier, mesurées en NOMBRE D'APPELS À
 * L'API — la seule chose qui compte pour un utilisateur :
 *
 *   1. deux écrans qui affichent la même donnée ne la demandent qu'UNE fois (le shell et la
 *      page rechargeaient les mêmes modules et les mêmes cas à chaque navigation) ;
 *   2. une mutation invalide ce qu'elle périme — sans que l'écran ait à rappeler `load()` ;
 *   3. une requête ne part pas tant que son identifiant n'existe pas (pendant une transition de
 *      route, `pid` passe à `undefined` et un appel `/projects/undefined/...` partirait).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

const listModules = vi.fn()
const listCases = vi.fn()
const createModule = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listCases: (...a: any[]) => listCases(...a),
    createModule: (...a: any[]) => createModule(...a),
  },
}))

import { useCas, useCreerModule, useModules } from '../lib/donnees'

beforeEach(() => {
  vi.clearAllMocks()
  listModules.mockResolvedValue([{ id: 1, name: 'Demandes' }])
  listCases.mockResolvedValue([{ id: 10, title: 'Un cas', module_id: 1 }])
  createModule.mockResolvedValue({ id: 2, name: 'Facturation' })
})

/** Un client NEUF par test, mais PARTAGÉ entre les composants d'un même test — c'est exactement
 *  la situation réelle : le shell et la page vivent sous le même client. */
function contexte() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
  const monterAvec = (composant: any) =>
    mount(composant, { global: { plugins: [[VueQueryPlugin, { queryClient: client }]] } })
  return { client, monterAvec }
}

const Ecran = (setup: () => any) => defineComponent({ setup, render: () => h('div') })

describe('la couche de données', () => {
  it('ne demande QU\'UNE FOIS une donnée affichée par deux écrans', async () => {
    // C'est LE défaut que le lot A corrige : le shell et la page demandaient les mêmes modules
    // et les mêmes cas, chacun de son côté, à chaque navigation.
    const { monterAvec } = contexte()
    monterAvec(Ecran(() => { useModules('1'); useCas('1'); return {} }))   // le shell
    monterAvec(Ecran(() => { useModules('1'); useCas('1'); return {} }))   // la page affichée
    await flushPromises()

    expect(listModules).toHaveBeenCalledTimes(1)
    expect(listCases).toHaveBeenCalledTimes(1)
  })

  it('sépare les projets : deux projets = deux jeux de données', async () => {
    // Un cache par clé, et la clé porte le projet. Sans ça, changer de projet montrerait les
    // cas du précédent — le mélange inter-projets que le référentiel interdit.
    const { monterAvec } = contexte()
    monterAvec(Ecran(() => { useCas('1'); return {} }))
    monterAvec(Ecran(() => { useCas('2'); return {} }))
    await flushPromises()

    expect(listCases).toHaveBeenCalledTimes(2)
    expect(listCases).toHaveBeenCalledWith('1')
    expect(listCases).toHaveBeenCalledWith('2')
  })

  it('une mutation PÉRIME ce qu\'elle change, sans rechargement manuel', async () => {
    // Avant : chaque écran rappelait `load()` après une création — un oubli et l'écran mentait.
    const { monterAvec } = contexte()
    let creer: any
    monterAvec(Ecran(() => { useModules('1'); creer = useCreerModule('1'); return {} }))
    await flushPromises()
    expect(listModules).toHaveBeenCalledTimes(1)

    await creer.mutateAsync({ name: 'Facturation' })
    await flushPromises()

    // La liste des modules a été redemandée — parce que la mutation l'a périmée, pas parce que
    // l'écran y a pensé.
    expect(listModules).toHaveBeenCalledTimes(2)
  })

  it('ne part PAS quand l\'identifiant n\'existe pas encore', async () => {
    // Pendant une transition de route, `pid` passe à `undefined` le temps d'un tick : une requête
    // `/api/projects/undefined/modules` partirait, échouerait, et polluerait l'écran d'une erreur
    // qui ne décrit rien de réel.
    const { monterAvec } = contexte()
    const pid = ref<string | undefined>(undefined)
    monterAvec(Ecran(() => { useModules(pid); return {} }))
    await flushPromises()
    expect(listModules).not.toHaveBeenCalled()

    pid.value = '1'
    await flushPromises()
    expect(listModules).toHaveBeenCalledWith('1')
  })
})
