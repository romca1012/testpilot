"""Lecture normalisée d'un nombre affiché + comparaison à tolérance déclarée (lot Q4, D21)."""

from __future__ import annotations

import sys
from decimal import Decimal

import pytest

from testpilot import config

sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
import _lecture_nombre as ln  # noqa: E402

D = Decimal


@pytest.mark.parametrize("texte, valeur, devise", [
    ("129,51", "129.51", None),
    ("1 234,50 €", "1234.50", "EUR"),
    ("1 234,50 €", "1234.50", "EUR"),
    ("1,234.50", "1234.50", None),
    ("1.234,50", "1234.50", None),
    ("$1,234,567.89", "1234567.89", "USD"),
    ("1.234.567", "1234567", None),
    ("1 234 567", "1234567", None),
    ("-12,50", "-12.50", None),
    ("−12,50 €", "-12.50", "EUR"),
    ("(12,50)", "-12.50", None),
    ("0,5", "0.5", None),
    ("0,125", "0.125", None),
    ("18 %", "18", None),
    ("5 000 FCFA", "5000", "XOF"),
    ("1’234.50", "1234.50", None),
])
def test_lectures_sans_ambiguite(texte, valeur, devise):
    lu = ln.lire_nombre(texte)

    assert lu.valeur == D(valeur) and lu.devise == devise


def test_pourcentage_est_signale():
    assert ln.lire_nombre("18 %").pourcentage is True and ln.lire_nombre("18").pourcentage is False


@pytest.mark.parametrize("texte", ["1,234", "1.234", "12,345", "999,999"])
def test_une_lecture_ambigue_est_refusee_jamais_devinee(texte):
    """Falsifiable : « 1,234 » lu au hasard comme 1.234 ou 1234 donnerait un faux verdict dans un cas sur deux."""
    with pytest.raises(ln.LectureImpossible, match="ambigu"):
        ln.lire_nombre(texte)


def test_le_separateur_decimal_connu_leve_l_ambiguite():
    assert ln.lire_nombre("1,234", separateur_decimal=",").valeur == D("1.234")
    assert ln.lire_nombre("1,234", separateur_decimal=".").valeur == D("1234")


@pytest.mark.parametrize("texte", ["", "  ", "abc", "12 abc", "1,2,3,4,5,6", "1.234,56,7", "12,34.567,8", "€"])
def test_un_texte_non_numerique_ou_incoherent_est_refuse(texte):
    with pytest.raises(ln.LectureImpossible):
        ln.lire_nombre(texte)


@pytest.mark.parametrize("texte", [
    "10 12", "3 4", "1 2", "1 2 3", "12 3456", "1'2", "12 5 €", "12 € 15 €", "€10 $12", "5 5%", "12 5%", "5 % 6 %",
    "12 € EUR", "1 234 5", "1 234,5 67", "1 234.567 8",
])
def test_deux_nombres_colles_ne_sont_jamais_fusionnes_en_un_seul(texte):
    """Falsifiable (revue du 2026-10-07) : « 10 12 » était lu 1012 — une pagination, ou une quantité suivie d'un prix, aurait
    pu faire réussir un `Alors` sans que la valeur soit prouvée."""
    with pytest.raises(ln.LectureImpossible):
        ln.lire_nombre(texte)


def test_les_vrais_groupes_de_milliers_restent_lus():
    assert ln.lire_nombre("1 234 567,89").valeur == D("1234567.89")
    assert ln.lire_nombre("12 345").valeur == D("12345")
    assert ln.lire_nombre("1’234’567").valeur == D("1234567")


@pytest.mark.parametrize("tolerance", ["Infinity", "NaN", "-Infinity"])
def test_une_tolerance_non_finie_est_refusee(tolerance):
    """Falsifiable : `Infinity` acceptait n'importe quelle valeur (5 pour un attendu 0)."""
    with pytest.raises(ValueError):
        ln.comparer(D(5), 0, tolerance=tolerance, source="x")


def test_une_tolerance_enorme_est_refusee_une_tolerance_raisonnable_passe():
    with pytest.raises(ValueError, match="excessive"):
        ln.comparer(D(5), 100, tolerance="100", source="x")
    with pytest.raises(ValueError, match="excessive"):
        ln.comparer(D("0.5"), "0.5", tolerance="1", source="x")
    assert ln.comparer(D("99.99"), 100, tolerance="0.01", source="arrondi").ok is True


