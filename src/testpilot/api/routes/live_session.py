"""Route WebSocket d'une session en direct — sous-lot C du lot « Enregistrement assisté du chemin
de connexion » (étapes 4-7).

⚠️ **Authentification par jeton dans l'URL, jamais par cookie.** `@app.middleware("http")`
(`api/app.py`, `verrou_acces`) ne s'exécute **jamais** sur une connexion WebSocket — limitation
Starlette documentée, vérifiée avant de coder. Le jeton du sous-lot B est donc la SEULE preuve
d'accès à cette route, consommé atomiquement avant même d'accepter la connexion (`websocket.accept()`) —
un jeton déjà utilisé, expiré ou inventé est refusé AVANT que quoi que ce soit ne s'ouvre.

⚠️ **Fermeture garantie (étape 7).** Quelle que soit l'issue — confirmation, annulation, timeout,
coupure brutale, exception — le `finally` du handler demande la fermeture du navigateur et attend
qu'elle soit effective avant de rendre la main. `WebSocketDisconnect` déclenche ce même `finally`
comme n'importe quelle autre sortie de fonction Python.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import queue as queue_mod

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket
from fastapi.exceptions import WebSocketException
from starlette.websockets import WebSocketDisconnect

from testpilot.api import access, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services.live_session_service import SessionLive
from testpilot.parametres import parcours
from testpilot.store import project_login_recordings
from testpilot.store.db import get_initialized_db
from testpilot.store.live_session_tokens import consommer, creer
from testpilot.store.repositories import CaseRepo, ParcoursRepo, ProjectRepo, UserRepo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["live-session"])

# Deux niveaux de timeout, indépendants l'un de l'autre — voir le rapport de fin de sous-lot pour
# le détail des deux scénarios prouvés (inactivité malgré un plafond non atteint, plafond atteint
# malgré une activité continue). Constantes au niveau module : les tests les réduisent par
# monkeypatch plutôt que d'attendre 20 minutes pour de vrai.
DUREE_INACTIVITE_SECONDES = 300
DUREE_AVERTISSEMENT_AVANT_INACTIVITE_SECONDES = 60
DUREE_ABSOLUE_SECONDES = 1200

_TIMEOUT_ATTENTE_FERMETURE_SECONDES = 30

# Délai laissé au thread navigateur pour finir de traiter tout clic déjà soumis avant qu'un
# `confirmer`/`recommencer` ne lise ou ne vide `service.etapes` — trouvé en revue verdict-reviewer
# (2026-09-29, reproduit avec un vrai Chromium) : sans cette attente, un clic tout juste envoyé
# pouvait être perdu d'une séquence confirmée (traité APRÈS la lecture) ou ressusciter après un
# « recommencer » (traité APRÈS le vidage). 10 s est largement au-dessus du temps réel de
# traitement d'un clic (CDP + calcul AccName, de l'ordre de quelques dizaines de ms).
_TIMEOUT_ATTENTE_CLICS_SECONDES = 10

# Ce que la page envoie au navigateur. `saisie`, `choix`, `verifier` : seulement en mode parcours (étape 7b) — le
# service de la connexion du projet les ignore.
COMMANDES_DU_NAVIGATEUR = frozenset({"clic", "saisie", "choix", "verifier"})


@router.websocket("/{project_id}/live-session/ws")
async def live_session_ws(websocket: WebSocket, project_id: int, token: str = Query(...)):
    conn = get_initialized_db()
    try:
        jeton_info = consommer(conn, token)
        # Étape 7b : un jeton de PARCOURS (`case_id`) n'ouvre jamais l'enregistrement de la connexion du projet.
        if jeton_info is None or jeton_info["project_id"] != project_id or jeton_info.get("case_id") is not None:
            # Même refus, quelle que soit la raison précise (déjà utilisé, expiré, inventé, ou
            # valide mais pour un AUTRE projet) — aucun indice qui aiderait à deviner un jeton
            # valide, même principe que `live_session_tokens.consommer`.
            raise WebSocketException(code=4401, reason="jeton invalide")
        projet = ProjectRepo(conn).get(project_id)
        if projet is None:
            raise WebSocketException(code=4404, reason="projet introuvable")
    finally:
        conn.close()

    await websocket.accept()
    service = SessionLive(project=projet, queue_label=f"session-live:{project_id}:{token[:8]}")
    service.demarrer()
    try:
        await _piloter(websocket, service,
                       lambda: _confirmer(websocket, service, project_id, jeton_info))
    finally:
        service.demander_fermeture()
        await asyncio.to_thread(service.attendre_fermeture, _TIMEOUT_ATTENTE_FERMETURE_SECONDES)
        with contextlib.suppress(RuntimeError):
            await websocket.close()


async def _pousser_sorties(websocket: WebSocket, service: SessionLive) -> None:
    """Relit `service.sortantes` (file thread-safe bloquante) sans jamais bloquer la boucle
    asyncio : `asyncio.to_thread` isole l'attente bloquante, comme `events_bus`/`_flux_evenements`
    le fait déjà ailleurs dans ce dépôt (même motif, pas une invention)."""
    while True:
        try:
            message = await asyncio.to_thread(service.sortantes.get, True, 0.5)
        except queue_mod.Empty:
            continue
        try:
            await websocket.send_json(message)
        except Exception:
            # Le socket peut déjà être fermé (coupure brutale, fermeture normale en cours) — la
            # boucle principale (`_piloter`) est l'autorité sur la fermeture, pas cette tâche.
            return


async def _piloter(websocket: WebSocket, service: SessionLive, confirmer) -> None:
    """La boucle commune aux deux enregistrements ; `confirmer` : la coroutine qui sauvegarde (connexion du projet, ou
    parcours d'un cas — étape 7b)."""
    boucle = asyncio.get_running_loop()
    fin_absolue = boucle.time() + DUREE_ABSOLUE_SECONDES
    dernier_clic_a = boucle.time()
    avertissement_envoye = False

    tache_envoi = asyncio.create_task(_pousser_sorties(websocket, service))
    try:
        while True:
            maintenant = boucle.time()
            limite_inactivite = dernier_clic_a + DUREE_INACTIVITE_SECONDES
            limite_avertissement = limite_inactivite - DUREE_AVERTISSEMENT_AVANT_INACTIVITE_SECONDES
            prochaine_echeance = min(
                fin_absolue, limite_inactivite,
                limite_avertissement if not avertissement_envoye else limite_inactivite)
            delai = max(0.0, prochaine_echeance - maintenant)

            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=delai)
            except asyncio.TimeoutError:
                # `asyncio.TimeoutError` explicitement, pas le `TimeoutError` natif : les deux ne
                # sont unifiés QUE depuis Python 3.11 — la CI de ce dépôt (« Backend — Python
                # 3.10 », CLAUDE.md §5.8) vérifie encore sur 3.10, où `wait_for` lève l'ancienne
                # classe distincte.
                maintenant = boucle.time()
                # Le plafond absolu mord même si l'inactivité n'a jamais été atteinte (activité
                # continue) — vérifié EN PREMIER, indépendamment de toute activité récente.
                if maintenant >= fin_absolue:
                    await websocket.send_json({"type": "fermeture", "raison": "plafond_absolu"})
                    return
                if maintenant >= limite_inactivite:
                    await websocket.send_json({"type": "fermeture", "raison": "inactivite"})
                    return
                if not avertissement_envoye and maintenant >= limite_avertissement:
                    avertissement_envoye = True
                    await websocket.send_json({
                        "type": "avertissement_inactivite",
                        "secondes_restantes": DUREE_AVERTISSEMENT_AVANT_INACTIVITE_SECONDES,
                    })
                continue
            except WebSocketDisconnect:
                return

            type_ = message.get("type")
            if type_ in COMMANDES_DU_NAVIGATEUR:
                # Un geste réel repousse l'échéance d'inactivité — jamais le plafond absolu, qui
                # reste un filet de sécurité indépendant de l'activité (étape 6, addendum timeout).
                dernier_clic_a = boucle.time()
                avertissement_envoye = False
                service.soumettre_clic(message)
            elif type_ == "recommencer":
                if not await _attendre_clics_ou_signaler(websocket, service):
                    continue
                service.reinitialiser_etapes()
            elif type_ == "retirer":
                if not await _attendre_clics_ou_signaler(websocket, service):
                    continue
                if service.retirer_action(int(message.get("rang", -1))):
                    await websocket.send_json({"type": "action_retiree", "rang": int(message["rang"])})
            elif type_ == "confirmer":
                if not await _attendre_clics_ou_signaler(websocket, service):
                    continue
                if await confirmer() is False:   # parcours refusé : la personne corrige et réessaie
                    continue
                return
            elif type_ == "annuler":
                return
    finally:
        tache_envoi.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tache_envoi


