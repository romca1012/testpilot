"""« Chantier F » (F.2/F.3) — résolution adaptative, dernier recours de `locate_field`.

F.1 (la cascade déterministe de `locate_field` — name/data-test(id)/classe CSS/libellé/
placeholder, doc officielle Playwright/Testing Library) reste TOUJOURS tentée en premier, jamais
court-circuitée : ces tests vérifient que le nouveau palier n'agit QUE lorsqu'elle a tout épuisé,
et seulement si une « intention » (le texte du step Gherkin, posé par `before_step` sur `page` —
voir `environment.py`) est disponible. Sans elle : zéro appel LLM, comportement STRICTEMENT
inchangé — c'est le point le plus important à verrouiller, puisque tous les appelants existants de
`locate_field` (`fill_field`, `select_field_value`, …) ne changent pas de signature.

Le modèle ne doit JAMAIS inventer un élément absent de la page réelle — il CHOISIT un `idx` parmi
la liste transmise, ou dit `idx=null`. Un `idx` halluciné (hors liste) n'est jamais suivi.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

import _adaptive_resolution  # noqa: E402
from _adaptive_resolution import resoudre_champ_adaptatif  # noqa: E402
from _base_helpers import (  # noqa: E402
    _MAX_TENTATIVES_ADAPTATIVES_MENU, ElementIntrouvableError, FIELD_FALLBACK_FILE_ENV,
    SELECTOR_TIER_FILE_ENV, click_button, click_first_actionable, locate_field, navigate_menu,
)


# ── `_adaptive_resolution.resoudre_champ_adaptatif`, en isolation ────────────────────────────

def test_qualification_ne_fait_aucun_appel_adaptatif(monkeypatch):
    from _base_helpers import _repli_adaptatif
    monkeypatch.setenv('TESTPILOT_QUALIFICATION', '1')
    def forbidden(*args, **kwargs):
        raise AssertionError('aucun appel LLM pendant la qualification stricte')
    monkeypatch.setattr(_adaptive_resolution, 'resoudre_champ_adaptatif', forbidden)
    assert _repli_adaptatif(object(), 'champ', 'saisir') is None

class _FakeLocatorAdaptatif:
    def __init__(self, count):
        self._count = count

    def count(self):
        return self._count

    @property
    def first(self):
        return self


class _FakePageAdaptatif:
    """Reproduit juste assez : `evaluate()` pour lire les candidats ET pour nettoyer les
    marqueurs, `locator()` pour retrouver l'élément élu par son index."""

    def __init__(self, candidats, existants=None):
        self._candidats = candidats
        self._existants = existants if existants is not None else {c["idx"] for c in candidats}
        self.nettoye = False

    def evaluate(self, script, *args):
        if "removeAttribute" in script:
            self.nettoye = True
            return None
        return self._candidats

    def locator(self, sel):
        m = re.search(r'"(\d+)"', sel)
        idx = int(m.group(1)) if m else None
        return _FakeLocatorAdaptatif(1 if idx in self._existants else 0)


class _FakeLLM:
    def __init__(self, idx):
        self.idx = idx
        self.appels = 0

    def call_json(self, **kw):
        self.appels += 1
        return {"idx": self.idx, "raison": "test"}


class _FakeLLMEnPanne:
    def call_json(self, **kw):
        raise RuntimeError("panne réseau simulée")


_CANDIDATS = [
    {"idx": 0, "role": "textbox", "nom": "Recherche", "type": "text"},
    {"idx": 1, "role": "combobox", "nom": "Produit", "type": ""},
    {"idx": 2, "role": "button", "nom": "Valider", "type": "submit"},
]


def test_sans_intention_aucun_appel_llm_ni_evaluate():
    """Le garde-fou coût zéro : sans intention, on ne lit même pas les candidats réels."""
    llm = _FakeLLM(idx=1)
    page = _FakePageAdaptatif(_CANDIDATS)
    assert resoudre_champ_adaptatif(page, "product_id", "", llm=llm) is None
    assert llm.appels == 0


