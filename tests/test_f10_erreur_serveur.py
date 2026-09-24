"""F10 (décision D12, 2026-09-24) — le CODE HTTP du serveur décide, jamais un silence supposé.

Le cas 99 recevait `HTTP 500` (`KeyError: 0`, équipe de support absente) sur `POST /website/form/…` ;
l'outil ne retenait que les corps JSON et concluait « REFUS SILENCIEUX », puis `non_conforme` alors que
son propre message refusait d'accuser. Décision du porteur :

- 5xx sur une action censée réussir → `non_conforme`, cause `erreur_serveur_5xx`, code + message en preuve ;
- 5xx sur une action censée être refusée → `non_conforme` aussi, avec la note « ce n'est PAS le refus
  attendu » ;
- ni réponse HTTP d'erreur, ni JSON, ni message affiché → `indetermine`, cause `refus_non_explique`,
  jamais réparé automatiquement.

Chaque branche est prouvée par le cas inverse : c'est ce qui en fait une garde.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "behave_runtime" / "steps_library"))

import _base_helpers as H  # noqa: E402

from testpilot.execution.behave_result import BehaveFailure  # noqa: E402
from testpilot.guardrails.repair_circuit import CircuitState, evaluate  # noqa: E402
from testpilot.verdict import defect_origin as do  # noqa: E402
from testpilot.verdict import defect_taxonomy as dt  # noqa: E402
from testpilot.verdict import status as st  # noqa: E402

MODEL = "helpdesk.ticket"
MESSAGE_ODOO = "An error has occured, the form has not been sent."


# ── Doublures ────────────────────────────────────────────────────────────────────────────────

class _Modele:
    def search_count(self, _):
        return 100

    def with_context(self, **_kw):
        return self

    def search(self, *a, **k):
        return []


class _Env(dict):
    def __getitem__(self, k):
        return self.setdefault(k, _Modele())


class _Element:
    def __init__(self, texte):
        self._texte = texte

    def is_visible(self):
        return True

    def inner_text(self):
        return self._texte


class _Page:
    """Aucun champ invalide natif ; un message d'erreur affiché sous `selecteur_visible`, s'il y en a."""

    def __init__(self, texte="", selecteur_visible="#s_website_form_result.text-danger"):
        self._texte, self._sel = texte, selecteur_visible

    def evaluate(self, *a, **k):
        return []

    def locator(self, selecteur, *a, **k):
        present = bool(self._texte) and selecteur == self._sel
        element = _Element(self._texte)

        class _L:
            def count(self_inner):
                return 1 if present else 0

            def nth(self_inner, i):
                return element
        return _L()


class _Context:
    def __init__(self, *, reponses=(), json=None, page=None):
        self.page = page or _Page()
        self.odoo = type("O", (), {"env": _Env()})()
        self._initial_count_helpdesk_ticket = 100
        self._initial_max_id_helpdesk_ticket = 100
        self.reponses_formulaire = list(reponses)
        self.reponse_formulaire = json


def _r(status):
    return {"status": status, "url": "http://x/website/form/helpdesk.ticket"}


@pytest.fixture(autouse=True)
def _rapide(monkeypatch):
    monkeypatch.setattr(H, "COUNT_SETTLE_TIMEOUT", 0.01, raising=False)


# ── 5xx sur une action censée RÉUSSIR ────────────────────────────────────────────────────────

def test_un_5xx_sans_json_est_une_erreur_serveur_avec_son_code_pour_preuve():
    """Le cas 99 : corps HTML 500, aucun JSON capté, message générique affiché par la page."""
    ctx = _Context(reponses=[_r(500)], page=_Page(MESSAGE_ODOO))

    with pytest.raises(H.ErreurServeur5xxError) as err:
        H.check_count_increased_by_one(ctx, MODEL)

    message = str(err.value)
    assert not isinstance(err.value, AssertionError)
    assert "HTTP 500" in message and MESSAGE_ODOO in message
    assert "aurait dû aboutir" in message and "REFUS" not in message
    assert "depuis id > 100" in message, "le constat de comptage cloisonné reste en tête"


def test_un_5xx_prime_sur_un_refus_serveur_generique_mais_pas_sur_des_champs_nommes():
    generique = _Context(reponses=[_r(500)], json={"error": "Enregistrement impossible"})
    with pytest.raises(H.ErreurServeur5xxError):
        H.check_count_increased_by_one(generique, MODEL)

    # Le serveur a NOMMÉ nos champs : c'est notre donnée (donnee_invalide), l'app n'est pas en cause.
    champs = _Context(reponses=[_r(500)], json={"error_fields": ["code_client1"]})
    with pytest.raises(H.DonneeRefuseeError):
        H.check_count_increased_by_one(champs, MODEL)


def test_un_200_avec_un_message_affiche_reste_le_constat_d_avant_pas_un_5xx():
    ctx = _Context(reponses=[_r(200)], page=_Page("Format invalide", ".alert-danger"))

    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, MODEL)

    assert not isinstance(err.value, (H.ErreurServeur5xxError, H.RefusNonExpliqueError))
    assert "L'APPLICATION A REFUSÉ la soumission et l'affiche" in str(err.value)


def test_un_4xx_sans_json_ni_message_reste_une_assertion_avec_le_code_http():
    """Le serveur a DIT quelque chose (HTTP 403) : ce n'est pas un silence."""
    ctx = _Context(reponses=[_r(403)])

    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, MODEL)

    assert not isinstance(err.value, (H.ErreurServeur5xxError, H.RefusNonExpliqueError))
    assert "HTTP 403 reçu sur la soumission" in str(err.value)


