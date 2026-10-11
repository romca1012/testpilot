"""Lot VH-06 (T3, T8) — les steps qui manquaient, chacun avec sa preuve de falsifiabilité.

Mesuré (banc base-3 à base-5) : faute de step partagé, l'agent écrivait du Playwright à la main pour « mettre la quantité de
la ligne "Câble HDMI" à 0 », « le total affiché est 129,51 € », « un numéro de commande CMD-… » — la première source d'erreur
technique après génération. Ici, sur un vrai Chromium (marqueur `conformance`) : chaque step réussit sur la bonne page ET
échoue quand l'application affiche autre chose ou que le test est mal posé.

La relecture du 2026-10-11 a reproduit sept faux verts et un faux rouge dans la première version de ces steps : chacun a ici
son test, nommé `falsifiable`, qui échoue sur le code d'avant la correction.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402

_PAGES = Path(__file__).resolve().parent / "fixtures" / "torture_app"


@pytest.fixture(scope="module")
def navigateur():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch()
        yield nav
        nav.close()


@pytest.fixture(autouse=True)
def etat_neuf():
    H._ETAT_RELEVES.update(jetons_a_substituer=0, actions=0, step_compte=False)
    yield
    H._ETAT_RELEVES.update(jetons_a_substituer=0, actions=0, step_compte=False)
    H.definir_etat_constat(scenario="", step_type="")


@pytest.fixture
def page(navigateur, monkeypatch):
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 800)
    p = navigateur.new_page()
    p.set_content((_PAGES / "panier.html").read_text(encoding="utf-8"))
    yield p
    p.close()


@pytest.fixture
def page_de(navigateur, monkeypatch):
    """Une page au contenu donné — pour les balisages que la relecture a trouvés mal lus."""
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 800)
    ouvertes = []

    def ouvrir(corps: str):
        p = navigateur.new_page()
        p.set_content(f"<html><body>{corps}</body></html>")
        ouvertes.append(p)
        return p

    yield ouvrir
    for p in ouvertes:
        p.close()


def _valeurs(page) -> list[str]:
    return page.locator("table input").evaluate_all("els => els.map(e => e.value)")


# ── Saisir dans la ligne contenant … ──────────────────────────────────────────────────────────────────────


@pytest.mark.conformance
@pytest.mark.parametrize("champ", ["Quantité", "quantite", "Quantité de Câble HDMI"])
def test_la_saisie_vise_la_ligne_demandee_et_elle_seule(page, champ):
    H.saisir_dans_ligne(page, champ, "5", "Câble HDMI")

    assert _valeurs(page) == ["5", "1", "3"]


@pytest.mark.conformance
def test_la_saisie_dans_une_carte_hors_tableau(page):
    H.saisir_dans_ligne(page, "Remise", "10", "Tapis de souris")

    assert page.locator("[name=remise]").input_value() == "10"


@pytest.mark.conformance
def test_falsifiable_une_ligne_ambigue_ou_absente_est_une_erreur_jamais_la_premiere(page):
    with pytest.raises(H.ElementIntrouvableError, match="ambigu"):
        H.saisir_dans_ligne(page, "Quantité", "5", "Câble")          # « Câble HDMI » et « Câble USB »
    with pytest.raises(H.ElementIntrouvableError):
        H.saisir_dans_ligne(page, "Quantité", "5", "Clavier")
    with pytest.raises(H.ElementIntrouvableError, match="Aucun champ"):
        H.saisir_dans_ligne(page, "Prix", "5", "Câble HDMI")
    assert _valeurs(page) == ["2", "1", "3"], "rien n'a été saisi au hasard"


@pytest.mark.conformance
@pytest.mark.parametrize("texte", ["Total HT", "Panier"])
def test_falsifiable_un_texte_hors_de_toute_ligne_n_ecrit_pas_dans_le_champ_le_plus_proche(page, texte):
    """Relecture : « Remise » était renseigné pour « Total HT » et pour « Panier » — le plus proche ancêtre à champ était la page."""
    with pytest.raises(H.ElementIntrouvableError):
        H.saisir_dans_ligne(page, "Remise", "7", texte)

    assert page.locator("[name=remise]").input_value() == "0" and _valeurs(page) == ["2", "1", "3"]


_LIGNES_SANS_CHAMP = {
    "tableau": '<table><tr><td>Câble HDMI</td><td>épuisé</td></tr>'
               '<tr><td>Souris</td><td><input name="quantite" aria-label="Quantité" value="1"></td></tr></table>',
    "liste": '<ul><li>Carte cadeau</li><li>Câble HDMI <label>Quantité <input name="quantite" value="1"></label></li></ul>',
    "cartes voisines": '<div class="cartes"><div class="carte">Carte cadeau</div>'
                       '<div class="carte"><span>Câble HDMI</span> <label>Quantité <input name="quantite" value="1"></label></div></div>',
    "autre casse et morceau": '<table><tr><td>Rallonge câble hdmi 5 m</td>'
                              '<td><input name="quantite" aria-label="Quantité" value="1"></td></tr></table>',
}


@pytest.mark.conformance
@pytest.mark.parametrize("cas, texte", [("tableau", "Câble HDMI"), ("liste", "Carte cadeau"), ("cartes voisines", "Carte cadeau"),
                                        ("autre casse et morceau", "Câble HDMI")])
def test_falsifiable_la_ligne_demandee_sans_champ_ne_modifie_pas_la_ligne_voisine(page_de, cas, texte):
    """Relecture, reproduit : la quantité d'un AUTRE produit était modifiée sans erreur."""
    p = page_de(_LIGNES_SANS_CHAMP[cas])

    with pytest.raises(H.ElementIntrouvableError):
        H.saisir_dans_ligne(p, "Quantité", "0", texte)

    assert p.locator("[name=quantite]").input_value() == "1"


