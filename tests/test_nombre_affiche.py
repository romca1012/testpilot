"""Lot PT-03 — « le nombre affiché pour "<libellé>" vaut "<valeur>" » : une valeur chiffrée se compare comme un NOMBRE avec
son unité, quelle que soit sa nature (monnaie, pourcentage, poids, durée, quantité…).

Mesuré avant ce lot : le seul step disponible (« la valeur affichée pour … est … ») compare du TEXTE. Une application saine
qui écrit « 129.51 EUR » là où la spécification dit « 129,51 € » sortait `non_conforme` — premier test ci-dessous.

Trois niveaux, du moins cher au plus proche du produit :
- le catalogue (suite par défaut) : le step est réservé et exécutable, mais montré à l'agent seulement interrupteur allumé ;
- le helper sur un vrai Chromium (marqueur `conformance`) : chaque issue, dont les refus de conclure ;
- le vrai Behave (marqueur `conformance`) : le VERDICT obtenu — `conforme`, `non_conforme`, `indetermine`, erreur technique.

Falsifiabilité (CLAUDE.md §4) : les tests nommés `falsifiable` prouvent que le step échoue quand l'application affiche un
autre nombre ou une autre devise, et qu'il ne conclut pas quand la devise attendue n'est pas à l'écran.
"""

from __future__ import annotations

import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from testpilot import config
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.generation import interrupteurs, steps_library
from testpilot.verdict import status as st

sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
import _base_helpers as H  # noqa: E402

_LIBELLE_DU_STEP = 'le nombre affiché pour "{libelle}" vaut "{valeur}"'

# Une fiche de paie et un panier, dans des écritures que le texte seul ne sait pas rapprocher de la spécification.
_PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Montants</title></head><body>
<h1>Montants</h1>
<dl>
  <dt>Total TTC</dt><dd>129.51 EUR</dd>
  <dt>Net à payer</dt><dd>412&nbsp;000 F&nbsp;CFA</dd>
  <dt>Taux de TVA</dt><dd>18 %</dd>
  <dt>Brut</dt><dd>500 000</dd>
  <dt>Remise</dt><dd>N/A</dd>
  <dt>Solde</dt><dd>-12,50 €</dd>
  <dt>Plafond</dt><dd>1,234</dd>
  <dt>Prix</dt><dd>12 € 15 €</dd>
  <dt>Acompte</dt><dd>100 Fr.</dd>
  <dt>Poids</dt><dd>1,5 kg</dd>
  <dt>Durée</dt><dd>90 min</dd>
  <dt>Stock</dt><dd>12 pièces</dd>
  <dt>Montant dû</dt><dd>129,51 € TTC</dd>
  <dt>Garantie</dt><dd>12 mois</dd>
  <dt>Chiffre d'affaires</dt><dd>5 k€</dd>
  <dt>Encours</dt><dd>5 HK$</dd>
  <dt>Pression</dt><dd>5 MPa</dd>
  <dt>Taux annuel</dt><dd>5 % annuel</dd>
  <dt>Compteur</dt><dd>(3)</dd>
  <dt>Colis</dt><dd>(12 pièces)</dd>
  <dt>Délai</dt><dd>2 jours</dd>
  <dt>Vitesse</dt><dd>100 km/h</dd>
  <dt>Prix affiché</dt><dd>12 € <s>15 €</s></dd>
  <dt>Tarif horaire</dt><dd>45 $/h</dd>
  <dt>Charge</dt><dd>1.234 kg</dd>
  <dt>Livraison</dt><dd>12 Palettes</dd>
