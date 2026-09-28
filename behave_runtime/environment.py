"""Infrastructure partagée Behave — session Odoo, navigateur Playwright, teardown.

Chargé automatiquement par Behave avant chaque run. Il est la fondation STABLE sur
laquelle s'appuient tous les steps (bibliothèque partagée + steps générés par l'IA).
Ne jamais le régénérer par l'IA.

context exposé aux steps :
    context.odoo       — session OdooRPC authentifiée
    context.page       — page Playwright (navigateur headless)
    context.browser    — instance Browser Playwright
    context.created    — dict {model: [ids]} alimenté par register_created(), purgé en teardown

────────────────────────────────────────────────────────────────────────────────────
SHIM D'ALIAS ``features.*`` — POURQUOI IL EXISTE (ne pas le supprimer par erreur)
────────────────────────────────────────────────────────────────────────────────────
Le prompt de génération (pilier generation) impose aux steps produits par l'IA la
convention historique d'imports qualifiés :

    from features.environment import register_created
    from features.steps._base_helpers import fill_field, ...

Or le runner d'exécution (pilier execution) assemble chaque run dans un layout PLAT et
jetable — ``environment.py`` à la racine, la bibliothèque + les steps générés dans
``steps/`` — sans aucun package ``features``. Sans pont, ces imports qualifiés lèvent
ModuleNotFoundError à la collecte et TOUT le run échoue (dry-run comme réel).

Plutôt que de modifier les piliers generation/execution déjà commités et testés, ce
module réenregistre dans ``sys.modules`` des alias qui font pointer la convention
``features.*`` vers le layout plat réel :
    features.environment          → CE module (register_created & co)
    features.steps._base_helpers  → le module plat steps/_base_helpers.py (via __path__)
Comme Behave charge ``environment.py`` AVANT les modules de steps, l'alias est en place
à temps. Les imports INTERNES de la bibliothèque, eux, ont été mis au plat directement.
"""

import json
import logging
import os
import re
import time
import sys
import types
from pathlib import Path
from urllib.parse import unquote

from behave import fixture, use_fixture

logger = logging.getLogger(__name__)
from dotenv import load_dotenv

load_dotenv()

# Lot 06 (D6, F6) : le profil d'instance choisi par le projet (s'il en expose un côté connecteur)
# — copié par le runner sous ce nom CANONIQUE (`BehaveRunner._profil_files`), jamais le nom
# original du fichier (deux profils différents porteraient sinon des noms différents, imprévisibles
# ici). Import PLAT, au NIVEAU MODULE (CLAUDE.md §6) : absent si aucun profil, ou si le profil
# choisi n'a rien à ajouter côté connecteur (son volet `generic/profils/` est chargé par Behave lui-
# même, comme tout fichier de `steps/` — aucun import n'est nécessaire pour ses steps).
try:
    from _profil_connecteur import apres_scenario as _profil_apres_scenario
except ImportError:
    _profil_apres_scenario = None


