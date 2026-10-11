"""Lot VH-06 (T3, T8) — les steps qui manquaient, chacun avec sa preuve de falsifiabilité.

Mesuré (banc base-3 à base-5) : faute de step partagé, l'agent écrivait du Playwright à la main pour « mettre la quantité de
la ligne "Câble HDMI" à 0 », « le total affiché est 129,51 € », « un numéro de commande CMD-… » — la première source d'erreur
technique après génération. Ici, sur un vrai Chromium (marqueur `conformance`) : chaque step réussit sur la bonne page ET
échoue quand l'application affiche autre chose ou que le test est mal posé.

Deux relectures (2026-10-11) ont reproduit dans le vrai Behave sept faux verts et un faux rouge, puis quatre autres chemins :
chacun a ici son test, nommé `falsifiable`, qui échoue sur le code d'avant la correction. Le mécanisme « je relève … comme
"nom" » puis `{relevé:nom}` — source de la moitié d'entre eux — est RETIRÉ ; il reste un step qui lit l'écran et l'oracle
ensemble, sans rien garder d'un step à l'autre.
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
    yield
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
    # Contre-relecture : l'égalité stricte des classes laissait passer ces deux-là.
    "classes voisines": '<div><div class="item gift">Carte cadeau</div>'
                        '<div class="item"><span>Câble HDMI</span> <label>Quantité <input name="quantite" value="1"></label></div></div>',
    "lignes paires et impaires": '<div><p class="row odd">Carte cadeau</p>'
                                 '<p class="row even">Câble HDMI <input name="quantite" aria-label="Quantité" value="1"></p></div>',
    "autre casse et morceau": '<table><tr><td>Rallonge câble hdmi 5 m</td>'
                              '<td><input name="quantite" aria-label="Quantité" value="1"></td></tr></table>',
}


@pytest.mark.conformance
@pytest.mark.parametrize("cas, texte", [("tableau", "Câble HDMI"), ("liste", "Carte cadeau"), ("cartes voisines", "Carte cadeau"),
                                        ("autre casse et morceau", "Câble HDMI"), ("classes voisines", "Carte cadeau"),
                                        ("lignes paires et impaires", "Carte cadeau")])
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
                '<div class="ligne" style="display:flex"><div class="col">Gomme</div>'
                '<div class="col"><label>Quantité</label> <input name="q3" aria-label="Quantité" value="1"></div></div>')

    H.saisir_dans_ligne(p, "Quantité", "4", "Stylo rouge")
    H.saisir_dans_ligne(p, "Quantité", "6", "Gomme")          # deux colonnes de même classe sur une même rangée : une ligne

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
    # Contre-relecture : seul le premier texte après le libellé était rendu (« 129,51 », puis « 1 »).
    ('<p><span>Montant dû :</span> 42,00 <span>€</span></p>', "Montant dû", "42,00 €"),
    ('<p><b>Montant dû :</b> 1 <span>042,00 €</span></p>', "Montant dû", "1 042,00 €"),
    ('<p><span>Réf. :</span> <span>R-7</span> <span>Statut :</span> <span>Validé</span></p>', "Réf.", "R-7"),
    # Troisième relecture : sans deux-points, le libellé et la valeur suivants étaient avalés (« DOS-1 Client Martin »).
    ('<p><span>Numéro</span> <span>DOS-1</span> <span>Client</span> <span>Martin</span></p>', "Numéro", "DOS-1"),
    ('<p><span>Numéro</span> <span>DOS-1</span> <span>Client</span> <span>Martin</span></p>', "Client", "Martin"),
    # … et un libellé sous `text-transform`, avec une espace insécable ou coupé par un retour à la ligne, devenait introuvable.
    ('<dl><dt style="text-transform:uppercase">Montant dû</dt><dd>42,00 €</dd></dl>', "Montant dû", "42,00 €"),
    ('<dl><dt style="text-transform:uppercase">Montant dû</dt><dd>42,00 €</dd></dl>', "MONTANT DÛ", "42,00 €"),
    ('<dl><dt>Montant&nbsp;dû</dt><dd>42,00 €</dd></dl>', "Montant dû", "42,00 €"),
    ('<dl><dt>Montant\n   dû</dt><dd>42,00 €</dd></dl>', "Montant dû", "42,00 €"),
    ('<table><tr><td>Numéro</td><td>DOS-1</td></tr><tr><td>Montant</td><td>42,00 €</td></tr></table>', "Numéro", "DOS-1"),   # fiche
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
    # Contre-relecture : la règle ne valait que pour la balise `th`.
    '<table><tr><td>Numéro</td><td>Montant</td><td>Client</td></tr><tr><td>DOS-1</td><td>42,00 €</td><td>Martin</td></tr></table>',
    '<table><tr><td><b>Numéro</b></td><td><b>Montant</b></td><td><b>Client</b></td></tr>'
    '<tr><td>DOS-1</td><td>42,00 €</td><td>Martin</td></tr></table>',
    '<div role="grid"><div role="row"><span role="columnheader">Numéro</span><span role="columnheader">Montant</span></div>'
    '<div role="row"><span role="gridcell">DOS-1</span><span role="gridcell">42,00 €</span></div></div>',
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
    H.page_affiche_texte_de_la_forme(page, r"CMD\-\d{4}\-\d{4}")   # tiret échappé : courant, et refusé à tort en mode Unicode


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
@pytest.mark.parametrize("motif", [r"(?i)cmd-\d{4}-\d{4}", r"(?P<n>CMD-\d{4})", r"CMD-\d{4}-\d{4}\Z", r"\ACMD-\d{4}",
                                   r"(CMD-\d{4}-\d{4}\Z)", r"(?s)CMD-.+", r"CMD-\d++", "CMD-(", "CMD-[0-9"])
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


# ── Oracle : la liste contient un élément dont … ──────────────────────────────────────────────────────────


@pytest.fixture
def oracle(monkeypatch, tmp_path):
    monkeypatch.setenv(H.CONSTATS_FILE_ENV, str(tmp_path / "c.jsonl"))
    H.definir_etat_constat(scenario="s", step_type="then")
    monkeypatch.setattr(H, "_executer_oracle", lambda context, requete: {
        "commandes": [{"client": "Dupont", "total": 129.51, "payee": True, "adresse": {"ville": "Lyon"}, "ref": "REF-77"},
                      {"client": "Martin", "total": 12.0, "ref": "REF-78"}],
        "vide": [], "textes": ["a", "b"], "panier": {"lignes": []}})
    return SimpleNamespace(journal=tmp_path / "c.jsonl")


def _constats(oracle):
    return [json.loads(ligne) for ligne in oracle.journal.read_text(encoding="utf-8").splitlines()]


def test_la_liste_de_l_oracle_contient_l_element_demande(oracle):
    H.oracle_liste_contient(oracle, "commandes", "etat", "client", "Dupont")
    H.oracle_liste_contient(oracle, "commandes", "etat", "total", "12")          # comparaison typée
    H.oracle_liste_contient(oracle, "commandes", "etat", "payee", "true")        # clé portée par un seul élément
    H.oracle_liste_contient(oracle, "commandes", "etat", "adresse.ville", "Lyon")

    assert {(c["ok"], c["source"]) for c in _constats(oracle)} == {(True, "oracle")}


def test_falsifiable_le_mauvais_element_ne_suffit_pas(oracle):
    """Avant : seul le comptage existait — « la liste compte 2 éléments » passait avec les mauvaises commandes."""
    with pytest.raises(AssertionError, match="aucun des 2"):
        H.oracle_liste_contient(oracle, "commandes", "etat", "client", "Durand")
    with pytest.raises(AssertionError):
        H.oracle_liste_contient(oracle, "commandes", "etat", "client", "dupont")     # casse respectée
    with pytest.raises(AssertionError):
        H.oracle_liste_contient(oracle, "commandes", "etat", "total", "129,50")
    with pytest.raises(AssertionError, match="aucun des 0"):
        H.oracle_liste_contient(oracle, "vide", "etat", "client", "Dupont")


@pytest.mark.parametrize("chemin, cle, valeur", [
    ("panier", "nom", "x"), ("absent", "nom", "x"), ("commandes", "nom_client", "Dupont"), ("commandes", "Client", "Dupont"),
    ("commandes", "adresse", "Lyon"), ("textes", "client", "a"), ("commandes", " ", "Dupont"),
    ("commandes", "total", "129,51 €"),          # un nombre contre un texte à unité : jamais égaux
])
def test_falsifiable_une_cle_une_liste_ou_une_valeur_qui_ne_se_compare_pas_est_un_test_mal_pose(oracle, chemin, cle, valeur):
    """Ni vert, ni `non_conforme` : la réponse de l'oracle n'a rien dit de l'application."""
    with pytest.raises((H.ReponseOracleNonComptableError, H.ElementIntrouvableError)):
        H.oracle_liste_contient(oracle, chemin, "etat", cle, valeur)