# ── Silence total : indéterminé, jamais un défaut ────────────────────────────────────────────

@pytest.mark.parametrize("reponses", [[], [_r(200)], [_r(302)]])
def test_aucune_reponse_d_erreur_ni_message_ni_json_est_un_refus_non_explique(reponses):
    """Un 200/302 sans corps exploitable n'explique rien : silence total."""
    ctx = _Context(reponses=reponses)

    with pytest.raises(H.RefusNonExpliqueError) as err:
        H.check_count_increased_by_one(ctx, MODEL)

    assert not isinstance(err.value, AssertionError)
    assert "REFUS NON EXPLIQUÉ" in str(err.value)


def test_un_message_affiche_suffit_a_sortir_du_silence():
    ctx = _Context(page=_Page("Erreur", ".alert-danger"))

    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, MODEL)

    assert not isinstance(err.value, H.RefusNonExpliqueError)


# ── 5xx sur une action censée être REFUSÉE ───────────────────────────────────────────────────

def test_un_5xx_sur_un_scenario_negatif_n_est_pas_le_refus_attendu():
    ctx = _Context(reponses=[_r(200), _r(500)], page=_Page(MESSAGE_ODOO))

    with pytest.raises(H.ErreurServeur5xxError) as err:
        H.check_count_not_increased(ctx, MODEL)

    assert "HTTP 500" in str(err.value)
    assert "attendait un REFUS" in str(err.value)
    assert "ce n'est PAS le refus attendu" in str(err.value)


def test_un_refus_propre_sur_un_scenario_negatif_passe_toujours():
    """Non-régression : 200 (validation JSON) ou aucune réponse → le négatif réussit comme avant."""
    H.check_count_not_increased(_Context(reponses=[_r(200)]), MODEL)
    H.check_count_not_increased(_Context(), MODEL)
    H.check_count_not_increased(_Context(reponses=[_r(400)]), MODEL)  # un 4xx est un refus propre


# ── Classement : verdict, origine, réparation ────────────────────────────────────────────────

def _echec(brut):
    return BehaveFailure("s", "", "unknown", "", raw=brut, step_type="then")


def test_les_exceptions_dediees_sont_classees_au_type():
    assert dt.classify_failure(_echec(
        "Traceback\nErreurServeur5xxError: LE SERVEUR A PLANTÉ (HTTP 500)")) == dt.ERREUR_SERVEUR_5XX
    assert dt.classify_failure(_echec(
        "Traceback\nRefusNonExpliqueError: REFUS NON EXPLIQUÉ")) == dt.REFUS_NON_EXPLIQUE
    assert dt.LABELS[dt.ERREUR_SERVEUR_5XX] == "Erreur interne du serveur (HTTP 5xx)"
    assert dt.LABELS[dt.REFUS_NON_EXPLIQUE] == "Refus non expliqué (à instruire)"