def test_modele_choisit_un_element_reel():
    llm = _FakeLLM(idx=1)
    page = _FakePageAdaptatif(_CANDIDATS)
    resultat = resoudre_champ_adaptatif(
        page, "product_id", "je sélectionne le produit contenant « Widget »", llm=llm)
    assert resultat is not None
    assert resultat.count() == 1
    assert llm.appels == 1


def test_le_libelle_reel_de_lelement_elu_est_pose_sur_la_page():
    """Lot 2 du plan de fiabilisation (2026-09-23) : `navigate_menu` relit
    `page._tp_dernier_libelle_choisi` pour apprendre, projet par projet, quel libellé RÉEL a
    permis de franchir un segment de menu introuvable tel quel — sans ce champ, l'apprentissage
    n'a rien à persister."""
    llm = _FakeLLM(idx=1)
    page = _FakePageAdaptatif(_CANDIDATS)
    resoudre_champ_adaptatif(page, "product_id", "je sélectionne le produit", llm=llm)
    assert page._tp_dernier_libelle_choisi == "Produit"


def test_modele_dit_aucune_correspondance():
    llm = _FakeLLM(idx=None)
    page = _FakePageAdaptatif(_CANDIDATS)
    assert resoudre_champ_adaptatif(page, "x", "une intention", llm=llm) is None
    assert page.nettoye, "le marqueur temporaire doit être retiré quand rien n'est retenu"


def test_idx_hallucine_hors_liste_jamais_suivi():
    """Le modèle désigne un idx qui n'existe pas dans les candidats transmis — jamais suivi,
    même s'il correspondrait par hasard à un élément DE LA PAGE (principe : choisir, pas deviner)."""
    llm = _FakeLLM(idx=99)
    page = _FakePageAdaptatif(_CANDIDATS)
    assert resoudre_champ_adaptatif(page, "x", "une intention", llm=llm) is None


def test_aucun_candidat_reel_rend_none_sans_appeler_le_modele():
    llm = _FakeLLM(idx=0)
    page = _FakePageAdaptatif([])
    assert resoudre_champ_adaptatif(page, "x", "une intention", llm=llm) is None
    assert llm.appels == 0


def test_panne_du_modele_ne_leve_jamais():
    page = _FakePageAdaptatif(_CANDIDATS)
    assert resoudre_champ_adaptatif(page, "x", "une intention", llm=_FakeLLMEnPanne()) is None


# ── Intégration dans `locate_field` : dernier recours, jamais le premier ─────────────────────

class _LocatorTechniqueVide:
    """Ce que rendent TOUS les paliers déterministes de `locate_field` — rien d'attaché,
    rien trouvé — pour isoler le dernier recours adaptatif."""

    @property
    def first(self):
        return self

    def wait_for(self, state="attached", timeout=8000):
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        raise PlaywrightTimeout("rien trouvé")

    def count(self):
        return 0


class _FakePageToutEchoue:
    """Un `page` dont AUCUN palier déterministe ne peut résoudre quoi que ce soit — même surface
    que `locate_field` interroge (`locator`, `get_by_label`, `get_by_placeholder`)."""

    def __init__(self, intention=""):
        if intention:
            self._tp_intention_step = intention

    def locator(self, sel):
        return _LocatorTechniqueVide()

    def get_by_label(self, text, exact=False):
        return _LocatorTechniqueVide()

    def get_by_placeholder(self, text, exact=False):
        return _LocatorTechniqueVide()


_SENTINEL = object()


def test_locate_field_sans_intention_reste_byte_pour_byte_identique():
    """Le changement le plus important à verrouiller : sans intention (page non instrumentée par
    `before_step`), le nouveau palier ne doit RIEN faire — comportement d'avant F.2, un `Locator`
    vide, exactement ce que rendait `locate_field` avant ce chantier."""
    page = _FakePageToutEchoue(intention="")
    resultat = locate_field(page, "champ_inconnu", timeout=50)
    assert resultat.count() == 0