def test_une_unite_contradictoire_fait_echouer_la_comparaison():
    """Falsifiable : 5 $ n'est pas 5 €, 5 % n'est pas 5."""
    assert ln.comparer(ln.lire_nombre("5 $"), 5, devise_attendue="EUR").ok is False
    assert ln.comparer(ln.lire_nombre("5 €"), 5, devise_attendue="EUR").ok is True
    assert ln.comparer(ln.lire_nombre("5 %"), 5, pourcentage_attendu=False).ok is False
    assert ln.comparer(ln.lire_nombre("5"), 5, pourcentage_attendu=True).ok is False
    assert ln.comparer(ln.lire_nombre("5 %"), 5, pourcentage_attendu=True).ok is True


def test_une_unite_non_declaree_est_dite_non_verifiee_dans_le_message():
    assert "devise lue EUR non vérifiée" in ln.comparer(ln.lire_nombre("5 €"), 5).message
    assert "pourcentage lu non vérifié" in ln.comparer(ln.lire_nombre("5 %"), 5).message


def test_exacte_par_defaut_un_centime_d_ecart_echoue():
    """Falsifiable : sans tolérance déclarée, 129,50 n'est PAS 129,51."""
    assert ln.comparer(ln.lire_nombre("129,51"), "129.51").ok is True
    c = ln.comparer(ln.lire_nombre("129,50"), "129.51")
    assert c.ok is False and "exacte, aucune tolérance" in c.message


def test_la_tolerance_declaree_figure_dans_le_message_avec_sa_source():
    c = ln.comparer(D("129.50"), "129.51", tolerance="0.01", source="arrondi de la devise")

    assert c.ok is True and "± 0.01 — arrondi de la devise" in c.message
    assert ln.comparer(D("129.48"), "129.51", tolerance="0.01", source="arrondi de la devise").ok is False


def test_une_tolerance_sans_source_est_refusee():
    with pytest.raises(ValueError, match="source"):
        ln.comparer(D("1"), "1", tolerance="0.01")
    with pytest.raises(ValueError, match="négative"):
        ln.comparer(D("1"), "1", tolerance="-1", source="x")


def test_un_float_n_introduit_pas_d_erreur_binaire():
    """0.1 + 0.2 != 0.3 en binaire ; la comparaison passe par le texte du nombre, pas par sa valeur binaire."""
    assert ln.comparer(D("0.3"), 0.3).ok is True


# ── Lot PT-03 : la devise varie d'un pays à l'autre ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("texte, valeur, devise, possibles", [
    ("412 000 MAD", "412000", "MAD", {"MAD"}),
    ("1 500 ₦", "1500", "NGN", {"NGN"}),
    ("R$ 12,50", "12.50", "BRL", {"BRL"}),
    ("EUR12.50", "12.50", "EUR", {"EUR"}),
    ("12,50 zł", "12.50", "PLN", {"PLN"}),
    ("412 000 F CFA", "412000", "XOF", {"XOF", "XAF"}),
    ("412\u00a0000 F\u00a0CFA", "412000", "XOF", {"XOF", "XAF"}),   # espaces insécables, comme à l'écran
    ("5 $", "5", "USD", None),
    ("100 DH", "100", "MAD", {"MAD", "AED"}),
])
def test_les_monnaies_de_tous_les_pays_sont_lues(texte, valeur, devise, possibles):
    lu = ln.lire_nombre(texte)

    assert (lu.valeur, lu.devise) == (D(valeur), devise)
    if possibles is not None:
        assert lu.devises == possibles
    else:
        assert {"USD", "CAD", "AUD"} <= lu.devises


@pytest.mark.parametrize("texte", ["USDT 5", "5 EURO", "krach 5", "12 XYZ", "5 Fr.", "12 € %", "12 USD EUR"])
def test_une_notation_inconnue_ou_double_n_est_jamais_devinee(texte):
    """Falsifiable : « USD » dans « USDT » ou un code inventé ne font pas une devise ; deux unités ne font pas un montant."""
    with pytest.raises(ln.LectureImpossible):
        ln.lire_nombre(texte)


def test_un_symbole_partage_satisfait_chacune_de_ses_monnaies_et_aucune_autre():
    assert ln.comparer(ln.lire_nombre("5 $"), 5, devise_attendue="CAD").ok is True
    assert ln.comparer(ln.lire_nombre("5 $"), 5, devise_attendue="EUR").ok is False
    assert ln.comparer(ln.lire_nombre("5 F CFA"), 5, devise_attendue="XAF").ok is True


def _etat(ecran: str, attendu: str) -> str:
    return ln.comparer_valeurs(ln.lire_nombre(ecran), ln.lire_nombre(attendu)).etat


