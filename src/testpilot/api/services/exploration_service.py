"""Exploration d'un projet — cartographier l'application AVANT d'écrire des tests contre elle.

C'est l'étape 2 du flux produit : on crée un projet, on saisit son connecteur, **on explore
l'application**, et seulement ensuite on écrit des cas. L'exploration est **payée une fois par
projet** ; toutes les générations suivantes lisent sa cartographie au lieu de deviner.

⚠️ **Aucun LLM ici.** Le crawl est un parcours Playwright déterministe : il ouvre des pages, lit
les formulaires et les liens, et écrit ce qu'il a vu. C'est ce qui distingue un **fait mesuré**
d'une **supposition** — la décision `0022` n°2.b exige que les routes, champs et valeurs viennent
de l'annuaire, plus d'un modèle qui lit la spec.

⚠️ **La cartographie est propre au PROJET, pas au type de connecteur** (décision `0005` appliquée
à ce qui lui avait échappé). Deux projets Odoo peuvent être deux instances différentes, avec des
modules, des routes et des champs différents.

La mesure est une **photo, et elle vieillit** : tout ce qui la consomme doit rester détective et
dire sa date (cf. `domain_model`). Ré-explorer est un geste humain, jamais automatique — sinon une
régression de l'application (un champ disparu) serait enregistrée comme la nouvelle vérité, et le
smoke-check se tairait. C'est le faux négatif que ce projet traque.

Étape 4, morceau 6 (A69 révisée, A77-A83 — porteur, 2026-10-21) : l'exploration est celle de l'APPLICATION, pour tous les cas
du projet. Elle passe par le compte principal (`projet-N.json`, EXACTEMENT comme avant : tous ses lecteurs n'y voient rien de
nouveau), puis par chaque compte déclaré (annexe `projet-N-comptes.json`) ; `charger_carte` en tire UNE carte qui dit quel compte
voit quoi. Plus aucune limite de pages (A81) ; pendant tout ce temps l'application est occupée (A77) ; la progression se voit et
l'exploration s'arrête sur demande (A83) — une exploration arrêtée est dite « incomplète », jamais présentée comme complète.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import types
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path

from testpilot.generation import carte_des_comptes, domain_model
from testpilot.store.repositories import ProjectAccountRepo, ProjectRepo

logger = logging.getLogger(__name__)

# job_id → {status: running|done|failed, project_id, error, resume, progression, arret_demande}
_JOBS: dict[str, dict] = {}
_RESERVATION = threading.Lock()   # « déjà en cours ? » puis réservation : d'un seul tenant, jamais deux explorations

# A81 (porteur, 2026-10-21) : PLUS AUCUNE LIMITE — les 60 pages tronquaient (projet 18 arrêté à exactement 60, projet 9 à 58).
# L'exploration finit quand tous les modèles de page sont visités ; les pages sœurs identiques sont regroupées (A82).
MAX_PAGES_DEFAUT: int | None = None


class ConnexionDuCompteImpossible(RuntimeError):
    """Un compte secondaire n'a pas pu se connecter (ou la session ouverte n'est pas la sienne) : son relevé n'est pas fait."""