def test_locate_field_appelle_l_adaptatif_en_dernier_recours(monkeypatch):
    appels = []

    def fake_resoudre(page, ident, intention, **kw):
        appels.append((ident, intention))
        return _SENTINEL

    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif", fake_resoudre)
    page = _FakePageToutEchoue(intention="je sélectionne le produit contenant « Widget »")

    resultat = locate_field(page, "product_id", timeout=50)

    assert resultat is _SENTINEL
    assert appels == [("product_id", "je sélectionne le produit contenant « Widget »")]


def test_locate_field_trace_la_resolution_adaptative(monkeypatch, tmp_path):
    """F.3 : une résolution adaptative n'est jamais un succès silencieux — même transport que
    les autres replis de `locate_field` (sidecars `SELECTOR_TIER_FILE_ENV`/`FIELD_FALLBACK_FILE_ENV`,
    déjà existants, jamais un troisième canal ad hoc)."""
    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif",
                        lambda page, ident, intention, **kw: _SENTINEL)
    tier_file = tmp_path / "tiers.jsonl"
    fallback_file = tmp_path / "fallbacks.txt"
    monkeypatch.setenv(SELECTOR_TIER_FILE_ENV, str(tier_file))
    monkeypatch.setenv(FIELD_FALLBACK_FILE_ENV, str(fallback_file))

    page = _FakePageToutEchoue(intention="je clique sur « Ajouter »")
    assert locate_field(page, "champ_x", timeout=50) is _SENTINEL

    trace = json.loads(tier_file.read_text(encoding="utf-8").strip())
    assert trace == {"ident": "champ_x", "tier": "adaptive"}
    assert "ADAPTATIVE" in fallback_file.read_text(encoding="utf-8")


def test_locate_field_trace_aussi_un_echec_de_resolution_adaptative(monkeypatch, tmp_path):
    """Bug RÉEL mesuré en run (Sapian, 2026-09-22) : un `logger.warning` seul ne survit à AUCUN
    scénario avec le formatter JSON custom (Behave capture le logging en mémoire et ne le
    recrache nulle part) — le premier jet de ce palier était totalement muet sur un échec, rendant
    le diagnostic impossible. Un échec doit lui aussi atteindre le sidecar, pas seulement un succès."""
    def fake_resoudre(page, ident, intention, **kw):
        page._tp_dernier_diagnostic_adaptatif = "aucune correspondance parmi 3 candidats"
        return None

    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif", fake_resoudre)
    fallback_file = tmp_path / "fallbacks.txt"
    monkeypatch.setenv(FIELD_FALLBACK_FILE_ENV, str(fallback_file))

    page = _FakePageToutEchoue(intention="je clique sur « Ajouter »")
    resultat = locate_field(page, "champ_x", timeout=50)

    assert resultat.count() == 0  # comportement d'échec inchangé
    assert "aucune correspondance parmi 3 candidats" in fallback_file.read_text(encoding="utf-8")


def test_locate_field_sans_resolution_adaptative_retombe_sur_le_comportement_dorigine(monkeypatch):
    """Même avec une intention, si l'adaptatif ne trouve rien (`None`), `locate_field` retombe
    sur SON comportement d'échec d'origine — un `Locator` vide, jamais une exception nouvelle."""
    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif",
                        lambda page, ident, intention, **kw: None)
    page = _FakePageToutEchoue(intention="une intention qui ne mène à rien")
    resultat = locate_field(page, "champ_y", timeout=50)
    assert resultat.count() == 0


# ── `click_first_actionable`/`click_button` — 3e point d'entrée, même dernier recours ────────
#
# Bug RÉEL mesuré en run (Sapian, 2026-09-22) : après que le repli adaptatif ait bien résolu la
# navigation vers un sous-menu jamais vu, le step suivant (`je clique sur le bouton "Nouveau"`)
# échouait quand même sur `click_button` — un TROISIÈME point d'entrée, distinct de `locate_field`
# et `navigate_menu`, qui n'avait pas encore ce dernier recours.