async def _attendre_clics_ou_signaler(websocket: WebSocket, service: SessionLive) -> bool:
    """Avant `confirmer`/`recommencer` : attend que tout clic déjà soumis ait été traité par le
    thread navigateur — jamais lire ni vider `service.etapes` pendant qu'un clic est encore en
    vol. Rend `False` (et signale l'échec au client, sans rien confirmer ni réinitialiser) si le
    délai est dépassé — un thread bloqué ne doit jamais faire agir la route sur un état encore en
    mouvement."""
    traite = await asyncio.to_thread(service.attendre_clics_traites, _TIMEOUT_ATTENTE_CLICS_SECONDES)
    if not traite:
        await websocket.send_json({"type": "erreur", "detail": "clics_en_attente"})
    return traite


async def _confirmer(websocket: WebSocket, service: SessionLive, project_id: int,
                     jeton_info: dict) -> None:
    """Étape 6 : rien n'est sauvegardé avant cet appel explicite — jamais déclenché par un simple
    clic, une déconnexion ou un timeout.

    `login_form` (extension 2026-09-30) : `None` si les 3 clics guidés n'ont pas tous abouti
    (personne arrêtée avant la fin, ou application sans écran de pré-connexion du tout) — stocké
    tel quel, jamais une valeur partielle. `enregistrer` REMPLACE alors un descripteur antérieur
    éventuel par « aucun », jamais un mélange (voir `project_login_recordings.py`)."""
    etapes = service.etapes
    login_form = service.login_form

    def _ecrire() -> None:
        conn = get_initialized_db()
        try:
            project_login_recordings.enregistrer(
                conn, project_id=project_id, etapes=etapes,
                recorded_by_user_id=jeton_info["created_by_user_id"], login_form=login_form)
        finally:
            conn.close()

    await asyncio.to_thread(_ecrire)
    await websocket.send_json({
        "type": "confirme", "etapes": len(etapes), "formulaire_connexion": login_form is not None,
    })