class ExplorationError(Exception):
    """Erreur métier de déclenchement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code  # not_found | no_connection | already_running
        self.detail = detail


def get_job(job_id: str) -> dict | None:
    return _JOBS.get(job_id)


def job_en_cours(project_id: int) -> str | None:
    """Le job d'exploration en cours pour ce projet, s'il y en a un."""
    for jid, job in _JOBS.items():
        if job.get("project_id") == project_id and job.get("status") == "running":
            return jid
    return None


def etat(project_id: int, projet: dict | None = None, conn=None) -> dict:
    """Ce que l'écran affiche : y a-t-il une cartographie, de quand, et combien couvre-t-elle.

    Étape 4, morceau 6 : la progression (« 142 pages vues · compte 2 sur 3 »), une exploration incomplète (A83), les familles de
    pages regroupées (A82) et, avec `conn`, l'état de chaque compte (exploré, en échec, à actualiser). Les nombres de routes
    et de champs restent ceux du principal (A79)."""
    modele = domain_model.charger_modele(projet) if projet else None
    job_id = job_en_cours(project_id)
    job = _JOBS.get(job_id) or {} if job_id else {}
    incomplete = (modele or {}).get("exploration_incomplete") or {}
    comptes = etat_des_comptes(conn, projet) if conn is not None and projet else {"total": 0, "par_compte": {}}
    pages = (modele or {}).get("pages") or {}
    transitions = (modele or {}).get("transitions") or {}
    champs = [c for i in pages.values() for c in (i.get("champs") or [])]
    return {
        "explored": bool(pages),
        "running": job_id is not None,
        "job_id": job_id or "",
        "mesure_le": (modele or {}).get("mesure_le", ""),
        "pages": len(pages),
        "transitions": sum(len(v) for v in transitions.values()),
        "champs": len(champs),
        # ⚠️ Le compte des RÈGLES DE VALIDATION est affiché parce qu'il est le seul signe VISIBLE
        # qu'une cartographie est à jour. Le 2026-07-21, une ré-exploration lancée depuis
        # l'interface a réécrit l'annuaire à l'identique — code de crawl périmé chargé en mémoire —
        # en affichant « terminée » : 37 routes, 373 champs, exactement comme avant. Rien à l'écran
        # ne pouvait le trahir. Les routes et les champs bougent peu ; les règles, elles, n'existent
        # que depuis la mesure enrichie. Zéro règle sur un portail qui en a = mesure à refaire.
        "contraintes": sum(1 for c in champs if c.get("contraintes")),
        # Complément back-office (2026-09-18) : sans ça, rien à l'écran ne dit si
        # `discover_menus` a effectivement tourné sur CETTE exploration — visible seulement en
        # lisant le fichier `data/domain/…json` à la main. Même motif que les règles de validation
        # ci-dessus : un signe visible qu'une mesure a bien apporté ce qu'elle promet.
        "modeles_backoffice": len((modele or {}).get("modeles_backoffice") or []),
        "resume": domain_model.resume(modele),
        "progression": dict(job.get("progression") or {}) if job_id else {},
        "arret_demande": bool(job.get("arret_demande")) if job_id else False,
        "incomplete": incomplete.get("raison", ""),
        "incomplete_pages": int(incomplete.get("pages") or 0),
        "familles": [{"modele": k, "exemples": v.get("exemples") or [], "pages_du_meme_modele": v.get("pages_du_meme_modele", 0)}
                     for k, v in ((modele or {}).get("familles") or {}).items()],
        # A84 : une exploration arrêtée qui a laissé la carte précédente en place — l'écran le dit.
        "derniere_tentative": _lire_json(domain_model.chemin_derniere_tentative(project_id)) or {} if modele else {},
        "comptes_total": comptes["total"],
        "comptes": [{"id": cid, **etat_compte} for cid, etat_compte in comptes["par_compte"].items()],
    }


def start_exploration(conn, project_id: int) -> tuple[str, dict]:
    """Valide la demande et prépare le job. Renvoie (job_id, paramètres de la tâche de fond)."""
    projet = ProjectRepo(conn).get(project_id)
    if projet is None:
        raise ExplorationError("not_found", f"projet {project_id} introuvable")
    # On refuse AVANT de lancer un navigateur : sans connexion complète, le crawl échouerait après
    # plusieurs secondes sur une erreur réseau incompréhensible — ou pire, explorerait l'instance
    # par défaut de la machine et écrirait un annuaire qui ne décrit PAS ce projet (2026-07-24).
    # Le message dit quoi corriger.
    from testpilot.connectors.runtime_env import ConnexionIncomplete, _config_oracle, verifier_connexion
    try:
        verifier_connexion(projet)
    except ConnexionIncomplete as err:
        raise ExplorationError("no_connection", err.message()) from err
    from testpilot.store import project_login_recordings

    with _RESERVATION:
        if job_en_cours(project_id):
            # Deux crawls simultanés écriraient le même fichier : le dernier gagnerait, et la mesure
            # rendue serait un mélange de deux passages.
            raise ExplorationError("already_running", "une exploration est déjà en cours sur ce projet")
        job_id = uuid.uuid4().hex
        _JOBS[job_id] = _nouveau_job(project_id)
    from testpilot.connectors.runtime_env import comptes_pour_l_exploration

    # Étape 4, morceau 6 : les comptes à parcourir, lus AU LANCEMENT — leurs secrets voyagent comme celui du principal, dans
    # les paramètres CHIFFRÉS de la tâche (`BackgroundJobRepo.creer`), jamais en clair, jamais dans un fichier de mesure.
    return job_id, {"project_id": project_id, "comptes": comptes_pour_l_exploration(conn, project_id), "connexion": {
        "base_url": projet.get("base_url") or "", "database": projet.get("database") or "",
        "username": projet.get("username") or "", "password": projet.get("password") or "",
        "connector_type": projet.get("connector_type") or "odoo",
        "nom": projet.get("name") or "",
        # Lot 07c : le contexte navigateur FIGÉ du projet — le crawl doit voir ce que le test verra.
        "browser_locale": projet.get("browser_locale") or "",
        "browser_timezone": projet.get("browser_timezone") or "",
        "browser_viewport": projet.get("browser_viewport") or "",
        # Sous-lot D (« Enregistrement assisté du chemin de connexion ») : la séquence confirmée
        # qui franchit un écran intercalé avant le formulaire de connexion, ou `[]` si aucune n'a
        # jamais été enregistrée pour ce projet — lue UNE fois ici (conn disponible), jamais par
        # le connecteur lui-même (voir `GenericWebConnector.from_project`).
        "sequence_connexion": project_login_recordings.lire(conn, project_id) or [],
        # Extension (2026-09-30) : le descripteur du formulaire de connexion lui-même (3 clics
        # guidés), ou `None` si jamais capturé — même motif que `sequence_connexion` ci-dessus.
        "login_form": project_login_recordings.lire_formulaire(conn, project_id),
        # Lot VH-08 (A51) : l'oracle du projet, pour en relever la FORME des réponses (requêtes GET seulement). `None` : aucun.
        "oracle": _config_oracle(projet),
        # Étape 4, morceau 6 : un projet web qui ne se connecte pas ne peut explorer aucun compte (même règle que l'exécution).
        "auth_strategie": projet.get("auth_strategie") or "",
    }}


def _nouveau_job(project_id: int) -> dict:
    return {"status": "running", "project_id": project_id, "error": "", "resume": "", "arret_demande": False,
            "progression": {"rang": 1, "total": 1, "libelle": carte_des_comptes.PRINCIPAL, "pages": 0, "attente": False}}


def demander_arret(project_id: int) -> bool:
    """A83 : « Arrêter ». Le crawl s'arrête à la page suivante ; ce qui a été vu est gardé et dit « incomplet »."""
    job_id = job_en_cours(project_id)
    if job_id is None:
        return False
    _JOBS[job_id]["arret_demande"] = True
    return True