</dl>
<table><tr><th>Poste</th><th>Montant (F CFA)</th></tr><tr><td>Retraite</td><td>28 000</td></tr></table>
</body></html>"""


# ── Le catalogue : réservé et exécutable toujours, montré seulement interrupteur allumé (suite par défaut) ──────────────


def _step_du_catalogue():
    trouves = [s for s in steps_library.catalogue(connector_type="web") if s.label == _LIBELLE_DU_STEP]
    assert len(trouves) == 1, trouves
    return trouves[0]


def test_le_step_est_un_alors_assertif_reserve_et_derriere_son_interrupteur():
    step = _step_du_catalogue()

    assert (step.keyword, step.asserte, step.interrupteur) == ("then", True, interrupteurs.ENV_STEP_NOMBRE)
    assert _LIBELLE_DU_STEP in steps_library.reserved_labels(connector_type="web")


def test_interrupteur_eteint_le_prompt_est_celui_d_avant_le_lot(monkeypatch):
    """Tant que rien n'est mesuré, ce que l'agent reçoit ne change pas d'un caractère."""
    monkeypatch.delenv(interrupteurs.ENV_STEP_NOMBRE, raising=False)
    catalogue = steps_library.catalogue(connector_type="web")
    sans_le_step = [s for s in catalogue if s.label != _LIBELLE_DU_STEP]

    assert steps_library.as_prompt_section(catalogue) == steps_library.as_prompt_section(sans_le_step)
    assert "le nombre affiché" not in steps_library.as_prompt_section(catalogue)


def test_interrupteur_allume_le_step_est_montre_avec_sa_note(monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_STEP_NOMBRE, "1")
    section = steps_library.as_prompt_section(steps_library.catalogue(connector_type="web"))

    assert f"- {_LIBELLE_DU_STEP}" in section and "comparé comme un NOMBRE avec son unité" in section


def test_tout_interrupteur_de_step_est_un_interrupteur_connu():
    """Le nom est écrit dans la bibliothèque (hors du paquet `testpilot`) : il doit exister côté génération."""
    connus = {v for k, v in vars(interrupteurs).items() if k.startswith("ENV_")}
    poses = {s.interrupteur for s in steps_library.catalogue() if s.interrupteur}

    assert poses and poses <= connus


def test_falsifiable_le_registre_des_steps_derriere_un_interrupteur_est_ferme():
    """Un step derrière un interrupteur éteint DISPARAÎT du prompt. Le poser sur un step existant le retirerait à l'agent
    sans qu'aucun test rougisse (revue du 2026-10-13) : la liste est donc fermée, et l'allonger se décide ici."""
    derriere = {s.label for s in steps_library.catalogue() if s.interrupteur}

    # Étape 4, morceau 7 (A89, porteur 2026-10-21) : les deux vérifications « ce que voit le compte du test », montrées à
    # l'IA seulement avec l'écriture par compte (`TESTPILOT_GENERATION_PAR_COMPTE`).
    assert derriere == {_LIBELLE_DU_STEP, "cet utilisateur voit l'enregistrement",
                        "cet utilisateur ne voit pas l'enregistrement"}


# ── Le helper, sur un vrai Chromium ─────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def navigateur():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch()
        yield nav
        nav.close()


@pytest.fixture(autouse=True)
def etat_neuf():
    yield
    H.definir_etat_constat(scenario="", step_type="")


@pytest.fixture
def page(navigateur, monkeypatch):
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 600)
    p = navigateur.new_page()
    p.set_content(_PAGE)
    yield p
    p.close()


@pytest.mark.conformance
def test_mesure_du_defaut_d_avant_le_step_texte_accuse_une_application_saine(page):
    """129.51 EUR EST 129,51 € : le step texte dit le contraire, le step de montant non."""
    with pytest.raises(AssertionError):
        H.valeur_affichee_vaut(page, "Total TTC", "129,51 €")

    H._nombre_affiche_vaut(page, "Total TTC", "129,51 €")