# ── Étape 7b (A109) : le parcours d'un cas ──────────────────────────────────────────────────────

router_parcours = APIRouter(prefix="/api/cases", tags=["parcours"])


@router_parcours.post("/{case_id}/parcours/session", response_model=schemas.LiveSessionOut, status_code=201,
                      dependencies=[Depends(access.require_project_role_depuis(
                          "case_id", access.project_id_depuis_case, access.ROLE_TESTEUR))])
def creer_session_parcours(case_id: int, request: Request, conn=Depends(get_conn)):
    """Le jeton d'une session d'enregistrement du parcours de CE cas. A109 : testeur, développeur, administrateur — le
    navigateur se connecte avec le compte du projet ; la personne ne voit jamais son mot de passe."""
    cas = CaseRepo(conn).get(case_id)
    if cas is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    jeton, expires_at = creer(conn, project_id=cas["project_id"], created_by_user_id=request.state.user["id"],
                              case_id=case_id)
    return schemas.LiveSessionOut(token=jeton, expires_at=expires_at)


@router_parcours.get("/{case_id}/parcours", response_model=schemas.ParcoursDuCasOut,
                     dependencies=[Depends(access.require_project_access_depuis(
                         "case_id", access.project_id_depuis_case))])
def lire_parcours(case_id: int, conn=Depends(get_conn)):
    """L'historique des parcours du cas, le plus récent d'abord, chacun avec son mode opératoire lisible."""
    if CaseRepo(conn).get(case_id) is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")
    return schemas.ParcoursDuCasOut(parcours=[
        schemas.ParcoursOut(id=p["id"], auteur=p["auteur"], created_at=p["created_at"], version_id=p["version_id"],
                            actions=p["actions"], mode_operatoire=parcours.mode_operatoire(p["actions"]))
        for p in ParcoursRepo(conn).du_cas(case_id)])


@router_parcours.websocket("/{case_id}/parcours/ws")
async def parcours_ws(websocket: WebSocket, case_id: int, token: str = Query(...)):
    conn = get_initialized_db()
    try:
        jeton_info = consommer(conn, token)
        cas = CaseRepo(conn).get(case_id)
        # Même refus quelle que soit la raison : jeton usé, expiré, inventé, d'un autre cas, ou de la connexion du projet.
        if jeton_info is None or jeton_info.get("case_id") != case_id or cas is None \
                or cas["project_id"] != jeton_info["project_id"]:
            raise WebSocketException(code=4401, reason="jeton invalide")
        projet = ProjectRepo(conn).get(jeton_info["project_id"])
        if projet is None:
            raise WebSocketException(code=4404, reason="projet introuvable")
        from testpilot.api.services.exploration_service import connexion_du_projet

        connexion = connexion_du_projet(conn, projet)
        auteur = (UserRepo(conn).get(jeton_info["created_by_user_id"]) or {}).get("username") or ""
    finally:
        conn.close()

    await websocket.accept()
    service = SessionLive(project=projet, queue_label=f"parcours:{case_id}:{token[:8]}", mode="parcours",
                          connexion=connexion)
    service.demarrer()
    try:
        await _piloter(websocket, service,
                       lambda: _confirmer_parcours(websocket, service, projet["id"], case_id, auteur))
    finally:
        service.demander_fermeture()
        await asyncio.to_thread(service.attendre_fermeture, _TIMEOUT_ATTENTE_FERMETURE_SECONDES)
        with contextlib.suppress(RuntimeError):
            await websocket.close()


async def _confirmer_parcours(websocket: WebSocket, service: SessionLive, project_id: int, case_id: int,
                              auteur: str) -> bool:
    """Rien n'est gardé avant « Enregistrer ». Un nouveau parcours s'ajoute à l'historique, jamais à la place d'un autre."""
    try:
        actions = parcours.normaliser(service.actions)
    except parcours.ParcoursInvalide as exc:
        await websocket.send_json({"type": "erreur", "detail": "parcours_invalide", "message": str(exc)})
        return False

    def _ecrire() -> int:
        conn = get_initialized_db()
        try:
            return ParcoursRepo(conn).enregistrer(project_id=project_id, case_id=case_id, actions=actions,
                                                  auteur=auteur)
        finally:
            conn.close()

    parcours_id = await asyncio.to_thread(_ecrire)
    await websocket.send_json({"type": "confirme", "actions": len(actions), "parcours_id": parcours_id})
    return True