def _crawl(connexion: dict, max_pages: int) -> dict:
    """Le parcours lui-même. Isolé pour être remplaçable en test (il exige un vrai navigateur).

    Réutilise `scripts/crawl_domaine.py` — sa logique BFS, sa normalisation de routes et sa
    tolérance au crash du navigateur sont éprouvées sur une mesure réelle (38 routes). La
    dupliquer ici en ferait deux versions à maintenir, qui divergeraient.

    ⚠️ **Ne branche plus sur `connector_type` (étape 1.1 du plan de consolidation, 2026-09-15).**
    Jusqu'ici, ce service choisissait racines/exclusion/connexion par un `if connector_type ==
    "odoo": ... else: ...` en dur — exactement le défaut que `connectors/factory.py` avait déjà
    fermé pour la génération et la réparation (2026-09-11), mais pas encore ici. Les 4 paramètres
    du crawl viennent maintenant du connecteur du projet (`Connector.crawl_roots`/
    `crawl_exclusion_pattern`/`crawl_relogin_hook`/`crawl_follow_hash_anchors`) : un 3ᵉ type de
    connecteur n'exige plus de modifier ce fichier, seulement d'implémenter ces 4 méthodes.
    """
    racine = Path(__file__).resolve().parents[4]
    for chemin in (racine / "scripts", racine / "behave_runtime" / "steps_library"):
        if str(chemin) not in sys.path:
            sys.path.insert(0, str(chemin))

    from playwright.sync_api import sync_playwright

    import crawl_domaine as cd
    from testpilot.connectors.contexte_navigateur import depuis_projet
    from testpilot.connectors.factory import build_connector

    connector = build_connector(connexion)
    suivi = connexion.get("_suivi") or {}
    bilan: dict = {}
    # Lot 07c (revue) : `nav.new_page()` nu prenait la langue et le fuseau de la MACHINE et une fenêtre de 1280x720 — un projet
    # réglé en fr-FR pouvait être crawlé en en-US. Le contexte est aussi posé sur `ctx` : le crawl recrée sa page après un crash.
    contexte_navigateur = depuis_projet(connexion).kwargs()

    with sync_playwright() as p:
        from testpilot.connectors.contexte_navigateur import arguments_de_confinement
        nav = p.chromium.launch(args=arguments_de_confinement())
        ctx = types.SimpleNamespace(page=nav.new_page(**contexte_navigateur), contexte_navigateur=contexte_navigateur)
        relogin = connector.crawl_relogin_hook()
        libelle = connexion.get("compte_libelle")
        if libelle:
            # Étape 4, morceau 6 : un compte SECONDAIRE doit prouver qu'il est connecté — à la première connexion comme après
            # chaque relance du navigateur. Sinon son relevé dirait « ce compte voit… » sur des écrans vus sans lui.
            connexion_brute = relogin

            def relogin(c):
                try:
                    connexion_brute(c)
                except Exception as exc:
                    # Le type d'erreur va au journal, pas à l'écran : l'utilisateur doit lire quoi faire.
                    logger.warning("[exploration] connexion du compte « %s » : %s", libelle, type(exc).__name__)
                    raise ConnexionDuCompteImpossible(
                        "connexion impossible — vérifiez son identifiant et son mot de passe") from exc
                raison = connector.crawl_identite_confirmee(c, connexion["username"])
                if raison:
                    raise ConnexionDuCompteImpossible(raison)
        relogin(ctx)  # première connexion — la même fonction sert de repli après un crash
        pages, transitions, onglets = cd.crawler(
            ctx, nav, connexion["base_url"], max_pages,
            racines=connector.crawl_roots(ctx.page),
            hors_perimetre=connector.crawl_exclusion_pattern(),
            relogin=relogin, suivre_ancres_hash=connector.crawl_follow_hash_anchors(),
            bilan=bilan, progression=suivi.get("progression"), arreter=suivi.get("arreter"))
        # ⚠️ La page de CONNEXION elle-même n'est jamais visitée par le BFS ci-dessus (il démarre
        # APRÈS la connexion, là où elle a laissé la page — `crawl_roots`) : sans ce complément,
        # ses champs (souvent le SEUL endroit où ils existent) restent invisibles à l'annuaire,
        # et « Points de vigilance » (`smoke_check.check_champs_existants`) les signale à tort
        # comme inconnus sur chaque cas qui s'y réfère (correctif du 2026-09-15, cas réel
        # SauceDemo). `setdefault` : une mesure du BFS, plus complète, prime toujours si les deux
        # coïncidaient un jour.
        page_connexion = getattr(ctx, "page_connexion", None)
        if page_connexion:
            route, infos = page_connexion
            pages.setdefault(route, infos)
        # ⚠️ Complément au BFS, jamais un remplacement (2026-09-18, module Parc IT/Odoo) : le
        # crawl n'atteint JAMAIS le back-office d'un connecteur comme Odoo — un module qui n'y vit
        # que là (menus, pas de lien portail) reste invisible au BFS quoi qu'il arrive, et son nom
        # de modèle technique impossible à deviner sans lui. Best-effort : un connecteur qui n'a
        # pas ce mécanisme (défaut de `Connector.discover_menus`) rend simplement `[]`.
        try:
            modeles_backoffice = connector.discover_menus(ctx.page)
        except Exception as exc:
            logger.warning("[exploration] découverte des menus a échoué : %s", exc)
            modeles_backoffice = []
        # Étape 4, morceau 6 : les menus que CE compte voit, pour la carte (jamais écrits dans le modèle du principal) ; et la
        # session est-elle restée la sienne jusqu'au bout ? Sinon « ne voit pas » ne pourra jamais être affirmé.
        try:
            menus_visibles = connector.menus_visibles(ctx.page)
        except Exception as exc:
            logger.warning("[exploration] menus visibles illisibles : %s", type(exc).__name__)
            menus_visibles = None
        try:
            session_fin = connector.crawl_session_toujours_ouverte(ctx, connexion.get("username") or "")
        except Exception as exc:
            logger.warning("[exploration] session de fin de parcours illisible : %s", type(exc).__name__)
            session_fin = None
        try:
            nav.close()
        except Exception:
            pass  # le navigateur a pu mourir : la mesure, elle, est faite

    return {
        "pages": pages,
        "transitions": {k: sorted(v) for k, v in transitions.items()},
        "onglets_internes": {k: sorted(v) for k, v in onglets.items()},
        "modeles_backoffice": modeles_backoffice,
        "familles": bilan.get("familles") or {},
        "_menus_visibles": menus_visibles,
        "_session_fin": session_fin,
        "_arretee": bool(bilan.get("arretee")),
        "_interrompue": bool(bilan.get("interrompue")),
    }


