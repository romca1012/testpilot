// Composable de la session en direct (lot « Enregistrement assisté du chemin de connexion »,
// sous-lots B/C/D) : ouvre la WebSocket authentifiée par jeton, relaie le flux vidéo (JPEG en
// base64, une image par frame CDP), envoie les clics réels, et porte l'état qu'un écran affiche
// (image courante, étapes capturées, avertissement d'inactivité, erreur, fermeture).
//
// Volontairement SANS connaissance du DOM (pas de coordonnées d'affichage, pas d'`<img>`) : la
// mise à l'échelle clic-affiché → clic-réel (limite connue du sous-lot C, jamais traitée avant ce
// frontend) est la responsabilité de l'écran qui, lui seul, connaît la taille RENDUE de l'image —
// ce composable ne reçoit que des coordonnées déjà réelles, ce qui le rend testable sans jsdom ni
// mesure de layout.
import { onUnmounted, ref } from 'vue'
import { api, liveSessionWsUrl } from './api'

export type EtapeCapturee = { role: string; name: string }

export type StatutSessionLive =
  | 'connexion'      // jeton demandé, WebSocket pas encore ouverte
  | 'en_direct'       // ouverte, image(s) reçue(s), pilotable
  | 'confirmee'        // confirmé côté serveur — la séquence est en base, la session va se fermer
  | 'fermee'          // fermeture (normale, timeout, ou coupure) — voir `raisonFermeture`
  | 'erreur'          // n'a jamais pu s'ouvrir (jeton refusé, réseau…)

// Les 3 clés du formulaire de connexion, dans l'ORDRE guidé — miroir exact de
// `live_session_service.py::_CHAMPS_FORMULAIRE_CONNEXION` (extension 2026-09-30).
export type ChampFormulaireConnexion = 'champ_identifiant' | 'champ_mdp' | 'bouton_soumission'

// Messages reçus du serveur — miroir exact de `live_session.py`/`live_session_service.py`
// (jamais une reconstruction : un champ qui diverge serait une régression silencieuse ici).
type MessageServeur =
  | { type: 'image'; data: string }
  | { type: 'etape_capturee'; role: string; name: string }
  | { type: 'clic_ambigu'; detail: string }
  | { type: 'capture_arretee'; raison: string }
  | { type: 'formulaire_connexion_invite'; champ: ChampFormulaireConnexion }
  | { type: 'formulaire_connexion_champ_capture'; champ: ChampFormulaireConnexion; role: string; name: string }
  | { type: 'formulaire_connexion_complet' }
  | { type: 'erreur'; detail: string }
  | { type: 'avertissement_inactivite'; secondes_restantes: number }
  | { type: 'fermeture'; raison: 'inactivite' | 'plafond_absolu' }
  | { type: 'confirme'; etapes: number; formulaire_connexion: boolean }