def test_falsifiable_la_forme_negative_et_le_releve_n_existent_pas():
    """Relectures, reproduit : « ne contient aucun élément dont "nom_client" est … » (clé inventée) sortait `conforme` ; un
    relevé comparé à l'écran d'où il venait, un jeton `{releve:x}` laissé tel quel, un relevé survivant au scénario suivant,
    aussi. Retirés plutôt que rafistolés une troisième fois."""
    generiques = (Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library" / "generic"
                  / "_generic_steps.py").read_text(encoding="utf-8")

    assert not hasattr(H, "oracle_liste_ne_contient_pas") and "ne contient aucun élément dont" not in generiques
    assert not hasattr(H, "avec_releves") and not hasattr(H, "relever_valeur")
    assert "relevé:" not in generiques and "je relève" not in generiques


# ── L'écran et l'oracle, dans le même step ────────────────────────────────────────────────────────────────


@pytest.mark.conformance
def test_ce_que_l_ecran_affiche_se_retrouve_dans_l_oracle(page, oracle):
    contexte = SimpleNamespace(page=page)

    H.oracle_liste_contient_valeur_affichee(contexte, "commandes", "etat", "ref", "Référence")     # l'écran affiche REF-77

    assert [(c["ok"], c["source"]) for c in _constats(oracle)] == [(True, "oracle")]
    assert not hasattr(contexte, "_tp_releves") and vars(contexte) == {"page": page}, "rien n'est gardé d'un step à l'autre"