@pytest.mark.conformance
def test_une_carte_sans_balisage_de_ligne_reste_servie(page_de):
    p = page_de('<div class="cartes"><div class="carte"><h3>Stylo bleu</h3><label>Quantité <input name="q1" value="1"></label></div>'
                '<div class="carte"><h3>Stylo rouge</h3><label>Quantité <input name="q2" value="1"></label></div></div>'
                '<div class="ligne"><div class="nom">Gomme</div><div class="saisie"><input name="q3" aria-label="Quantité" value="1"></div></div>')

    H.saisir_dans_ligne(p, "Quantité", "4", "Stylo rouge")
    H.saisir_dans_ligne(p, "Quantité", "6", "Gomme")

    assert [p.locator(f"[name={n}]").input_value() for n in ("q1", "q2", "q3")] == ["1", "4", "6"]


# ── La valeur affichée à côté d'un libellé ────────────────────────────────────────────────────────────────


@pytest.mark.conformance
@pytest.mark.parametrize("libelle, valeur", [
    ("Total TTC", "129,51 €"),       # terme / définition
    ("Référence", "REF-77"),         # élément voisin, deux-points
    ("Statut", "En attente"),        # même texte, après « : »
    ("Remise", "0"),                 # libellé d'un champ
])
def test_la_valeur_a_cote_d_un_libelle_est_lue(page, libelle, valeur):
    H.valeur_affichee_vaut(page, libelle, valeur)


@pytest.mark.conformance
@pytest.mark.parametrize("corps, libelle, valeur", [
    ('<table><tr><td><strong>Montant dû</strong></td><td>42,00 €</td></tr></table>', "Montant dû", "42,00 €"),
    ('<div><span>Montant dû</span></div><div>42,00 €</div>', "Montant dû", "42,00 €"),
    ('<p>Numéro de dossier : <strong>DOS-0001</strong></p>', "Numéro de dossier", "DOS-0001"),
    ('<p><span>Statut :</span> Validée <a href="#">Modifier</a></p>', "Statut", "Validée"),
    ('<table><tr><th>Montant dû</th><td>42,00 €</td></tr></table>', "Montant dû", "42,00 €"),      # en-tête de LIGNE
    ('<label>Pays <select><option>France</option><option selected>Belgique</option></select></label>', "Pays", "Belgique"),
])
def test_les_balisages_courants_sont_lus(page_de, corps, libelle, valeur):
    """Relecture : les trois premiers n'étaient pas lus (dont la page de confirmation du banc), le quatrième rendait « Modifier »."""
    H.valeur_affichee_vaut(page_de(corps), libelle, valeur)