class _LocatorClicTimeout:
    @property
    def first(self):
        return self

    def click(self, timeout=None):
        from playwright.sync_api import TimeoutError as PWTimeout
        raise PWTimeout("rien trouvé")


class _LocatorClicAdaptatif:
    def __init__(self, journal):
        self._journal = journal

    def click(self, timeout=None):
        self._journal.append("clic-adaptatif")


class _FakePageBoutonIntrouvable:
    """Simule TOUS les candidats CSS/rôle de `click_button` en échec — pour isoler le dernier
    recours adaptatif de `click_first_actionable`. `evaluate` répond vide pour
    `verifier_soumission_non_bloquee` (pas de formulaire invalide à signaler)."""

    def __init__(self):
        self.url = "https://sapian.example.com/web#action=206"

    def get_by_role(self, role, name=None, exact=False):
        return _LocatorClicTimeout()

    def locator(self, sel):
        return _LocatorClicTimeout()

    def evaluate(self, script):
        return []


def test_click_first_actionable_sans_ident_reste_byte_pour_byte_identique():
    """Sans `ident` (les appelants qui ne le fournissent pas, ex. `select_first_service_in_list`),
    comportement STRICTEMENT inchangé : `ElementIntrouvableError`, jamais de tentative adaptative."""
    page = _FakePageBoutonIntrouvable()
    try:
        click_first_actionable(page, ["#introuvable"], quoi="Bouton 'X'", timeout=50)
        assert False, "un ElementIntrouvableError devait être levé"
    except ElementIntrouvableError:
        pass


def test_click_button_utilise_le_repli_adaptatif_en_dernier_recours(monkeypatch):
    """Le cas réel : `click_button(page, 'Nouveau')` échoue sur tous les candidats codés en dur,
    le repli adaptatif choisit l'élément réel et le clic aboutit quand même."""
    journal = []
    monkeypatch.setattr(
        _adaptive_resolution, "resoudre_champ_adaptatif",
        lambda page, ident, intention, **kw: _LocatorClicAdaptatif(journal)
        if ident == "Nouveau" else None,
    )
    page = _FakePageBoutonIntrouvable()

    click_button(page, "Nouveau")

    assert journal == ["clic-adaptatif"]


def test_click_button_sans_solution_adaptative_leve_element_introuvable(monkeypatch):
    """Si l'adaptatif ne trouve rien non plus, l'échec d'origine (`ElementIntrouvableError`,
    qui nomme le bouton et l'URL) remonte — jamais masqué par un succès inventé."""
    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif",
                        lambda page, ident, intention, **kw: None)
    page = _FakePageBoutonIntrouvable()
    try:
        click_button(page, "Nouveau")
        assert False, "un ElementIntrouvableError devait être levé"
    except ElementIntrouvableError as exc:
        assert "Nouveau" in str(exc)


# ── `navigate_menu` — même dernier recours, deuxième point d'entrée ──────────────────────────
#
# Bug RÉEL, mesuré en run (Sapian, 2026-09-22) : `discover_menus` avait capturé le libellé
# anglais « Surveys », la session d'exécution affichait le menu en français (« Sondages ») —
# `get_by_text("Surveys", exact=True)` timeout puisque ce texte n'existe pas dans CE DOM. Le
# repli adaptatif (même mécanisme que `locate_field`, `_repli_adaptatif` partagé) doit alors
# recevoir une chance de choisir l'élément réel qui correspond à l'intention.

class _LocatorMenuTimeout:
    @property
    def first(self):
        return self

    def click(self, timeout=None):
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        raise PlaywrightTimeout("rien trouvé")


class _LocatorMenuOk:
    def __init__(self, journal, texte):
        self._journal = journal
        self._texte = texte

    @property
    def first(self):
        return self

    def click(self, timeout=None):
        self._journal.append(self._texte)