@pytest.mark.parametrize("ecran, attendu", [
    ("129.51 EUR", "129,51 €"), ("412 000 FCFA", "412 000 F CFA"), ("5 $", "5 $"), ("18 %", "18,0 %"),
    ("500 000", "500000"), ("(12,50 €)", "-12,50 €"),
])
def test_deux_ecritures_du_meme_montant_sont_egales(ecran, attendu):
    assert _etat(ecran, attendu) == ln.EGAL


@pytest.mark.parametrize("ecran, attendu", [
    ("129,50 €", "129,51 €"), ("130,81 €", "129,51 €"), ("129,51 $", "129,51 €"), ("412 000 XAF", "412 000 XOF"),
    ("412 000 F CFA", "412 000 NGN"), ("18 %", "18 €"), ("18 €", "18 %"), ("12,50 €", "-12,50 €"), ("50 000", "500 000"),
])
def test_falsifiable_un_autre_nombre_ou_une_unite_incompatible_est_different(ecran, attendu):
    assert _etat(ecran, attendu) == ln.DIFFERENT


@pytest.mark.parametrize("ecran, attendu", [("500 000", "500 000 XOF"), ("18", "18 %"), ("5", "5 $")])
def test_falsifiable_une_unite_attendue_et_non_affichee_ne_conclut_pas(ecran, attendu):
    """Ni égal (la devise n'est pas prouvée) ni différent (l'application n'est pas en cause)."""
    assert _etat(ecran, attendu) == ln.UNITE_NON_VERIFIABLE


def test_le_nombre_prime_sur_l_unite_un_mauvais_nombre_est_different_meme_sans_unite_affichee():
    """Falsifiable : un total faux sans devise affichée reste un total faux, jamais un « non concluant » qui le cacherait."""
    assert _etat("500 001", "500 000 XOF") == ln.DIFFERENT


def test_le_message_dit_ce_qui_n_a_pas_ete_verifie_ou_distingue():
    # Décision A24 : ces deux cas réussissaient avec une réserve que personne ne lisait ; ils ne concluent plus, et le disent.
    m = ln.comparer_valeurs(ln.lire_nombre("129,51 €"), ln.lire_nombre("129,51")).message
    assert "l'attendu n'écrit pas d'unité" in m and "écrivez-la dans le test" in m
    m = ln.comparer_valeurs(ln.lire_nombre("5 $"), ln.lire_nombre("5 CAD")).message
    assert "ne prouve pas" in m and "comparaison exacte" in m
    m = ln.comparer_valeurs(ln.lire_nombre("5 $"), ln.lire_nombre("5 $")).message
    assert "ne distingue pas" in m


# ── Lot PT-03 : points de la revue du 2026-10-13 ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("texte", ["5€300", "1$234", "5ALL300", "5%300", "12 € 5"])
def test_falsifiable_une_unite_au_milieu_des_chiffres_n_est_pas_un_separateur(texte):
    """« 5€300 » était lu 5300 € : le symbole, remplacé par une espace, devenait un séparateur de milliers."""
    with pytest.raises(ln.LectureImpossible):
        ln.lire_nombre(texte)


def test_falsifiable_un_pourcentage_entre_parentheses_n_est_pas_un_nombre_negatif():
    """« (20 %) » était lu −20 % : un test attendant « 20 % » accusait une application saine."""
    with pytest.raises(ln.LectureImpossible):
        ln.lire_nombre("(20 %)")
    assert ln.lire_nombre("(12,50 €)").valeur == D("-12.50")   # la convention comptable, elle, reste lue pour un montant


def test_une_valeur_construite_a_la_main_reste_coherente():
    euros = ln.NombreLu(D(5), "EUR")
    taux = ln.NombreLu(D(5), pourcentage=True)

    assert euros.devises == {"EUR"} and (euros.nature, euros.unite) == (ln.MONNAIE, "EUR")
    assert (taux.nature, taux.unite) == (ln.POURCENTAGE, "%")
    assert ln.comparer(euros, 5, devise_attendue="EUR").ok is True


# ── Lot PT-03 : une valeur n'est pas toujours une somme d'argent ──────────────────────────────────────────────────────────


def _lu(texte: str):
    return ln.lire_nombre(texte, avec_unite=True)