@pytest.mark.conformance
@pytest.mark.parametrize("attendu", ["107,92 €", "129,51", "29,51 €"])
def test_falsifiable_une_autre_valeur_ou_un_morceau_echoue(page, attendu):
    """« 107,92 € » est affiché sur la page (Total HT) : « la page affiche le texte » passerait — pas ici."""
    with pytest.raises(AssertionError, match="Total TTC"):
        H.valeur_affichee_vaut(page, "Total TTC", attendu)


@pytest.mark.conformance
def test_falsifiable_un_libelle_inconnu_est_une_erreur_du_test(page):
    with pytest.raises(H.ElementIntrouvableError):
        H.valeur_affichee_vaut(page, "Total", "129,51 €")           # « Total » seul n'est le libellé d'aucune valeur


@pytest.mark.conformance
@pytest.mark.parametrize("corps", [
    '<table><thead><tr><th scope="col">Numéro</th><th scope="col">Montant</th></tr></thead>'
    '<tbody><tr><td>DOS-1</td><td>42,00 €</td></tr></tbody></table>',
    '<table><tr><th>Numéro</th><th>Montant</th></tr><tr><td>DOS-1</td><td>42,00 €</td></tr></table>',
    '<table><tr><th><span>Numéro</span></th><th>Montant</th></tr><tr><td>DOS-1</td><td>42,00 €</td></tr></table>',
])
def test_falsifiable_un_en_tete_de_colonne_n_a_pas_de_valeur_a_cote(page_de, corps):
    """Relecture, reproduit sur la page du banc : « Numéro » rendait l'en-tête voisin — relevé puis « retrouvé » sur la page."""
    p = page_de(corps)

    with pytest.raises(H.ElementIntrouvableError):
        H.lire_valeur_affichee(p, "Numéro")
    with pytest.raises(H.ElementIntrouvableError):
        H.valeur_affichee_vaut(p, "Numéro", "Montant")


@pytest.mark.conformance
@pytest.mark.parametrize("champ", ['<input type="checkbox">', '<input type="checkbox" checked>', '<input type="radio" value="oui">',
                                   '<input type="file">', '<input type="password" value="secret">'])
def test_falsifiable_une_case_ou_un_bouton_radio_n_affiche_pas_sa_valeur(page_de, champ):
    """Relecture : `value` y vaut « on » quel que soit l'état — « est "on" » sortait `conforme`, case cochée ou non."""
    p = page_de(f"<label>Lettre d'information {champ}</label>")

    with pytest.raises(H.ElementIntrouvableError):
        H.valeur_affichee_vaut(p, "Lettre d'information", "on")


@pytest.mark.conformance
def test_falsifiable_une_valeur_cachee_ou_deux_valeurs_differentes_ne_se_lisent_pas(page_de):
    cachee = page_de('<dl><dt>Montant dû</dt><dd style="display:none">42,00 €</dd></dl>')
    double = page_de('<dl><dt>Montant dû</dt><dd>42,00 €</dd></dl><p>Montant dû : 40,00 €</p>')

    with pytest.raises(H.ElementIntrouvableError):
        H.valeur_affichee_vaut(cachee, "Montant dû", "42,00 €")
    with pytest.raises(H.ElementIntrouvableError, match="ambigu"):
        H.valeur_affichee_vaut(double, "Montant dû", "42,00 €")


@pytest.mark.conformance
def test_une_valeur_recalculee_juste_apres_l_action_est_relue(page_de, monkeypatch):
    """Relecture : la première lecture sortait `non_conforme` sur une application saine dont le total se met à jour en retard."""
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 3000)
    p = page_de('<dl><dt>Montant dû</dt><dd id="m">…</dd></dl>'
                '<script>setTimeout(() => { document.getElementById("m").textContent = "42,00 €"; }, 400);</script>')

    H.valeur_affichee_vaut(p, "Montant dû", "42,00 €")


# ── Un texte selon un motif ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.conformance
def test_un_texte_de_la_forme_demandee_est_trouve(page):
    H.page_affiche_texte_de_la_forme(page, r"CMD-\d{4}-\d{4}")
    H.page_affiche_texte_de_la_forme(page, r"REF-[0-9]+")


