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

import os
import sys
import types
from pathlib import Path

from behave import fixture, use_fixture
from dotenv import load_dotenv

load_dotenv()


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

# Seuls ces modèles sont supprimés en teardown : ce sont les enregistrements PRODUITS
# par les actions UI du test. Le portail « Demande de matériel » crée un helpdesk.ticket
# (soumission vers /website/form/helpdesk.ticket). Les données prérequises (produits,
# accessoires, catégories) ne sont JAMAIS supprimées. Ajouter ici le modèle de sortie
# d'un nouveau module au besoin.
_TEST_OUTPUT_MODELS = {"helpdesk.ticket"}

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


def _doit_ouvrir_session_odoo(connector_type: str) -> bool:
    """Un projet sans backend Odoo (ex. connecteur `web` générique) ferait échouer TOUT
    scénario dès `before_scenario` si la session RPC s'ouvrait quand même — il n'y a rien à
    quoi se connecter. Fonction PURE, testée hors-ligne (`test_behave_harness.py`)."""
    return (connector_type or "odoo").lower() == "odoo"


# ── Fixtures ──────────────────────────────────────────────────────────────────
@fixture
def odoo_session(context):
    """Ouvre une session OdooRPC pour le scénario."""
    import odoorpc
    from urllib.parse import urlparse

    parsed = urlparse(_ODOO_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 8069)
    protocol = "jsonrpc+ssl" if parsed.scheme == "https" else "jsonrpc"

    context.odoo = odoorpc.ODOO(host, protocol=protocol, port=port)
    context.odoo.login(_ODOO_DB, _ODOO_USER, _ODOO_PASSWORD)
    yield context.odoo


@fixture
def playwright_browser(context):
    """Lance un navigateur Playwright pour le scénario (PLAYWRIGHT_HEADED=1 pour le voir)."""
    from playwright.sync_api import sync_playwright

    headed = os.environ.get("PLAYWRIGHT_HEADED", "0") == "1"
    context._playwright = sync_playwright().start()
    context.browser = context._playwright.chromium.launch(headless=not headed)
    context.page = context.browser.new_page()
    yield context.page
    context.browser.close()
    context._playwright.stop()


# ── Hooks Behave ──────────────────────────────────────────────────────────────
def before_all(context):
    context.odoo_url      = _ODOO_URL
    context.odoo_db       = _ODOO_DB
    context.odoo_user     = _ODOO_USER
    context.odoo_password = _ODOO_PASSWORD
    # Connecteur `web` générique (bug SauceDemo, 2026-09-13) — voir le commentaire sur
    # `_WEB_URL` ci-dessus. Vide par défaut : un run Odoo (ou hors API) n'en a jamais besoin.
    context.web_url      = _WEB_URL
    context.web_user     = _WEB_USER
    context.web_password = _WEB_PASSWORD
    # Projet du run (§2bis) : le résolveur déterministe s'en sert pour charger le bon annuaire.
    # Posé par BehaveRunner dans l'environnement du sous-processus ; absent hors run piloté.
    _pid = os.environ.get("TESTPILOT_PROJECT_ID")
    context.project_id = int(_pid) if _pid and _pid.isdigit() else None


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

    def _on_response(response):
        try:
            if "/website/form/" not in response.url:
                return
            # Corps JSON attendu ; si ce n'en est pas (redirect HTML…), on ignore silencieusement.
            context.reponse_formulaire = response.json()
        except Exception:
            pass  # jamais fatal — l'absence de capture retombe sur le comportement muet d'avant

    try:
        context.page.on("response", _on_response)
    except Exception:
        pass


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


def before_scenario(context, scenario):
    """Initialise le registre de teardown et ouvre les connexions du scénario."""
    context.created = {}
    if _doit_ouvrir_session_odoo(_CONNECTOR_TYPE):
        use_fixture(odoo_session, context)
    use_fixture(playwright_browser, context)
    _capturer_reponse_formulaire(context)
    _marquer_si_scenario_negatif(context, scenario)


def _capturer_ecran(context, scenario) -> None:
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
    """
    if getattr(context.config, "dry_run", False):
        return
    page = getattr(context, "page", None)
    if page is None:
        return
    try:
        dossier = Path("screenshots")
        dossier.mkdir(exist_ok=True)
        n = getattr(context, "_indice_scenario", 0) + 1
        context._indice_scenario = n
        statut = scenario.status.name if getattr(scenario, "status", None) else "inconnu"
        page.screenshot(path=str(dossier / f"{n:02d}-{statut}.png"), full_page=True)
    except Exception as exc:
        print(f"[capture] écran non capturé pour le scénario « {scenario.name} » : {exc}")


def after_scenario(context, scenario):
    """Capture une preuve visuelle, PUIS supprime UNIQUEMENT les enregistrements produits par le
    test (jamais les prérequis)."""
    _capturer_ecran(context, scenario)

    odoo = getattr(context, "odoo", None)
    if odoo is None:
        return

    # Restauration des rôles temporairement ajoutés par des steps (si applicable).
    for user_id, role_id in getattr(context, "_roles_to_restore", []):
        try:
            odoo.env["res.users"].browse(user_id).write(
                {"employee_front_role_ids": [(3, role_id)]}
            )
        except Exception as exc:  # teardown best-effort : ne jamais masquer le verdict
            print(f"[teardown] rôle {role_id} non retiré de l'user {user_id} : {exc}")

    for model, ids in getattr(context, "created", {}).items():
        if model not in _TEST_OUTPUT_MODELS or not ids:
            continue  # hors whitelist ou vide → on ne touche à rien
        try:
            odoo.env[model].browse(ids).unlink()
        except Exception as exc:
            print(f"[teardown] {model} ids={ids} non supprimés : {exc}")


def after_all(context):
    pass


# ── Helper exposé aux steps ────────────────────────────────────────────────────
def register_created(context, model: str, record_id: int) -> None:
    """Enregistre un ID créé par le test pour suppression automatique en teardown."""
    context.created.setdefault(model, []).append(record_id)


# Installé EN DERNIER : la photo globals() doit inclure register_created (voir docstring).
_install_features_alias()
