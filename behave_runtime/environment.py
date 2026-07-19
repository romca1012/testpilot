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


def before_scenario(context, scenario):
    """Initialise le registre de teardown et ouvre les connexions du scénario."""
    context.created = {}
    use_fixture(odoo_session, context)
    use_fixture(playwright_browser, context)


def after_scenario(context, scenario):
    """Supprime UNIQUEMENT les enregistrements produits par le test (jamais les prérequis)."""
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