# ── Appariement des steps TOLÉRANT AUX ACCENTS (voir steps/_accent_matcher.py) ─
# Behave apparie le texte du .feature aux libellés @when(...) À L'EXACT. Un tirage LLM qui écrit
# le .feature sans accents (« le modele » vs la bibliothèque « le modèle ») rend TOUS les steps
# partagés accentués `undefined` → dry-run en échec → génération `dry_run_stalled` (mesuré le
# 2026-07-19). On installe un matcher qui décide sans accents mais préserve les valeurs capturées.
#
# ⚠️ MODULE-LEVEL, PAS DANS UN HOOK : le matcher doit être choisi AVANT que les step files ne
# s'enregistrent. Behave charge environment.py puis les steps, et le documente lui-même
# (« Default matcher can be overridden in environment.py hook »). Le fichier _accent_matcher.py
# est copié dans steps/ par le runner (_assemble) ; on l'y trouve relativement à ce fichier.
def _install_accent_tolerant_matcher() -> None:
    import importlib.util
    matcher_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "steps", "_accent_matcher.py")
    if not os.path.exists(matcher_path):
        return  # bibliothèque non assemblée (contexte inattendu) : on ne casse rien.
    spec = importlib.util.spec_from_file_location("_accent_matcher", matcher_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from behave.matchers import register_step_matcher_class, use_step_matcher
    register_step_matcher_class("accent_tolerant", module.AccentTolerantParseMatcher)
    use_step_matcher("accent_tolerant")


_install_accent_tolerant_matcher()


# ── SHIM D'ALIAS features.* → layout plat (voir docstring du module) ──────────
def _install_features_alias() -> None:
    """Enregistre les alias ``features.*``. Appelé EN FIN DE FICHIER (voir plus bas).

    Behave charge ``environment.py`` via ``exec_file`` dans un espace de noms où
    ``__name__ == 'builtins'`` : impossible de s'auto-référencer par ``sys.modules[__name__]``.
    On construit donc un module ``features.environment`` synthétique dont le contenu est une
    photo du namespace courant (``globals()``) — d'où l'appel APRÈS toutes les définitions,
    pour que ``register_created`` (et le reste) y figure.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    steps_dir = os.path.join(here, "steps")

    features = sys.modules.get("features")
    if features is None:
        features = types.ModuleType("features")
        features.__path__ = [here]  # package-espace de noms
        sys.modules["features"] = features

    steps_pkg = sys.modules.get("features.steps")
    if steps_pkg is None:
        steps_pkg = types.ModuleType("features.steps")
        steps_pkg.__path__ = [steps_dir]  # y résoudre _base_helpers.py & co
        sys.modules["features.steps"] = steps_pkg
        features.steps = steps_pkg

    # features.environment → module synthétique exposant register_created & co.
    env_mod = types.ModuleType("features.environment")
    env_mod.__dict__.update(globals())
    sys.modules["features.environment"] = env_mod
    features.environment = env_mod


# ── Garde de sécurité production ─────────────────────────────────────────────
if os.environ.get("ODOO_ENV") == "prod":
    raise EnvironmentError(
        "SAFETY: refus d'exécution contre une instance Odoo de production."
    )

# Lot 06 (D6, F6) : le teardown ne supprime plus par LISTE BLANCHE de modèle (une commande, un
# partenaire ou une facture créés par un test restaient auparavant, provoquant des collisions
# d'unicité au rejeu) — il supprime EXACTEMENT ce que `register_created` a enregistré, quel que soit
# le modèle, jamais par domaine ni par comparaison à un `max_id` (voir `_teardown_odoo_generique`).
#
# Sidecar des RÉSIDUS de teardown (F6, ticket 30298 : un scénario qui crée SANS aucun step de
# comptage ne laissait rien à nettoyer — `register_created` n'était jamais appelé). Noms DUPLIQUÉS
# de `execution/behave_result.py` (le harnais ne dépend pas du paquet applicatif), même motif que
# les autres sidecars (`FIELD_FALLBACK_FILE_ENV`…) — accord tenu par test.
RESIDUS_FILE_ENV = "TP_RESIDUS_FILE"

# Un nom de modèle Odoo technique : `module.nom` (ex. `helpdesk.ticket`, `res.partner`) — jamais
# autre chose. Sert à REFUSER un segment de route qui ne ressemble pas à un modèle (voir
# `_modele_depuis_route_formulaire`) : un id sans modèle SÛR n'est jamais enregistré pour nettoyage
# automatique, seulement consigné en résidu (F6, précision du porteur, 2026-09-28).
_MODELE_ODOO_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

_ODOO_URL      = os.environ.get("ODOO_URL", "http://localhost:10017")
_ODOO_DB       = os.environ.get("ODOO_DB", "odoo_test")
_ODOO_USER     = os.environ.get("ODOO_USER", "admin")
_ODOO_PASSWORD = os.environ.get("ODOO_PASSWORD", "admin")

# Connecteur du projet (2026-09-08, multi-connecteurs) — posé par `BehaveRunner._subprocess_env`.
# Défaut « odoo » : un run hors API (CLI, `.env` de la machine, qui ne pose jamais cette variable)
# garde exactement le comportement d'avant cette variable.
_CONNECTOR_TYPE = os.environ.get("TESTPILOT_CONNECTOR_TYPE", "odoo")

# ⚠️ Connexion du connecteur `web` générique (bug SauceDemo, 2026-09-13) — posées par
# `runtime_env.project_env()` / `BehaveRunner._subprocess_env` (`WEB_URL`/`WEB_USER`/
# `WEB_PASSWORD`, déjà câblées côté runner) mais JAMAIS lues ici avant ce correctif : aucun
# step de `generic/` n'avait de quoi naviguer vers l'application testée. Le navigateur restait
# sur `about:blank` toute la durée du scénario, et l'IA détournait un step de clic d'onglet
# (`j'accède à la section "…" du portail`, pensé pour un portail DÉJÀ chargé) en le prenant pour
# une navigation initiale — capture d'écran finale entièrement blanche, échec sur l'assertion
# finale plutôt que sur la vraie cause. Voir `steps_library/generic/_generic_steps.py` pour le
# step qui les consomme.
_WEB_URL      = os.environ.get("WEB_URL", "")
_WEB_USER     = os.environ.get("WEB_USER", "")
_WEB_PASSWORD = os.environ.get("WEB_PASSWORD", "")

# ⚠️ Stratégie de connexion du compte principal (lot 07b-2, C2) — noms et défaut DUPLIQUÉS de
# `connectors/auth_strategie.py` (ce harnais ne dépend pas du paquet applicatif), même motif que le contexte navigateur
# (lot 07c) et les comptes secondaires (lot 07b-1) ci-dessus.
_AUTH_STRATEGIE     = os.environ.get("TESTPILOT_AUTH_STRATEGIE", "formulaire")
_TOTP_SECRET        = os.environ.get("TESTPILOT_TOTP_SECRET", "")
_INJECTED_SESSION   = os.environ.get("TESTPILOT_INJECTED_SESSION", "")
# Sous-lot D (« Enregistrement assisté du chemin de connexion ») : DUPLIQUÉ de
# `connectors/runtime_env.py::ENV_LOGIN_RECORDING`, même motif que les constantes ci-dessus.
_LOGIN_RECORDING_JSON = os.environ.get("TESTPILOT_LOGIN_RECORDING", "")
# Extension (2026-09-30) : DUPLIQUÉ de `connectors/runtime_env.py::ENV_LOGIN_FORM`, même motif.
_LOGIN_FORM_JSON = os.environ.get("TESTPILOT_LOGIN_FORM", "")
_CHEMIN_STORAGE_STATE = "storage_state.json"   # dupliqué de `_base_helpers._CHEMIN_STORAGE_STATE" (même valeur, même run_dir)


def _doit_ouvrir_session_odoo(connector_type: str) -> bool:
    """Un projet sans backend Odoo (ex. connecteur `web` générique) ferait échouer TOUT
    scénario dès `before_scenario` si la session RPC s'ouvrait quand même — il n'y a rien à
    quoi se connecter. Fonction PURE, testée hors-ligne (`test_behave_harness.py`)."""
    return (connector_type or "odoo").lower() == "odoo"


# ── Fixtures ──────────────────────────────────────────────────────────────────
@fixture
def odoo_session(context):
    """Ouvre une session OdooRPC pour le scénario.

    ⚠️ **Écart au texte du lot 08a** : la version détectée (`context.odoo_version`) est posée ICI,
    pas dans `before_all`. `odoorpc.ODOO(...)` détecte déjà la version automatiquement à la
    CONSTRUCTION (appel `/web/webclient/version_info`, avant même `.login()`) — la lire depuis
    `before_all` aurait exigé une connexion RPC jetable, rien qu'à cette fin, alors que chaque
    scénario en ouvre déjà une ici. Même résultat (disponible pour tout scénario), sans aller-retour
    RPC superflu.
    """
    import odoorpc
    from urllib.parse import urlparse

    from _selecteurs import parser_version

    parsed = urlparse(_ODOO_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 8069)
    protocol = "jsonrpc+ssl" if parsed.scheme == "https" else "jsonrpc"

    context.odoo = odoorpc.ODOO(host, protocol=protocol, port=port)
    context.odoo_version = parser_version(context.odoo.version)
    context.odoo.login(_ODOO_DB, _ODOO_USER, _ODOO_PASSWORD)
    _instrumenter_creations_rpc(context)
    yield context.odoo


def _instrumenter_creations_rpc(context) -> None:
    """Enregistre AUTOMATIQUEMENT tout enregistrement créé par RPC pendant le scénario — sans
    dépendre d'un step de comptage (F6, ticket 30298 : un scénario qui crée SANS aucun step de
    comptage ne laissait rien à nettoyer, ses steps personnalisés n'appelant jamais
    `register_created`). Intercepte `execute_kw`, le SEUL point de passage de TOUT appel RPC —
    `odoorpc.models.Model.__getattr__` y délègue CHAQUE méthode (`create`, `write`, `search`…),
    quel que soit le modèle : jamais un comportement construit ou deviné, seulement observé.

    ⚠️ **Transparent** : la valeur de retour et les exceptions de l'appel RÉEL ne sont JAMAIS
    modifiées — seul un `create` qui RÉUSSIT déclenche un enregistrement, et seulement APRÈS que
    l'appel réel a rendu la main (jamais avant, jamais si l'appel a levé).
    """
    reel = context.odoo.execute_kw
    touches = context._touched_models

    def _relever_baseline(model: str) -> None:
        """Relève le max_id ACTUEL de `model`, la PREMIÈRE fois qu'il est touché dans ce scénario —
        JAMAIS pour supprimer (le teardown ne supprime que par id exact enregistré, jamais par
        domaine), seulement pour LISTER après coup les ids trouvés au-dessus, jamais enregistrés
        par ce scénario (résidu possible : tiers ou effet de bord — `_signaler_residus_possibles`).
        Appelle `reel` DIRECTEMENT (jamais `context.odoo.execute_kw`, déjà remplacé ci-dessous : un
        appel à la version instrumentée re-déclencherait cette même fonction, sans fin)."""
        if model in touches:
            return
        try:
            ids = reel(model, "search", [[]],
                      {"order": "id desc", "limit": 1, "context": {"active_test": False}})
            touches[model] = ids[0] if ids else 0
        except Exception:
            pass  # relevé impossible (droits, modèle inexistant…) : pas de détection de résidu ICI

    def _execute_kw_instrumente(model, method, args=None, kwargs=None):
        _relever_baseline(model)
        resultat = reel(model, method, args, kwargs)
        if method == "create":
            valeurs = [resultat] if isinstance(resultat, int) else (resultat or [])
            for record_id in valeurs:
                if isinstance(record_id, int):
                    register_created(context, model, record_id)
        return resultat

    context.odoo.execute_kw = _execute_kw_instrumente


# Lot 07c (C3) : contexte navigateur FIGÉ. Noms et défauts DUPLIQUÉS de `testpilot/connectors/contexte_navigateur.py` (ce harnais ne
# dépend pas du paquet applicatif) — même test d'accord que les sidecars (`tests/test_contexte_navigateur.py`).
_ENV_LOCALE = "TESTPILOT_BROWSER_LOCALE"
_ENV_TIMEZONE = "TESTPILOT_BROWSER_TIMEZONE"
_ENV_VIEWPORT = "TESTPILOT_BROWSER_VIEWPORT"
_DEFAUT_LOCALE, _DEFAUT_TIMEZONE, _DEFAUT_VIEWPORT = "fr-FR", "Europe/Paris", (1440, 900)
_BORNES_VIEWPORT = ((320, 3840), (320, 2160))   # dupliquées de `contexte_navigateur.py` (test d'accord)


def _avertir_contexte(message: str) -> None:
    print(f"[contexte navigateur] {message} — le défaut ({_DEFAUT_VIEWPORT[0]}x{_DEFAUT_VIEWPORT[1]}) est utilisé", file=sys.stderr)


def contexte_navigateur_fige() -> dict:
    """Les arguments de `browser.new_context(...)` : langue, fuseau et fenêtre décidés par le PROJET, jamais par la machine.

    Sans ces réglages Chromium prend la langue et le fuseau de l'hôte : la même campagne changeait de libellés et de dates d'un poste
    à l'autre. Une valeur absente ou illisible retombe sur le défaut (l'API refuse déjà une valeur mal formée à la saisie).
    """
    largeur, hauteur = _DEFAUT_VIEWPORT
    texte = os.environ.get(_ENV_VIEWPORT) or ""
    brut = texte.lower().replace("×", "x").split("x")
    if len(brut) == 2 and all(p.strip().isdigit() for p in brut):
        (l_min, l_max), (h_min, h_max) = _BORNES_VIEWPORT
        if l_min <= int(brut[0]) <= l_max and h_min <= int(brut[1]) <= h_max:
            largeur, hauteur = int(brut[0]), int(brut[1])
        else:
            _avertir_contexte(f"{_ENV_VIEWPORT}={texte!r} hors bornes")
    elif texte.strip():
        # Présente mais illisible : le run tourne dans un AUTRE contexte que celui du projet — jamais sans le dire.
        _avertir_contexte(f"{_ENV_VIEWPORT}={texte!r} illisible")
    return {"locale": (os.environ.get(_ENV_LOCALE) or "").strip() or _DEFAUT_LOCALE,
            "timezone_id": (os.environ.get(_ENV_TIMEZONE) or "").strip() or _DEFAUT_TIMEZONE,
            "viewport": {"width": largeur, "height": hauteur}}


@fixture
def playwright_browser(context):
    """Lance un navigateur Playwright pour le scénario (PLAYWRIGHT_HEADED=1 pour le voir).

    Un `BrowserContext` explicite (plutôt que le sucre `browser.new_page()`) est nécessaire pour
    pouvoir démarrer la trace AVANT la création de la page, comme le recommande la doc officielle
    (playwright.dev/python/docs/trace-viewer-intro) — voir `_demarrer_trace`.
    """
    from playwright.sync_api import sync_playwright

    headed = os.environ.get("PLAYWRIGHT_HEADED", "0") == "1"
    context._playwright = sync_playwright().start()
    context.browser = context._playwright.chromium.launch(headless=not headed)
    # Lot 07b-2 : la session du compte principal, obtenue UNE fois dans `before_all`, équipe le PREMIER contexte du scénario
    # (jamais les réouvertures du lot 07b-1 : un changement de compte reste un contexte neuf).
    _ouvrir_contexte_navigateur(context, avec_storage_state=True)
    # Lot 07b-1 (D8) : « je me connecte en tant que … » repart d'un contexte NEUF (cookies et stockage vides) via ce crochet.
    context._reouvrir_contexte = lambda: reouvrir_contexte_navigateur(context)
    yield context.page
    context._browser_context.close()
    context.browser.close()
    context._playwright.stop()


def _ouvrir_contexte_navigateur(context, *, avec_storage_state: bool = False) -> None:
    """Un `BrowserContext` (langue, fuseau et fenêtre du projet), sa trace, sa page — une seule fonction pour le premier et pour ceux
    qu'un changement de compte rouvre (`avec_storage_state=False` dans ce cas : lot 07b-1, jamais la session du principal).

    `avec_storage_state=True` (lot 07b-2) : charge la session du compte principal obtenue par `before_all`, si le fichier existe
    (absent quand la stratégie est `aucune`, ou quand la connexion initiale a échoué — `before_scenario` bloque alors avant
    d'ouvrir quoi que ce soit)."""
    kwargs = contexte_navigateur_fige()
    if avec_storage_state and os.path.isfile(_CHEMIN_STORAGE_STATE):
        kwargs["storage_state"] = _CHEMIN_STORAGE_STATE
    context._browser_context = context.browser.new_context(**kwargs)
    _demarrer_trace(context)
    context.page = context._browser_context.new_page()


def reouvrir_contexte_navigateur(context) -> None:
    """Remplace le contexte navigateur par un contexte NEUF (lot 07b-1, D8) : aucune session, aucun cookie, aucun stockage du compte
    précédent ne survit — un changement d'utilisateur qui garderait la session de l'ancien ne prouverait rien sur les droits du nouveau.

    La trace de l'ancien contexte est exportée avant sa fermeture (`traces/NN-compte-K.zip`) ; les marqueurs `_tp_*` posés sur la page
    (scénario négatif attendu…) passent à la nouvelle ; les observateurs sont réinstallés AVANT toute navigation (les événements
    antérieurs à ce step ne pouvaient de toute façon pas prouver ce que le nouveau compte fait)."""
    from _base_helpers import installer_les_observateurs

    ancien, ancienne_page = context._browser_context, context.page
    if getattr(context, "_tracing_started", False):
        try:
            k = getattr(context, "_indice_compte", 0) + 1
            context._indice_compte = k
            dossier = Path("traces")
            dossier.mkdir(exist_ok=True)
            ancien.tracing.stop(path=str(dossier / f"{getattr(context, '_indice_scenario', 0) + 1:02d}-compte-{k}.zip"))
        except Exception as exc:
            print(f"[trace] trace du compte précédent non exportée : {exc}")
    try:
        ancien.close()
    except Exception:
        pass
    _ouvrir_contexte_navigateur(context)
    for cle, valeur in list(vars(ancienne_page).items()):
        if cle.startswith("_tp_"):
            setattr(context.page, cle, valeur)
    _capturer_reponse_formulaire(context)
    installer_les_observateurs(context)


# ── Hooks Behave ──────────────────────────────────────────────────────────────
def _lire_sequence_et_formulaire_connexion() -> tuple[list, dict | None]:
    """Décode `TESTPILOT_LOGIN_RECORDING`/`TESTPILOT_LOGIN_FORM` — commun aux DEUX connecteurs
    UI (`web` depuis le sous-lot D/son extension ; `odoo`, essai 2026-09-30, voir
    `odoo_login.py::playwright_login`). Best-effort : jamais produit par une saisie humaine
    (toujours sérialisé par `runtime_env.project_env`), une valeur invalide trahirait un bug de
    ce dépôt — on continue sans rejeu/formulaire enregistré plutôt que de bloquer tout le run."""
    sequence_connexion: list = []
    if _LOGIN_RECORDING_JSON:
        try:
            sequence_connexion = json.loads(_LOGIN_RECORDING_JSON)
        except (ValueError, TypeError):
            logger.warning("[connexion] TESTPILOT_LOGIN_RECORDING n'est pas un JSON valide — "
                           "aucune séquence de connexion rejouée pour ce run.")
    login_form = None
    if _LOGIN_FORM_JSON:
        try:
            login_form = json.loads(_LOGIN_FORM_JSON)
        except (ValueError, TypeError):
            logger.warning("[connexion] TESTPILOT_LOGIN_FORM n'est pas un JSON valide — "
                           "détection par défaut utilisée pour ce run.")
    return sequence_connexion, login_form


def before_all(context):
    context.odoo_url      = _ODOO_URL
    context.odoo_db       = _ODOO_DB
    context.odoo_user     = _ODOO_USER
    context.odoo_password = _ODOO_PASSWORD
    # Posés AVANT tout, pour les DEUX connecteurs (essai 2026-09-30) — bloquant trouvé en revue
    # verdict-reviewer chantier-entier (2026-09-30) pour le connecteur `web` : sans ceci sur
    # `context`, `_verifier_ou_reconnecter_session` (reconnexion EN COURS de scénario) n'avait
    # aucun moyen de lire cette séquence, qui ne vivait que dans `_tenter_connexion_initiale`. Les
    # steps Odoo qui appellent `playwright_login(context)` (« je me connecte avec mes identifiants
    # utilisateur », navigation sur page vide…) profitent maintenant du MÊME câblage, sans jamais
    # rien recalculer localement — voir `odoo_login.py::playwright_login`.
    context.sequence_connexion, context.login_form = _lire_sequence_et_formulaire_connexion()
    # Connecteur `web` générique (bug SauceDemo, 2026-09-13) — voir le commentaire sur
    # `_WEB_URL` ci-dessus. Vide par défaut : un run Odoo (ou hors API) n'en a jamais besoin.
    context.web_url      = _WEB_URL
    context.web_user     = _WEB_USER
    context.web_password = _WEB_PASSWORD
    # Projet du run (§2bis) : le résolveur déterministe s'en sert pour charger le bon annuaire.
    # Posé par BehaveRunner dans l'environnement du sous-processus ; absent hors run piloté.
    _pid = os.environ.get("TESTPILOT_PROJECT_ID")
    context.project_id = int(_pid) if _pid and _pid.isdigit() else None
    # Jeton unique de CETTE tentative physique (Lot 4 du plan de fiabilisation, 2026-09-23) —
    # le step partagé « … rendue unique pour cette tentative » (`generic/_generic_steps.py`)
    # le lit pour qu'une valeur potentiellement contrainte par une règle d'unicité côté
    # application ne collisionne jamais avec une tentative précédente. `"tentative-locale"` hors
    # run piloté (CLI, tests) : jamais vide, pour qu'un appel direct du step ne lève pas.
    context.tentative_token = os.environ.get("TESTPILOT_ATTEMPT_TOKEN", "tentative-locale")
    # Lot 07b-1 (D8) : les comptes du projet (le principal + les secondaires), résolus par libellé au step « je me connecte en tant que ».
    from _base_helpers import construire_comptes

    context.comptes, context.comptes_erreur = construire_comptes(_CONNECTOR_TYPE, os.environ)
    context.compte_courant = "principal"
    # Lot 07e (D7) : l'oracle backend du projet, résolu une fois pour tout le run (les requêtes
    # nommées et l'authentification ne changent jamais en cours de run).
    from _base_helpers import construire_oracle

    context.oracle, context.oracle_erreur = construire_oracle(os.environ)
    # Lot 07b-2 (C2) : la stratégie de connexion du compte principal, et sa connexion initiale (une fois pour tout le run).
    context.auth_strategie = _AUTH_STRATEGIE
    context.totp_secret = _TOTP_SECRET
    context.injected_session = _INJECTED_SESSION
    context._erreur_connexion_initiale = ""
    if _CONNECTOR_TYPE == "web" and _AUTH_STRATEGIE != "aucune" and _WEB_URL:
        _tenter_connexion_initiale(context)


def _tenter_connexion_initiale(context) -> None:
    """Une SEULE connexion, avant le premier scénario du run (lot 07b-2) : écrit `storage_state.json`, réutilisé ensuite par
    chaque scénario (`playwright_browser`). Best-effort dans SA PROPRE tentative — une erreur est mémorisée sur `context`,
    jamais levée ici (`before_all` ne doit jamais faire planter tout le run Behave) ; `before_scenario` la relève et bloque
    chaque scénario proprement (jamais un vert, jamais un défaut applicatif présumé)."""
    from playwright.sync_api import sync_playwright

    from _base_helpers import PreconditionNonRemplieError, authentifier_selon_la_strategie

    injection = None
    if _AUTH_STRATEGIE == "session_injectee" and _INJECTED_SESSION:
        try:
            injection = json.loads(_INJECTED_SESSION)
        except (ValueError, TypeError):
            context._erreur_connexion_initiale = "la session fournie (« session déjà ouverte ») n'est pas un JSON valide."
            return
    # `context.sequence_connexion`/`context.login_form` : déjà posés par `before_all`
    # (`_lire_sequence_et_formulaire_connexion`, commune aux deux connecteurs UI) — jamais
    # recalculés ici, pour qu'une seule lecture des variables d'environnement fasse foi.
    sequence_connexion = context.sequence_connexion
    login_form = context.login_form
    with sync_playwright() as p:
        navigateur = p.chromium.launch(headless=os.environ.get("PLAYWRIGHT_HEADED", "0") != "1")
        try:
            contexte = navigateur.new_context(storage_state=injection, **contexte_navigateur_fige())
            page = contexte.new_page()
            try:
                authentifier_selon_la_strategie(page, strategie=_AUTH_STRATEGIE, web_url=_WEB_URL,
                                                user=_WEB_USER, password=_WEB_PASSWORD, totp_secret=_TOTP_SECRET,
                                                sequence_connexion=sequence_connexion,
                                                login_form=login_form)
            except PreconditionNonRemplieError as exc:
                context._erreur_connexion_initiale = str(exc)
                return
            contexte.storage_state(path=_CHEMIN_STORAGE_STATE)
        finally:
            navigateur.close()


def _capturer_reponse_formulaire(context):
    """Capte la réponse SERVEUR de la soumission du formulaire (§2bis, étape 3a).

    ⚠️ **Le signal qui manquait pour lever les refus SILENCIEUX.** Quand une soumission ne crée
    rien et que la page reste muette, on ne pouvait pas distinguer « notre donnée refusée par une
    règle serveur » d'un « vrai défaut applicatif ». Odoo poste vers `/website/form/…` et renvoie
    pourtant un JSON (`{"id": N}` créé ; `{"error_fields": […]}` / `{"error": …}` refusé) — on ne
    lisait QUE la page. On capte donc la réponse : c'est « vérifier par l'état » au niveau réseau.

    Best-effort ABSOLU : un handler qui plante ne doit jamais faire échouer le scénario qu'il
    éclaire. On stocke le dernier JSON `/website/form/` sur `context.reponse_formulaire` (un
    scénario = une soumission). Réinitialisé ici à chaque scénario.
    """
    context.reponse_formulaire = None
    # Le CODE HTTP de chaque réponse de soumission (F10, 2026-09-24) — un signal du RUNTIME, pas un
    # texte de l'agent. Le cas 99 recevait un `HTTP 500` (corps HTML, donc pas de JSON) que cette
    # capture ignorait : l'outil concluait à un « refus silencieux » alors que le serveur avait planté.
    context.reponses_formulaire = []

    def _on_response(response):
        try:
            if "/website/form/" not in response.url:
                return
            # La trace est posée AVANT la lecture du corps : un corps non JSON ne doit pas la perdre.
            # `t` : horodatage monotone — le comptage ne juge que les réponses POSTÉRIEURES à son relevé.
            context.reponses_formulaire.append(
                {"status": int(response.status), "url": response.url, "t": time.monotonic()})
            # Le JSON d'une soumission PRÉCÉDENTE ne doit pas survivre à une réponse non JSON plus
            # récente (un `error_fields` périmé l'emporterait sur un 5xx actuel).
            context.reponse_formulaire = None
            # Corps JSON attendu ; si ce n'en est pas (erreur 5xx HTML, redirect…), on garde la trace.
            corps = response.json()
            context.reponse_formulaire = corps
            # Lot 06 (F6) : enregistrement AUTOMATIQUE de l'id créé — sans dépendre d'un step de
            # comptage (ticket 30298 : c'est exactement ce chemin, une soumission portail, qui
            # laissait un résidu quand les steps de comptage personnalisés du scénario n'appelaient
            # jamais `register_created`).
            _enregistrer_creation_formulaire(context, response.url, corps)
        except Exception:
            pass  # jamais fatal — l'absence de capture retombe sur le comportement muet d'avant

    try:
        context.page.on("response", _on_response)
    except Exception:
        pass


def _modele_depuis_route_formulaire(url: str) -> str:
    """Le modèle technique d'une soumission `/website/form/<modele>` — DÉDUIT de la route
    elle-même (convention du website builder Odoo : le formulaire poste vers `/website/form/`
    suivi du nom TECHNIQUE du modèle, ex. `/website/form/helpdesk.ticket`), jamais deviné ni
    construit. Rend `""` si le segment ne ressemble pas à un modèle Odoo (`module.nom`) — un id
    dont le modèle n'est pas SÛR n'est jamais enregistré pour nettoyage automatique (voir
    `_enregistrer_creation_formulaire`)."""
    marqueur = "/website/form/"
    i = url.find(marqueur)
    if i < 0:
        return ""
    segment = unquote(url[i + len(marqueur):].split("?", 1)[0].split("/", 1)[0])
    return segment if _MODELE_ODOO_RE.match(segment) else ""


def _enregistrer_creation_formulaire(context, url: str, corps) -> None:
    """Enregistre AUTOMATIQUEMENT l'id créé par une soumission de formulaire réussie (F6) — jamais
    sur un refus (`error`/`error_fields` dans le corps, cf. `_capturer_reponse_formulaire`) ni sans
    modèle SÛR (consigné en résidu plutôt que deviné)."""
    if not isinstance(corps, dict) or "error" in corps or "error_fields" in corps:
        return
    record_id = corps.get("id")
    if not isinstance(record_id, int):
        return
    modele = _modele_depuis_route_formulaire(url)
    if modele:
        register_created(context, modele, record_id)
    else:
        _consigner_residu(
            context, f"soumission de formulaire ({url}) : id {record_id} créé mais le modèle n'a "
                     "pas pu être déduit de la route — non enregistré pour nettoyage automatique, "
                     "à vérifier manuellement")


def _consigner_residu(context, message: str) -> None:
    """Consigne un message de diagnostic de teardown (F6) — best-effort, jamais fatal : un contexte
    sans `_residus` (test minimal, appel hors run) ignore silencieusement."""
    residus = getattr(context, "_residus", None)
    if residus is not None:
        residus.append(message)


def _marquer_si_scenario_negatif(context, scenario) -> None:
    """Désigne AVANT toute action si ce scénario n'attend AUCUNE création (2026-08-07).

    ⚠️ **Pourquoi ICI, avant le premier `Quand`.** `verifier_soumission_non_bloquee` (dans
    `_base_helpers.py`) tourne au moment du clic — trop tard pour lire les steps À VENIR. Behave,
    lui, connaît TOUTE la liste des steps du scénario dès `before_scenario` : on la lit une fois,
    ici, et on pose le résultat sur la page pour que le clic le retrouve plus tard.

    Le signal retenu — `… n'a pas augmenté` — est STRUCTUREL, pas un texte de titre deviné : c'est
    le step que `check_count_not_increased` reconnaît. Mesuré sur les 85 scénarios de
    `behave_runtime/generated/` le 2026-08-07 : les 35 négatifs le portent TOUS, aucun des 43
    nominaux ne le porte, et AUCUN scénario ne porte les deux assertions à la fois. Voir
    `_base_helpers.marquer_scenario_attend_un_refus` pour le détail de ce que ça change.

    `all_steps` (Background + Scénario) plutôt que `steps` : l'assertion vit toujours dans le
    corps du scénario, mais lire les deux ne coûte rien et ne dépend pas de cette convention.
    """
    from _base_helpers import marquer_scenario_attend_un_refus
    steps = getattr(scenario, "all_steps", None) or scenario.steps
    if any("n'a pas augmenté" in step.name for step in steps):
        marquer_scenario_attend_un_refus(context.page)


def _demarrer_trace(context) -> None:
    """Démarre la trace Playwright du scénario (timeline des actions, snapshots DOM, réseau).

    ⚠️ **Pourquoi en plus de la capture d'écran.** La doc officielle Playwright est explicite : pour
    diagnostiquer un échec, la trace est recommandée AU-DESSUS des captures d'écran/vidéos — une
    capture n'est qu'un instant figé, la trace rejoue tout le scénario dans le trace viewer
    (playwright.dev/python/docs/trace-viewer-intro). `screenshots=True, snapshots=True,
    sources=True` : ce sont exactement les trois options de l'exemple officiel, pour un trace
    viewer complet (pas seulement les captures, aussi les snapshots DOM interactifs et le code).

    Pas en `--dry-run` (même garde que `_capturer_ecran`) : la page reste `about:blank`, tracer ne
    produirait qu'une trace vide. Best-effort ABSOLU : `context._tracing_started` retombe à `False`
    au moindre souci, et `_capturer_trace` s'en remet à ce drapeau pour ne jamais appeler `stop()`
    sur une trace qui n'a pas démarré.
    """
    context._tracing_started = False
    if getattr(context.config, "dry_run", False):
        return
    try:
        context._browser_context.tracing.start(screenshots=True, snapshots=True, sources=True)
        context._tracing_started = True
    except Exception as exc:
        print(f"[trace] démarrage de trace impossible : {exc}")


def before_step(context, step):
    """Pose le texte du step COURANT sur `context.page` — l'« intention » du Chantier F (F.0).

    Les steps Gherkin de ce dépôt sont déjà des phrases lisibles (« je sélectionne le produit
    contenant… ») : c'est exactement l'intention sémantique dont a besoin la résolution adaptative
    de `locate_field` (voir `_base_helpers.py`) quand toute la cascade déterministe a échoué. Rien
    à construire pour l'obtenir — seulement la transmettre.

    Posée sur `page` (pas `context`) : même patron que `_tp_scenario_attend_un_refus`/
    `_tp_champs_vides_intentionnels` dans `_base_helpers.py`, pour que `locate_field(page, ident)`
    y accède sans changement de signature. `context.page` peut ne pas encore exister avant le tout
    premier step d'un scénario (login) — `getattr` silencieux dans ce cas, jamais fatal.
    """
    page = getattr(context, "page", None)
    if page is not None:
        page._tp_intention_step = step.name
    # Lot 03 : le type EFFECTIF du step (`Et`/`Mais` héritent) accompagne chaque constat consigné.
    from _base_helpers import definir_etat_constat, poser_repere_action
    definir_etat_constat(step_type=getattr(step, "step_type", "") or "")
    # Lot 07d : chaque ACTION pose un repère — « la requête … répond », « un nouvel onglet s'ouvre » ne jugent que ce qui l'a suivi.
    if (getattr(step, "step_type", "") or "") in ("given", "when"):
        poser_repere_action(context)


def before_scenario(context, scenario):
    """Initialise le registre de teardown et ouvre les connexions du scénario."""
    context.created = {}
    # Lot 06 (F6) : `created_ordre` (liste PLATE, ordre de création TOUS MODÈLES confondus) sert au
    # teardown générique à supprimer dans l'ordre INVERSE de création — `created` (dict par modèle)
    # reste pour la compatibilité des appelants existants (comptage du lot 01, etc.).
    context.created_ordre = []
    # Modèles touchés par RPC pendant ce scénario → max_id relevé à leur PREMIER contact (détection
    # de résidu SEULEMENT, jamais une suppression — voir `_instrumenter_creations_rpc`).
    context._touched_models = {}
    # Messages de diagnostic de teardown (échecs de suppression/archivage, résidus possibles) — un
    # sidecar, jamais le log (Behave l'avale sur un scénario vert).
    context._residus = []
    # Lot 03 : le scénario courant, pour rattacher chaque constat consigné à SON scénario.
    from _base_helpers import definir_etat_constat
    definir_etat_constat(scenario=scenario.name, step_type="")
    # Lot 07b-2 (C2) : la connexion initiale du run a échoué (avant tout scénario) — bloqué, jamais un vert ni un défaut
    # applicatif présumé. AVANT d'ouvrir quoi que ce soit (navigateur, session RPC).
    if getattr(context, "_erreur_connexion_initiale", ""):
        from _base_helpers import PreconditionNonRemplieError

        raise PreconditionNonRemplieError(
            f"PRÉREQUIS MANQUANT : la connexion initiale du run a échoué ({context._erreur_connexion_initiale}) — vérifiez "
            "la stratégie de connexion et ses secrets dans les réglages du projet.")
    context._reconnexion_tentee = False
    if _doit_ouvrir_session_odoo(_CONNECTOR_TYPE):
        use_fixture(odoo_session, context)
    use_fixture(playwright_browser, context)
    _capturer_reponse_formulaire(context)
    # Lot 07d : réponses réseau, boîtes de dialogue et onglets du scénario (tous onglets), numérotés — il faut observer AVANT l'action.
    from _base_helpers import installer_les_observateurs
    installer_les_observateurs(context)
    _marquer_si_scenario_negatif(context, scenario)


def _capturer_ecran(context, scenario, n: int) -> None:
    """Capture l'état visuel de la page à la fin du scénario, TOUS statuts confondus (§A du plan
    « fiabiliser le verdict automatique », 2026-08-06).

    ⚠️ Même discipline que la pièce jointe qu'un humain ajoute en saisie manuelle
    (`AddResultDialog.vue`) : une preuve visuelle doit accompagner CHAQUE résultat automatique, pas
    seulement les échecs — un utilisateur qui vérifie un « passed » doit pouvoir constater ce que
    la machine a réellement vu, pas seulement la croire sur parole.

    Écrit en RELATIF (`screenshots/`) : le process behave tourne avec `run_dir` en cwd
    (`BehaveRunner._run`, `cwd=str(run_dir)`), et c'est `_archiver` qui rapatrie ce dossier vers
    les artefacts de l'exécution avant que `run_dir` ne soit détruit.

    Pas de capture en `--dry-run` : aucune page n'a réellement été parcourue (les steps sont
    `skipped`), une capture y serait une image d'`about:blank` sans aucune valeur de preuve.

    ⚠️ **`full_page=True`, et ce n'est pas cosmétique.** Trouvé en dogfooding réel (2026-08-06,
    campagne 18) : deux captures de la même page fermée sur les premiers champs, prises PAR
    DÉFAUT (viewport seul), se ressemblaient au premier coup d'œil alors que les deux échecs
    n'avaient rien à voir — le formulaire n'avait simplement pas encore défilé au moment de la
    capture. La page entière montre toujours l'endroit réel du problème, même hors du viewport.

    Best-effort ABSOLU (même principe que `_capturer_reponse_formulaire`) : un souci de capture ne
    doit jamais faire échouer ou masquer le verdict réel du scénario.

    `n` est calculé UNE FOIS par `after_scenario` et partagé avec `_capturer_trace` : capture et
    trace du même scénario portent ainsi le même numéro (`01-passed.png` / `01-passed.zip`).
    """
    if getattr(context.config, "dry_run", False):
        return
    page = getattr(context, "page", None)
    if page is None:
        return
    try:
        dossier = Path("screenshots")
        dossier.mkdir(exist_ok=True)
        statut = scenario.status.name if getattr(scenario, "status", None) else "inconnu"
        page.screenshot(path=str(dossier / f"{n:02d}-{statut}.png"), full_page=True)
    except Exception as exc:
        print(f"[capture] écran non capturé pour le scénario « {scenario.name} » : {exc}")


def _capturer_trace(context, scenario, n: int) -> None:
    """Exporte la trace Playwright du scénario en `.zip` (voir `_demarrer_trace` pour le pourquoi).

    Appelée depuis `after_scenario`, donc AVANT la fermeture du `BrowserContext` (celle-ci n'a lieu
    qu'au nettoyage de la fixture `playwright_browser`, après `after_scenario` — voir sa docstring).
    `context.tracing.stop(path=...)` a besoin du contexte encore ouvert pour exporter.

    Écrit en RELATIF (`traces/`), même motif que `_capturer_ecran` : `_archiver` rapatrie ce dossier
    avant le `rmtree` du run_dir.

    Ne s'exécute que si `_demarrer_trace` a réellement démarré la trace (`_tracing_started`) — ni en
    `--dry-run`, ni après un échec de démarrage déjà journalisé là-bas. Best-effort ABSOLU : jamais
    fatal, jamais un motif d'échec ou de masquage du verdict réel du scénario.
    """
    if not getattr(context, "_tracing_started", False):
        return
    browser_context = getattr(context, "_browser_context", None)
    if browser_context is None:
        return
    try:
        dossier = Path("traces")
        dossier.mkdir(exist_ok=True)
        statut = scenario.status.name if getattr(scenario, "status", None) else "inconnu"
        browser_context.tracing.stop(path=str(dossier / f"{n:02d}-{statut}.zip"))
    except Exception as exc:
        print(f"[trace] trace non exportée pour le scénario « {scenario.name} » : {exc}")


def _tenter_annulation(odoo, model: str, record_id: int) -> bool:
    """Tente `action_cancel` puis `button_cancel` si le modèle les expose — `True` si l'un des deux
    a réussi (le `unlink` qui suit a alors une chance d'aboutir sur un document confirmé, ex. une
    commande de vente validée). Jamais fatal : un modèle sans l'un ou l'autre lève, on continue."""
    for methode in ("action_cancel", "button_cancel"):
        try:
            getattr(odoo.env[model].browse([record_id]), methode)()
            return True
        except Exception:
            continue
    return False


def _tenter_archivage(odoo, model: str, record_id: int) -> bool:
    """`write({"active": False})` SI le modèle expose un champ `active` — jamais deviné : relu via
    `fields_get`, qui rend un dict vide (pas une exception) pour un champ absent."""
    try:
        champs = odoo.env[model].fields_get(["active"])
    except Exception:
        return False
    if "active" not in champs:
        return False
    try:
        odoo.env[model].browse([record_id]).write({"active": False})
        return True
    except Exception:
        return False


def _teardown_odoo_generique(context, odoo) -> None:
    """Supprime, dans l'ORDRE INVERSE de création, tout et SEULEMENT ce que `register_created` a
    enregistré (F6, lot 06) — **jamais** par domaine, **jamais** par comparaison à un `max_id` : un
    id qui n'a pas été explicitement enregistré n'est jamais touché ici (voir
    `_signaler_residus_possibles` pour les ids relevés au-dessus d'un `max_id`, jamais supprimés).

    Par enregistrement : `unlink` direct ; refusé → tente une annulation (`action_cancel`/
    `button_cancel`) puis `unlink` ; refusé → archive (`active=False`) si le champ existe ; sinon,
    consigne un résidu. Jamais d'exception qui remonte — le verdict est déjà rendu.
    """
    for model, record_id in reversed(context.created_ordre):
        try:
            odoo.env[model].browse([record_id]).unlink()
            continue
        except Exception:
            pass
        if _tenter_annulation(odoo, model, record_id):
            try:
                odoo.env[model].browse([record_id]).unlink()
                continue
            except Exception:
                pass
        if _tenter_archivage(odoo, model, record_id):
            continue
        _consigner_residu(
            context, f"{model} id={record_id} : ni supprimé ni archivé (suppression, annulation "
                     "puis suppression, et champ actif tous refusés ou absents) — à traiter "
                     "manuellement")


def _signaler_residus_possibles(context, odoo) -> None:
    """Après le teardown : pour chaque modèle TOUCHÉ par RPC pendant le scénario, liste les ids
    au-dessus du `max_id` relevé à son PREMIER contact qui n'ont JAMAIS été enregistrés par ce
    scénario — un tiers actif sur l'instance est indiscernable d'un effet de bord de l'action
    testée : jamais supprimé automatiquement, seulement signalé (F6, précision du porteur,
    2026-09-28). `active_test=False` : un résidu archivé par CE teardown reste visible pour ne pas
    le compter deux fois (exclu ci-dessous via `connus`, qui contient tout ce qu'on a enregistré,
    supprimé ou archivé)."""
    for model, max_id in getattr(context, "_touched_models", {}).items():
        connus = set(context.created.get(model, []))
        try:
            surplus = odoo.env[model].search([("id", ">", max_id)], context={"active_test": False})
        except Exception:
            continue
        inconnus = [i for i in surplus if i not in connus]
        if inconnus:
            _consigner_residu(
                context, f"{model} id(s) {inconnus} : au-dessus de l'id {max_id} relevé en début de "
                         "scénario mais jamais enregistrés par lui — résidu possible (tiers actif "
                         "sur l'instance ou effet de bord de l'action testée), non supprimé")


def _ecrire_sidecar_residus(context, scenario) -> None:
    chemin = os.environ.get(RESIDUS_FILE_ENV)
    residus = getattr(context, "_residus", None) or []
    if not chemin or not residus:
        return
    try:
        with open(chemin, "a", encoding="utf-8") as handle:
            for message in residus:
                handle.write(f"[{scenario.name}] {message}".replace("\n", " ") + "\n")
    except OSError:
        pass


def after_scenario(context, scenario):
    """Capture une preuve visuelle et une trace, PUIS supprime UNIQUEMENT les enregistrements
    produits par le test (jamais les prérequis), par leur id EXACT enregistré — jamais par domaine
    ni par `max_id` (F6, lot 06)."""
    n = getattr(context, "_indice_scenario", 0) + 1
    context._indice_scenario = n
    _capturer_ecran(context, scenario, n)
    _capturer_trace(context, scenario, n)

    # Lot 07b-1 (D8) : le nettoyage supprime ce qu'a créé le compte principal — sa session RPC revient avant.
    from _base_helpers import retablir_le_compte_principal
    retablir_le_compte_principal(context)

    odoo = getattr(context, "odoo", None)
    if odoo is not None:
        _teardown_odoo_generique(context, odoo)
        _signaler_residus_possibles(context, odoo)

    # Lot 06 (D6) : un profil d'instance peut ajouter SON PROPRE nettoyage (ex. restauration d'un
    # rôle propre à un client) — jamais dans le socle commun. Absent si aucun profil n'en expose un.
    if _profil_apres_scenario is not None:
        try:
            _profil_apres_scenario(context)
        except Exception as exc:
            print(f"[profil] apres_scenario a échoué : {exc}")

    _ecrire_sidecar_residus(context, scenario)


def after_all(context):
    pass


# ── Helper exposé aux steps ────────────────────────────────────────────────────
def register_created(context, model: str, record_id: int) -> None:
    """Enregistre un ID créé par le test pour suppression automatique en teardown.

    Idempotent : le même (modèle, id) peut être enregistré par PLUSIEURS chemins (le comptage du
    lot 01, ET la capture automatique RPC/formulaire du lot 06) — une seule entrée compte, dans
    l'ordre de sa PREMIÈRE apparition. `created_ordre` (liste plate, tous modèles confondus) sert au
    teardown générique à supprimer dans l'ordre INVERSE de création ; absent sur un contexte de test
    minimal, il est alors simplement ignoré (comportement historique inchangé pour `context.created`
    seul)."""
    ids = context.created.setdefault(model, [])
    if record_id not in ids:
        ids.append(record_id)
    ordre = getattr(context, "created_ordre", None)
    if ordre is not None and (model, record_id) not in ordre:
        ordre.append((model, record_id))


# Installé EN DERNIER : la photo globals() doit inclure register_created (voir docstring).
_install_features_alias()