@pytest.mark.conformance
def test_falsifiable_un_motif_que_rien_ne_suit_echoue(page):
    with pytest.raises(AssertionError):
        H.page_affiche_texte_de_la_forme(page, r"CMD-\d{9}")
    with pytest.raises(AssertionError):
        H.page_affiche_texte_de_la_forme(page, r"MD-\d{4}")          # morceau de mot


@pytest.mark.conformance
@pytest.mark.parametrize("motif", [".*", r"\d*", "(CMD)?", r"\d+", ".+", ".", r"\S+", r"\w+", "[0-9]+", r"\d{4}", r"(?=\s)",
                                   "ab", r"[0-9]{2}/[0-9]{2}", "(CMD-)?[0-9]+", "CMD|[0-9]+"])
def test_falsifiable_un_motif_sans_partie_fixe_est_refuse(page_de, motif):
    """Relecture, reproduit : une page « Erreur 500 … © 2026 » sortait `conforme` pour « un texte de la forme "\\d+" »."""
    p = page_de("<h1>Erreur 500</h1><p>Une erreur est survenue. © 2026 ab</p>")

    with pytest.raises(H.ConstatInvalideError):
        H.page_affiche_texte_de_la_forme(p, motif)


@pytest.mark.conformance
@pytest.mark.parametrize("motif", [r"(?i)cmd-\d{4}-\d{4}", r"(?P<n>CMD-\d{4})", r"CMD-\d{4}-\d{4}\Z", r"CMD-\d++", "CMD-(", "CMD-[0-9"])
def test_falsifiable_un_motif_illisible_est_une_erreur_du_test_jamais_un_defaut(page, motif):
    """Relecture, reproduit : valide en Python, refusé par le navigateur, avalé par la boucle — `non_conforme` sur une page saine."""
    with pytest.raises(H.ConstatInvalideError):
        H.page_affiche_texte_de_la_forme(page, motif)


@pytest.mark.conformance
def test_falsifiable_un_texte_cache_ou_une_option_ne_suit_pas_le_motif(page_de):
    p = page_de('<p style="display:none">FAC-0001</p><select><option>France</option><option>FAC-0002</option></select>'
                '<input value="FAC-0003">')

    with pytest.raises(AssertionError):
        H.page_affiche_texte_de_la_forme(p, r"FAC-[0-9]{4}")


# ── Relever puis réutiliser ───────────────────────────────────────────────────────────────────────────────


def _step(texte: str, type_: str) -> None:
    """Ce que `environment.before_step` fait au début d'un step."""
    H.definir_etat_constat(scenario="s", step_type=type_)
    H.debut_de_step_pour_les_releves(texte, type_ in ("given", "when"))


@pytest.mark.conformance
def test_une_valeur_relevee_se_reutilise(page):
    contexte = SimpleNamespace(page=page)
    _step('je relève la valeur affichée pour "Référence" comme "ref"', "when")

    H.relever_valeur(contexte, "Référence", "ref")

    _step('je renseigne le champ "Recherche" avec la valeur "{relevé:ref}"', "when")
    assert H.avec_releves(contexte, "Dossier {relevé:ref} créé") == "Dossier REF-77 créé"
    assert H.avec_releves(contexte, "sans relevé") == "sans relevé"


@pytest.mark.conformance
def test_falsifiable_une_valeur_vide_n_est_pas_relevee(page_de):
    p = page_de('<dl><dt>Montant dû</dt><dd><span style="display:inline-block;width:4px;height:4px"></span></dd></dl>')

    with pytest.raises(H.ElementIntrouvableError):
        H.relever_valeur(SimpleNamespace(page=p), "Montant dû", "m")


def test_falsifiable_un_nom_jamais_releve_est_une_erreur():
    with pytest.raises(H.ElementIntrouvableError, match="n'a pas été relevé"):
        H.avec_releves(SimpleNamespace(_tp_releves={"ref": ("REF-77", 0)}), "{relevé:numero}")


