"""§6 / multi-connecteurs (2026-09-08) — `crawl_domaine.crawler` reste UTILISABLE pour un
connecteur autre qu'Odoo, sans rien changer au comportement historique.

`racines`/`hors_perimetre`/`relogin` sont de nouveaux paramètres optionnels (défaut `None` =
constantes Odoo, comportement STRICTEMENT inchangé pour l'appelant historique — voir
`exploration_service.py::_crawl` pour l'appelant réel du connecteur `web`). On les couvre ici
avec un navigateur ENTIÈREMENT simulé (aucun Playwright réel), le BFS étant une pure boucle
Python autour de `ctx.page`/`nav.new_page()`.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import types
from pathlib import Path
from urllib.parse import urlparse

RACINE = Path(__file__).resolve().parent.parent


def _charger_crawl():
    """Importe le script de crawl sans le lancer (même helper que test_normalisation_route.py)."""
    sys.path.insert(0, str(RACINE / "behave_runtime" / "steps_library"))
    spec = importlib.util.spec_from_file_location(
        "_crawl_domaine_sous_test_generique", RACINE / "scripts" / "crawl_domaine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakePage:
    """Un site ENTIER tient dans `pages` : chemin → liens sortants. `evaluate` répond selon
    l'URL où `goto` vient d'atterrir — c'est ce qui fait avancer le BFS d'une page à l'autre.

    `ancres` (2026-09-11, suivi des `href="#"` par clic) : chemin → {id_lien: url_apres_clic} —
    simule une SPA où un clic change l'URL par History API, jamais par un `href` réel."""

    def __init__(self, pages: dict[str, list[str]], *, ancres: dict[str, dict] | None = None):
        self.url = ""
        self._pages = pages
        self._ancres = ancres or {}

    def goto(self, url, **_kwargs):
        self.url = url

    def wait_for_load_state(self, *_args, **_kwargs):
        pass

    def click(self, selector, **_kwargs):
        m = re.match(r'\[id="(.+)"\]', selector)
        lien_id = m.group(1) if m else None
        ancres_ici = self._ancres.get(urlparse(self.url).path or "/", {})
        if lien_id not in ancres_ici:
            raise RuntimeError(f"sélecteur introuvable : {selector}")
        self.url = ancres_ici[lien_id]

    def evaluate(self, _script):
        chemin = urlparse(self.url).path or "/"
        liens = [{"href": h, "text": "", "role": None, "id": ""}
                for h in self._pages.get(chemin, [])]
        liens += [{"href": "#", "text": "", "role": None, "id": lien_id}
                 for lien_id in self._ancres.get(chemin, {})]
        return {"champs": [], "actions": [], "formulaires": [], "titre": "", "liens": liens}


class _FakeNav:
    def new_page(self):
        return _FakePage({})  # non utilisé : aucun crash simulé dans ces tests


def test_crawler_respecte_des_racines_personnalisees():
    """Le connecteur `web` n'a pas les racines Odoo (`/my/home`, `/myservices`) — il part de `/`."""
    crawl = _charger_crawl()
    page = _FakePage({"/": ["/dashboard"], "/dashboard": []})
    pages, _transitions, _onglets = crawl.crawler(
        types.SimpleNamespace(page=page), _FakeNav(), "http://app.local", max_pages=10,
        racines=["/"], hors_perimetre=crawl._HORS_PERIMETRE_GENERIQUE, relogin=lambda c: None)

    assert set(pages) == {"/", "/dashboard"}


def test_crawler_applique_l_exclusion_generique_fournie():
    """Une exclusion PERSONNALISÉE (pas celle d'Odoo) doit vraiment être celle qui décide."""
    crawl = _charger_crawl()
    page = _FakePage({"/": ["/dashboard", "/rapport.pdf"], "/dashboard": []})
    pages, _transitions, _onglets = crawl.crawler(
        types.SimpleNamespace(page=page), _FakeNav(), "http://app.local", max_pages=10,
        racines=["/"], hors_perimetre=crawl._HORS_PERIMETRE_GENERIQUE, relogin=lambda c: None)

    assert "/rapport.pdf" not in pages   # exclu par _HORS_PERIMETRE_GENERIQUE (asset)
    assert "/dashboard" in pages         # pas un asset : suivi normalement


def test_exclusion_generique_ne_connait_aucun_chemin_odoo():
    """⚠️ La différence structurelle avec `_HORS_PERIMETRE` : rien de spécifique à un ERP.
    Un chemin `/web/...` (back-office Odoo) n'a AUCUNE raison d'être exclu pour un connecteur
    `web` — ce pourrait très bien être une route légitime de l'application ciblée."""
    crawl = _charger_crawl()
    assert crawl._HORS_PERIMETRE.search("/web/login")
    assert not crawl._HORS_PERIMETRE_GENERIQUE.search("/web/login")
    assert crawl._HORS_PERIMETRE_GENERIQUE.search("/assets/logo.png")


def test_sans_parametres_le_comportement_odoo_historique_est_inchange():
    """Les nouveaux paramètres sont keyword-only avec défaut `None` — un appel à l'ancienne
    (positionnel, comme `main()` le fait encore) doit retomber sur les racines Odoo.

    `relogin` n'est jamais fourni ICI (donc son défaut, `H.playwright_login`, resterait actif) —
    sûr uniquement parce qu'aucun crash n'est simulé : la fonction n'est alors jamais appelée."""
    crawl = _charger_crawl()
    # Racines Odoo réelles (`/my/home`, `/myservices`) atteintes SANS jamais les passer.
    # `/my/home` → `/home` : PIÈGE documenté (`test_normalisation_route.py`) — `my` (birman,
    # ISO 639-1) est pris pour un préfixe de langue par `normaliser_route`, pas une régression ici.
    page = _FakePage({"/my/home": [], "/myservices": []})
    pages, _transitions, _onglets = crawl.crawler(
        types.SimpleNamespace(page=page), _FakeNav(), "http://app.local", max_pages=10)

    assert set(pages) == {"/home", "/myservices"}