@pytest.mark.parametrize("texte, valeur, nature, unite", [
    ("1,5 kg", "1.5", "masse", "kg"), ("1 500 g", "1500", "masse", "g"), ("3 jours", "3", "durée", "j"),
    ("90 min", "90", "durée", "min"), ("250 m2", "250", "surface", "m²"), ("0,5 l", "0.5", "volume", "l"),
    ("45 kWh", "45", "énergie", "kWh"), ("120 km/h", "120", "vitesse", "km/h"), ("-4 °C", "-4", "température", "°C"),
    ("12 pièces", "12", ln.INCONNUE, "pièces"), ("7 UI/L", "7", ln.INCONNUE, "UI/L"),
    ("412 000 F CFA", "412000", ln.MONNAIE, "XOF"), ("18 %", "18", ln.POURCENTAGE, "%"), ("12", "12", "", ""),
    ("12 € / kg", "12", ln.INCONNUE, "EUR/kg"), ("5 ‰", "5", ln.POURCENTAGE, "‰"),
])
def test_chaque_valeur_porte_un_nombre_une_unite_et_une_nature(texte, valeur, nature, unite):
    lu = _lu(texte)

    assert (lu.valeur, lu.nature, lu.unite) == (D(valeur), nature, unite)


def test_un_qualificatif_n_est_pas_une_unite():
    lu = _lu("129,51 € TTC")

    assert (lu.valeur, lu.nature, lu.unite, lu.qualificatif) == (D("129.51"), ln.MONNAIE, "EUR", "TTC")


@pytest.mark.parametrize("texte", ["2 sur 5", "1 h 30", "12.", "Total 12", "10 12", "CMD-2026",
                                   "12 articles en stock depuis hier matin"])
def test_falsifiable_ce_qui_suit_le_nombre_n_est_une_unite_que_si_c_en_est_une(texte):
    """Un second nombre, un préfixe ou une phrase ne sont pas une unité : la lecture reste refusée."""
    with pytest.raises(ln.LectureImpossible):
        _lu(texte)


def test_sans_avec_unite_le_lecteur_refuse_comme_avant():
    """Le comportement d'avant le lot est inchangé pour qui n'en demande pas plus."""
    for texte in ("12 abc", "1,5 kg", "3 jours"):
        with pytest.raises(ln.LectureImpossible):
            ln.lire_nombre(texte)


def _issue(ecran: str, attendu: str) -> str:
    return ln.comparer_valeurs(_lu(ecran), _lu(attendu)).etat


@pytest.mark.parametrize("ecran, attendu", [
    ("1 500 g", "1,5 kg"), ("1,5 kg", "1500 g"), ("90 min", "1,5 h"), ("36 km/h", "10 m/s"), ("2 000 000 mm²", "2 m²"),
    ("1 lb", "453,59237 g"), ("3 jours", "3 j"), ("12 pièces", "12 pièces"),
    ("129,51 € TTC", "129,51 € TTC"), ("12 €/kg", "12 € / kg"), ("412 000 FCFA", "412 000 F CFA"),
])
def test_la_meme_grandeur_ecrite_autrement_est_egale(ecran, attendu):
    assert _issue(ecran, attendu) == ln.EGAL


@pytest.mark.parametrize("ecran, attendu", [
    ("1,6 kg", "1500 g"), ("5 kg", "5 km"), ("18 %", "18 €"), ("5 kg", "5 €"), ("13 pièces", "12 pièces"),
    ("3 h", "90 min"), ("412 000 XAF", "412 000 XOF"), ("412 001", "412 000 XOF"),
])
def test_falsifiable_une_autre_grandeur_ou_une_autre_nature_est_differente(ecran, attendu):
    assert _issue(ecran, attendu) == ln.DIFFERENT


@pytest.mark.parametrize("ecran, attendu", [
    ("1,5", "1,5 kg"), ("1500", "1,5 kg"), ("12 mois", "1 an"), ("20 °C", "68 °F"), ("12 pièces", "12 unités"),
    ("13 pièces", "12 unités"), ("12 €/kg", "12 €"), ("129,51 € HT", "129,51 € TTC"),
])
def test_falsifiable_ce_qui_ne_se_rapproche_pas_ne_conclut_pas(ecran, attendu):
    """Ni égal ni différent : sans unité à l'écran, ou sans conversion exacte, l'outil ne tranche pas."""
    assert _issue(ecran, attendu) == ln.UNITE_NON_VERIFIABLE


def test_une_monnaie_ne_se_convertit_jamais():
    assert _issue("100 €", "100 $") == ln.DIFFERENT
    assert "ne se convertit pas" in ln.comparer_valeurs(_lu("100 €"), _lu("100 $")).message


# ── Lot PT-03 : décision A24 (porteur, 2026-10-13, « prudent ») — jamais de réussite sans que l'unité soit vérifiée ────────


def _a24(ecran: str, attendu: str, devise: str = "") -> str:
    return ln.comparer_valeurs(_lu(ecran), _lu(attendu), devise_du_projet=devise).etat