class _LocatorAdaptatifCliquable:
    """Un clic adaptatif dont le modèle est CONFIANT que c'est la destination finale — pose
    `page._tp_dernier_choix_menu_parent = False` ET `page._tp_dernier_libelle_choisi`, exactement
    ce que `resoudre_champ_adaptatif` fait sur un vrai succès (voir `_adaptive_resolution.py`)."""

    def __init__(self, page, journal, label, libelle_reel=""):
        self._page, self._journal, self._label = page, journal, label
        self._libelle_reel = libelle_reel or label

    def click(self, timeout=None):
        self._journal.append(f"adaptatif:{self._label}")
        self._page._tp_dernier_choix_menu_parent = False
        self._page._tp_dernier_libelle_choisi = self._libelle_reel


class _LocatorAdaptatifOuvreSousMenu:
    """Un clic adaptatif dont le modèle SOUPÇONNE avoir choisi un menu/groupe générique plutôt
    qu'une destination finale — pose `page._tp_dernier_choix_menu_parent = True`. Le cas réel
    mesuré sur C127 (clic sur le lien parent « Tickets », pas sur l'item réel « Tous les tickets »)."""

    def __init__(self, page, journal, label):
        self._page, self._journal, self._label = page, journal, label

    def click(self, timeout=None):
        self._journal.append(f"ouvre-sous-menu:{self._label}")
        self._page._tp_dernier_choix_menu_parent = True


class _FakePageMenuAdaptatif:
    """Comme `_FakePageMenu` (tests de délégation `_odoo_steps`), mais un sous-ensemble des
    libellés recherchés timeout au premier essai — pour isoler le repli adaptatif."""

    def __init__(self, echoue_sur):
        self.url = "about:blank"
        self.urls_visitees = []
        self.clics = []
        self._echoue_sur = set(echoue_sur)

    def goto(self, url, **_k):
        self.urls_visitees.append(url)
        self.url = url

    def get_by_text(self, texte, exact=True):
        if texte in self._echoue_sur:
            return _LocatorMenuTimeout()
        return _LocatorMenuOk(self.clics, texte)


def test_navigate_menu_reussit_directement_sans_jamais_appeler_l_adaptatif(monkeypatch):
    """Chemin heureux : `get_by_text(exact=True)` trouve tout — F.1 (déterministe) n'est jamais
    court-circuité, l'adaptatif n'est même pas importé."""
    appele = []
    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif",
                        lambda *a, **kw: appele.append(1) or None)
    page = _FakePageMenuAdaptatif(echoue_sur=set())
    import types
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    navigate_menu(ctx, "Assistance / Tickets")

    assert page.clics == ["Assistance", "Tickets"]
    assert appele == []


def test_navigate_menu_repli_adaptatif_sur_un_libelle_dans_une_autre_langue(monkeypatch):
    """Le cas réel : « Surveys » n'existe pas dans un DOM affiché en français ; le repli
    adaptatif choisit l'élément réel (« Sondages ») et le clic aboutit quand même."""
    journal = []
    monkeypatch.setattr(
        _adaptive_resolution, "resoudre_champ_adaptatif",
        lambda page, ident, intention, **kw: _LocatorAdaptatifCliquable(page, journal, ident)
        if ident == "Surveys" else None,
    )
    page = _FakePageMenuAdaptatif(echoue_sur={"Surveys"})
    import types
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    navigate_menu(ctx, "Surveys")

    assert journal == ["adaptatif:Surveys"]