def test_le_5xx_est_non_conforme_et_le_silence_indetermine():
    from testpilot.execution.behave_result import BehaveResult, BehaveScenario
    from testpilot.execution.executor import ExecutionOutcome

    def verdict(brut):
        real = BehaveResult(success=False, returncode=1,
                            scenarios=[BehaveScenario("s", "failed", error="e")],
                            failures=[_echec(brut)])
        return st.derive_verdict(ExecutionOutcome(module_name="m", dry_run_passed=True, real_run=real))

    plante = verdict("ErreurServeur5xxError: LE SERVEUR A PLANTÉ (HTTP 500)")
    silence = verdict("RefusNonExpliqueError: REFUS NON EXPLIQUÉ")

    assert (plante.execution_status, plante.functional_status) == (st.EXEC_SUCCESS, st.FUNC_NON_CONFORME)
    assert st.statut_de_test(plante.execution_status, plante.functional_status) == st.STATUT_FAILED
    assert (silence.execution_status, silence.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)
    assert st.statut_de_test(silence.execution_status, silence.functional_status) == st.STATUT_RETEST


def test_ni_l_un_ni_l_autre_ne_sont_jamais_envoyes_en_reparation_automatique():
    for cause, origine in ((dt.ERREUR_SERVEUR_5XX, do.VRAI_BUG), (dt.REFUS_NON_EXPLIQUE, do.INDETERMINE)):
        assert do.classify_defect_origin(cause) == origine
    for brut in ("ErreurServeur5xxError: HTTP 500", "RefusNonExpliqueError: silence"):
        decision = evaluate(CircuitState(max_iterations=5, stall_limit=3), [_echec(brut)])
        assert decision.should_continue is False, brut


# ── La capture (environment.py) ──────────────────────────────────────────────────────────────

def _charger_environment():
    spec = importlib.util.spec_from_file_location("environment_f10", RACINE / "behave_runtime" / "environment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Reponse:
    def __init__(self, url, status, corps=None):
        self.url, self.status, self._corps = url, status, corps

    def json(self):
        if self._corps is None:
            raise ValueError("corps HTML")
        return self._corps


class _PageEcoute:
    def __init__(self):
        self.gestionnaire = None

    def on(self, evenement, gestionnaire):
        assert evenement == "response"
        self.gestionnaire = gestionnaire


def test_la_capture_garde_le_code_http_meme_quand_le_corps_n_est_pas_du_json():
    environment = _charger_environment()
    contexte = type("C", (), {})()
    contexte.page = _PageEcoute()
    environment._capturer_reponse_formulaire(contexte)

    contexte.page.gestionnaire(_Reponse("http://x/web/webclient/version_info", 200, {"a": 1}))  # ignorée
    contexte.page.gestionnaire(_Reponse("http://x/website/form/helpdesk.ticket", 500))            # HTML
    contexte.page.gestionnaire(_Reponse("http://x/website/form/helpdesk.ticket", 200, {"id": 7}))

    assert [r["status"] for r in contexte.reponses_formulaire] == [500, 200]
    assert contexte.reponse_formulaire == {"id": 7}, "le comportement JSON d'avant est inchangé"


def test_le_5xx_html_ne_pose_aucun_json_mais_garde_sa_trace():
    environment = _charger_environment()
    contexte = type("C", (), {})()
    contexte.page = _PageEcoute()
    environment._capturer_reponse_formulaire(contexte)

    contexte.page.gestionnaire(_Reponse("http://x/website/form/helpdesk.ticket", 500))

    assert contexte.reponse_formulaire is None
    (trace,) = contexte.reponses_formulaire
    assert (trace["status"], trace["url"]) == (500, "http://x/website/form/helpdesk.ticket")
    assert isinstance(trace["t"], float), "horodatage monotone, pour ne juger que l'action testée"


def test_un_5xx_html_efface_le_json_perime_d_une_soumission_precedente():
    """Sans cela, un `error_fields` ancien l'emporterait sur un 5xx plus récent (revue du lot 02)."""
    environment = _charger_environment()
    contexte = type("C", (), {})()
    contexte.page = _PageEcoute()
    environment._capturer_reponse_formulaire(contexte)

    contexte.page.gestionnaire(_Reponse("http://x/website/form/helpdesk.ticket", 200,
                                        {"error_fields": ["code_client1"]}))
    contexte.page.gestionnaire(_Reponse("http://x/website/form/helpdesk.ticket", 500))

    assert contexte.reponse_formulaire is None


def test_le_message_rouge_d_odoo_est_dans_les_selecteurs_surveilles():
    assert "#s_website_form_result.text-danger" in H._SELECTEURS_ERREUR


# ── Navigateur RÉEL : le code HTTP et le message rouge sont vraiment vus ─────────────────────

@pytest.mark.conformance
def test_reel_un_500_html_est_capte_avec_son_code_et_le_message_rouge_est_lu():
    """Reproduit la forme du cas 99 : `POST /website/form/…` → HTTP 500 corps HTML, et la page affiche
    « An error has occured… » dans `<span id="s_website_form_result" class="text-danger">`."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from playwright.sync_api import sync_playwright

    page_html = (
        "<html><body><form id='f'><input name='x'></form><div id='zone'></div><script>"
        "fetch('/website/form/helpdesk.ticket',{method:'POST',body:'x'}).then(function(r){"
        "if(!r.ok){document.getElementById('zone').innerHTML="
        "'<span id=\"s_website_form_result\" class=\"text-danger ml8\">MESSAGE</span>';}});"
        "</script></body></html>").replace("MESSAGE", MESSAGE_ODOO)

    class Appli(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page_html.encode())

        def do_POST(self):
            self.send_response(500)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body>500: Internal Server Error</body></html>")

    serveur = HTTPServer(("127.0.0.1", 0), Appli)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    environment = _charger_environment()
    try:
        with sync_playwright() as p:
            navigateur = p.chromium.launch(headless=True)
            page = navigateur.new_context().new_page()
            contexte = type("C", (), {})()
            contexte.page = page
            environment._capturer_reponse_formulaire(contexte)

            page.goto(f"http://127.0.0.1:{serveur.server_port}/")
            page.wait_for_selector("#s_website_form_result", timeout=5000)
            texte = H._texte_erreur_visible(page)
            navigateur.close()
    finally:
        serveur.shutdown()

    assert [r["status"] for r in contexte.reponses_formulaire] == [500]
    assert contexte.reponse_formulaire is None
    assert texte == MESSAGE_ODOO


# ── Revue du lot 02 : délimiter l'action testée, ne conclure au silence que si on a PU observer ──

def test_un_5xx_ancien_suivi_d_un_refus_propre_n_est_pas_l_action_testee_en_positif():
    """La dernière soumission est celle qu'on juge : son refus JSON générique reste le constat expliqué
    de l'arbitrage du 2026-07-23, pas un plantage serveur."""
    ctx = _Context(reponses=[_r(500), _r(200)], json={"error": "Contrainte métier violée"})

    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, MODEL)

    assert not isinstance(err.value, (H.ErreurServeur5xxError, H.RefusNonExpliqueError))
    assert "LE SERVEUR A REFUSÉ" in str(err.value)