@pytest.mark.parametrize("ecran, attendu, devise, issue", [
    # L'attendu n'écrit pas d'unité, l'écran en affiche une, rien n'est déclaré : on ne conclut pas.
    ("129,51 $", "129,51", "", ln.UNITE_NON_VERIFIABLE), ("129,51 €", "129,51", "", ln.UNITE_NON_VERIFIABLE),
    ("18 %", "18", "", ln.UNITE_NON_VERIFIABLE), ("12 pièces", "12", "", ln.UNITE_NON_VERIFIABLE),
    ("1,5 kg", "1,5", "", ln.UNITE_NON_VERIFIABLE), ("12 articles en stock", "12", "", ln.UNITE_NON_VERIFIABLE),
    ("TOP 5", "5", "", ln.UNITE_NON_VERIFIABLE),
    # … et un autre nombre n'accuse l'application que si aucune autre écriture n'est possible.
    ("130 $", "129,51", "", ln.DIFFERENT), ("20 %", "18", "", ln.DIFFERENT),
    ("18 %", "0,18", "", ln.UNITE_NON_VERIFIABLE), ("5 ‰", "0,005", "", ln.UNITE_NON_VERIFIABLE),
    ("1500 g", "1,5", "", ln.UNITE_NON_VERIFIABLE), ("13 pièces", "12", "", ln.UNITE_NON_VERIFIABLE),
    # Le projet a déclaré sa monnaie : un attendu sans unité est lu dans cette monnaie.
    ("129,51 €", "129,51", "EUR", ln.EGAL), ("129,51 $", "129,51", "EUR", ln.DIFFERENT),
    ("129,51 $", "129,51", "USD", ln.EGAL), ("129,51 $", "129,51", "CAD", ln.EGAL),
    ("130 €", "129,51", "EUR", ln.DIFFERENT), ("129,51 € TTC", "129,51", "EUR", ln.UNITE_NON_VERIFIABLE),
    ("12 pièces", "12", "EUR", ln.UNITE_NON_VERIFIABLE), ("18 %", "18", "EUR", ln.UNITE_NON_VERIFIABLE),
    ("129,51", "129,51", "EUR", ln.EGAL), ("129,51", "129,51 €", "EUR", ln.UNITE_NON_VERIFIABLE),
    # Une notation partagée ne prouve une monnaie précise que si le projet a déclaré celle-ci.
    ("5 $", "5 CAD", "", ln.UNITE_NON_VERIFIABLE), ("5 $", "5 CAD", "CAD", ln.EGAL), ("5 $", "5 CAD", "USD", ln.UNITE_NON_VERIFIABLE),
    ("5 $", "5 $", "", ln.EGAL), ("412 000 XAF", "412 000 F CFA", "", ln.UNITE_NON_VERIFIABLE),
    ("412 000 F CFA", "412 000 XOF", "XOF", ln.EGAL), ("412 000 FCFA", "412 000 F CFA", "", ln.EGAL),
    ("6 $", "5 CAD", "", ln.DIFFERENT), ("5 $", "5 EUR", "USD", ln.DIFFERENT),
])
def test_falsifiable_jamais_de_reussite_sans_que_l_unite_soit_verifiee(ecran, attendu, devise, issue):
    assert _a24(ecran, attendu, devise) == issue


def test_le_message_dit_dans_quelle_monnaie_l_attendu_a_ete_lu():
    resultat = ln.comparer_valeurs(_lu("129,51 $"), _lu("129,51"), devise_du_projet="EUR")

    assert resultat.etat == ln.DIFFERENT and "monnaie du projet (EUR)" in resultat.message
    assert "écrivez-la dans le test" in ln.comparer_valeurs(_lu("12 pièces"), _lu("12")).message


_ECRITURES = {"1 234,56": (",", None), "1,234.56": (".", ","), "1.234,56": (",", ".")}


def _lu_par(ecriture: str, texte: str, **plus):
    decimal, milliers = _ECRITURES[ecriture]
    return ln.lire_nombre(texte, decimal_si_ambigu=decimal, milliers_si_ambigu=milliers, **plus)


@pytest.mark.parametrize("ecriture, texte, valeur", [
    ("1 234,56", "1,234", "1.234"),
    ("1,234.56", "1,234", "1234"), ("1,234.56", "1.234", "1.234"),
    ("1.234,56", "1.234", "1234"), ("1.234,56", "1,234", "1.234"),
])
def test_l_ecriture_des_nombres_du_projet_tranche_pour_les_separateurs_qu_elle_nomme(ecriture, texte, valeur):
    assert _lu_par(ecriture, texte).valeur == D(valeur)
    assert _lu_par("1,234.56", "1,234 kg", avec_unite=True).valeur == D("1234")
    with pytest.raises(ln.LectureImpossible):
        ln.lire_nombre(texte)