def _relever_l_oracle(config: dict) -> dict:
    """{requête: forme} pour les requêtes GET déclarées (`connectors/forme_oracle`). Isolé pour être remplaçable en test."""
    from testpilot.connectors import forme_oracle
    from testpilot.connectors.oracle_http import OracleHttp

    oracle = OracleHttp(config.get("base_url") or "", config.get("auth") or {}, config.get("queries") or [])
    lecture = forme_oracle.requetes_en_lecture(json.dumps(config.get("queries") or []))
    return forme_oracle.relever(oracle.executer, lecture)


def _suivi(job_id: str, rang: int, total: int, libelle: str) -> dict:
    """La progression affichée (« 142 pages vues · compte 2 sur 3 ») et la demande d'arrêt, pour UN passage du crawl."""
    progression = _JOBS[job_id]["progression"]
    progression.update(rang=rang, total=total, libelle=libelle, pages=0, attente=False)
    return {"progression": lambda n: progression.update(pages=n),
            "arreter": lambda: bool(_JOBS[job_id].get("arret_demande"))}


def _incomplete(mesure: dict) -> str:
    """`""` si le crawl est allé au bout ; sinon pourquoi il ne l'est pas (A83 : jamais présenté comme complet)."""
    if mesure.get("_arretee"):
        return "arrêtée"
    if mesure.get("_interrompue"):
        return "interrompue"   # le navigateur a planté et n'a pas pu être relancé
    if mesure.get("_session_fin") is False:
        return "session perdue en cours de route"
    return ""