@pytest.mark.parametrize("jeton", ["{releve:ref}", "{Relevé:ref}", "{relevé : ref}", "{ relevé:ref }", "{RELEVE:ref}",
                                   "{relevé:ref}", "{relevé:}"])
def test_falsifiable_un_jeton_mal_ecrit_n_est_jamais_laisse_tel_quel(jeton):
    """Relecture, reproduit : le jeton restait dans le texte — « la page n'affiche pas "{releve:ref}" » était toujours vraie."""
    contexte = SimpleNamespace(_tp_releves={"ref": ("REF-77", 0)})
    _step(f'la page n\'affiche pas le texte "{jeton}"', "when")

    with pytest.raises(H.ElementIntrouvableError, match="mal écrit|n'a pas été relevé"):
        H.avec_releves(contexte, jeton)


def _relever_sans_page(contexte, valeur="999,99 €"):
    _step('je relève la valeur affichée pour "Montant dû" comme "m"', "when")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(H, "lire_valeur_affichee", lambda page, libelle: valeur)
        H.relever_valeur(contexte, "Montant dû", "m")


def test_falsifiable_un_releve_ne_se_compare_pas_a_l_ecran_sans_action_entre_les_deux():
    """Relecture, reproduit : la page affiche un montant FAUX, on le relève, on vérifie qu'il vaut ce qu'on vient de relever —
    `conforme`. Sous un « Alors » qui lit l'écran, un relevé ne s'utilise qu'après une action."""
    contexte = SimpleNamespace(page=None)
    _relever_sans_page(contexte)

    _step('la valeur affichée pour "Montant dû" est "{relevé:m}"', "then")
    with pytest.raises(H.ConstatInvalideError, match="aucune action"):
        H.avec_releves(contexte, "{relevé:m}")

    # Deux relevés de suite ne sont pas une action.
    _relever_sans_page(contexte)
    _relever_sans_page(contexte)
    _step('la page affiche le texte "{relevé:m}"', "then")
    with pytest.raises(H.ConstatInvalideError, match="aucune action"):
        H.avec_releves(contexte, "{relevé:m}")


def test_un_releve_s_utilise_contre_l_oracle_et_a_l_ecran_apres_une_action():
    contexte = SimpleNamespace(page=None)
    _relever_sans_page(contexte, "DOS-1")

    _step('la liste "dossiers" de l\'oracle "etat" contient un élément dont "numero" est "{relevé:m}"', "then")
    assert H.avec_releves(contexte, "{relevé:m}", ecran=False) == "DOS-1", "autre source : pas une auto-référence"

    _step('je clique sur le bouton "Mes dossiers"', "when")
    _step('la page affiche le texte "{relevé:m}"', "then")
    assert H.avec_releves(contexte, "{relevé:m}") == "DOS-1"