@pytest.mark.parametrize("texte", ["1.234", "1.000", "1.234 kg", "1.234 €", "2.500"])
def test_falsifiable_une_ecriture_ne_dit_rien_d_un_separateur_qu_elle_n_emploie_pas(texte):
    """Troisième revue (N2, reproduit) : « 1 234,56 » dit que la virgule est décimale ; elle ne dit rien du point. Lire
    « 1.234 kg » comme 1234 kg validait un poids mille fois trop grand ; lire « 1.000 » comme 1000 accusait un arrondi."""
    with pytest.raises(ln.LectureImpossible):
        _lu_par("1 234,56", texte, avec_unite=True)


def test_falsifiable_les_gardes_de_l_ecriture_declaree():
    with pytest.raises(ln.LectureImpossible):
        ln.lire_nombre("00.123", decimal_si_ambigu=",", milliers_si_ambigu=".")     # un entier « 00 » n'est jamais des milliers
    assert ln.lire_nombre("0.123", decimal_si_ambigu=",", milliers_si_ambigu=".").valeur == D("0.123")
    for mauvais in ({"decimal_si_ambigu": ";"}, {"milliers_si_ambigu": " "}, {"decimal_si_ambigu": ",", "milliers_si_ambigu": ","}):
        with pytest.raises(ValueError):
            ln.lire_nombre("1.234", **mauvais)


@pytest.mark.parametrize("texte, valeur", [("1234.50", "1234.50"), ("1 234,56", "1234.56"), ("1,5", "1.5"), ("12.345.678", "12345678")])
def test_falsifiable_une_ecriture_lisible_sans_aide_se_lit_comme_avant(texte, valeur):
    """`separateur_decimal=","`, lui, lirait « 1234.50 » comme 123450 : il ne convient pas à un réglage de projet."""
    for declare in (",", "."):
        assert ln.lire_nombre(texte, decimal_si_ambigu=declare).valeur == D(valeur)
    assert ln.est_un_code_de_monnaie("XOF") and not ln.est_un_code_de_monnaie("ZZZ") and not ln.est_un_code_de_monnaie("$")


# ── Lot PT-03 : deuxième revue du 2026-10-13 — chaque cas a été REPRODUIT avant d'être corrigé ─────────────────────────────


@pytest.mark.parametrize("ecran, attendu", [
    # B1 — un multiplicateur collé à la devise était avalé puis ignoré : « 5 k€ » valait « 5 € ».
    ("5 €", "5 k€"), ("5 k€", "5 €"), ("5 M€", "5 €"), ("5 c€", "5 €"), ("12.5k €", "12.5 €"), ("$5k", "5 $"),
    # … et, à l'inverse, une application saine était accusée.
    ("12 k€", "12 000 €"), ("1,5 M€", "1 500 000 €"), ("$5k", "5000 $"),
    # B2 — un dollar qualifié était réduit au « $ » nu.
    ("5 HK$", "5 USD"), ("5 CA$", "5 USD"), ("5 US$", "5 CAD"),
    # B3 — la casse d'une unité inconnue était pliée : méga et milli confondus.
    ("5 MPa", "5 mPa"), ("5 mA", "5 MA"), ("5 MJ", "5 mJ"), ("5 Mw", "5 mW"), ("12 Pièces", "12 pièces"),
    # B4 — la mention d'un pourcentage n'était jamais comparée.
    ("5 %o", "5 %"), ("5 % annuel", "5 % mensuel"), ("20 % de remise", "20 % de hausse"), ("5 % annuel", "5 %"),
    # Une mention écrite d'un seul côté, ou dans une autre casse.
    ("129,51 €", "129,51 € TTC"), ("129,51 € HT", "129,51 €"), ("129,51 € ttc", "129,51 € TTC"),
])
def test_falsifiable_ce_qui_accompagne_une_unite_n_est_jamais_ignore(ecran, attendu):
    assert _issue(ecran, attendu) == ln.UNITE_NON_VERIFIABLE


@pytest.mark.parametrize("ecran, attendu, issue", [
    ("5 k€", "5 k€", ln.EGAL), ("129,51 € TTC", "129.51 EUR TTC", ln.EGAL), ("5 % annuel", "5 % annuel", ln.EGAL),
    ("5 MPa", "5 MPa", ln.EGAL),
    ("5 k€", "6 k€", ln.DIFFERENT), ("5 € TTC", "5 XOF TTC", ln.DIFFERENT), ("129,51 € TTC", "130 € TTC", ln.DIFFERENT),
    ("5 % annuel", "6 % annuel", ln.DIFFERENT), ("5 MPa", "6 MPa", ln.DIFFERENT),
])
def test_la_meme_mention_des_deux_cotes_se_compare_normalement(ecran, attendu, issue):
    assert _issue(ecran, attendu) == issue