def test_en_scenario_negatif_un_5xx_sur_n_importe_quelle_soumission_est_un_plantage():
    """Chaque soumission d'un négatif était censée être refusée PROPREMENT : un 5xx, même ancien, est
    un plantage serveur (ordre `[500, 200]` comme `[200, 500]`)."""
    for reponses in ([_r(500), _r(200)], [_r(200), _r(500)]):
        with pytest.raises(H.ErreurServeur5xxError):
            H.check_count_not_increased(_Context(reponses=reponses), MODEL)


def test_une_reponse_anterieure_au_releve_de_comptage_est_ignoree():
    import time

    ctx = _Context(reponses=[{"status": 500, "url": "u", "t": 100.0}])
    ctx._tp_releve_t = time.monotonic()  # le relevé date d'APRÈS ce 5xx

    with pytest.raises(H.RefusNonExpliqueError):  # plus aucun signal : silence total
        H.check_count_increased_by_one(ctx, MODEL)
    H.check_count_not_increased(ctx, MODEL)  # et un négatif ne le retient pas non plus


def test_sans_page_le_silence_n_est_pas_un_refus_non_explique():
    """Un scénario RPC seul n'a rien pu observer : on garde le constat d'avant (non_conforme), on ne
    fabrique pas un `indetermine` par défaut de mesure."""
    ctx = _Context()
    ctx.page = None

    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, MODEL)

    assert not isinstance(err.value, (H.RefusNonExpliqueError, H.ErreurServeur5xxError))


def test_une_page_dont_la_lecture_plante_n_est_pas_un_silence_observe():
    class _PageQuiPlante(_Page):
        def locator(self, *a, **k):
            raise RuntimeError("navigateur mort")

    ctx = _Context(page=_PageQuiPlante())

    with pytest.raises(AssertionError) as err:
        H.check_count_increased_by_one(ctx, MODEL)

    assert not isinstance(err.value, H.RefusNonExpliqueError)
    assert "indisponible" in str(err.value)
