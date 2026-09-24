"""Lot 07a (C1) — le connecteur `web` générique se CONNECTE à l'exécution.

Avant : `WEB_USER`/`WEB_PASSWORD` étaient posés dans `before_all` et jamais lus ; les cas tournaient en
anonyme alors que l'exploration se connectait. Maintenant : le step d'entrée « j'accède à la page
d'accueil de l'application » connecte automatiquement (via `tenter_connexion_generique`, la fonction de
l'exploration), un échec est un prérequis non rempli (`blocked`), et un cas qui TESTE la connexion
s'ouvre par « j'accède à la page de connexion sans me connecter ».

Chaque test prouve les DEUX sens (falsifiabilité) : la connexion qui aboutit laisse passer, celle qui
n'aboutit pas lève `PreconditionNonRemplieError` — jamais une `AssertionError` ni un succès silencieux.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

import pytest

from testpilot.execution.behave_result import BehaveFailure
from testpilot.generation import steps_library
from testpilot.verdict import defect_taxonomy as dt

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"
_CHEMINS = [str(_STEPS_LIB), str(_STEPS_LIB / "generic"), str(_STEPS_LIB / "web")]
H = generic = web = None  # posés par la fixture ci-dessous


@pytest.fixture(scope="module", autouse=True)
def _steps_isoles():
    """Charge les steps SANS laisser leurs déclarations dans le registre GLOBAL de Behave.

    ⚠️ Un run réel ne charge que `generic/` + UN connecteur ; ce fichier charge `generic/` + `web/`. Sans
    cette isolation, le libellé « je me connecte… » (aussi déclaré côté `odoo/`) resterait enregistré et
    ferait lever `AmbiguousStep` aux tests qui importent les steps Odoo ensuite (mesuré : 26 échecs).
    """
    global H, generic, web
    from behave import step_registry

    avant = {mot_cle: list(liste) for mot_cle, liste in step_registry.registry.steps.items()}
    deja = {nom for nom in ("_generic_steps", "_web_steps") if nom in sys.modules}
    for chemin in _CHEMINS:
        sys.path.insert(0, chemin)
    import _base_helpers as helpers
    import _generic_steps as generic_steps
    import _web_steps as web_steps
    H, generic, web = helpers, generic_steps, web_steps
    yield
    for mot_cle in list(step_registry.registry.steps):
        step_registry.registry.steps[mot_cle][:] = avant.get(mot_cle, [])
    for nom in ("_generic_steps", "_web_steps"):
        if nom not in deja:
            sys.modules.pop(nom, None)
    for chemin in _CHEMINS:
        if chemin in sys.path:
            sys.path.remove(chemin)


class _Champs:
    def __init__(self, page):
        self._page = page

    def count(self):
        return 1 if self._page.mdp_present else 0

    def nth(self, _i):
        return types.SimpleNamespace(is_visible=lambda: self._page.mdp_present)


class _Page:
    """Une page dont la seule chose observable est l'URL et la présence d'un champ mot de passe."""

    def __init__(self, url="https://app.test/login", mdp=True):
        self.url = url
        self.mdp_present = mdp
        self.visites = []

    def locator(self, selecteur):
        assert "password" in selecteur
        return _Champs(self)

    def goto(self, url, wait_until=None):
        self.visites.append(url)
        self.url = url


def _contexte(page=None, *, user="tomsmith", mdp="secret", web_url="https://app.test/login"):
    return types.SimpleNamespace(page=page or _Page(), web_user=user, web_password=mdp, web_url=web_url)


@pytest.fixture
def connexion(monkeypatch):
    """Remplace la détection PARTAGÉE par une double qui journalise son appel et rejoue une issue."""
    appels = []

    def installer(*, soumis=True, apres_url=None, apres_mdp=False, leve=None):
        def faux(page, user, password):
            appels.append((page, user, password))
            if leve:
                raise leve
            if soumis:
                if apres_url:
                    page.url = apres_url
                page.mdp_present = apres_mdp
            return soumis
        monkeypatch.setattr(H, "tenter_connexion_generique", faux)
        monkeypatch.setattr(H, "lire_message_erreur_visible", lambda page: "")
        return appels

    return installer


# ── Le critère de connexion réussie : les DEUX conditions ──────────────────────────────────────

@pytest.mark.parametrize("avant, apres, mdp, attendu", [
    ("https://a/login", "https://a/secure", False, True),      # the-internet : connecté
    ("https://a", "https://a/inventory.html", False, True),    # SauceDemo : connecté
    ("https://a/login", "https://a/login", True, False),       # refusé : rien ne bouge
    ("https://a/login", "https://a/login", False, False),      # URL inchangée seule ne suffit pas
    ("https://a/login", "https://a/login?e=1", True, False),   # l'URL a bougé mais le mot de passe reste
    ("https://a/login", "https://a/login/", True, False),      # `/` final : même page
    ("https://a/login", "https://a/login#x", False, False),    # fragment : même page
])
def test_le_critere_par_defaut_exige_l_url_partie_ET_plus_de_mot_de_passe(avant, apres, mdp, attendu):
    assert H.connexion_reussie(avant, apres, mdp) is attendu


# ── Le step d'entrée se connecte, en DÉLÉGUANT à la fonction de l'exploration ──────────────────

def test_le_step_d_entree_delegue_a_tenter_connexion_generique(connexion):
    appels = connexion(soumis=True, apres_url="https://app.test/secure")
    ctx = _contexte()

    generic.step_access_home_page(ctx)

    assert len(appels) == 1, "aucune seconde implémentation : la fonction PARTAGÉE est appelée"
    assert appels[0][1:] == ("tomsmith", "secret")
    assert ctx.page.visites == ["https://app.test/login"]
    assert ctx._tp_connecte is True


def test_aucune_seconde_implementation_de_connexion_dans_les_steps():
    """La fonction de l'exploration est la SEULE qui remplit un formulaire de connexion (incident du
    2026-09-18 : deux copies du même geste, une seule corrigée)."""
    sources = "\n".join(p.read_text(encoding="utf-8") for p in (
        _STEPS_LIB / "generic" / "_generic_steps.py", _STEPS_LIB / "web" / "_web_steps.py"))
    assert ".fill(" not in sources and "type='password'" not in sources
    bloc = re.search(r"def connexion_web_utilisateur.*?\n\ndef navigate", _source_helpers(), re.S).group(0)
    assert "tenter_connexion_generique(page, utilisateur, mot_de_passe)" in bloc
    assert ".fill(" not in bloc and ".press(" not in bloc


def _source_helpers() -> str:
    return (_STEPS_LIB / "_base_helpers.py").read_text(encoding="utf-8").replace("\r\n", "\n")


def test_echec_de_connexion_est_un_prerequis_non_rempli_avec_url_et_schema(connexion):
    connexion(soumis=True, apres_url=None, apres_mdp=True)  # refus : même URL, mot de passe encore là
    ctx = _contexte()

    with pytest.raises(H.PreconditionNonRemplieError) as err:
        generic.step_access_home_page(ctx)

    message = str(err.value)
    assert not isinstance(err.value, AssertionError)
    assert "https://app.test/login" in message
    assert "un écran" in message
    assert not getattr(ctx, "_tp_connecte", False)


def test_sso_ou_second_facteur_est_un_prerequis_non_rempli_qui_le_dit(connexion):
    connexion(leve=H.ConnexionGeneriqueImpossibleError("aucun champ mot de passe … SSO/second facteur"))
    ctx = _contexte(_Page(mdp=False))

    with pytest.raises(H.PreconditionNonRemplieError) as err:
        generic.step_access_home_page(ctx)

    assert "deux écrans" in str(err.value) and "SSO" in str(err.value)


def test_identifiants_vides_sur_une_application_qui_exige_une_connexion_est_bloque(connexion):
    appels = connexion()
    ctx = _contexte(user="", mdp="")  # la page affiche un champ mot de passe

    with pytest.raises(H.PreconditionNonRemplieError, match="ni identifiant ni mot de passe"):
        generic.step_access_home_page(ctx)

    assert appels == [], "sans identifiants, rien n'est tenté"


def test_identifiants_vides_sur_une_application_publique_ne_bloquent_pas(connexion):
    appels = connexion()
    ctx = _contexte(_Page(url="https://app.test/", mdp=False), user="", mdp="",
                    web_url="https://app.test/")

    generic.step_access_home_page(ctx)  # aucun champ mot de passe : rien n'exige de connexion

    assert appels == []


def test_une_application_sans_formulaire_de_connexion_reste_utilisable_a_l_entree(connexion):
    connexion(soumis=False)  # la détection ne trouve aucun formulaire
    ctx = _contexte(_Page(url="https://app.test/", mdp=False))

    generic.step_access_home_page(ctx)  # comportement historique : pas de blocage

    assert not getattr(ctx, "_tp_connecte", False)


# ── Le cas qui TESTE la connexion ──────────────────────────────────────────────────────────────

def test_sans_me_connecter_charge_la_page_sans_rien_tenter(connexion):
    appels = connexion()
    ctx = _contexte()

    generic.step_access_login_page_without_login(ctx)

    assert appels == []
    assert ctx.page.visites == ["https://app.test/login"]


def test_sans_me_connecter_sans_url_est_un_prerequis_manquant_pas_une_assertion(connexion):
    connexion()

    with pytest.raises(H.NavigationImpossibleError):
        generic.step_access_login_page_without_login(_contexte(web_url=""))


# ── Le step explicite, en milieu de parcours ──────────────────────────────────────────────────

def test_step_explicite_delegue_et_connecte(connexion):
    appels = connexion(soumis=True, apres_url="https://app.test/secure")
    ctx = _contexte()

    web.step_login_web(ctx)

    assert len(appels) == 1 and ctx._tp_connecte is True


def test_step_explicite_sans_formulaire_alors_qu_on_n_est_pas_connecte_est_bloque(connexion):
    connexion(soumis=False)

    with pytest.raises(H.PreconditionNonRemplieError, match="aucun formulaire de connexion"):
        web.step_login_web(_contexte(_Page(url="https://app.test/x", mdp=False)))


def test_step_explicite_apres_une_connexion_automatique_ne_bloque_pas(connexion):
    """L'agent écrit quand même le step : déjà connecté, il n'y a plus de formulaire — pas un échec."""
    connexion(soumis=False)
    ctx = _contexte(_Page(url="https://app.test/secure", mdp=False))
    ctx._tp_connecte = True

    web.step_login_web(ctx)


def test_step_explicite_echec_de_connexion_est_bloque(connexion):
    connexion(soumis=True, apres_mdp=True)

    with pytest.raises(H.PreconditionNonRemplieError, match="n'a pas abouti"):
        web.step_login_web(_contexte())


# ── De l'exception au verdict : `blocked`, jamais `failed` ni `technical_error` ───────────────

def test_l_echec_de_connexion_donne_la_cause_precondition_donc_blocked(connexion):
    connexion(soumis=True, apres_mdp=True)
    with pytest.raises(H.PreconditionNonRemplieError) as err:
        generic.step_access_home_page(_contexte())

    for type_de_step in ("given", "when"):
        echec = BehaveFailure("s", "", "unknown", "",
                              raw=("Traceback (most recent call last):\n"
                                   "  File \"_base_helpers.py\", line 1, in x\n"
                                   f"_base_helpers.{type(err.value).__name__}: {err.value}"),
                              step_type=type_de_step)
        assert dt.classify_failure(echec) == dt.PRECONDITION_NON_REMPLIE, type_de_step


# ── La bibliothèque : pas de collision de libellés, rien d'Odoo dans le socle générique ───────

def _labels(connecteur):
    return [s.label for s in steps_library.catalogue(connector_type=connecteur)]


@pytest.mark.parametrize("connecteur", ["web", "odoo"])
def test_aucun_libelle_n_est_declare_deux_fois_pour_un_meme_connecteur(connecteur):
    """`generic/` + UN connecteur sont chargés ensemble : un doublon = `AmbiguousStep` au chargement."""
    paires = [(s.keyword, s.label) for s in steps_library.catalogue(connector_type=connecteur)]
    assert len(paires) == len(set(paires)), sorted(p for p in set(paires) if paires.count(p) > 1)


def test_le_step_de_connexion_web_n_existe_que_dans_le_catalogue_web():
    web_sources = {s.source for s in steps_library.catalogue(connector_type="web")
                   if s.label == "je me connecte avec mes identifiants utilisateur"}
    odoo_sources = {s.source for s in steps_library.catalogue(connector_type="odoo")
                    if s.label == "je me connecte avec mes identifiants utilisateur"}

    assert web_sources == {"web/_web_steps.py"}
    assert odoo_sources == {"odoo/_odoo_steps.py"}


def test_les_deux_steps_d_entree_sont_dans_le_socle_generique():
    for connecteur in ("web", "odoo"):
        labels = _labels(connecteur)
        assert "j'accède à la page d'accueil de l'application" in labels
        assert "j'accède à la page de connexion sans me connecter" in labels


def test_aucun_step_generique_ni_web_ne_reference_context_odoo():
    """Lu dans l'AST (un docstring qui en parle n'est pas une référence)."""
    import ast

    for dossier in ("generic", "web"):
        for chemin in (_STEPS_LIB / dossier).glob("*.py"):
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Attribute) and noeud.attr == "odoo"                         and isinstance(noeud.value, ast.Name) and noeud.value.id == "context":
                    pytest.fail(f"{chemin.name}:{noeud.lineno} référence context.odoo")