@pytest.mark.conformance
def test_une_valeur_rendue_juste_apres_l_action_est_relue_avant_de_juger(page_de, oracle, monkeypatch):
    """Troisième relecture, reproduit : le step lisait l'écran une seule fois — « … » comparé à l'oracle, `non_conforme` sur
    une application saine."""
    monkeypatch.setattr(H, "_ATTENDRE_UNIVERSELLE_MS", 3000)
    p = page_de('<p>Référence : <strong id="r">…</strong></p>'
                '<script>setTimeout(() => { document.getElementById("r").textContent = "REF-77"; }, 500);</script>')

    H.oracle_liste_contient_valeur_affichee(SimpleNamespace(page=p), "commandes", "etat", "ref", "Référence")

    assert [(c["ok"], c["source"]) for c in _constats(oracle)] == [(True, "oracle")], "un seul constat, sur la dernière lecture"


@pytest.mark.conformance
def test_falsifiable_un_ecran_et_un_serveur_qui_ne_concordent_pas_echouent(page, oracle, monkeypatch):
    contexte = SimpleNamespace(page=page)
    monkeypatch.setattr(H, "_executer_oracle", lambda context, requete: {"commandes": [{"ref": "REF-78"}]})

    with pytest.raises(AssertionError, match="REF-77"):
        H.oracle_liste_contient_valeur_affichee(contexte, "commandes", "etat", "ref", "Référence")
    assert [(c["ok"], c["source"]) for c in _constats(oracle)] == [(False, "oracle")]


@pytest.mark.conformance
def test_falsifiable_un_libelle_absent_ou_une_valeur_non_comparable_est_un_test_mal_pose(page, oracle):
    contexte = SimpleNamespace(page=page)

    with pytest.raises(H.ElementIntrouvableError):
        H.oracle_liste_contient_valeur_affichee(contexte, "commandes", "etat", "ref", "Numéro de commande")
    with pytest.raises(H.ReponseOracleNonComptableError):
        H.oracle_liste_contient_valeur_affichee(contexte, "commandes", "etat", "total", "Total TTC")   # « 129,51 € » / 129.51
    assert _constats(oracle) == [] if oracle.journal.exists() else True


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


SCENARIOS = {
    "le vocabulaire du lot": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Et je renseigne "Quantité" avec "5" dans la ligne contenant "Câble HDMI"',
        'Alors la page affiche le texte "Dernière saisie : Quantité de Câble HDMI = 5"',
        'Et la valeur affichée pour "Total TTC" est "129,51 €"',
        'Et la page affiche un texte de la forme "CMD-[0-9]{4}-[0-9]{4}"'], "conforme"),
    "une valeur lue sur la page de confirmation": ([
        'Quand j\'ouvre la page "/releve-confirmation.html"',
        'Alors la valeur affichée pour "Numéro de dossier" est "DOS-2026-0042"'], "conforme"),
    "la phrase longue de saisie dans une ligne": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Et je renseigne le champ "Quantité" avec la valeur "7" dans la ligne contenant "Câble USB"',
        'Alors la page affiche le texte "Dernière saisie : Quantité de Câble USB = 7"'], "conforme"),
    "une mauvaise valeur à côté du libellé": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Alors la valeur affichée pour "Total TTC" est "107,92 €"'], "non_conforme"),
    # ── Ce que les relectures ont reproduit : plus jamais un verdict sur l'application ────────────────────────
    "S8 un en-tête de colonne n'a pas de valeur": ([
        'Quand j\'ouvre la page "/releve-liste.html"',
        'Alors la valeur affichée pour "Numéro" est "Montant"'], "technique"),
    "S5 un motif sans partie fixe": ([
        'Quand j\'ouvre la page "/releve-liste.html"',
        'Alors la page affiche un texte de la forme "[0-9]+"'], "technique"),
    "S6 un motif que le navigateur ne lit pas": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Alors la page affiche un texte de la forme "(?i)cmd-[0-9]{4}-[0-9]{4}"'], "technique"),
    "l'oracle sans oracle configuré": ([
        'Quand j\'ouvre la page "/panier.html"',
        'Alors la liste "commandes" de l\'oracle "etat" contient un élément dont "ref" est la valeur affichée pour "Référence"'],
        "bloque"),
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
            # « technique » : erreur du test ; « bloque » : prérequis manquant (aucun oracle déclaré) — jamais un verdict.
            assert v.execution_status != st.EXEC_SUCCESS, obtenu
            assert v.functional_status not in (st.FUNC_CONFORME, st.FUNC_NON_CONFORME), obtenu