@pytest.mark.conformance
@pytest.mark.parametrize("libelle, attendu", [
    ("Total TTC", "129,51 €"), ("Total TTC", "129.51 EUR"),
    ("Net à payer", "412000 F CFA"), ("Net à payer", "412 000 FCFA"),
    ("Taux de TVA", "18 %"), ("Taux de TVA", "18,0 %"),
    ("Brut", "500 000"), ("Brut", "500000"),
    ("Solde", "-12,50 €"), ("Solde", "(12,50 €)"),
    # Toute valeur n'est pas une somme d'argent : poids, durée, quantité se comparent de la même façon.
    ("Poids", "1,5 kg"), ("Poids", "1500 g"), ("Poids", "1 500 grammes"),
    ("Durée", "90 min"), ("Durée", "1,5 h"),
    ("Stock", "12 pièces"),
    ("Montant dû", "129,51 € TTC"), ("Montant dû", "129.51 EUR TTC"),
    ("Garantie", "12 mois"),
])
def test_le_meme_montant_ecrit_autrement_est_reconnu(page, libelle, attendu):
    H._nombre_affiche_vaut(page, libelle, attendu)


@pytest.mark.conformance
@pytest.mark.parametrize("libelle, attendu, pourquoi", [
    ("Total TTC", "129,50 €", "un centime d'écart"),
    ("Total TTC", "130,81 €", "le défaut « total faux » du banc (+1 %)"),
    ("Total TTC", "129,51 $", "le bon nombre dans une autre devise"),
    ("Net à payer", "412 000 €", "le bon nombre dans une autre devise"),
    ("Net à payer", "412 000 NGN", "une devise que « F CFA » ne peut pas désigner"),
    ("Net à payer", "41 200 XOF", "un zéro de moins"),
    ("Taux de TVA", "18 €", "un taux n'est pas un montant en devise"),
    ("Taux de TVA", "20 %", "un autre taux"),
    ("Solde", "12,50 €", "le signe"),
    ("Remise", "0,00 €", "l'écran n'affiche pas de nombre"),
    ("Brut", "50 000", "un autre nombre, sans devise des deux côtés"),
    ("Poids", "1,6 kg", "un autre poids"),
    ("Poids", "1,5 km", "un poids n'est pas une distance"),
    ("Poids", "1,5 €", "un poids n'est pas un montant"),
    ("Durée", "2 h", "une autre durée, après conversion"),
    ("Stock", "13 pièces", "une autre quantité dans la même unité"),
    ("Total TTC", "130", "sans unité dans l'attendu, mais un autre nombre : une monnaie ne se convertit pas"),
    ("Chiffre d'affaires", "6 k€", "un autre nombre, même mention"),
    ("Chiffre d'affaires", "5 XOF", "une autre monnaie, quelle que soit la mention"),
    ("Taux annuel", "6 % annuel", "un autre taux, même mention"),
    ("Compteur", "4", "ni 3 ni -3"),
    ("Délai", "3 jours", "un autre nombre dans la même unité"),
    ("Vitesse", "30 m/s", "une autre vitesse, bien au-delà de l'arrondi"),
])
def test_falsifiable_un_autre_montant_ou_une_autre_devise_est_un_defaut(page, libelle, attendu, pourquoi):
    with pytest.raises(AssertionError, match=libelle):
        H._nombre_affiche_vaut(page, libelle, attendu)