def _absence_fiable(mesure: dict) -> bool:
    """« Ce compte ne voit pas X » ne se conclura que d'un parcours complet DONT la session a été revérifiée à la fin."""
    return not _incomplete(mesure) and mesure.get("_session_fin") is True


def _sans_marques(mesure: dict) -> dict:
    return {k: v for k, v in mesure.items() if not k.startswith("_")}


def _masquer(objet, secrets: list[str], intouchables: frozenset = frozenset()):
    """Aucun identifiant ni mot de passe d'un compte dans un fichier : remplacés partout où une page les afficherait — clés
    comprises (une route `/profil/jdupont`). Par MOT ENTIER seulement (revue du 2026-10-21) : remplacer une sous-chaîne
    abîmait la structure (identifiant « user » → le champ `username` devenait `•••name`, et la carte ne le retrouvait plus)."""
    import re

    if isinstance(objet, str):
        if objet in intouchables:
            return objet   # une route ou un champ que le PRINCIPAL voit aussi (`/admin/…` pour un identifiant « admin »)
        for secret in secrets:
            objet = re.sub(rf"(?<![\w]){re.escape(secret)}(?![\w])", "•••", objet)
        return objet
    if isinstance(objet, list):
        return [_masquer(x, secrets, intouchables) for x in objet]
    if isinstance(objet, dict):
        return {_masquer(k, secrets, intouchables): _masquer(v, secrets, intouchables) for k, v in objet.items()}
    return objet


def _structure_du_principal(modele: dict) -> frozenset:
    """Routes et noms de champs du principal : jamais masqués dans le relevé d'un compte (sinon la carte ne les rapproche
    plus, et un compte complet « ne verrait pas » une page qu'il voit). Ils ne sont pas un secret : le principal les voit."""
    pages = (modele or {}).get("pages") or {}
    return frozenset(list(pages) + [c.get("name", "") for p in pages.values() for c in (p.get("champs") or [])])