export function useLiveSession(projectId: number | string) {
  const statut = ref<StatutSessionLive>('connexion')
  const image = ref('')                      // JPEG base64, prêt pour un `src="data:image/jpeg;base64,..."`
  const etapes = ref<EtapeCapturee[]>([])
  const erreur = ref('')
  const avertissementInactivite = ref<number | null>(null)
  const raisonFermeture = ref('')
  // Un clic ambigu (accname.ElementIntrouvableError côté serveur) ne bloque pas la capture (sous-
  // lot C, écart de périmètre assumé) — signalé ici pour que l'écran le montre plutôt que de
  // laisser une personne confirmer une séquence silencieusement incomplète (risque déjà noté au
  // rapport de fin de sous-lot C).
  const dernierClicAmbigu = ref('')
  // Extension (2026-09-30) : 3 clics guidés APRÈS l'écran de pré-connexion, pour identifier le
  // champ identifiant, le champ mot de passe et le bouton de soumission — jamais une valeur/texte,
  // seulement rôle/nom (miroir exact de `live_session_service.py`). `formulaireInvite` porte le
  // prochain champ attendu, ou `''` hors de ce mode ; `formulaireCapture` accumule ce qui a déjà
  // été résolu ; `formulaireComplet` devient vrai à la réception de l'accusé serveur.
  const formulaireInvite = ref<ChampFormulaireConnexion | ''>('')
  const formulaireCapture = ref<Partial<Record<ChampFormulaireConnexion, EtapeCapturee>>>({})
  const formulaireComplet = ref(false)
  // `null` tant qu'aucune confirmation n'a eu lieu — distingue « pas encore confirmé » de
  // « confirmé sans formulaire » (`false`), qui sont deux états différents pour l'écran.
  const formulaireConnexionEnregistre = ref<boolean | null>(null)

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

  function surMessage(evt: MessageEvent) {
    let message: MessageServeur
    try {
      message = JSON.parse(evt.data)
    } catch {
      return   // best-effort : un message non-JSON ne doit jamais faire planter l'écran
    }
    switch (message.type) {
      case 'image':
        image.value = message.data
        if (statut.value === 'connexion') statut.value = 'en_direct'
        break
      case 'etape_capturee':
        etapes.value = [...etapes.value, { role: message.role, name: message.name }]
        dernierClicAmbigu.value = ''
        break
      case 'clic_ambigu':
        dernierClicAmbigu.value = message.detail
        break
      case 'capture_arretee':
        // `raison: 'mot_de_passe_visible'` — le champ mot de passe est redevenu visible, la
        // capture s'arrête d'elle-même (sous-lot C, étape 5) : rien à faire ici, l'écran lit
        // `captureArretee` pour l'afficher.
        captureArretee.value = message.raison
        break
      case 'formulaire_connexion_invite':
        formulaireInvite.value = message.champ
        break
      case 'formulaire_connexion_champ_capture':
        formulaireCapture.value = { ...formulaireCapture.value,
          [message.champ]: { role: message.role, name: message.name } }
        dernierClicAmbigu.value = ''
        break
      case 'formulaire_connexion_complet':
        formulaireComplet.value = true
        formulaireInvite.value = ''
        break
      case 'avertissement_inactivite':
        avertissementInactivite.value = message.secondes_restantes
        break
      case 'fermeture':
        raisonFermeture.value = message.raison
        statut.value = 'fermee'
        fermerSocket()
        break
      case 'erreur':
        // Le serveur a refusé un `confirmer`/`recommencer` (clic encore en cours de traitement,
        // sous-lot C) — jamais fatal, l'écran invite juste à réessayer dans un instant. `statut`
        // reste `en_direct` (voir `confirmer()` : il n'anticipe plus la confirmation) — sinon ce
        // message n'aurait jamais pu s'afficher, masqué par un état déjà passé à « confirmée ».
        erreur.value = message.detail
        break
      case 'confirme':
        // Bloquant trouvé en revue verdict-reviewer (2026-09-30) : `confirmer()` faisait passer
        // `statut` à « confirmée » à l'ENVOI du message, jamais à la RÉCEPTION de cet accusé —
        // un refus serveur (`erreur: clics_en_attente`) restait alors invisible (l'écran affichait
        // déjà « confirmée »), et rien ne distinguait une confirmation VRAIMENT actée d'un simple
        // souhait côté client. Cette transition est désormais la SEULE source de vérité.
        statut.value = 'confirmee'
        formulaireConnexionEnregistre.value = message.formulaire_connexion
        break
    }
  }

  const captureArretee = ref('')

  function surFermeture() {
    if (statut.value !== 'confirmee' && statut.value !== 'fermee') {
      statut.value = 'fermee'
      raisonFermeture.value = raisonFermeture.value || 'connexion_interrompue'
    }
  }

  async function demarrer() {
    // Bloquant trouvé en revue verdict-reviewer (2026-09-30) : une remise à zéro PARTIELLE
    // (seulement `statut`/`erreur`) laissait l'état d'une session PRÉCÉDENTE visible pendant toute
    // une nouvelle session — `etapes` en particulier, ce qui pouvait faire confirmer un chemin qui
    // semblait déjà contenir des étapes alors que la nouvelle session, côté serveur, en base 0.
    // Reproduit et prouvé par le reviewer (test vitest ad hoc) : fermeture puis « Recommencer une
    // session » (qui appelle CE `demarrer()`, jamais `recommencer()`) laissait `etapes` peuplé
    // d'une capture qui n'existait plus côté serveur.
    statut.value = 'connexion'
    erreur.value = ''
    etapes.value = []
    image.value = ''
    captureArretee.value = ''
    dernierClicAmbigu.value = ''
    raisonFermeture.value = ''
    avertissementInactivite.value = null
    formulaireInvite.value = ''
    formulaireCapture.value = {}
    formulaireComplet.value = false
    formulaireConnexionEnregistre.value = null
    try {
      const jeton = await api.createLiveSession(projectId)
      socket = new WebSocket(liveSessionWsUrl(projectId, jeton.token))
      socket.onmessage = surMessage
      socket.onclose = surFermeture
      socket.onerror = surFermeture
    } catch (e: any) {
      statut.value = 'erreur'
      erreur.value = e?.message || 'Impossible de démarrer la session en direct.'
    }
  }

  // `x`/`y` en coordonnées RÉELLES du viewport distant — voir la note de tête du fichier, la mise
  // à l'échelle depuis l'image affichée est la responsabilité de l'appelant.
  function clic(x: number, y: number) {
    socket?.send(JSON.stringify({ type: 'clic', x, y }))
  }

  function confirmer() {
    // N'anticipe plus `statut`: la transition n'a lieu qu'à la réception de l'accusé serveur
    // (`case 'confirme'` dans `surMessage`) — voir le commentaire là-bas pour le bloquant que ça
    // corrige.
    socket?.send(JSON.stringify({ type: 'confirmer' }))
  }

  function recommencer() {
    etapes.value = []
    dernierClicAmbigu.value = ''
    formulaireCapture.value = {}
    formulaireComplet.value = false
    // Le navigateur réel n'est pas renavigué en arrière par un recommencer (voir
    // `live_session_service.py::reinitialiser_etapes`) : si l'écran de pré-connexion était déjà
    // franchi (`captureArretee` posé), on reste en mode formulaire et on redémarre son invite au
    // premier champ — jamais une ré-invite au serveur pour un état qu'il n'annoncera plus.
    if (captureArretee.value) formulaireInvite.value = 'champ_identifiant'
    socket?.send(JSON.stringify({ type: 'recommencer' }))
  }

  function annuler() {
    socket?.send(JSON.stringify({ type: 'annuler' }))
    statut.value = 'fermee'
    raisonFermeture.value = 'annulee'
    fermerSocket()
  }

  onUnmounted(fermerSocket)

  return {
    statut, image, etapes, erreur, avertissementInactivite, raisonFermeture,
    dernierClicAmbigu, captureArretee,
    formulaireInvite, formulaireCapture, formulaireComplet, formulaireConnexionEnregistre,
    demarrer, clic, confirmer, recommencer, annuler,
  }
}