def test_falsifiable_un_step_qui_ne_substitue_pas_ne_constate_rien(monkeypatch, tmp_path):
    """Relecture, reproduit : « le tableau … contient une ligne avec "{relevé:n}" » cherchait le jeton lui-même (`non_conforme`
    sur une application saine) ; dans une absence, c'était un vert. La garde est au constat, que toute vérification traverse."""
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(tmp_path / "c.jsonl"))
    contexte = SimpleNamespace(_tp_releves={"n": ("DOS-1", 0)})

    _step('le tableau "Dossiers" contient une ligne avec "{relevé:n}" et "42,00 €"', "then")
    with pytest.raises(H.ConstatInvalideError, match="ne sait pas remplacer"):
        H.constater(True, "ligne trouvée")
    consignes = [json.loads(ligne) for ligne in (tmp_path / "c.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [c["ok"] for c in consignes] == [False], "un test qui avalerait l'erreur garde la trace d'un constat raté"

    H._ETAT_RELEVES.update(actions=1)
    _step('la page affiche le texte "{relevé:n}"', "then")
    H.avec_releves(contexte, "{relevé:n}")
    H.constater(True, "texte trouvé")          # substitué : le constat vaut


# ── Oracle : la liste contient un élément dont … ──────────────────────────────────────────────────────────


@pytest.fixture
def oracle(monkeypatch, tmp_path):
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(tmp_path / "c.jsonl"))
    H.definir_etat_constat(scenario="s", step_type="then")
    monkeypatch.setattr(H, "_executer_oracle", lambda context, requete: {
        "commandes": [{"client": "Dupont", "total": 129.51, "payee": True, "adresse": {"ville": "Lyon"}},
                      {"client": "Martin", "total": 12.0}],
        "vide": [], "textes": ["a", "b"], "panier": {"lignes": []}})
    return SimpleNamespace(journal=tmp_path / "c.jsonl")


def test_la_liste_de_l_oracle_contient_l_element_demande(oracle):
    H.oracle_liste_contient(oracle, "commandes", "etat", "client", "Dupont")
    H.oracle_liste_contient(oracle, "commandes", "etat", "total", "12")          # comparaison typée
    H.oracle_liste_contient(oracle, "commandes", "etat", "payee", "true")        # clé portée par un seul élément
    H.oracle_liste_contient(oracle, "commandes", "etat", "adresse.ville", "Lyon")

    constats = [json.loads(ligne) for ligne in oracle.journal.read_text(encoding="utf-8").splitlines()]
    assert {(c["ok"], c["source"]) for c in constats} == {(True, "oracle")}


def test_falsifiable_le_mauvais_element_ne_suffit_pas(oracle):
    """Avant : seul le comptage existait — « la liste compte 2 éléments » passait avec les mauvaises commandes."""
    with pytest.raises(AssertionError, match="aucun des 2"):
        H.oracle_liste_contient(oracle, "commandes", "etat", "client", "Durand")
    with pytest.raises(AssertionError):
        H.oracle_liste_contient(oracle, "commandes", "etat", "client", "dupont")     # casse respectée
    with pytest.raises(AssertionError, match="aucun des 0"):
        H.oracle_liste_contient(oracle, "vide", "etat", "client", "Dupont")


@pytest.mark.parametrize("chemin, cle", [("panier", "nom"), ("absent", "nom"), ("commandes", "nom_client"), ("commandes", "Client"),
                                         ("commandes", "adresse"), ("textes", "client"), ("commandes", " ")])
def test_falsifiable_une_cle_ou_une_liste_qui_ne_se_lit_pas_est_un_test_mal_pose(oracle, chemin, cle):
    """Ni vert, ni `non_conforme` : la réponse de l'oracle n'a rien dit de l'application."""
    with pytest.raises((H.ReponseOracleNonComptableError, H.ElementIntrouvableError)):
        H.oracle_liste_contient(oracle, chemin, "etat", cle, "Dupont")


def test_falsifiable_la_forme_negative_n_existe_pas():
    """Relecture, reproduit : « ne contient aucun élément dont "nom_client" est "Dupont" » (clé inventée) sortait `conforme`
    avec `oracle_verifie`, la commande de Dupont toujours là. Hors plan, retirée plutôt que rafistolée."""
    generiques = (Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library" / "generic"
                  / "_generic_steps.py").read_text(encoding="utf-8")

    assert not hasattr(H, "oracle_liste_ne_contient_pas")
    assert "ne contient aucun élément dont" not in generiques


# ── Bout en bout : les phrases Gherkin, dans le vrai Behave ───────────────────────────────────────────────


class _Statique(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        fichier = _PAGES / ("accueil.html" if self.path in ("/", "") else self.path.split("?")[0].lstrip("/"))
        corps = fichier.read_bytes() if fichier.is_file() else b"absent"
        self.send_response(200 if fichier.is_file() else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)


@pytest.fixture(scope="module")
def application():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Statique)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{serveur.server_address[1]}"
    serveur.shutdown()


_RELEVER = ['Quand j\'ouvre la page "/releve-confirmation.html"',
            'Et je relève la valeur affichée pour "Numéro de dossier" comme "numero"']
SCENARIOS = {
    "le vocabulaire du lot": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Et je renseigne "Quantité" avec "5" dans la ligne contenant "Câble HDMI"',
        'Alors la page affiche le texte "Dernière saisie : Quantité de Câble HDMI = 5"',
        'Et la valeur affichée pour "Total TTC" est "129,51 €"',
        'Et la page affiche un texte de la forme "CMD-[0-9]{4}-[0-9]{4}"'], "conforme"),
    "un relevé retrouvé sur une autre page après une action": ([
        *_RELEVER, 'Et je clique sur le bouton "Mes dossiers"',
        'Alors la page affiche le texte "{relevé:numero}"',
        'Et l\'URL courante contient "releve-liste"'], "conforme"),
    "la phrase longue de saisie dans une ligne": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Et je renseigne le champ "Quantité" avec la valeur "7" dans la ligne contenant "Câble USB"',
        'Alors la page affiche le texte "Dernière saisie : Quantité de Câble USB = 7"'], "conforme"),
    "une mauvaise valeur à côté du libellé": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Alors la valeur affichée pour "Total TTC" est "107,92 €"'], "non_conforme"),
    "un relevé jamais fait": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Alors la page affiche le texte "{relevé:inconnu}"'], "technique"),
    # ── Les faux verts et le faux rouge reproduits à la relecture : plus jamais un verdict sur l'application ──
    "S1 une valeur comparée à elle-même": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Et je relève la valeur affichée pour "Total TTC" comme "total"',
        'Alors la valeur affichée pour "Total TTC" est "{relevé:total}"'], "technique"),
    "S1 bis la même par le texte de la page": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Et je relève la valeur affichée pour "Total TTC" comme "total"',
        'Alors la page affiche le texte "{relevé:total}"'], "technique"),
    "S2 un jeton mal écrit dans une absence": ([
        *_RELEVER, 'Et je clique sur le bouton "Mes dossiers"',
        'Alors la page n\'affiche pas le texte "{releve:numero}"'], "technique"),
    "S9 un step qui ne substitue pas": ([
        *_RELEVER, 'Et je clique sur le bouton "Mes dossiers"',
        'Alors le tableau "Dossiers" contient une ligne avec "{relevé:numero}" et "129,51 €"'], "technique"),
    "S8 un en-tête de colonne relevé": ([
        'Quand j\'ouvre la page "/releve-liste.html"',
        'Et je relève la valeur affichée pour "Numéro" comme "n"',
        'Et je clique sur le bouton "Mes dossiers"',
        'Alors la page affiche le texte "{relevé:n}"'], "technique"),
    "S5 un motif sans partie fixe": ([
        'Quand j\'ouvre la page "/releve-liste.html"',
        'Alors la page affiche un texte de la forme "[0-9]+"'], "technique"),
    "S6 un motif que le navigateur ne lit pas": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Alors la page affiche un texte de la forme "(?i)cmd-[0-9]{4}-[0-9]{4}"'], "technique"),
}