def _ecrire(chemin: Path, contenu: dict) -> None:
    """Écriture d'un seul tenant (fichier temporaire puis remplacement) : un lecteur ne voit jamais un fichier à moitié écrit."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    temporaire = chemin.with_suffix(chemin.suffix + ".tmp")
    temporaire.write_text(json.dumps(contenu, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporaire, chemin)


def _lire_json(chemin: Path) -> dict | None:
    try:
        return json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _empreinte_du_fichier(chemin: Path) -> str:
    try:
        return hashlib.sha256(chemin.read_bytes()).hexdigest()
    except OSError:
        return ""


def run_exploration(job_id: str, *, project_id: int, connexion: dict, comptes: list[dict] | None = None,
                    max_pages: int | None = MAX_PAGES_DEFAUT) -> None:
    """Tâche de fond : cartographie l'application DU PROJET — le principal, puis chaque compte déclaré — et range le résultat
    sous son id. L'application est tenue pendant tout ce temps (A77)."""
    from testpilot.guardrails import bac_a_sable

    arret_deja_demande = bool((_JOBS.get(job_id) or {}).get("arret_demande"))
    _JOBS[job_id] = _nouveau_job(project_id)
    _JOBS[job_id]["arret_demande"] = arret_deja_demande
    try:
        progression = _JOBS[job_id]["progression"]
        with bac_a_sable.exploration(bac_a_sable.cle_d_application(connexion.get("base_url")),
                                     en_attente=lambda: progression.update(attente=True)):
            _explorer(job_id, project_id, connexion, comptes or [], max_pages)
    except Exception as exc:  # jamais laisser un job « en cours » sur un plantage
        logger.exception("[exploration] job %s en échec : %s", job_id, exc)
        _JOBS[job_id].update(status="failed", error=str(exc)[:300])


def _explorer(job_id: str, project_id: int, connexion: dict, comptes: list[dict], max_pages: int | None) -> None:
    total = 1 + len(comptes)

    mesure = _crawl({**connexion, "_suivi": _suivi(job_id, 1, total, carte_des_comptes.PRINCIPAL)}, max_pages)
    if mesure.get("_arretee") and len(mesure.get("pages") or {}) <= 1:
        # Revue du 2026-10-21 : arrêtée avant d'avoir commencé (dans la file, ou en attente des tests) — rien n'est écrit, la
        # carte précédente reste telle quelle (elle remplaçait un modèle complet par « incomplète, 1 page »).
        _JOBS[job_id].update(status="done", resume="exploration arrêtée avant de commencer — la carte précédente est gardée")
        return
    if not mesure.get("pages"):
        # Zéro page n'est pas une cartographie : l'écrire ferait passer un échec pour une
        # mesure « vide mais valide », et la génération croirait le domaine connu.
        _JOBS[job_id].update(
            status="failed",
            error="aucune page atteinte — vérifiez l'URL et les identifiants du projet")
        return

    incomplete = _incomplete(mesure)
    tentative = domain_model.chemin_derniere_tentative(project_id)
    if incomplete:
        # A84 (porteur, 2026-10-21) : une exploration arrêtée ne remplace pas une carte précédente complète — les tests déjà
        # écrits continueraient sinon de viser des pages que la carte ne connaît plus (erreur technique, régression visible).
        precedent = _lire_json(domain_model.chemin_du_modele(project_id))
        if precedent and (not precedent.get("exploration_incomplete")
                          or len(precedent.get("pages") or {}) >= len(mesure["pages"])):
            _ecrire(tentative, {"le": date.today().isoformat(), "raison": incomplete, "pages": len(mesure["pages"]),
                                "carte_gardee_du": precedent.get("mesure_le", "")})
            _JOBS[job_id].update(status="done", resume=(
                f"exploration {incomplete} à {len(mesure['pages'])} pages — la carte du "
                f"{precedent.get('mesure_le', '?')} est gardée"))
            return
    modele = {
        "connector_type": connexion["connector_type"],
        "projet": connexion["nom"],
        "project_id": project_id,
        "base_url": connexion["base_url"],
        "mesure_le": date.today().isoformat(),
        "methode": "crawl déterministe Playwright, aucun LLM",
        **_sans_marques(mesure),
    }
    if incomplete:
        modele["exploration_incomplete"] = {"raison": incomplete, "pages": len(mesure["pages"])}
    from testpilot.generation import interrupteurs
    if connexion.get("oracle") and interrupteurs.forme_oracle_actif():
        # Lot VH-08 (A51, interrupteur) : la forme des réponses de chaque requête GET de l'oracle — jamais une valeur ni
        # un compte. Éteint : l'oracle n'est pas appelé, l'exploration est celle d'avant.
        modele["formes_oracle"] = _relever_l_oracle(connexion["oracle"])
    chemin = domain_model.chemin_du_modele(project_id)
    _ecrire(chemin, modele)
    tentative.unlink(missing_ok=True)

    annexe_chemin = domain_model.chemin_annexe_des_comptes(project_id)
    resume_comptes = ""
    if comptes and not incomplete:
        annexe = {"mesure_le": modele["mesure_le"], "principal_sha256": _empreinte_du_fichier(chemin),
                  # Les menus du principal vivent ici, pas dans son modèle : ses lecteurs d'aujourd'hui n'y voient rien.
                  "principal_menus_visibles": mesure.get("_menus_visibles"),
                  "principal_absence_fiable": _absence_fiable(mesure),
                  "comptes": _explorer_les_comptes(job_id, connexion, comptes, max_pages,
                                                   intouchables=_structure_du_principal(modele))}
        _ecrire(annexe_chemin, annexe)
        explores = sum(1 for c in annexe["comptes"].values() if c["statut"] == "explore")
        incomplets = sum(1 for c in annexe["comptes"].values() if c["statut"] == "incomplet")
        resume_comptes = (f", {explores} compte(s) sur {len(comptes)} exploré(s)"
                          + (f" dont {incomplets} incomplet(s) en plus" if incomplets else ""))
    else:
        # Aucun compte, ou principal arrêté en route : aucune vue de compte n'est gardée (A78 — la carte n'a qu'une date).
        annexe_chemin.unlink(missing_ok=True)

    n_transitions = sum(len(v) for v in modele["transitions"].values())
    _JOBS[job_id].update(
        status="done",
        resume=(f"{len(modele['pages'])} routes, {n_transitions} transitions{resume_comptes}"
                + (f" — exploration incomplète ({incomplete})" if incomplete else "")))
    logger.info("[exploration] projet %s cartographié : %s → %s",
                project_id, _JOBS[job_id]["resume"], chemin.name)


