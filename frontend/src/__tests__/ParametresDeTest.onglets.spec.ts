/**
 * Lot PT-01a — les trois onglets de « Paramètres de test » d'un projet.
 *
 * Ces réglages vivaient dans la fenêtre « Identité et application ». Ils passent par les MÊMES routes, sur les MÊMES données.
 * Ce que ces tests gardent :
 * 1. un projet existant retrouve ses valeurs sans rien saisir ;
 * 2. un onglet n'envoie QUE ses champs — jamais le nom, l'adresse ni un mot de passe du projet (les renvoyer les écraserait) ;
 * 3. le mot de passe d'un compte reste en écriture seule ;
 * 4. l'écran ne propose pas un geste que le serveur refuserait.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const updateProject = vi.fn()
const listProjectAccounts = vi.fn()
const createProjectAccount = vi.fn()
const updateProjectAccount = vi.fn()
const deleteProjectAccount = vi.fn()
const valeursDuProjetOptions = vi.fn()
const listProjectUnits = vi.fn()
const createProjectUnit = vi.fn()
const updateProjectUnit = vi.fn()
const deleteProjectUnit = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    updateProject: (...a: any[]) => updateProject(...a),
    listProjectAccounts: (...a: any[]) => listProjectAccounts(...a),
    createProjectAccount: (...a: any[]) => createProjectAccount(...a),
    updateProjectAccount: (...a: any[]) => updateProjectAccount(...a),
    deleteProjectAccount: (...a: any[]) => deleteProjectAccount(...a),
    valeursDuProjetOptions: (...a: any[]) => valeursDuProjetOptions(...a),
    listProjectUnits: (...a: any[]) => listProjectUnits(...a),
    createProjectUnit: (...a: any[]) => createProjectUnit(...a),
    updateProjectUnit: (...a: any[]) => updateProjectUnit(...a),
    deleteProjectUnit: (...a: any[]) => deleteProjectUnit(...a),
  },
  AUTH_STRATEGIES: ['formulaire', 'totp', 'session_injectee', 'aucune'],
  LIBELLE_AUTH_STRATEGIE: { formulaire: 'Formulaire de connexion', totp: 'Code à usage unique (TOTP)',
                           session_injectee: 'Session déjà ouverte (jeton fourni)', aucune: 'Aucune connexion' },
}))

import OngletConfigurations from '../components/parametres/OngletConfigurations.vue'
import OngletComptes from '../components/parametres/OngletComptes.vue'
import OngletEtatDeDepart from '../components/parametres/OngletEtatDeDepart.vue'
import OngletValeursAttendues from '../components/parametres/OngletValeursAttendues.vue'
import UnitesAjoutees from '../components/parametres/UnitesAjoutees.vue'

const SECRET = 'S3cret-Commercial-9f2c'
const projet = (plus: Record<string, unknown> = {}) => ({
  id: 4, name: 'Portail', description: '', connector_type: 'web', connector_version: '', base_url: 'https://app.example',
  database: '', username: 'admin', module_count: 1, case_count: 3, effective_role: 'admin',
  calibration_writes_enabled: true, bac_a_sable_reset: '/reset', bac_a_sable_non_remis: false,
  browser_locale: 'en-GB', browser_timezone: '', browser_viewport: '390x844',
  browser_effectif: { locale: 'en-GB', timezone: 'Europe/Paris', viewport: '390x844' }, browser_avertissements: [],
  ...plus,
}) as any
const COMPTES = [
  { id: null, label: 'principal', username: 'admin', business_role: '', has_secret: true, principal: true },
  { id: 7, label: 'Commercial', username: 'banc_commercial', business_role: 'Vendeur', has_secret: true, principal: false },
]
const stubs = {
  // `v-bind="$attrs"` : le bouton factice garde son type, son état désactivé, son repère de test et son clic.
  Button: { template: '<button v-bind="$attrs"><slot/></button>', inheritAttrs: false },
  Hint: true,
  Modal: { props: ['open'], template: '<div v-if="open" data-testid="fenetre"><slot/><slot name="footer"/></div>' },
  ConfirmDialog: { props: ['open'], emits: ['confirm', 'cancel'],
                   template: '<div v-if="open" data-testid="confirmation"><button data-testid="confirmer" @click="$emit(\'confirm\')">ok</button></div>' },
}

beforeEach(() => {
  vi.clearAllMocks()
  // Comme le vrai serveur : `PATCH /api/projects/:id` rend `effective_role: ''` (il ne recalcule pas le rôle).
  updateProject.mockImplementation((_id: number, patch: any) => Promise.resolve({ ...projet(), ...patch, effective_role: '' }))
  listProjectAccounts.mockResolvedValue(COMPTES)
  createProjectAccount.mockResolvedValue({ ...COMPTES[1], id: 8 })
  updateProjectAccount.mockResolvedValue(COMPTES[1])
  deleteProjectAccount.mockResolvedValue(undefined)
  listProjectUnits.mockResolvedValue([{ id: 3, nom: 'palette', ecritures: ['palettes', 'Palettes'] }])
  createProjectUnit.mockResolvedValue({ id: 4, nom: 'carton', ecritures: [] })
  updateProjectUnit.mockResolvedValue({ id: 3, nom: 'palette', ecritures: ['palettes'] })
  deleteProjectUnit.mockResolvedValue(undefined)
  valeursDuProjetOptions.mockResolvedValue({
    formats_nombre: [{ cle: 'espace_virgule', libelle: '1 234,56' }, { cle: 'virgule_point', libelle: '1,234.56' }] })
})

describe('Paramètres de test — onglet Configurations', () => {
  it('reprend le navigateur de test déjà enregistré, sans rien à ressaisir', async () => {
    const w = mount(OngletConfigurations, { props: { projet: projet(), peutRegler: true }, global: { stubs } })

    expect((w.get('[data-testid="browser-locale"]').element as HTMLInputElement).value).toBe('en-GB')
    expect((w.get('[data-testid="browser-viewport"]').element as HTMLInputElement).value).toBe('390x844')
    // Un champ vide montre le défaut que le serveur appliquera.
    expect(w.get('[data-testid="browser-timezone"]').attributes('placeholder')).toBe('Europe/Paris')
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  })

  it('falsifiable : n\'envoie que les trois champs du navigateur, jamais l\'identité ni la connexion', async () => {
    const w = mount(OngletConfigurations, { props: { projet: projet(), peutRegler: true }, global: { stubs } })
    await w.get('[data-testid="browser-timezone"]').setValue('Africa/Dakar')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledTimes(1)
    expect(updateProject).toHaveBeenCalledWith(4, { browser_locale: 'en-GB', browser_timezone: 'Africa/Dakar', browser_viewport: '390x844' })
    expect(w.emitted('enregistre')![0][0]).toMatchObject({ id: 4, name: 'Portail', browser_timezone: 'Africa/Dakar' })
    expect(w.get('[data-testid="enregistre"]').text()).toBe('Enregistré')
  })

  it('falsifiable : le rôle sur le projet survit à l\u2019enregistrement (le serveur le rend vide)', async () => {
    const w = mount(OngletConfigurations, { props: { projet: projet(), peutRegler: true }, global: { stubs } })
    await w.get('[data-testid="browser-timezone"]').setValue('Africa/Dakar')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect((w.emitted('enregistre')![0][0] as any).effective_role).toBe('admin')
  })

  it('une saisie en cours n\u2019est pas écrasée quand la page renvoie le projet', async () => {
    const w = mount(OngletConfigurations, { props: { projet: projet(), peutRegler: true }, global: { stubs } })
    await w.get('[data-testid="browser-locale"]').setValue('fr-CA')
    await w.setProps({ projet: projet({ name: 'Portail renommé' }) })

    expect((w.get('[data-testid="browser-locale"]').element as HTMLInputElement).value).toBe('fr-CA')
  })

  it('signale une modification non enregistrée, puis la lève à l\'annulation', async () => {
    const w = mount(OngletConfigurations, { props: { projet: projet(), peutRegler: true }, global: { stubs } })
    await w.get('[data-testid="browser-locale"]').setValue('fr-FR')
    expect(w.emitted('modifie')!.at(-1)).toEqual([true])

    await w.findAll('button').find((b) => b.text() === 'Annuler')!.trigger('click')
    expect((w.get('[data-testid="browser-locale"]').element as HTMLInputElement).value).toBe('en-GB')
    expect(w.emitted('modifie')!.at(-1)).toEqual([false])
  })

  it('reste en lecture pour qui n\'administre pas le projet, et n\'envoie rien', async () => {
    const w = mount(OngletConfigurations, { props: { projet: projet(), peutRegler: false }, global: { stubs } })

    expect(w.get('fieldset').attributes('disabled')).toBeDefined()
    // On MODIFIE avant d'envoyer : sinon c'est « rien n'a changé » qui arrête l'envoi, et la garde du rôle n'est pas éprouvée.
    await w.get('[data-testid="browser-locale"]').setValue('fr-CA')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(updateProject).not.toHaveBeenCalled()
  })

  it('montre le refus du serveur et garde la saisie', async () => {
    updateProject.mockRejectedValueOnce(new Error('taille de fenêtre mal formée'))
    const w = mount(OngletConfigurations, { props: { projet: projet(), peutRegler: true }, global: { stubs } })
    await w.get('[data-testid="browser-viewport"]').setValue('grand')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(w.get('[role="alert"]').text()).toContain('taille de fenêtre mal formée')
    expect((w.get('[data-testid="browser-viewport"]').element as HTMLInputElement).value).toBe('grand')
    expect(w.emitted('enregistre')).toBeUndefined()
  })

  it('dit quand une valeur enregistrée est écartée au profit du défaut', () => {
    const w = mount(OngletConfigurations, {
      props: { projet: projet({ browser_avertissements: ['langue « xx » inconnue'] }), peutRegler: true }, global: { stubs } })

    expect(w.get('[data-testid="browser-avertissements"]').text()).toContain('langue « xx » inconnue')
  })
})

describe('Paramètres de test — onglet Comptes', () => {
  async function ouvrir(peutGerer: boolean) {
    const w = mount(OngletComptes, { props: { projet: projet(), peutGerer }, global: { stubs } })
    await flushPromises()
    return w
  }

  it('liste le compte principal puis les autres, sans jamais afficher un secret', async () => {
    const w = await ouvrir(true)
    const lignes = w.findAll('[data-testid="compte-ligne"]')

    expect(lignes).toHaveLength(2)
    expect(lignes[0].text()).toContain('principal')
    expect(lignes[0].text()).toContain('Principal')
    expect(lignes[1].text()).toContain('Commercial')
    expect(lignes[1].text()).toContain('Vendeur')
    expect(w.html()).not.toContain(SECRET)
    // Le compte principal ne se modifie ni ne se supprime ici.
    expect(lignes[0].findAll('button')).toHaveLength(0)
  })

  it('ajoute un compte par la route existante', async () => {
    const w = await ouvrir(true)
    await w.get('[data-testid="compte-ajouter"]').trigger('click')
    await w.get('[data-testid="compte-libelle"]').setValue('Gestionnaire')
    await w.get('[data-testid="compte-identifiant"]').setValue('gest.demo')
    await w.get('[data-testid="compte-mot-de-passe"]').setValue(SECRET)
    await w.get('[data-testid="compte-formulaire"]').trigger('submit')
    await flushPromises()

    expect(createProjectAccount).toHaveBeenCalledWith(4, { label: 'Gestionnaire', username: 'gest.demo', password: SECRET, business_role: '' })
    expect(w.find('[data-testid="fenetre"]').exists()).toBe(false)
    expect(listProjectAccounts).toHaveBeenCalledTimes(2)
  })

  it('falsifiable : modifier un compte sans saisir de mot de passe ne l\'envoie pas (l\'envoyer vide l\'effacerait)', async () => {
    const w = await ouvrir(true)
    await w.findAll('button').find((b) => b.text() === 'Modifier')!.trigger('click')

    expect((w.get('[data-testid="compte-mot-de-passe"]').element as HTMLInputElement).value).toBe('')
    await w.get('[data-testid="compte-libelle"]').setValue('Commercial Nord')
    await w.get('[data-testid="compte-formulaire"]').trigger('submit')
    await flushPromises()

    expect(updateProjectAccount).toHaveBeenCalledWith(4, 7, { label: 'Commercial Nord', username: 'banc_commercial', business_role: 'Vendeur' })
  })

  it('ne supprime un compte qu\'après confirmation', async () => {
    const w = await ouvrir(true)
    await w.findAll('button').find((b) => b.text() === 'Supprimer')!.trigger('click')

    expect(deleteProjectAccount).not.toHaveBeenCalled()
    await w.get('[data-testid="confirmer"]').trigger('click')
    await flushPromises()

    expect(deleteProjectAccount).toHaveBeenCalledWith(4, 7)
  })

  it('ne montre aucun geste à qui ne peut pas gérer les comptes', async () => {
    const w = await ouvrir(false)

    expect(w.find('[data-testid="compte-ajouter"]').exists()).toBe(false)
    expect(w.findAll('button')).toHaveLength(0)
    expect(w.findAll('[data-testid="compte-ligne"]')).toHaveLength(2)
  })
})

// Lot PT-01b (décision du porteur, 2026-10-13) : le compte principal se règle ici, comme les autres, avec sa façon de se connecter.
describe('Paramètres de test — onglet Comptes, compte principal', () => {
  async function ouvrir(plus: Record<string, unknown> = {}, peutRegler = true) {
    const w = mount(OngletComptes, { props: { projet: projet(plus), peutGerer: true, peutRegler }, global: { stubs } })
    await flushPromises()
    return w
  }

  it('s\'ouvre sur l\'identifiant enregistré, secrets vides', async () => {
    const w = await ouvrir({ auth_strategie: 'totp', has_totp_secret: true })
    await w.get('[data-testid="principal-modifier"]').trigger('click')

    expect((w.get('[data-testid="principal-identifiant"]').element as HTMLInputElement).value).toBe('admin')
    expect((w.get('[data-testid="principal-mot-de-passe"]').element as HTMLInputElement).value).toBe('')
    expect((w.get('[data-testid="auth-strategie"]').element as HTMLSelectElement).value).toBe('totp')
    // Le secret enregistré n'est jamais réaffiché : le champ dit seulement qu'il existe.
    expect((w.get('[data-testid="totp-secret"]').element as HTMLInputElement).value).toBe('')
    expect(w.get('[data-testid="totp-secret"]').attributes('placeholder')).toBe('Inchangé')
  })

  it('falsifiable : sans secret saisi, n\'envoie ni mot de passe ni secret (les envoyer vides les effacerait)', async () => {
    const w = await ouvrir({ auth_strategie: 'totp', has_totp_secret: true })
    await w.get('[data-testid="principal-modifier"]').trigger('click')
    await w.get('[data-testid="principal-identifiant"]').setValue('testeur')
    await w.get('[data-testid="principal-formulaire"]').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledTimes(1)
    expect(updateProject).toHaveBeenCalledWith(4, { username: 'testeur', auth_strategie: 'totp' })
    expect(w.emitted('enregistre')![0][0]).toMatchObject({ id: 4, username: 'testeur', effective_role: 'admin' })
    expect(w.find('[data-testid="principal-formulaire"]').exists()).toBe(false)
  })

  it('envoie le mot de passe et le secret quand ils sont saisis, et jamais le nom ni l\'adresse du projet', async () => {
    const w = await ouvrir()
    await w.get('[data-testid="principal-modifier"]').trigger('click')
    await w.get('[data-testid="principal-mot-de-passe"]').setValue(SECRET)
    await w.get('[data-testid="auth-strategie"]').setValue('totp')
    await w.get('[data-testid="totp-secret"]').setValue('JBSWY3DPEHPK3PXP')
    await w.get('[data-testid="principal-formulaire"]').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledWith(4, { username: 'admin', password: SECRET, auth_strategie: 'totp', totp_secret: 'JBSWY3DPEHPK3PXP' })
    expect(w.html()).not.toContain(SECRET)
  })

  it('Odoo : pas de façon de se connecter, ni à l\'écran ni dans l\'envoi', async () => {
    const w = await ouvrir({ connector_type: 'odoo' })
    await w.get('[data-testid="principal-modifier"]').trigger('click')

    expect(w.find('[data-testid="auth-strategie"]').exists()).toBe(false)
    await w.get('[data-testid="principal-identifiant"]').setValue('admin2')
    await w.get('[data-testid="principal-formulaire"]').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledWith(4, { username: 'admin2' })
  })

  it('montre le refus du serveur et garde la fenêtre ouverte', async () => {
    updateProject.mockRejectedValueOnce(new Error('secret TOTP mal formé'))
    const w = await ouvrir()
    await w.get('[data-testid="principal-modifier"]').trigger('click')
    await w.get('[data-testid="principal-formulaire"]').trigger('submit')
    await flushPromises()

    expect(w.get('[role="alert"]').text()).toContain('secret TOTP mal formé')
    expect(w.find('[data-testid="principal-formulaire"]').exists()).toBe(true)
    expect(w.emitted('enregistre')).toBeUndefined()
  })

  it('qui gère les comptes sans administrer le projet ne peut pas modifier le compte principal', async () => {
    const w = await ouvrir({}, false)

    expect(w.find('[data-testid="principal-modifier"]').exists()).toBe(false)
    expect(w.find('[data-testid="compte-ajouter"]').exists()).toBe(true)
  })
})

describe('Paramètres de test — onglet État de départ', () => {
  it('reprend l\'autorisation et l\'adresse de remise à zéro déjà enregistrées', () => {
    const w = mount(OngletEtatDeDepart, { props: { projet: projet(), peutRegler: true }, global: { stubs } })

    expect((w.get('[data-testid="bac-a-sable-autorise"]').element as HTMLInputElement).checked).toBe(true)
    expect((w.get('[data-testid="bac-a-sable-reset"]').element as HTMLInputElement).value).toBe('/reset')
  })

  it('falsifiable : n\'envoie que ses deux réglages', async () => {
    const w = mount(OngletEtatDeDepart, { props: { projet: projet(), peutRegler: true }, global: { stubs } })
    await w.get('[data-testid="bac-a-sable-reset"]').setValue('/remise-a-zero')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledWith(4, { calibration_writes_enabled: true, bac_a_sable_reset: '/remise-a-zero' })
  })

  it('Odoo : pas d\'adresse de remise à zéro, ni à l\'écran ni dans l\'envoi', async () => {
    const w = mount(OngletEtatDeDepart, {
      props: { projet: projet({ connector_type: 'odoo', calibration_writes_enabled: false, bac_a_sable_reset: '' }), peutRegler: true },
      global: { stubs } })

    expect(w.find('[data-testid="bac-a-sable-reset"]').exists()).toBe(false)
    await w.get('[data-testid="bac-a-sable-autorise"]').setValue(true)
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledWith(4, { calibration_writes_enabled: true })
  })

  it('une remise à zéro en échec se voit, et se déclare levée par la route existante', async () => {
    updateProject.mockResolvedValueOnce({ ...projet(), bac_a_sable_non_remis: false })
    const w = mount(OngletEtatDeDepart, { props: { projet: projet({ bac_a_sable_non_remis: true }), peutRegler: true }, global: { stubs } })

    expect(w.get('[data-testid="bac-a-sable-non-remis"]').text()).toContain('les exécutions de ce projet sont retenues')
    // Une adresse tapée mais pas encore enregistrée ne doit pas disparaître quand on déclare la remise à zéro.
    await w.get('[data-testid="bac-a-sable-reset"]').setValue('/nouvelle-remise')
    await w.get('[data-testid="bac-a-sable-declarer-remis"]').trigger('click')
    // Ce geste lève la retenue des exécutions : rien ne part avant la confirmation.
    expect(updateProject).not.toHaveBeenCalled()
    await w.get('[data-testid="confirmer"]').trigger('click')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledWith(4, { bac_a_sable_remis_a_zero: true })
    const enregistre = w.emitted('enregistre')![0][0] as any
    expect(enregistre).toMatchObject({ bac_a_sable_non_remis: false, effective_role: 'admin' })
    await w.setProps({ projet: enregistre })
    expect((w.get('[data-testid="bac-a-sable-reset"]').element as HTMLInputElement).value).toBe('/nouvelle-remise')
  })

  it('falsifiable : une remise à zéro déclarée pour une AUTRE adresse que celle du projet est signalée', () => {
    const perimee = mount(OngletEtatDeDepart, {
      props: { projet: projet({ base_url: 'https://production.example', bac_a_sable_reset: 'https://recette.example/reset' }), peutRegler: true },
      global: { stubs } })
    const valide = mount(OngletEtatDeDepart, {
      props: { projet: projet({ base_url: 'https://recette.example', bac_a_sable_reset: 'https://recette.example/reset' }), peutRegler: true },
      global: { stubs } })

    expect(perimee.get('[data-testid="declaration-perimee"]').text()).toContain("n'est plus celle de l'application du projet")
    expect(valide.find('[data-testid="declaration-perimee"]').exists()).toBe(false)
  })

  it('reste en lecture pour qui n\'administre pas le projet', async () => {
    const w = mount(OngletEtatDeDepart, { props: { projet: projet(), peutRegler: false }, global: { stubs } })

    expect(w.get('fieldset').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="bac-a-sable-reset"]').setValue('/autre')   // modifié : c'est bien le rôle qui arrête l'envoi
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(updateProject).not.toHaveBeenCalled()
  })
})

describe('Paramètres de test — onglet Valeurs attendues (PT-03, A38)', () => {
  const ouvrir = async (plus: Record<string, unknown> = {}, peutRegler = true) => {
    const w = mount(OngletValeursAttendues, { props: { projet: projet(plus), peutRegler }, global: { stubs } })
    await flushPromises()
    return w
  }
  const choix = (w: any, repere: string) => w.get(`[data-testid="${repere}"]`).findAll('option').map((o: any) => o.attributes('value'))

  it('un projet qui n\u2019a rien déclaré ne montre rien de choisi, et propose ce que le serveur connaît', async () => {
    const w = await ouvrir()

    expect((w.get('[data-testid="format-nombre"]').element as HTMLSelectElement).value).toBe('')
    expect(choix(w, 'format-nombre')).toEqual(['', 'espace_virgule', 'virgule_point'])
    expect(w.get('[data-testid="format-nombre"]').text()).toContain('1 234,56')
  })

  it('falsifiable (A38) : aucune monnaie n\u2019est proposée, ni envoyée — même pour un projet qui en avait une', async () => {
    const w = await ouvrir({ devise: 'EUR', format_nombre: 'espace_virgule' })
    expect(w.find('[data-testid="devise"]').exists()).toBe(false)
    expect(w.text()).not.toMatch(/monnaie/i)

    await w.get('[data-testid="format-nombre"]').setValue('virgule_point')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(updateProject).toHaveBeenCalledWith(4, { format_nombre: 'virgule_point' })
  })

  it('reprend l\u2019écriture déjà déclarée', async () => {
    const w = await ouvrir({ format_nombre: 'espace_virgule' })

    expect((w.get('[data-testid="format-nombre"]').element as HTMLSelectElement).value).toBe('espace_virgule')
  })

  it('falsifiable : n\u2019envoie que son réglage, jamais l\u2019identité ni la connexion', async () => {
    const w = await ouvrir()
    await w.get('[data-testid="format-nombre"]').setValue('espace_virgule')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledTimes(1)
    expect(updateProject).toHaveBeenCalledWith(4, { format_nombre: 'espace_virgule' })
    expect(w.get('[data-testid="enregistre"]').text()).toBe('Enregistré')
    expect(w.emitted('enregistre')![0][0]).toMatchObject({ format_nombre: 'espace_virgule', effective_role: 'admin' })
  })

  it('falsifiable : retirer la déclaration envoie une valeur vide (et non rien)', async () => {
    const w = await ouvrir({ format_nombre: 'virgule_point' })
    await w.get('[data-testid="format-nombre"]').setValue('')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledWith(4, { format_nombre: '' })
  })

  it('une écriture enregistrée reste affichée sous un libellé même si le catalogue ne répond pas', async () => {
    valeursDuProjetOptions.mockRejectedValue(new Error('Serveur injoignable'))
    const w = await ouvrir({ format_nombre: 'point_virgule' })

    expect((w.get('[data-testid="format-nombre"]').element as HTMLSelectElement).value).toBe('point_virgule')
    expect(w.get('[data-testid="format-nombre"]').text()).not.toContain('point_virgule')
    expect(w.get('[role="alert"]').text()).toContain('Serveur injoignable')
  })

  it('signale une modification non enregistrée, puis la lève à l\u2019annulation', async () => {
    const w = await ouvrir()
    await w.get('[data-testid="format-nombre"]').setValue('virgule_point')
    expect(w.emitted('modifie')!.at(-1)).toEqual([true])

    await w.findAll('button').find((b) => b.text() === 'Annuler')!.trigger('click')
    expect(w.emitted('modifie')!.at(-1)).toEqual([false])
    expect((w.get('[data-testid="format-nombre"]').element as HTMLSelectElement).value).toBe('')
  })

  it('montre le refus du serveur et garde le choix', async () => {
    updateProject.mockRejectedValue(new Error('écriture des nombres inconnue'))
    const w = await ouvrir()
    await w.get('[data-testid="format-nombre"]').setValue('virgule_point')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(w.get('[role="alert"]').text()).toContain('écriture des nombres inconnue')
    expect((w.get('[data-testid="format-nombre"]').element as HTMLSelectElement).value).toBe('virgule_point')
  })

  it('reste en lecture pour qui n\u2019administre pas le projet, et n\u2019envoie rien', async () => {
    const w = await ouvrir({}, false)

    expect(w.get('fieldset').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="format-nombre"]').setValue('virgule_point')   // modifié : c'est bien le rôle qui arrête l'envoi
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(updateProject).not.toHaveBeenCalled()
  })
})


describe('Paramètres de test — unités ajoutées (PT-03)', () => {
  const ouvrir = async (peutRegler = true) => {
    const w = mount(UnitesAjoutees, { props: { projet: projet(), peutRegler }, global: { stubs } })
    await flushPromises()
    return w
  }
  const bouton = (w: any, texte: string) => w.findAll('button').find((b: any) => b.text() === texte)!

  it('liste les unités du projet avec leurs autres écritures', async () => {
    const w = await ouvrir()

    expect(listProjectUnits).toHaveBeenCalledWith(4)
    expect(w.findAll('[data-testid="unite"]').map((l) => l.text())).toEqual([expect.stringMatching(/^palette\s*palettes, Palettes/)])
  })

  it('un projet sans unité le dit en un mot', async () => {
    listProjectUnits.mockResolvedValue([])
    const w = await ouvrir()

    expect(w.get('[data-testid="aucune-unite"]').text()).toBe('Aucune')
    expect(w.find('table').exists()).toBe(false)
  })

  it('falsifiable : ajoute une unité, ses autres écritures découpées et nettoyées', async () => {
    const w = await ouvrir()
    await w.get('[data-testid="unite-ajouter"]').trigger('click')
    await w.get('[data-testid="unite-nom"]').setValue('  carton ')
    await w.get('[data-testid="unite-ecritures"]').setValue(' cartons , Cartons,, ')
    await w.get('[data-testid="unite-formulaire"]').trigger('submit')
    await flushPromises()

    expect(createProjectUnit).toHaveBeenCalledWith(4, { nom: 'carton', ecritures: ['cartons', 'Cartons'] })
    expect(w.find('[data-testid="fenetre"]').exists()).toBe(false)
    expect(listProjectUnits).toHaveBeenCalledTimes(2)   // la liste est relue : elle montre ce que le serveur a gardé
  })

  it('modifie une unité en repartant de ce qui est enregistré', async () => {
    const w = await ouvrir()
    await bouton(w, 'Modifier').trigger('click')

    expect((w.get('[data-testid="unite-nom"]').element as HTMLInputElement).value).toBe('palette')
    expect((w.get('[data-testid="unite-ecritures"]').element as HTMLInputElement).value).toBe('palettes, Palettes')
    await w.get('[data-testid="unite-ecritures"]').setValue('palettes')
    await w.get('[data-testid="unite-formulaire"]').trigger('submit')
    await flushPromises()

    expect(updateProjectUnit).toHaveBeenCalledWith(4, 3, { nom: 'palette', ecritures: ['palettes'] })
    expect(createProjectUnit).not.toHaveBeenCalled()
  })

  it('falsifiable : le refus du serveur est montré tel quel et la fenêtre reste ouverte', async () => {
    createProjectUnit.mockRejectedValue(new Error('unité refusée : « kg » est déjà une unité ou une monnaie que l\u2019outil connaît'))
    const w = await ouvrir()
    await w.get('[data-testid="unite-ajouter"]').trigger('click')
    await w.get('[data-testid="unite-nom"]').setValue('kg')
    await w.get('[data-testid="unite-formulaire"]').trigger('submit')
    await flushPromises()

    expect(w.get('[data-testid="fenetre"] [role="alert"]').text()).toContain('est déjà une unité')
    expect((w.get('[data-testid="unite-nom"]').element as HTMLInputElement).value).toBe('kg')
  })

  it('ne supprime une unité qu\u2019après confirmation', async () => {
    const w = await ouvrir()
    await bouton(w, 'Supprimer').trigger('click')
    expect(deleteProjectUnit).not.toHaveBeenCalled()

    await w.get('[data-testid="confirmer"]').trigger('click')
    await flushPromises()
    expect(deleteProjectUnit).toHaveBeenCalledWith(4, 3)
  })

  it('falsifiable : qui n\u2019administre pas le projet lit la liste, sans aucun geste', async () => {
    const w = await ouvrir(false)

    expect(w.findAll('[data-testid="unite"]')).toHaveLength(1)
    expect(w.find('[data-testid="unite-ajouter"]').exists()).toBe(false)
    expect(w.findAll('button').map((b) => b.text())).toEqual([])
  })

  it('l\u2019onglet « Valeurs attendues » montre les unités sous la monnaie', async () => {
    const w = mount(OngletValeursAttendues, { props: { projet: projet(), peutRegler: true }, global: { stubs } })
    await flushPromises()

    expect(w.find('[data-testid="valeurs-attendues"]').exists()).toBe(true)
    expect(w.find('[data-testid="unites-ajoutees"]').exists()).toBe(true)
  })
})