@pytest.mark.parametrize("texte", ["(12 pièces)", "(5 kg)", "(3 jours)", "(7 UI/L)"])
def test_falsifiable_des_parentheses_ne_font_un_negatif_que_pour_un_montant(texte):
    """C1 — « (12 pièces) » était lu −12 pièces : une application saine sortait `non_conforme`."""
    with pytest.raises(ln.LectureImpossible):
        _lu(texte)
    assert _lu("(12,50 €)").valeur == D("-12.50")


@pytest.mark.parametrize("ecran, attendu, issue", [
    ("(3)", "3", ln.UNITE_NON_VERIFIABLE), ("3", "(3)", ln.UNITE_NON_VERIFIABLE),
    ("(3)", "-3", ln.UNITE_NON_VERIFIABLE), ("-3", "(3)", ln.UNITE_NON_VERIFIABLE),   # ni « différent de 3 » ni « égal à -3 »
    ("(3)", "(3)", ln.EGAL), ("(3)", "4", ln.DIFFERENT), ("(0)", "0", ln.EGAL),
    ("(12,50 €)", "-12,50 €", ln.EGAL), ("(12,50 €)", "12,50 €", ln.DIFFERENT),
    # Quatrième revue : seul le côté ENTRE PARENTHÈSES dit si la convention comptable s'applique.
    ("(3)", "3 €", ln.UNITE_NON_VERIFIABLE), ("(3)", "-3 €", ln.UNITE_NON_VERIFIABLE), ("3", "(3 €)", ln.DIFFERENT),
])
def test_un_nombre_nu_entre_parentheses_ne_conclut_pas_sur_son_signe(ecran, attendu, issue):
    assert _issue(ecran, attendu) == issue


@pytest.mark.parametrize("ecran, attendu, issue", [
    # C2 — un jour ouvré n'est pas 24 heures, une semaine n'est pas toujours sept jours.
    ("1 jour", "8 h", ln.UNITE_NON_VERIFIABLE), ("2 jours", "16 heures", ln.UNITE_NON_VERIFIABLE),
    ("1 semaine", "5 jours", ln.UNITE_NON_VERIFIABLE), ("2 jours", "48 h", ln.UNITE_NON_VERIFIABLE),
    ("3 jours", "3 j", ln.EGAL), ("3 jours", "4 jours", ln.DIFFERENT),
    # C3 — pour mille et pour cent sont la même grandeur.
    ("5 ‰", "0,5 %", ln.EGAL), ("0,5 %", "5 ‰", ln.EGAL), ("5 ‰", "5 %", ln.DIFFERENT),
    # C4 — après conversion, un écart plus petit que l'arrondi de l'affichage n'est ni un défaut ni une égalité.
    ("0,33 h", "20 min", ln.UNITE_NON_VERIFIABLE), ("100 km/h", "27,78 m/s", ln.UNITE_NON_VERIFIABLE),
    ("1 lb", "0,454 kg", ln.UNITE_NON_VERIFIABLE),
    ("3 h", "90 min", ln.DIFFERENT), ("1,6 kg", "1500 g", ln.DIFFERENT), ("100 km/h", "30 m/s", ln.DIFFERENT),
    ("1,50 kg", "1400 g", ln.DIFFERENT),
    # Borne COMPRISE : une application qui arrondit au demi supérieur affiche « 1 h » pour 30 minutes, « 2 h » pour 90.
    ("1 h", "30 min", ln.UNITE_NON_VERIFIABLE), ("2 h", "90 min", ln.UNITE_NON_VERIFIABLE),
    # L'arrondi de l'ATTENDU ne compte que s'il est écrit avec des décimales (« 1,5 kg » couvre de 1450 à 1550 g).
    ("1451 g", "1,5 kg", ln.UNITE_NON_VERIFIABLE), ("1449 g", "1,5 kg", ln.DIFFERENT),
    # Troisième revue : un attendu ENTIER n'élargit pas la fenêtre — ces quatre écarts n'étaient plus vus.
    ("91 min", "2 h", ln.DIFFERENT), ("149 min", "2 h", ln.DIFFERENT), ("600 kg", "1 t", ln.DIFFERENT),
    ("1400 g", "1 kg", ln.DIFFERENT),
    ("1 kg", "1400 g", ln.UNITE_NON_VERIFIABLE),      # l'ÉCRAN, lui, peut avoir arrondi 1,4 à 1
])
def test_falsifiable_une_conversion_n_accuse_ni_ne_valide_ce_qu_elle_ne_prouve_pas(ecran, attendu, issue):
    assert _issue(ecran, attendu) == issue