def _explorer_les_comptes(job_id: str, connexion: dict, comptes: list[dict], max_pages: int | None,
                          intouchables: frozenset = frozenset()) -> dict:
    """Un passage par compte secondaire, l'un après l'autre. Un compte en échec n'arrête jamais les autres ; le relevé ne
    porte ni son identifiant ni son mot de passe (empreinte seulement). `{str(id): {libelle, empreinte, statut, message,
    releve}}` — statut : `explore`, `incomplet` (arrêté en route), `connexion_impossible`, `echec`, `non_explore`."""
    resultats: dict[str, dict] = {}
    total = 1 + len(comptes)
    sans_connexion = (connexion.get("connector_type") or "") != "odoo" and connexion.get("auth_strategie") == "aucune"
    for rang, compte in enumerate(comptes, start=2):
        entree = {"libelle": compte["libelle"], "empreinte": compte["empreinte"], "statut": "", "message": "", "releve": None}
        resultats[str(compte["id"])] = entree
        if _JOBS[job_id].get("arret_demande"):
            entree.update(statut="non_explore", message="exploration arrêtée avant ce compte")
            continue
        if sans_connexion:
            entree.update(statut="connexion_impossible", message="le projet ne se connecte pas (connexion « aucune »)")
            continue
        if not compte.get("password"):
            entree.update(statut="connexion_impossible", message="connexion impossible — ce compte n'a pas de mot de passe")
            continue
        secrets = [s for s in (compte.get("password"), compte.get("username")) if s and len(s) >= 3]
        try:
            mesure = _crawl({**connexion, "username": compte["username"], "password": compte["password"],
                             "compte_libelle": compte["libelle"], "oracle": None,
                             "_suivi": _suivi(job_id, rang, total, compte["libelle"])}, max_pages)
        except ConnexionDuCompteImpossible as exc:
            entree.update(statut="connexion_impossible", message=_masquer(str(exc), secrets)[:200])
            continue
        except Exception as exc:
            # Le détail technique (souvent en anglais) va au journal ; l'écran dit quoi faire.
            logger.warning("[exploration] compte « %s » en échec : %s", compte["libelle"],
                           _masquer(f"{type(exc).__name__} : {exc}", secrets)[:300])
            entree.update(statut="echec", message="l'exploration de ce compte a échoué en cours de route — relancez-la")
            continue
        if not mesure.get("pages"):
            entree.update(statut="echec", message="aucune page atteinte avec ce compte")
            continue
        incomplete = _incomplete(mesure)
        entree.update(statut="incomplet" if incomplete else "explore",
                      message=f"exploration incomplète ({incomplete})" if incomplete else "",
                      releve=_masquer({**_sans_marques(mesure), "menus_visibles": mesure.get("_menus_visibles"),
                                       "absence_fiable": _absence_fiable(mesure)}, secrets, intouchables))
    return resultats


# ── Ce que l'écran affiche, et ce que lira la génération (morceau 7) ────────────────────────────────────────────────────────