def test_navigate_menu_consigne_le_libelle_reel_appris_dans_le_sidecar(monkeypatch, tmp_path):
    """Lot 2 du plan de fiabilisation (2026-09-23) : un succès du repli adaptatif de
    `navigate_menu` doit être APPRIS pour ce projet — sans ce câblage, `discover_menus` reproposera
    indéfiniment le même libellé faux à chaque régénération (cas RÉEL, Sapian, « Surveys » vs
    « Sondages »)."""
    from _base_helpers import MENU_LEARNED_FILE_ENV

    sidecar = tmp_path / "menus_appris.jsonl"
    monkeypatch.setenv(MENU_LEARNED_FILE_ENV, str(sidecar))
    monkeypatch.setattr(
        _adaptive_resolution, "resoudre_champ_adaptatif",
        lambda page, ident, intention, **kw: _LocatorAdaptatifCliquable(
            page, [], ident, libelle_reel="Sondages") if ident == "Surveys" else None,
    )
    page = _FakePageMenuAdaptatif(echoue_sur={"Surveys"})
    import types
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    navigate_menu(ctx, "Surveys")

    fait = json.loads(sidecar.read_text(encoding="utf-8").strip())
    assert fait == {"segment_original": "Surveys", "libelle_reel": "Sondages",
                    "menu_path": "Surveys"}


def test_navigate_menu_reboucle_si_le_clic_adaptatif_n_ouvre_qu_un_sous_menu(monkeypatch):
    """Le VRAI cas mesuré sur C127 (Sapian, 2026-09-22) : le premier clic adaptatif choisit le
    lien parent « Tickets » (ouvre un sous-menu, URL inchangée) — au lieu d'avancer au segment
    suivant en croyant la navigation acquise, `navigate_menu` retente une résolution adaptative
    sur LE MÊME segment, et la deuxième passe (sous-menu maintenant ouvert) réussit."""
    journal = []
    appels = {"n": 0}

    def fake_resoudre(page, ident, intention, **kw):
        appels["n"] += 1
        if appels["n"] == 1:
            return _LocatorAdaptatifOuvreSousMenu(page, journal, "Tickets (parent)")
        return _LocatorAdaptatifCliquable(page, journal, "Tous les tickets")

    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif", fake_resoudre)
    page = _FakePageMenuAdaptatif(echoue_sur={"All Tickets"})
    import types
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    navigate_menu(ctx, "All Tickets")

    assert journal == ["ouvre-sous-menu:Tickets (parent)", "adaptatif:Tous les tickets"]
    assert appels["n"] == 2


def test_navigate_menu_plafonne_les_tentatives_adaptatives_sans_progression(monkeypatch):
    """Si le modèle pense TOUJOURS avoir choisi un menu/groupe (jamais confiant d'être arrivé),
    `navigate_menu` ne boucle pas indéfiniment — elle échoue proprement après un nombre borné de
    tentatives, avec un message qui nomme le segment et l'URL."""
    journal = []
    monkeypatch.setattr(
        _adaptive_resolution, "resoudre_champ_adaptatif",
        lambda page, ident, intention, **kw: _LocatorAdaptatifOuvreSousMenu(page, journal, ident),
    )
    page = _FakePageMenuAdaptatif(echoue_sur={"All Tickets"})
    import types
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    try:
        navigate_menu(ctx, "All Tickets")
        assert False, "un ElementIntrouvableError devait être levé"
    except ElementIntrouvableError as exc:
        assert "All Tickets" in str(exc)
    assert len(journal) == _MAX_TENTATIVES_ADAPTATIVES_MENU


def test_navigate_menu_sans_solution_adaptative_laisse_remonter_le_timeout_dorigine(monkeypatch):
    """Si l'adaptatif ne trouve rien non plus, l'échec d'origine (`TimeoutError`, classé
    `wrong_navigation`) remonte — jamais masqué par un succès inventé."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    monkeypatch.setattr(_adaptive_resolution, "resoudre_champ_adaptatif",
                        lambda *a, **kw: None)
    page = _FakePageMenuAdaptatif(echoue_sur={"Surveys"})
    import types
    ctx = types.SimpleNamespace(page=page, odoo_url="https://sapian.example.com")

    try:
        navigate_menu(ctx, "Surveys")
        assert False, "un TimeoutError devait remonter"
    except PlaywrightTimeout:
        pass