@pytest.mark.conformance
@pytest.mark.parametrize("libelle, attendu, pourquoi", [
    ("Brut", "500 000 XOF", "le bon nombre, mais aucune devise n'est affichée à côté"),
    ("Brut", "500 000 %", "le bon nombre, mais aucun pourcentage n'est affiché"),
    ("Retraite", "28 000 F CFA", "la devise n'est que dans l'en-tête de la colonne"),
    ("Plafond", "1234", "« 1,234 » : mille deux cent trente-quatre ou un virgule deux cent trente-quatre ?"),
    ("Prix", "12 €", "deux montants à côté du libellé"),
    ("Acompte", "100 CHF", "une notation de devise que le lecteur ne connaît pas"),
    ("Stock", "12 unités", "deux unités que rien ne permet de rapprocher"),
    ("Garantie", "1 an", "mois et années : aucune conversion exacte"),
    ("Brut", "500 kg", "aucune unité à l'écran, et l'attendu en déclare une qui se convertit"),
    ("Montant dû", "129,51 € HT", "le bon montant, mais « TTC » est affiché là où « HT » est attendu"),
    # Décision A24 (« prudent ») : jamais de réussite sans que l'unité soit vérifiée.
    ("Total TTC", "129,51", "l'attendu n'écrit pas d'unité, l'écran affiche des euros"),
    ("Stock", "12", "l'attendu n'écrit pas d'unité, l'écran affiche des pièces"),
    ("Taux de TVA", "18", "l'attendu n'écrit pas d'unité, l'écran affiche un pourcentage"),
    ("Poids", "1500", "l'attendu n'écrit pas d'unité : 1500 grammes, peut-être"),
    ("Net à payer", "412 000 XOF", "« F CFA » ne dit pas s'il s'agit de XOF ou de XAF"),
    ("Net à payer", "412 000 XAF", "« F CFA » ne dit pas s'il s'agit de XOF ou de XAF"),
    ("Montant dû", "129,51 €", "l'écran ajoute « TTC », que l'attendu n'écrit pas"),
    # Deuxième revue du 2026-10-13 : ces sept cas RÉUSSISSAIENT ou accusaient une application saine.
    ("Chiffre d'affaires", "5 €", "« 5 k€ » n'est pas « 5 € » (faux vert reproduit)"),
    ("Chiffre d'affaires", "5 000 €", "« 5 k€ » n'est pas un défaut face à « 5 000 € » (faux rouge reproduit)"),
    ("Encours", "5 USD", "des dollars de Hong Kong ne sont pas des dollars américains (faux vert reproduit)"),
    ("Pression", "5 mPa", "méga et milli : un facteur un milliard (faux vert reproduit)"),
    ("Taux annuel", "5 % mensuel", "le bon taux, pas la bonne période (faux vert reproduit)"),
    ("Taux annuel", "5 %", "l'écran ajoute « annuel », que l'attendu n'écrit pas"),
    ("Compteur", "3", "« (3) » : moins trois, ou trois entre parenthèses ? (faux rouge reproduit)"),
    ("Compteur", "-3", "… et si l'on ne sait pas, on ne peut pas non plus le dire égal à moins trois"),
    ("Tarif horaire", "45 USD/h", "« 45 $/h » peut être en dollars canadiens (faux vert reproduit, troisième revue)"),
    ("Charge", "1234 kg", "« 1.234 kg » : rien ne dit si le point sépare des milliers"),
    ("Livraison", "12 palettes", "« Palettes » et « palettes » : deux écritures que le projet n'a pas déclarées"),
    ("Colis", "12 pièces", "des parenthèses hors d'un montant ne disent pas « négatif » (faux rouge reproduit)"),
    ("Délai", "16 heures", "un jour n'a pas une durée fixe (faux rouge reproduit)"),
    ("Délai", "48 h", "un jour n'a pas une durée fixe (faux vert reproduit)"),
    ("Vitesse", "27,78 m/s", "l'écart tient dans l'arrondi de l'affichage (faux rouge reproduit)"),
])
def test_falsifiable_ce_qui_ne_se_prouve_pas_n_est_ni_un_succes_ni_un_defaut(page, libelle, attendu, pourquoi):
    """Ni `conforme` (la devise ou la lecture n'est pas prouvée) ni `non_conforme` (l'application n'est pas en cause)."""
    with pytest.raises(H.ConstatNonConcluantError, match=libelle):
        H._nombre_affiche_vaut(page, libelle, attendu)


@pytest.mark.conformance
@pytest.mark.parametrize("attendu", ["environ 130", "1,234", "12 € 15 €", "cent euros", "129,51 € %"])
def test_falsifiable_un_montant_attendu_illisible_est_une_erreur_du_test(page, attendu):
    with pytest.raises(H.ConstatInvalideError, match="valeur attendue"):
        H._nombre_affiche_vaut(page, "Total TTC", attendu)