@pytest.mark.parametrize("texte", ["5²", "10⁶", "5½", "5 ²", "5 x²y½"])
def test_falsifiable_un_exposant_ou_une_fraction_n_est_pas_une_unite(texte):
    """« 5² » était lu 5, d'unité « ² »."""
    with pytest.raises(ln.LectureImpossible):
        _lu(texte)


def test_le_carre_d_une_unite_reste_lu_y_compris_derriere_une_monnaie():
    assert (_lu("250 m2").unite, _lu("250 m²").unite, _lu("3 cm3").unite) == ("m²", "m²", "cm³")
    assert (_lu("5 €/m2").nature, _lu("5 €/m2").unite) == (ln.INCONNUE, "EUR/m²")   # refusé avant : « 2 » pris pour un second nombre
    assert _issue("5 €/m2", "5 € / m²") == ln.EGAL


def test_falsifiable_une_valeur_construite_a_la_main_ne_peut_pas_etre_incoherente():
    """C6 — une monnaie sans monnaie se comparait `different`… à elle-même."""
    euros = ln.NombreLu(D(5), nature=ln.MONNAIE, unite="EUR")
    assert euros.devises == {"EUR"} and ln.comparer_valeurs(euros, euros).etat == ln.EGAL
    with pytest.raises(ValueError):
        ln.NombreLu(D(5), nature=ln.MONNAIE, unite="pièces")
    with pytest.raises(ValueError):
        ln.NombreLu(D(5), "EUR", True)


# ── Lot PT-03 : troisième revue du 2026-10-13 ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ecran, attendu, devise, issue", [
    # N1 (faux vert reproduit) — un RAPPORT réduisait « $ » à sa monnaie la plus courante : « 45 $/h » valait « 45 USD/h ».
    ("12 $/kg", "12 USD/kg", "", ln.UNITE_NON_VERIFIABLE), ("12 $/kg", "12 USD/kg", "CAD", ln.UNITE_NON_VERIFIABLE),
    ("1 500 F CFA/mois", "1500 XOF/mois", "XAF", ln.UNITE_NON_VERIFIABLE), ("5 kr/h", "5 SEK/h", "", ln.UNITE_NON_VERIFIABLE),
    ("5 £/h", "5 GBP/h", "", ln.UNITE_NON_VERIFIABLE), ("5 DH par jour", "5 MAD par jour", "", ln.UNITE_NON_VERIFIABLE),
    ("12 €/kg", "12 EUR/kg", "", ln.EGAL), ("12 $/kg", "12 $ / kg", "", ln.EGAL), ("13 $/kg", "12 $/kg", "", ln.DIFFERENT),
    # Un symbole partagé précisé par une mention n'est plus le symbole nu : on n'accuse pas (faux rouges reproduits).
    ("5 C$", "5 NIO", "", ln.UNITE_NON_VERIFIABLE), ("5 T$", "5 TOP", "", ln.UNITE_NON_VERIFIABLE),
    ("5 k€", "5 k$", "", ln.UNITE_NON_VERIFIABLE), ("5 C$", "5", "NIO", ln.UNITE_NON_VERIFIABLE),
    ("5 C$", "5", "EUR", ln.UNITE_NON_VERIFIABLE),
    # … sans mention, une autre monnaie reste un défaut.
    ("5 $", "5 NIO", "", ln.DIFFERENT), ("5 $", "5", "EUR", ln.DIFFERENT),
    # Quatrième revue : une mention SÉPARÉE du symbole (« HT ») ne change pas la monnaie — le défaut reste prouvé.
    ("129,51 $ HT", "129,51 € HT", "", ln.DIFFERENT), ("5 £ TTC", "5 € TTC", "", ln.DIFFERENT),
    ("5 $ HT", "6 € HT", "", ln.DIFFERENT), ("129,51 USD HT", "129,51", "EUR", ln.DIFFERENT),
    ("129,51 $ HT", "129,51", "EUR", ln.DIFFERENT), ("129,51 € HT", "129,51", "EUR", ln.UNITE_NON_VERIFIABLE),
])
def test_falsifiable_une_notation_partagee_n_est_jamais_reduite_a_une_seule_monnaie(ecran, attendu, devise, issue):
    assert _a24(ecran, attendu, devise) == issue