_MESSAGES_A_ACTUALISER = {
    "ajoute": "pas encore exploré",
    "change": "identifiant changé depuis la dernière exploration",
}


def etat_des_comptes(conn, projet: dict | None) -> dict:
    """Par compte secondaire : `explore`, `incomplet` (arrêté en route), `connexion_impossible`, `echec` (l'exploration a
    planté) — avec le message — ou `a_actualiser` (avec la raison). Jamais un compte arrêté compté comme exploré (A83).

    L'annexe ne vaut que pour l'exploration qui a écrit le modèle actuel (empreinte du fichier) ; un compte n'y vaut que si
    son empreinte n'a pas changé (même personne : un identifiant de connexion changé, c'est quelqu'un d'autre)."""
    from testpilot.connectors.runtime_env import empreinte_du_compte

    if not projet:
        return {"total": 0, "par_compte": {}}
    comptes = ProjectAccountRepo(conn).liste(projet["id"])
    annexe = domain_model.charger_annexe_des_comptes(projet["id"]) or {}
    valide = bool(annexe) and annexe.get("principal_sha256") == _empreinte_du_fichier(
        domain_model.chemin_du_modele(projet["id"]))
    par_compte: dict[int, dict] = {}
    for compte in comptes:
        entree = (annexe.get("comptes") or {}).get(str(compte["id"])) if valide else None
        if entree is None:
            par_compte[compte["id"]] = {"libelle": compte["label"], "statut": "a_actualiser",
                                        "message": _MESSAGES_A_ACTUALISER["ajoute"]}
        elif entree.get("empreinte") != empreinte_du_compte(compte):
            par_compte[compte["id"]] = {"libelle": compte["label"], "statut": "a_actualiser",
                                        "message": _MESSAGES_A_ACTUALISER["change"]}
        elif entree.get("statut") in ("explore", "incomplet"):
            par_compte[compte["id"]] = {"libelle": compte["label"], "statut": entree["statut"],
                                        "message": entree.get("message") or ""}
        elif entree.get("statut") == "non_explore":
            par_compte[compte["id"]] = {"libelle": compte["label"], "statut": "a_actualiser",
                                        "message": _MESSAGES_A_ACTUALISER["ajoute"]}
        else:
            statut = "connexion_impossible" if entree.get("statut") == "connexion_impossible" else "echec"
            par_compte[compte["id"]] = {"libelle": compte["label"], "statut": statut,
                                        "message": entree.get("message") or "connexion impossible"}
    return {"total": len(comptes), "par_compte": par_compte}


def charger_carte(conn, projet: dict | None) -> dict | None:
    """LA carte de l'application (A69 révisée) : toutes les routes, et quel compte voit quoi. Lue par le morceau 7 ; aucun
    lecteur d'aujourd'hui ne l'appelle (ils lisent la vue du principal, inchangée)."""
    modele = domain_model.charger_modele(projet) if projet else None
    if not modele:
        return None
    etat_comptes = etat_des_comptes(conn, projet)
    annexe = domain_model.charger_annexe_des_comptes(projet["id"]) or {}
    if annexe.get("principal_sha256") != _empreinte_du_fichier(domain_model.chemin_du_modele(projet["id"])):
        annexe = {}   # une annexe d'une autre exploration : rien d'elle ne vaut, pas même les menus du principal
    releves = [(carte_des_comptes.PRINCIPAL, {**modele, "menus_visibles": annexe.get("principal_menus_visibles"),
                                              "absence_fiable": bool(annexe.get("principal_absence_fiable"))})]
    incomplets, en_echec = [], []
    if modele.get("exploration_incomplete"):
        incomplets.append(carte_des_comptes.PRINCIPAL)
    for compte_id, etat_compte in etat_comptes["par_compte"].items():
        if etat_compte["statut"] in ("explore", "incomplet"):
            releve = ((annexe.get("comptes") or {}).get(str(compte_id)) or {}).get("releve")
            if releve:
                releves.append((etat_compte["libelle"], releve))
                if etat_compte["statut"] == "incomplet":
                    incomplets.append(etat_compte["libelle"])
        elif etat_compte["statut"] in ("echec", "connexion_impossible"):
            en_echec.append({"libelle": etat_compte["libelle"], "message": etat_compte["message"]})
    return carte_des_comptes.fusionner(releves, en_echec=en_echec, incomplets=incomplets)
