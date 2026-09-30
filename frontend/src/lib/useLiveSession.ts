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

// Messages reçus du serveur — miroir exact de `live_session.py`/`live_session_service.py`
// (jamais une reconstruction : un champ qui diverge serait une régression silencieuse ici).
type MessageServeur =
  | { type: 'image'; data: string }
  | { type: 'etape_capturee'; role: string; name: string }
  | { type: 'clic_ambigu'; detail: string }
  | { type: 'capture_arretee'; raison: string }
  | { type: 'erreur'; detail: string }
  | { type: 'avertissement_inactivite'; secondes_restantes: number }
  | { type: 'fermeture'; raison: 'inactivite' | 'plafond_absolu' }
  | { type: 'confirme'; etapes: number }

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
        // sous-lot C) — jamais fatal, l'écran invite juste à réessayer dans un instant.
        erreur.value = message.detail
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
    statut.value = 'connexion'
    erreur.value = ''
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
    socket?.send(JSON.stringify({ type: 'confirmer' }))
    statut.value = 'confirmee'
  }

  function recommencer() {
    etapes.value = []
    dernierClicAmbigu.value = ''
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
    demarrer, clic, confirmer, recommencer, annuler,
  }
}