@pytest.mark.conformance
def test_falsifiable_un_libelle_absent_ou_un_montant_vide_est_une_erreur_du_test(page):
    with pytest.raises(H.ElementIntrouvableError):
        H._nombre_affiche_vaut(page, "Total", "129,51 €")           # « Total » seul n'est le libellé d'aucune valeur
    with pytest.raises(H.ConstatInvalideError, match="valeur attendue"):
        H._nombre_affiche_vaut(page, "Total TTC", " ")


@pytest.mark.conformance
def test_falsifiable_deux_valeurs_distinctes_a_cote_du_libelle_ne_sont_pas_lues(page):
    """Un prix et son prix barré : le constat ne choisit pas lequel lire."""
    with pytest.raises((H.ElementIntrouvableError, H.ConstatNonConcluantError)):
        H._nombre_affiche_vaut(page, "Prix affiché", "12 €")
    with pytest.raises((H.ElementIntrouvableError, H.ConstatNonConcluantError)):
        H._nombre_affiche_vaut(page, "Prix affiché", "15 €")


# ── Ce que le PROJET a déclaré (onglet « Valeurs attendues ») : l'écriture des nombres, et aucune monnaie (A38) ─────────


@pytest.fixture
def projet(monkeypatch):
    """Pose ce que le lanceur transmet au sous-processus pour un projet qui a déclaré son écriture des nombres."""
    for nom in ("TESTPILOT_PROJET_DEVISE", "TESTPILOT_PROJET_FORMAT_NOMBRE"):
        monkeypatch.delenv(nom, raising=False)

    def declarer(format_nombre: str = "") -> None:
        monkeypatch.setenv("TESTPILOT_PROJET_FORMAT_NOMBRE", format_nombre)
    return declarer


@pytest.mark.conformance
@pytest.mark.parametrize("libelle, attendu", [
    ("Total TTC", "129,51"), ("Net à payer", "412 000"), ("Montant dû", "129,51"),
])
def test_falsifiable_un_montant_attendu_sans_unite_ne_conclut_jamais(page, projet, monkeypatch, libelle, attendu):
    """A24 et A38 (porteur, 2026-10-15) : le projet ne déclare pas de monnaie. Même une ancienne variable de monnaie laissée
    dans l'environnement du serveur n'est pas lue : le constat demande d'écrire l'unité, il ne conclut ni dans un sens ni
    dans l'autre."""
    projet()
    monkeypatch.setenv("TESTPILOT_PROJET_DEVISE", "EUR")

    with pytest.raises(H.ConstatNonConcluantError, match=libelle):
        H._nombre_affiche_vaut(page, libelle, attendu)


@pytest.mark.conformance
def test_l_ecriture_des_nombres_du_projet_tranche_une_valeur_affichee_ambigue(page, projet):
    """« 1,234 » à l'écran : sans déclaration, l'outil ne conclut pas (liste plus haut) ; avec, il lit comme l'application écrit."""
    projet(format_nombre="espace_virgule")
    H._nombre_affiche_vaut(page, "Plafond", "1,2340")
    with pytest.raises(AssertionError, match="Plafond"):
        H._nombre_affiche_vaut(page, "Plafond", "1234")

    projet(format_nombre="virgule_point")
    H._nombre_affiche_vaut(page, "Plafond", "1234")
    with pytest.raises(AssertionError, match="Plafond"):
        H._nombre_affiche_vaut(page, "Plafond", "1,2340")