def test_relogin_personnalise_est_appele_apres_un_crash_simule():
    """La reconnexion générique (pas Odoo) doit être RÉELLEMENT utilisée après un crash.

    Comportement HISTORIQUE inchangé : la page qui a crashé est PERDUE (aucune reprise sur la
    même route — mieux vaut l'admettre que deviner son contenu), mais le navigateur relancé +
    reconnecté doit permettre aux pages SUIVANTES d'aboutir."""
    crawl = _charger_crawl()

    class _PageQuiCrashe:
        def goto(self, url, **_kwargs):
            raise RuntimeError("Page crashed!")

    class _PageOK:
        def __init__(self):
            self.url = ""

        def goto(self, url, **_kwargs):
            self.url = url

        def evaluate(self, _script):
            return {"champs": [], "actions": [], "formulaires": [], "titre": "", "liens": []}

    class _NavQuiRelance:
        def new_page(self):
            return _PageOK()

    relogin_appele = []
    ctx = types.SimpleNamespace(page=_PageQuiCrashe())
    pages, _t, _o = crawl.crawler(
        ctx, _NavQuiRelance(), "http://app.local", max_pages=5,
        racines=["/", "/dashboard"], hors_perimetre=crawl._HORS_PERIMETRE_GENERIQUE,
        relogin=lambda c: relogin_appele.append(True))

    assert relogin_appele == [True]
    assert "/" not in pages          # perdue : pas de reprise sur la route qui a crashé
    assert "/dashboard" in pages     # aboutit grâce au navigateur relancé + reconnecté


# ── Suivi des ancres `href="#"` par clic (2026-09-11, SauceDemo sur /dev) ──────────────────────

def test_par_defaut_une_ancre_hash_reste_un_onglet_jamais_une_page():
    """`suivre_ancres_hash` NON fourni = comportement Odoo HISTORIQUE, strictement inchangé —
    même avec un `id` cliquable et une cible qui existerait, rien n'est suivi."""
    crawl = _charger_crawl()
    page = _FakePage({"/": []}, ancres={"/": {"voir-produit": "http://app.local/produit-1"}})
    pages, _t, onglets = crawl.crawler(
        types.SimpleNamespace(page=page), _FakeNav(), "http://app.local", max_pages=10,
        racines=["/"], hors_perimetre=crawl._HORS_PERIMETRE_GENERIQUE, relogin=lambda c: None)

    assert set(pages) == {"/"}
    assert onglets["/"]  # toujours compté comme changement d'état


def test_suivre_ancres_hash_decouvre_une_page_atteinte_seulement_par_clic():
    """⚠️ Le vrai bug SauceDemo : une fiche produit n'a pas de `href` réel, seulement un clic qui
    change l'URL via l'History API. Avec `suivre_ancres_hash=True`, ce clic doit être tenté et sa
    cible RÉELLE ajoutée au parcours — exactement ce qui manquait pour cartographier un catalogue
    dont chaque page n'est joignable que par ce chemin-là."""
    crawl = _charger_crawl()
    page = _FakePage(
        {"/": [], "/produit-1": []},
        ancres={"/": {"voir-produit": "http://app.local/produit-1"}})
    pages, transitions, _onglets = crawl.crawler(
        types.SimpleNamespace(page=page), _FakeNav(), "http://app.local", max_pages=10,
        racines=["/"], hors_perimetre=crawl._HORS_PERIMETRE_GENERIQUE, relogin=lambda c: None,
        suivre_ancres_hash=True)

    assert set(pages) == {"/", "/produit-1"}
    assert "/produit-1" in transitions["/"]
    # La page reste RESTAURÉE après le test du clic — le BFS termine sur l'état attendu.
    assert page.url == "http://app.local/produit-1"  # dernière page RÉELLEMENT visitée par le BFS


def test_une_ancre_hash_sans_id_n_est_jamais_cliquee():
    """Sans identifiant fiable pour la RECLIQUER, mieux vaut renoncer que deviner — un clic sur
    le mauvais élément (parmi plusieurs liens au texte identique) mesurerait une fausse route."""
    crawl = _charger_crawl()

    class _PageSansId:
        def __init__(self):
            self.url = "http://app.local/"

        def goto(self, url, **_kwargs):
            self.url = url

        def wait_for_load_state(self, *_a, **_k):
            pass

        def click(self, *_a, **_k):
            raise AssertionError("aucun clic ne devrait être tenté sans id")

        def evaluate(self, _script):
            return {"champs": [], "actions": [], "formulaires": [], "titre": "",
                    "liens": [{"href": "#", "text": "Voir", "role": None, "id": ""}]}

    pages, _t, onglets = crawl.crawler(
        types.SimpleNamespace(page=_PageSansId()), _FakeNav(), "http://app.local", max_pages=10,
        racines=["/"], hors_perimetre=crawl._HORS_PERIMETRE_GENERIQUE, relogin=lambda c: None,
        suivre_ancres_hash=True)

    assert set(pages) == {"/"}
    assert onglets["/"] == {"Voir"}
