// Étape 7b (A109) : le parcours d'un cas, joué dans le navigateur en direct. Même transport que `useLiveSession.ts` (jeton
// à usage unique, WebSocket, images JPEG) ; ici la personne clique, saisit, choisit dans une liste et désigne l'élément où
// elle vérifie le résultat. Rien n'est gardé avant « Enregistrer » ; un mot de passe n'est jamais gardé (le serveur vide sa
// valeur). Comme `useLiveSession`, ce composable ne connaît pas le DOM : il reçoit des coordonnées déjà réelles.
import { onUnmounted, ref } from 'vue'
import { api, parcoursWsUrl, type ActionParcours } from './api'

export type StatutParcours = 'connexion' | 'en_direct' | 'enregistre' | 'fermee' | 'erreur'

// Le champ que la personne vient de désigner : la valeur suit (saisie, ou choix pour une liste).
export interface ChampDesigne { nom: string; secret: boolean; options: string[] }

type MessageServeur =
  | { type: 'image'; data: string }
  | { type: 'connexion_auto'; ok: boolean }
  | { type: 'capture_commencee' }
  | ({ type: 'action_capturee'; rang: number } & ActionParcours)
  | { type: 'champ_designe'; nom: string; secret: boolean; options: string[] }
  | { type: 'action_retiree'; rang: number }
  | { type: 'clic_ambigu'; detail: string }
  | { type: 'clic_non_enregistre'; raison: string }
  | { type: 'erreur'; detail: string; message?: string }
  | { type: 'avertissement_inactivite'; secondes_restantes: number }
  | { type: 'fermeture'; raison: string }
  | { type: 'confirme'; actions: number; parcours_id: number }

const NON_ENREGISTRE: Record<string, string> = {
  element_non_reconnu: 'Élément non reconnu : l\'action a été faite mais pas ajoutée au parcours.',
  element_sans_designation: 'Cet élément n\'a pas d\'identifiant : choisissez-en un autre où lire le résultat.',
  mot_de_passe: 'Mot de passe saisi, mais jamais enregistré dans le parcours.',
}

const ERREURS: Record<string, string> = {
  saisie_impossible: 'La saisie n\'a pas pu se faire dans ce champ.',
  choix_impossible: 'Ce choix n\'a pas pu se faire.',
  rang_invalide: 'Action introuvable.',
  aucun_champ_designe: 'Cliquez d\'abord sur le champ à remplir.',
  aucune_liste_designee: 'Cliquez d\'abord sur la liste.',
  clics_en_attente: 'Une action est encore en cours — réessayez dans un instant.',
  navigateur: 'Le navigateur distant s\'est arrêté.',
}

export function useParcours(caseId: number | string) {
  const statut = ref<StatutParcours>('connexion')
  const image = ref('')
  const actions = ref<ActionParcours[]>([])
  const champ = ref<ChampDesigne | null>(null)
  const connexionAuto = ref<boolean | null>(null)
  // Connexion automatique en échec : rien n'est capturé avant « Je suis connecté » (la connexion n'entre jamais au parcours).
  const captureCommencee = ref(false)
  const avertissement = ref('')        // clic ambigu ou non retenu : dit, jamais silencieux
  const erreur = ref('')
  const avertissementInactivite = ref<number | null>(null)
  const raisonFermeture = ref('')

  let socket: WebSocket | null = null

  function fermerSocket() {
    if (socket) {
      socket.onmessage = null
      socket.onclose = null
      socket.onerror = null
      socket.close()
      socket = null
    }
  }

  function envoyer(message: object) {
    socket?.send(JSON.stringify(message))
  }

  function surMessage(evt: MessageEvent) {
    let m: MessageServeur
    try {
      m = JSON.parse(evt.data)
    } catch {
      return
    }
    switch (m.type) {
      case 'image':
        image.value = m.data
        if (statut.value === 'connexion') statut.value = 'en_direct'
        break
      case 'connexion_auto':
        connexionAuto.value = m.ok
        break
      case 'capture_commencee':
        captureCommencee.value = true
        actions.value = []
        champ.value = null
        break
      case 'action_capturee': {
        const { type: _t, rang: _r, ...action } = m
        actions.value = [...actions.value, action]
        champ.value = null
        avertissement.value = ''
        erreur.value = ''
        break
      }
      case 'champ_designe':
        champ.value = { nom: m.nom, secret: m.secret, options: m.options || [] }
        avertissement.value = ''
        break
      case 'action_retiree':
        actions.value = actions.value.filter((_, i) => i !== m.rang)
        break
      case 'clic_ambigu':
        avertissement.value = 'Plusieurs éléments identiques à cet endroit : l\'action n\'a pas été ajoutée.'
        break
      case 'clic_non_enregistre':
        avertissement.value = NON_ENREGISTRE[m.raison] || NON_ENREGISTRE.element_non_reconnu
        if (m.raison === 'mot_de_passe') champ.value = null
        break
      case 'erreur':
        erreur.value = m.message || ERREURS[m.detail] || m.detail
        break
      case 'avertissement_inactivite':
        avertissementInactivite.value = m.secondes_restantes
        break
      case 'fermeture':
        raisonFermeture.value = m.raison
        statut.value = 'fermee'
        fermerSocket()
        break
      case 'confirme':
        statut.value = 'enregistre'
        break
    }
  }

  function surFermeture() {
    if (statut.value !== 'enregistre' && statut.value !== 'fermee') {
      statut.value = 'fermee'
      raisonFermeture.value = raisonFermeture.value || 'connexion_interrompue'
    }
  }

  async function demarrer() {
    statut.value = 'connexion'
    image.value = ''
    actions.value = []
    champ.value = null
    connexionAuto.value = null
    captureCommencee.value = false
    avertissement.value = ''
    erreur.value = ''
    avertissementInactivite.value = null
    raisonFermeture.value = ''
    try {
      const jeton = await api.createParcoursSession(caseId)
      socket = new WebSocket(parcoursWsUrl(caseId, jeton.token))
      socket.onmessage = surMessage
      socket.onclose = surFermeture
      socket.onerror = surFermeture
    } catch (e: any) {
      statut.value = 'erreur'
      erreur.value = e?.message || 'Impossible d\'ouvrir le navigateur.'
    }
  }

  const clic = (x: number, y: number) => { avertissementInactivite.value = null; envoyer({ type: 'clic', x, y }) }
  const verifier = (x: number, y: number) => { avertissementInactivite.value = null; envoyer({ type: 'verifier', x, y }) }
  const saisir = (valeur: string) => envoyer({ type: 'saisie', valeur })
  const choisir = (valeur: string) => envoyer({ type: 'choix', valeur })
  const retirer = (rang: number) => envoyer({ type: 'retirer', rang })
  const commencer = () => envoyer({ type: 'commencer' })
  const enregistrer = () => envoyer({ type: 'confirmer' })   // l'état ne change qu'à l'accusé du serveur

  function annuler() {
    envoyer({ type: 'annuler' })
    statut.value = 'fermee'
    raisonFermeture.value = 'annulee'
    fermerSocket()
  }

  onUnmounted(fermerSocket)

  return {
    statut, image, actions, champ, connexionAuto, captureCommencee, avertissement, erreur, avertissementInactivite,
    raisonFermeture, demarrer, clic, verifier, saisir, choisir, retirer, commencer, enregistrer, annuler,
  }
}