@pytest.mark.conformance
def test_les_unites_ajoutees_par_le_projet_se_reconnaissent_sous_leurs_ecritures(page, monkeypatch):
    """Décision du porteur (2026-10-13) : « 12 Palettes » à l'écran, « 12 palettes » attendu. Sans déclaration, pas de verdict
    (liste plus haut) ; une fois l'unité et ses écritures déclarées par le projet, c'est la même unité — sans conversion."""
    monkeypatch.setenv("TESTPILOT_PROJET_UNITES", '[{"nom": "palette", "ecritures": ["palettes", "Palettes"]}]')

    H._nombre_affiche_vaut(page, "Livraison", "12 palettes")
    H._nombre_affiche_vaut(page, "Livraison", "12 palette")
    with pytest.raises(AssertionError, match="Livraison"):
        H._nombre_affiche_vaut(page, "Livraison", "13 palettes")
    for attendu in ("12", "12 cartons", "12 PALETTES"):
        with pytest.raises(H.ConstatNonConcluantError, match="Livraison"):
            H._nombre_affiche_vaut(page, "Livraison", attendu)


@pytest.mark.conformance
def test_falsifiable_une_ecriture_declaree_ne_tranche_que_pour_ses_propres_separateurs(page, projet):
    """Troisième revue (N2) : projet déclaré « 1 234,56 », un champ affiche « 1.234 kg ». L'outil ne devine pas : ni 1234 kg
    (le poids serait validé mille fois trop grand), ni 1,234 kg."""
    projet(format_nombre="espace_virgule")
    for attendu in ("1234 kg", "1,2340 kg"):
        with pytest.raises(H.ConstatNonConcluantError, match="Charge"):
            H._nombre_affiche_vaut(page, "Charge", attendu)

    projet(format_nombre="point_virgule")           # « 1.234,56 » : là, le point est bien déclaré séparateur de milliers
    H._nombre_affiche_vaut(page, "Charge", "1234 kg")
    with pytest.raises(AssertionError, match="Charge"):
        H._nombre_affiche_vaut(page, "Charge", "1,2340 kg")


@pytest.mark.conformance
def test_falsifiable_l_ecriture_du_projet_ne_change_rien_a_ce_qui_se_lit_sans_elle_ni_a_l_attendu(page, projet):
    projet(format_nombre="virgule_point")
    H._nombre_affiche_vaut(page, "Poids", "1,5 kg")              # « 1,5 kg » se lit sans aide : 1,5 — pas 15
    H._nombre_affiche_vaut(page, "Solde", "-12,50 €")
    with pytest.raises(H.ConstatInvalideError, match="valeur attendue"):
        H._nombre_affiche_vaut(page, "Plafond", "1,234")         # l'attendu, lui, doit se lire sans aide


@pytest.mark.conformance
def test_un_total_recalcule_juste_apres_l_action_est_relu(navigateur, monkeypatch):
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 3000)
    p = navigateur.new_page()
    p.set_content("<dl><dt>Total TTC</dt><dd id=t>0,00 €</dd></dl>"
                  "<script>setTimeout(() => { document.getElementById('t').textContent = '129,51 €'; }, 500)</script>")
    try:
        H._nombre_affiche_vaut(p, "Total TTC", "129,51 €")
    finally:
        p.close()


# ── Le verdict, dans le vrai Behave ─────────────────────────────────────────────────────────────────────────────────────


