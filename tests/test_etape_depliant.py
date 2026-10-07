"""Étape « bloc dépliant » du chemin de connexion (2026-10-07).

Cas réel : la page de connexion du portail d'intégration Odoo cache son formulaire derrière un
`<details><summary>Connexion externe par email</summary>`. Le clic sur ce `<summary>` n'était pas
enregistrable (aucun rôle rejouable) : la séquence enregistrée ne pouvait jamais rouvrir le
formulaire, et le rejeu butait sur des champs invisibles.

Capture (`accname.calculer`) et rejeu (`_web_helpers.localiser_etape`) sont deux implémentations
distinctes : ces tests prouvent, dans un VRAI Chromium, que ce que l'une capture l'autre le retrouve.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from testpilot.connectors import _web_helpers as helpers
from testpilot.connectors._web_helpers import (
    SequenceConnexionObsoleteError,
    localiser_etape,
    rejouer_sequence_connexion,
)
from testpilot.generation import accname

_PAGE = """<!doctype html><html><body>
<details id="d"><summary>Connexion externe par email</summary>
  <input type="text" aria-label="Email"><input type="password" aria-label="Mot de passe">
</details>
<details><summary>Connexion externe par email pro</summary><p>autre bloc</p></details>
</body></html>"""


def test_le_jeton_du_rejeu_est_celui_de_la_capture():
    """Dupliqué entre `accname` (capture) et `_web_helpers` (rejeu, tourne aussi dans Behave) :
    s'ils divergeaient, une étape capturée ne serait plus jamais rejouée comme un dépliant."""
    assert helpers.ROLE_DEPLIANT == accname.ROLE_DEPLIANT == "summary"


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        navigateur = p.chromium.launch(headless=True)
        pg = navigateur.new_context().new_page()
        yield pg
        navigateur.close()


def _champ_mdp_visible(page) -> bool:
    return page.get_by_label("Mot de passe").is_visible()


@pytest.mark.conformance
def test_capture_puis_rejeu_ouvrent_le_formulaire_cache(page):
    page.set_content(_PAGE)
    boite = page.locator("details#d > summary").bounding_box()
    capture = accname.calculer(page, boite["x"] + boite["width"] / 2, boite["y"] + boite["height"] / 2)
    assert capture == {"role": "summary", "name": "Connexion externe par email"}

    page.set_content(_PAGE)  # page neuve, comme au rejeu
    assert not _champ_mdp_visible(page)
    assert rejouer_sequence_connexion(page, [capture], attendre_reseau=False) is True

    assert _champ_mdp_visible(page)  # falsifiable : sans l'étape, le champ reste invisible


@pytest.mark.conformance
def test_le_rejeu_exige_le_texte_exact_pas_une_sous_chaine(page):
    """« Connexion externe par email » est une sous-chaîne de « … pro » : le rejeu ne doit viser que
    le bloc dont le texte est exactement le nom enregistré — jamais le premier qui y ressemble."""
    page.set_content(_PAGE)

    assert localiser_etape(page, "summary", "Connexion externe par email").count() == 1
    assert localiser_etape(page, "summary", "Connexion externe").count() == 0


@pytest.mark.conformance
def test_un_bloc_renomme_arrete_le_rejeu_au_lieu_de_cliquer_ailleurs(page):
    page.set_content(_PAGE)

    with pytest.raises(SequenceConnexionObsoleteError):
        rejouer_sequence_connexion(
            page, [{"role": "summary", "name": "Connexion par mot de passe"}],
            timeout_ms=800, attendre_reseau=False)
    assert not _champ_mdp_visible(page)


@pytest.mark.conformance
def test_les_blancs_du_dom_ne_changent_pas_la_correspondance(page):
    page.set_content('<details><summary>\n   Connexion\n   externe  </summary>'
                     '<input aria-label="Mot de passe" type="password"></details>')

    rejouer_sequence_connexion(page, [{"role": "summary", "name": "Connexion externe"}],
                               attendre_reseau=False)

    assert _champ_mdp_visible(page)


# ── Rejeu avant la fin de l'initialisation de la page (2026-10-07) ─────────────────────────────
# Même mécanique que le portail d'intégration Odoo : un clic envoyé tant que le JavaScript de la
# page n'a pas fini son initialisation est annulé (le bloc s'ouvre puis la page le referme).

import http.server  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

_PAGE_INIT_TARDIVE = b"""<!doctype html><html><body>
<details id="d"><summary>Connexion externe par email</summary>
  <input type="text" aria-label="Email"><input type="password" aria-label="Mot de passe">
</details>
<style>details > :not(summary) { display: none } details.pret[open] > :not(summary) { display: block }</style>
<script>
fetch('/init').then(() => {            // l'initialisation de la page arrive APRES un appel lent
  const d = document.getElementById('d');
  d.open = false;                       // elle referme le bloc qu'un clic trop precoce aurait ouvert
  d.classList.add('pret');
});
</script></body></html>"""


class _HandlerInit(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_a):
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/init":
            time.sleep(1.2)
            corps, type_ = b"ok", "text/plain"
        else:
            corps, type_ = _PAGE_INIT_TARDIVE, "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", type_)
        self.end_headers()
        self.wfile.write(corps)


@pytest.mark.conformance
def test_le_rejeu_attend_la_fin_de_l_initialisation_avant_le_premier_clic(page):
    serveur = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _HandlerInit)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    try:
        page.goto(f"http://127.0.0.1:{serveur.server_address[1]}/", wait_until="domcontentloaded")

        rejouer_sequence_connexion(
            page, [{"role": "summary", "name": "Connexion externe par email"}],
            attendre_reseau=False)
        page.wait_for_timeout(300)

        # Falsifiable : sans l'attente préalable, le clic tombe avant `/init`, le bloc est refermé
        # par la page et le champ reste invisible.
        assert page.get_by_label("Mot de passe").is_visible()
    finally:
        serveur.shutdown()


def test_la_stabilisation_prealable_est_bornee_et_son_timeout_n_empeche_pas_le_rejeu():
    from playwright.sync_api import TimeoutError as PWTimeout

    appels: list[str] = []

    class _Loc:
        def click(self, **_kw):
            appels.append("clic")

    class _Page:
        url = "https://exemple.test/"

        def wait_for_load_state(self, etat, timeout=None):
            appels.append(f"stabilisation:{etat}:{timeout}")
            raise PWTimeout("jamais idle")

        def get_by_role(self, *_a, **_kw):
            return _Loc()

        def wait_for_timeout(self, _ms):
            pass

    rejouer_sequence_connexion(_Page(), [{"role": "button", "name": "Continuer"}], attendre_reseau=False)

    assert appels == [f"stabilisation:networkidle:{helpers._STABILISATION_AVANT_PREMIER_CLIC_MS}", "clic"]


@pytest.mark.conformance
def test_un_bloc_cache_homonyme_ne_rend_pas_le_rejeu_ambigu(page):
    page.set_content('<details style="display:none"><summary>Connexion externe</summary>'
                     '<input aria-label="Mot de passe" type="password"></details>'
                     '<details><summary>Connexion externe</summary>'
                     '<input aria-label="Mot de passe" type="password"></details>')

    assert localiser_etape(page, "summary", "Connexion externe").count() == 1


def test_une_autre_erreur_que_le_timeout_remonte_pendant_la_stabilisation():
    """Seul le timeout Playwright est toléré : une page morte ne doit pas être masquée."""
    class _Page:
        def wait_for_load_state(self, *_a, **_kw):
            raise RuntimeError("page fermée")

    with pytest.raises(RuntimeError):
        helpers._laisser_la_page_se_stabiliser(_Page())
