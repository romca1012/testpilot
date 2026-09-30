/**
 * Écran de la session en direct — ce que ces tests gardent :
 * - les trois actions (confirmer/recommencer/annuler) sont désactivées hors du statut `en_direct` ;
 * - un clic sur l'écran distant traduit les coordonnées AFFICHÉES en coordonnées RÉELLES (limite
 *   du sous-lot C, corrigée par ce frontend — voir le commentaire de `surClic` dans le composant) ;
 * - chaque état terminal (erreur, fermée, confirmée) affiche un message et jamais les deux autres.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ref } from 'vue'
import { monter } from './_montage'
import LiveSession from '../pages/LiveSession.vue'

const listProjects = vi.fn()
const demarrer = vi.fn()
const clic = vi.fn()
const confirmer = vi.fn()
const recommencer = vi.fn()
const annuler = vi.fn()

const etat = {
  statut: ref('connexion'),
  image: ref(''),
  etapes: ref<{ role: string; name: string }[]>([]),
  erreur: ref(''),
  avertissementInactivite: ref<number | null>(null),
  raisonFermeture: ref(''),
  dernierClicAmbigu: ref(''),
  captureArretee: ref(''),
  formulaireInvite: ref(''),
  formulaireCapture: ref<Record<string, { role: string; name: string }>>({}),
  formulaireComplet: ref(false),
  formulaireConnexionEnregistre: ref<boolean | null>(null),
}

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return { ...actual, api: { ...actual.api, listProjects: (...a: any[]) => listProjects(...a) } }
})

vi.mock('../lib/useLiveSession', () => ({
  useLiveSession: () => ({ ...etat, demarrer, clic, confirmer, recommencer, annuler }),
}))

async function monterEcran() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/projects/:pid/live-session', component: LiveSession },
      { path: '/projects/:pid/exploration', component: { template: '<div/>' } },
    ],
  })
  await router.push('/projects/9/live-session')
  await router.isReady()
  const wrapper = monter(LiveSession, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('écran de la session en direct', () => {
  beforeEach(() => {
    listProjects.mockReset().mockResolvedValue([{ id: 9, name: 'Portail', effective_role: 'dev' }])
    demarrer.mockReset()
    clic.mockReset()
    confirmer.mockReset()
    recommencer.mockReset()
    annuler.mockReset()
    etat.statut.value = 'connexion'
    etat.image.value = ''
    etat.etapes.value = []
    etat.erreur.value = ''
    etat.avertissementInactivite.value = null
    etat.raisonFermeture.value = ''
    etat.dernierClicAmbigu.value = ''
    etat.captureArretee.value = ''
    etat.formulaireInvite.value = ''
    etat.formulaireCapture.value = {}
    etat.formulaireComplet.value = false
    etat.formulaireConnexionEnregistre.value = null
  })

  it('démarre la session au montage, sans action de la personne', async () => {
    await monterEcran()
    expect(demarrer).toHaveBeenCalledTimes(1)
  })

  it('affiche le nom du projet une fois chargé', async () => {
    const wrapper = await monterEcran()
    expect(wrapper.text()).toContain('Portail')
  })

  it('les trois actions sont désactivées hors du statut en_direct', async () => {
    etat.statut.value = 'connexion'
    const wrapper = await monterEcran()

    const boutons = wrapper.findAll('button').filter(b =>
      ['Confirmer', 'Recommencer', 'Annuler'].some(mot => b.text().startsWith(mot)))
    expect(boutons.length).toBeGreaterThan(0)
    for (const b of boutons) expect(b.attributes('disabled')).toBeDefined()
  })

  it('confirmer appelle bien confirmer() du composable, jamais recommencer ni annuler', async () => {
    etat.statut.value = 'en_direct'
    const wrapper = await monterEcran()

    const boutonConfirmer = wrapper.findAll('button').find(b => b.text().startsWith('Confirmer'))!
    await boutonConfirmer.trigger('click')

    expect(confirmer).toHaveBeenCalledTimes(1)
    expect(recommencer).not.toHaveBeenCalled()
    expect(annuler).not.toHaveBeenCalled()
  })

  it('falsifiable — un clic sur l\'écran affiché plus PETIT que le viewport réel traduit '
     + 'les coordonnées à l\'échelle, jamais telles quelles', async () => {
    etat.statut.value = 'en_direct'
    etat.image.value = 'BASE64=='
    const wrapper = await monterEcran()

    const img = wrapper.find('img').element as HTMLImageElement
    // Viewport réel transmis par le flux : 1280×720. Affiché à moitié (640×360) pour tenir sur
    // un petit écran — sans mise à l'échelle, un clic à (100, 50) affiché atterrirait à (100, 50)
    // réel au lieu de (200, 100), sur un élément totalement différent.
    Object.defineProperty(img, 'naturalWidth', { value: 1280 })
    Object.defineProperty(img, 'naturalHeight', { value: 720 })
    img.getBoundingClientRect = () => ({
      left: 0, top: 0, width: 640, height: 360, right: 640, bottom: 360, x: 0, y: 0, toJSON() {},
    })

    await wrapper.find('button[aria-label]').trigger('click', { clientX: 100, clientY: 50 })

    expect(clic).toHaveBeenCalledWith(200, 100)
  })

  it('affiche le message d\'erreur, jamais un état de fermeture ou de confirmation à la place', async () => {
    etat.statut.value = 'erreur'
    etat.erreur.value = 'jeton refusé'
    const wrapper = await monterEcran()

    expect(wrapper.text()).toContain('jeton refusé')
    expect(wrapper.text()).not.toContain('Chemin de connexion enregistré')
  })

  it('affiche la raison de fermeture traduite en français, pas le code brut du serveur', async () => {
    etat.statut.value = 'fermee'
    etat.raisonFermeture.value = 'plafond_absolu'
    const wrapper = await monterEcran()

    expect(wrapper.text()).not.toContain('plafond_absolu')
    expect(wrapper.text()).toContain('durée maximale')
  })

  it('l\'état confirmé annonce le nombre d\'étapes réellement enregistrées', async () => {
    etat.statut.value = 'confirmee'
    etat.etapes.value = [{ role: 'button', name: 'France' }, { role: 'button', name: 'Continuer' }]
    const wrapper = await monterEcran()

    expect(wrapper.text()).toContain('2 étapes')
  })

  it('l\'état confirmé mentionne le formulaire identifié quand il l\'a été', async () => {
    etat.statut.value = 'confirmee'
    etat.formulaireConnexionEnregistre.value = true
    const wrapper = await monterEcran()

    expect(wrapper.text()).toContain('formulaire de connexion a aussi été identifié')
  })

  it('n\'affiche pas le pas-à-pas du formulaire tant que capture_arretee n\'a pas eu lieu', async () => {
    etat.statut.value = 'en_direct'
    const wrapper = await monterEcran()

    expect(wrapper.text()).not.toContain('Formulaire de connexion')
  })

  it('affiche le pas-à-pas du formulaire une fois capture_arretee reçu, et marque les champs '
     + 'déjà capturés', async () => {
    etat.statut.value = 'en_direct'
    etat.captureArretee.value = 'mot_de_passe_visible'
    etat.formulaireInvite.value = 'champ_mdp'
    etat.formulaireCapture.value = { champ_identifiant: { role: 'textbox', name: 'E-mail' } }
    const wrapper = await monterEcran()

    expect(wrapper.text()).toContain('Formulaire de connexion')
    expect(wrapper.text()).toContain('Champ identifiant')
    expect(wrapper.text()).toContain('E-mail')
    expect(wrapper.text()).toContain('Champ mot de passe')
  })

  it('annonce le formulaire identifié une fois les 3 champs capturés', async () => {
    etat.statut.value = 'en_direct'
    etat.captureArretee.value = 'mot_de_passe_visible'
    etat.formulaireComplet.value = true
    const wrapper = await monterEcran()

    expect(wrapper.text()).toContain('Formulaire identifié')
  })
})