@pytest.mark.conformance
def test_les_phrases_du_lot_dans_le_vrai_behave(application):
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.execution.executor import Executor
    from testpilot.verdict import status as st

    lignes = ["Fonctionnalité: Steps du lot VH-06", ""]
    for titre, (etapes, _) in SCENARIOS.items():
        lignes += [f"  Scénario: {titre}", "    Soit j'accède à la page d'accueil de l'application",
                   *[f"    {e}" for e in etapes], ""]
    dossier = Path(tempfile.mkdtemp(prefix="vh06_"))
    (dossier / "v6.feature").write_text("\n".join(lignes), encoding="utf-8")
    runner = BehaveRunner(connection={"WEB_URL": application, "WEB_USER": "", "WEB_PASSWORD": ""},
                          connector_type="web", generated_dir=dossier)
    outcome = Executor(runner, max_retries=0).execute("v6")
    assert outcome.dry_run_passed, f"un step du lot n'est pas défini ou est ambigu : {outcome.error}"
    verdicts = {v.name: v for v in st.derive_verdict(outcome, connector_type="web").scenarios}

    for titre, (_, attendu) in SCENARIOS.items():
        v = verdicts[titre]
        obtenu = f"{titre} : {v.execution_status}/{v.functional_status} — {v.error[:300]}"
        if attendu == "conforme":
            assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), obtenu
        elif attendu == "non_conforme":
            assert v.functional_status == st.FUNC_NON_CONFORME, obtenu
        else:
            assert v.execution_status == st.EXEC_TECHNICAL_ERROR, obtenu
            assert v.functional_status not in (st.FUNC_CONFORME, st.FUNC_NON_CONFORME), obtenu