class _Application(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def do_GET(self):
        corps = (_PAGE if self.path.startswith("/montants") else "<html><body><h1>Accueil</h1></body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Application)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


_OK, _DEFAUT, _RIEN = ((st.EXEC_SUCCESS, st.FUNC_CONFORME), (st.EXEC_SUCCESS, st.FUNC_NON_CONFORME), (None, st.FUNC_INDETERMINE))
_SCENARIOS = {
    # titre : (l'Alors, (exécution, fonctionnel) attendus) — le projet ne déclare pas de monnaie (A38, 2026-10-15)
    "le même montant écrit autrement": ('le nombre affiché pour "Total TTC" vaut "129,51 €"', _OK),
    "un centime d'écart": ('le nombre affiché pour "Total TTC" vaut "129,50 €"', _DEFAUT),
    "une autre devise": ('le nombre affiché pour "Net à payer" vaut "412 000 €"', _DEFAUT),
    "la devise attendue n'est pas à l'écran": ('le nombre affiché pour "Brut" vaut "500 000 XOF"', _RIEN),
    "un montant attendu illisible": ('le nombre affiché pour "Total TTC" vaut "environ 130"', (st.EXEC_TECHNICAL_ERROR, None)),
    # Décision A24 : jamais de réussite sans que l'unité soit vérifiée.
    "franc CFA et code de la monnaie": ('le nombre affiché pour "Net à payer" vaut "412 000 XOF"', _RIEN),
    "un attendu sans unité": ('le nombre affiché pour "Net à payer" vaut "412 000"', _RIEN),
    "un attendu sans unité, une autre monnaie à l'écran": ('le nombre affiché pour "Total TTC" vaut "129,51"', _RIEN),
    "un attendu sans unité, une quantité à l'écran": ('le nombre affiché pour "Stock" vaut "12"', _RIEN),
    # Deuxième revue : ces deux scénarios sortaient `conforme`.
    "un multiplicateur à l'écran": ('le nombre affiché pour "Chiffre d\'affaires" vaut "5 €"', _RIEN),
    "une autre mention à l'écran": ('le nombre affiché pour "Taux annuel" vaut "5 % mensuel"', _RIEN),
}


@pytest.mark.conformance
@pytest.mark.parametrize("ancienne_monnaie", ["", "XOF"])
def test_falsifiable_le_verdict_dans_le_vrai_behave(application, ancienne_monnaie):
    """LA GARDE, de bout en bout (lanceur, sous-processus Behave, verdict) : aucun scénario n'est `conforme` sans que le
    nombre ET l'unité soient prouvés. Un nombre ou une devise différents accusent l'application ; une unité non affichée,
    non écrite ou accompagnée d'une mention que l'attendu ne dit pas ne conclut pas ; un attendu illisible est une erreur
    du test. Aucune monnaie du projet (A38) : une ancienne variable `TESTPILOT_PROJET_DEVISE` transmise au sous-processus ne
    change AUCUN verdict (deuxième paramètre)."""
    lignes = ["Fonctionnalité: Montants affichés", ""]
    for titre, (alors, _) in _SCENARIOS.items():
        lignes += [f"  Scénario: {titre}", "    Soit j'accède à la page d'accueil de l'application",
                   '    Quand j\'ouvre la page "/montants.html"', f"    Alors {alors}", ""]
    dossier = Path(tempfile.mkdtemp(prefix="pt03_"))
    (dossier / "montants.feature").write_text("\n".join(lignes), encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": application, "WEB_USER": "", "WEB_PASSWORD": "",
                                      **({"TESTPILOT_PROJET_DEVISE": ancienne_monnaie} if ancienne_monnaie else {})},
                          connector_type="web", generated_dir=dossier)

    outcome = Executor(runner, max_retries=0).execute("montants")

    assert outcome.dry_run_passed, f"le step ne se résout pas : {outcome.error}"
    verdicts = {v.name: v for v in st.derive_verdict(outcome, connector_type="web").scenarios}
    fautes = []
    for titre, (_, (execution, fonctionnel)) in _SCENARIOS.items():
        v = verdicts[titre]
        if fonctionnel != st.FUNC_CONFORME and v.functional_status == st.FUNC_CONFORME:
            fautes.append(f"« {titre} » est `conforme` — FAUX VERT")
        if execution is not None and v.execution_status != execution:
            fautes.append(f"« {titre} » : exécution {v.execution_status}, {execution} attendu ({v.error[:200]})")
        if fonctionnel is not None and v.functional_status != fonctionnel:
            fautes.append(f"« {titre} » : fonctionnel {v.functional_status}, {fonctionnel} attendu ({v.error[:200]})")
    assert not fautes, "\n".join(fautes)
