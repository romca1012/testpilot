"""Lot Q2-b — l'application web à défauts injectables du banc d'agents, prouvée en HTTP RÉEL sur loopback.

Pourquoi ces tests. Cette application est l'ÉTALON du futur banc d'agents web : si un défaut était invisible, ou s'il
en altérait un autre, ou si l'application « saine » avait un défaut caché, toute mesure de faux verts / faux rouges
bâtie dessus serait fausse sans qu'on le voie. Chaque propriété est donc prouvée par des requêtes `urllib` contre un
serveur lancé dans un thread sur un port libre — aucun navigateur, aucun réseau extérieur.

L'INDÉPENDANCE des défauts est prouvée par une observation complète du même parcours sous chaque configuration : les
seules observations qui diffèrent de l'application saine sont EXACTEMENT celles que le défaut est censé changer
(`DIFFERENCES_ATTENDUES`, écrites ici à la main d'après la description du défaut, pas d'après un run).
"""

from __future__ import annotations

import http.client
import json
import math
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from decimal import Decimal
from fractions import Fraction
from html import unescape
from http.cookiejar import CookieJar
from pathlib import Path

import pytest
import yaml

from banc.app_web import calcul, defauts, pages, serveur

RACINE = Path(__file__).resolve().parent.parent
SPECS = RACINE / "specs" / "banc_local"
MDP_FAUX = "mauvais-mot-de-passe-1"


# ── Outillage HTTP ───────────────────────────────────────────────────────────────────────────────────────────


@contextmanager
def demarrer(codes=""):
    """Un serveur sur un port libre (127.0.0.1) dans un thread, arrêté proprement à la sortie."""
    srv = serveur.creer_serveur("127.0.0.1", 0, codes)
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        fil.join(timeout=5)


class Navigateur:
    """Un client HTTP qui garde ses cookies et suit les redirections, comme un navigateur sans JavaScript."""

    def __init__(self, base: str) -> None:
        self.base = base
        self._ouvreur = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def _appeler(self, requete: urllib.request.Request) -> tuple[int, str, str]:
        try:
            with self._ouvreur.open(requete, timeout=10) as reponse:
                return reponse.status, reponse.read().decode("utf-8"), reponse.geturl()
        except urllib.error.HTTPError as erreur:
            return erreur.code, erreur.read().decode("utf-8"), erreur.geturl()

    def get(self, chemin: str) -> tuple[int, str, str]:
        return self._appeler(urllib.request.Request(self.base + chemin))

    def post(self, chemin: str, champs: dict | None = None) -> tuple[int, str, str]:
        donnees = urllib.parse.urlencode(champs or {}).encode()
        return self._appeler(urllib.request.Request(self.base + chemin, data=donnees, method="POST"))

    def connecter(self) -> None:
        _, corps, _ = self.post("/connexion", {"identifiant": "testeur", "mot_de_passe": "motdepasse-test"})
        assert "<h1>Produits</h1>" in corps, "la connexion avec les identifiants de test doit réussir"


def appel_json(base: str, methode: str, chemin: str, corps: dict | None = None, entetes: dict | None = None):
    """Un appel aux routes `/__*` : (code, JSON décodé)."""
    donnees = json.dumps(corps).encode() if corps is not None else (b"" if methode == "POST" else None)
    requete = urllib.request.Request(base + chemin, data=donnees, method=methode, headers=entetes or {})
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as erreur:
        return erreur.code, json.loads(erreur.read() or b"{}")


def cellule(page: str, libelle: str) -> str | None:
    """La valeur de la ligne de tableau dont l'en-tête de ligne est `libelle` (None si absente)."""
    trouve = re.search(r'<th scope="row">' + re.escape(libelle) + r"</th><td>([^<]*)</td>", page)
    return unescape(trouve.group(1)) if trouve else None


def noms_produits(page: str) -> list[str]:
    return [unescape(n) for n in re.findall(r'<th scope="row">([^<]+)</th><td>', page)]


def etat(base: str) -> dict:
    code, donnees = appel_json(base, "GET", "/__etat")
    assert code == 200
    return donnees


def frais(base: str) -> Navigateur:
    """État remis à zéro (la session aussi) puis un navigateur connecté : le début de chaque cas d'une spec."""
    assert appel_json(base, "POST", "/__reset")[0] == 200
    navigateur = Navigateur(base)
    navigateur.connecter()
    return navigateur


# ── Le parcours complet observé sous une configuration ───────────────────────────────────────────────────────


def observer(base: str) -> dict:
    """Rejoue les parcours des 11 specs et rend ce que l'ÉCRAN et l'ÉTAT SERVEUR montrent, clé par clé."""
    obs: dict = {}

    # Connexion (un navigateur neuf par essai, sans session)
    appel_json(base, "POST", "/__reset")
    mauvais = Navigateur(base)
    _, corps, _ = mauvais.post("/connexion", {"identifiant": "testeur", "mot_de_passe": MDP_FAUX})
    obs["connexion_mauvais_mdp_acceptee"] = "<h1>Produits</h1>" in corps
    obs["connexion_mauvais_mdp_message"] = "Identifiant ou mot de passe incorrect." in corps
    bon = Navigateur(base)
    _, corps, _ = bon.post("/connexion", {"identifiant": "testeur", "mot_de_passe": "motdepasse-test"})
    obs["connexion_bon_mdp_acceptee"] = "Connecté en tant que <strong>testeur</strong>" in corps
    inconnu = Navigateur(base)
    _, corps, _ = inconnu.post("/connexion", {"identifiant": "intrus", "mot_de_passe": MDP_FAUX})
    obs["connexion_identifiant_inconnu_acceptee"] = "<h1>Produits</h1>" in corps

    # Recherche
    nav = frais(base)
    obs["recherche_souris"] = noms_produits(nav.get("/produits?q=souris")[1])
    obs["recherche_majuscules"] = noms_produits(nav.get("/produits?q=CLAVIER")[1])
    obs["recherche_zzz_message"] = "Aucun produit ne correspond à « zzz »." in nav.get("/produits?q=zzz")[1]
    obs["recherche_vide"] = len(noms_produits(nav.get("/produits")[1]))

    # Client : nom vide
    nav = frais(base)
    _, corps, _ = nav.post("/clients/nouveau", {"nom": "", "ville": "Lyon"})
    obs["client_vide_refuse"] = "<h1>Nouveau client</h1>" in corps
    obs["client_vide_message"] = "Le nom est obligatoire." in corps
    obs["client_vide_nb_etat"] = len(etat(base)["enregistrements"])

    # Client : 41 caractères puis 40
    nav = frais(base)
    _, corps, _ = nav.post("/clients/nouveau", {"nom": "N" * 41, "ville": ""})
    obs["client_41_refuse"] = "<h1>Nouveau client</h1>" in corps
    obs["client_41_message"] = "Le nom ne doit pas dépasser 40 caractères." in corps
    obs["client_41_nb_etat"] = len(etat(base)["enregistrements"])
    _, corps, _ = nav.post("/clients/nouveau", {"nom": "N" * 40, "ville": ""})
    obs["client_40_confirmation"] = "a été créé." in corps

    # Client valide
    nav = frais(base)
    _, corps, _ = nav.post("/clients/nouveau", {"nom": "Dupont SARL", "ville": "Lyon"})
    obs["client_valide_confirmation"] = "Le client « Dupont SARL » a été créé." in corps
    liste = nav.get("/clients")[1]
    obs["client_valide_dans_liste"] = "Dupont SARL" in liste and "Lyon" in liste
    obs["client_valide_nb_etat"] = len(etat(base)["enregistrements"])

    # Panier : TVA et arrondi
    nav = frais(base)
    nav.post("/panier/ajouter", {"produit": "P001", "quantite": "2"})
    nav.post("/panier/ajouter", {"produit": "P005", "quantite": "1"})
    page = nav.get("/panier")[1]
    ligne = re.search(r"Clavier mécanique</th><td>[^<]*</td><td>.*?</td><td>([^<]*)</td>", page)
    obs["panier_ligne_clavier"] = unescape(ligne.group(1)) if ligne else None
    for cle, libelle in (
        ("panier_sous_total", "Sous-total HT"),
        ("panier_tva", "TVA (18 %)"),
        ("panier_ttc", "Total TTC"),
    ):
        obs[cle] = cellule(page, libelle)
    nav.post("/panier/mettre-a-jour", {"quantite_P001": "2", "quantite_P005": "0", "remise": "0"})
    nav.post("/panier/mettre-a-jour", {"quantite_P001": "0", "remise": "0"})
    page = nav.get("/panier")[1]
    obs["panier_zero_vide"] = "Votre panier est vide." in page
    obs["panier_zero_ttc"] = cellule(page, "Total TTC")

    # Panier : remise puis remise invalide
    nav = frais(base)
    nav.post("/panier/ajouter", {"produit": "P005", "quantite": "1"})
    page = nav.post("/panier/mettre-a-jour", {"quantite_P005": "1", "remise": "10"})[1]
    for cle, libelle in (
        ("remise_montant", "Remise (10 %)"),
        ("remise_ht", "Total HT après remise"),
        ("remise_tva", "TVA (18 %)"),
        ("remise_ttc", "Total TTC"),
    ):
        obs[cle] = cellule(page, libelle)
    nav.post("/panier/mettre-a-jour", {"quantite_P005": "1", "remise": "0"})
    page = nav.post("/panier/mettre-a-jour", {"quantite_P005": "1", "remise": "120"})[1]
    obs["remise_invalide_message"] = "La remise doit être comprise entre 0 et 100." in page
    obs["remise_invalide_ttc"] = cellule(page, "Total TTC")

    # Commande : panier vide refusé, puis confirmation et persistance
    nav = frais(base)
    _, corps, _ = nav.post("/commande/confirmer")
    obs["commande_vide_message"] = "Le panier est vide." in corps
    obs["commande_vide_confirmee"] = "<h1>Commande confirmée</h1>" in corps
    nav.post("/panier/ajouter", {"produit": "P006", "quantite": "3"})
    _, corps, _ = nav.post("/commande/confirmer")
    numero = re.search(r'id="numero-commande">(CMD-\d{4})<', corps)
    obs["commande_numero"] = numero.group(1) if numero else None
    obs["commande_total_affiche"] = (re.search(r"Total TTC : ([^<]*)</p>", corps) or [None, None])[1]
    obs["commande_panier_vide_apres"] = "Votre panier est vide." in nav.get("/panier")[1]
    commandes = etat(base)["commandes"]
    obs["commande_nb_etat"] = len(commandes)
    obs["commande_total_etat"] = commandes[0]["total_ttc"] if commandes else None
    obs["commande_numero_etat"] = commandes[0]["numero"] if commandes else None
    obs["commande_lignes_etat"] = (
        [(ligne["nom"], ligne["quantite"]) for ligne in commandes[0]["lignes"]] if commandes else None
    )
    obs["commande_panier_etat_vide"] = etat(base)["panier"]["lignes"] == []

    # Contrôle d'accès (IT-3e, 2026-10-20) : 17 refusé, 18 accepté, un âge illisible refusé avec son message
    nav = frais(base)
    obs["acces_17_refuse"] = "Accès refusé : il faut avoir 18 ans ou plus." in unescape(
        nav.post("/acces", {"client": "Dupont SARL", "age": "17"})[1])
    obs["acces_18_bienvenue"] = "Bienvenue, Dupont SARL !" in unescape(
        nav.post("/acces", {"client": "Dupont SARL", "age": "18"})[1])
    obs["acces_16_refuse"] = "Accès refusé" in unescape(nav.post("/acces", {"client": "", "age": "16"})[1])
    obs["acces_illisible_message"] = "L'âge doit être un nombre entier entre 0 et 130." in unescape(
        nav.post("/acces", {"client": "", "age": "dix-sept"})[1])
    return obs


# Ce que CHAQUE défaut doit changer — et rien d'autre. Écrit d'après la description du défaut (defauts.py), jamais
# d'après un run : c'est la preuve d'indépendance (« n'altère QUE son comportement »).
DIFFERENCES_ATTENDUES: dict[str, set[str]] = {
    "total_faux": {
        "panier_ttc",
        "remise_ttc",
        "remise_invalide_ttc",
        "commande_total_affiche",
        "commande_total_etat",
    },
    "validation_absente": {"client_vide_refuse", "client_vide_message", "client_vide_nb_etat"},
    "message_erreur_absent": {"client_vide_message", "client_41_message"},
    "etat_non_enregistre": {
        "client_valide_dans_liste",
        "client_valide_nb_etat",
        "commande_nb_etat",
        "commande_total_etat",
        "commande_numero_etat",
        "commande_lignes_etat",
    },
    # (`recherche_vide` n'y figure pas : une recherche vide liste déjà tout, comme l'application saine)
    "filtre_ignore": {"recherche_souris", "recherche_majuscules", "recherche_zzz_message"},
    "login_accepte_tout": {"connexion_mauvais_mdp_acceptee", "connexion_mauvais_mdp_message"},
    # Seul 17 ans change : 16 reste refusé, 18 accepté (« n'altère QUE la limite »).
    "limite_age_decalee": {"acces_17_refuse"},
}


@pytest.fixture(scope="module")
def observations() -> dict[str, dict]:
    """Une observation complète par configuration : « sain » puis chaque défaut seul (un serveur chacun)."""
    resultats: dict[str, dict] = {}
    for config in ("sain", *defauts.CODES):
        with demarrer("" if config == "sain" else config) as srv:
            resultats[config] = observer(srv.url)
    return resultats


# ── L'application saine ──────────────────────────────────────────────────────────────────────────────────────


def test_application_saine_n_a_aucun_defaut(monkeypatch):
    monkeypatch.delenv(serveur.ENV_DEFAUTS, raising=False)
    with demarrer(None) as srv:  # None = lire la variable d'environnement, ici absente
        assert srv.defauts.liste() == []
        assert appel_json(srv.url, "GET", "/__defauts")[1]["defauts"] == []


def test_application_saine_donne_les_valeurs_des_specs(observations):
    """Les valeurs ci-dessous viennent des SPECS écrites à la main (specs/banc_local), pas d'un run."""
    sain = observations["sain"]
    assert sain["connexion_bon_mdp_acceptee"] is True
    assert sain["connexion_mauvais_mdp_acceptee"] is False and sain["connexion_mauvais_mdp_message"] is True
    assert sain["connexion_identifiant_inconnu_acceptee"] is False
    assert sain["recherche_souris"] == ["Souris sans fil", "Tapis de souris"]
    assert sain["recherche_majuscules"] == ["Clavier mécanique"]
    assert sain["recherche_zzz_message"] is True and sain["recherche_vide"] == 6
    assert sain["client_vide_refuse"] and sain["client_vide_message"] and sain["client_vide_nb_etat"] == 0
    assert sain["client_41_refuse"] and sain["client_41_message"] and sain["client_41_nb_etat"] == 0
    assert sain["client_40_confirmation"] is True
    assert sain["client_valide_confirmation"] and sain["client_valide_dans_liste"]
    assert sain["client_valide_nb_etat"] == 1
    assert (sain["panier_ligne_clavier"], sain["panier_sous_total"]) == ("99,80 €", "109,75 €")
    assert (sain["panier_tva"], sain["panier_ttc"]) == ("19,76 €", "129,51 €")
    assert sain["panier_zero_vide"] is True and sain["panier_zero_ttc"] == "0,00 €"
    assert (sain["remise_montant"], sain["remise_ht"]) == ("1,00 €", "8,95 €")
    assert (sain["remise_tva"], sain["remise_ttc"]) == ("1,61 €", "10,56 €")
    assert sain["remise_invalide_message"] is True and sain["remise_invalide_ttc"] == "11,74 €"
    assert sain["commande_vide_message"] is True and sain["commande_vide_confirmee"] is False
    assert sain["commande_numero"] == "CMD-0001" and sain["commande_total_affiche"] == "42,48 €"
    assert sain["commande_panier_vide_apres"] is True and sain["commande_panier_etat_vide"] is True
    assert sain["commande_nb_etat"] == 1 and sain["commande_total_etat"] == "42.48"
    assert sain["commande_numero_etat"] == "CMD-0001"
    assert sain["commande_lignes_etat"] == [("Tapis de souris", 3)]
    assert sain["acces_17_refuse"] and sain["acces_18_bienvenue"] and sain["acces_16_refuse"]
    assert sain["acces_illisible_message"] is True


# ── Chaque défaut est observable et n'altère QUE son comportement ────────────────────────────────────────────


def test_les_differences_attendues_couvrent_exactement_le_catalogue():
    assert set(DIFFERENCES_ATTENDUES) == set(defauts.CODES)
    assert all(DIFFERENCES_ATTENDUES[code] for code in defauts.CODES), "un défaut sans effet observable"


@pytest.mark.parametrize("code", defauts.CODES)
def test_defaut_observable_et_independant(code, observations):
    sain, avec_defaut = observations["sain"], observations[code]
    assert set(sain) == set(avec_defaut)
    differences = {cle for cle in sain if sain[cle] != avec_defaut[cle]}
    assert differences, f"{code} : aucun effet observable — le défaut est invisible"
    assert differences == DIFFERENCES_ATTENDUES[code], (
        f"{code} : observations changées {sorted(differences)} au lieu de {sorted(DIFFERENCES_ATTENDUES[code])}"
    )


def test_valeurs_precises_sous_les_defauts(observations):
    """Au-delà « ça diffère » : le défaut produit la valeur fautive décrite, pas n'importe quelle autre."""
    faux = observations["total_faux"]
    assert (faux["panier_ttc"], faux["remise_ttc"], faux["remise_invalide_ttc"]) == ("130,81 €", "10,67 €", "11,86 €")
    assert faux["panier_tva"] == "19,76 €", "la ligne de TVA reste juste : seul le total TTC est majoré"
    assert faux["panier_zero_ttc"] == "0,00 €", "0,00 majoré de 1 % reste 0,00"
    assert observations["validation_absente"]["client_vide_nb_etat"] == 1
    assert observations["validation_absente"]["client_41_message"] is True, "la limite de 40 reste appliquée"
    assert observations["message_erreur_absent"]["client_vide_refuse"] is True, "le refus a bien lieu"
    assert observations["message_erreur_absent"]["client_41_nb_etat"] == 0
    assert observations["etat_non_enregistre"]["commande_numero"] == "CMD-0001", "la confirmation s'affiche"
    assert observations["etat_non_enregistre"]["client_valide_confirmation"] is True
    assert observations["filtre_ignore"]["recherche_souris"] == [p.nom for p in calcul.PRODUITS]
    assert observations["login_accepte_tout"]["connexion_mauvais_mdp_acceptee"] is True
    assert observations["login_accepte_tout"]["connexion_identifiant_inconnu_acceptee"] is False


def test_les_defauts_se_cumulent_sans_s_influencer():
    """Deux défauts actifs ensemble produisent l'union de leurs effets (la composition ne crée rien de neuf)."""
    with demarrer("") as sain, demarrer("total_faux,filtre_ignore") as double:
        ref, combine = observer(sain.url), observer(double.url)
    differences = {cle for cle in ref if ref[cle] != combine[cle]}
    assert differences == DIFFERENCES_ATTENDUES["total_faux"] | DIFFERENCES_ATTENDUES["filtre_ignore"]


@pytest.mark.parametrize("code", ["total_faux", "etat_non_enregistre"])
def test_bascule_a_chaud_equivaut_a_un_demarrage_avec_le_defaut(code, observations):
    with demarrer("") as srv:
        assert appel_json(srv.url, "POST", "/__defauts", {"defauts": [code]}) == (200, {"defauts": [code]})
        assert appel_json(srv.url, "GET", "/__defauts")[1]["defauts"] == [code]
        assert observer(srv.url) == observations[code]
        assert appel_json(srv.url, "POST", "/__defauts", {"defauts": []})[1] == {"defauts": []}
        assert observer(srv.url) == observations["sain"]


def test_variable_d_environnement_des_defauts(monkeypatch):
    monkeypatch.setenv(serveur.ENV_DEFAUTS, "total_faux, filtre_ignore")
    with demarrer(None) as srv:
        assert srv.defauts.liste() == ["total_faux", "filtre_ignore"]
    monkeypatch.setenv(serveur.ENV_DEFAUTS, "total_fau")
    with pytest.raises(defauts.DefautInconnu):
        serveur.creer_serveur(defauts=None)


def test_bascule_refuse_un_code_inconnu_sans_rien_changer():
    with demarrer("filtre_ignore") as srv:
        code, corps = appel_json(srv.url, "POST", "/__defauts", {"defauts": ["inconnu"]})
        assert code == 400 and "inconnu" in corps["erreur"]
        assert appel_json(srv.url, "GET", "/__defauts")[1]["defauts"] == ["filtre_ignore"]
        requete = urllib.request.Request(srv.url + "/__defauts", data=b"pas du json", method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(requete, timeout=10)
        assert exc.value.code == 400


def test_etat_ne_revele_jamais_les_defauts_actifs():
    with demarrer("total_faux") as srv:
        brut = json.dumps(etat(srv.url))
        assert "total_faux" not in brut and "defaut" not in brut.lower()
        assert set(etat(srv.url)) == {"commandes", "panier", "enregistrements"}


# ── Remise à zéro ────────────────────────────────────────────────────────────────────────────────────────────


def test_reset_remet_tout_a_zero_mais_garde_les_defauts():
    with demarrer("filtre_ignore") as srv:
        nav = frais(srv.url)
        nav.post("/clients/nouveau", {"nom": "Dupont SARL", "ville": "Lyon"})
        nav.post("/panier/ajouter", {"produit": "P001", "quantite": "2"})
        nav.post("/panier/mettre-a-jour", {"quantite_P001": "2", "remise": "15"})
        nav.post("/commande/confirmer")
        nav.post("/panier/ajouter", {"produit": "P002", "quantite": "1"})
        avant = etat(srv.url)
        assert avant["commandes"] and avant["enregistrements"] and avant["panier"]["lignes"]
        # A75 (2026-10-20) : la remise à zéro le dit — seule preuve acceptée par TestPilot.
        assert appel_json(srv.url, "POST", "/__reset") == (200, {"ok": True, "remis_a_zero": True})
        assert etat(srv.url) == {
            "commandes": [],
            "panier": {"lignes": [], "remise_pct": "0"},
            "enregistrements": [],
        }
        assert nav.get("/produits")[2].endswith("/connexion"), "la session est effacée avec l'état"
        assert appel_json(srv.url, "GET", "/__defauts")[1]["defauts"] == ["filtre_ignore"]
        nav.connecter()
        nav.post("/panier/ajouter", {"produit": "P002", "quantite": "1"})
        nav.post("/commande/confirmer")
        assert etat(srv.url)["commandes"][0]["numero"] == "CMD-0001", "la numérotation repart de 1"


# ── Loopback uniquement ──────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("hote", "attendu"),
    [
        ("127.0.0.1", True), ("127.0.0.2", True), ("::1", True), ("[::1]", True), ("localhost", True),
        ("LOCALHOST", True), ("::ffff:127.0.0.1", True),
        ("0.0.0.0", False), ("192.168.1.10", False), ("10.0.0.5", False), ("8.8.8.8", False),
        ("::", False), ("2001:db8::1", False), ("::ffff:10.0.0.5", False),
        ("example.com", False), ("127.0.0.1.evil.example", False), ("", False), ("n'importe quoi", False),
    ],
)
def test_est_hote_loopback(hote, attendu):
    assert serveur.est_hote_loopback(hote) is attendu


@pytest.mark.parametrize("hote", ["0.0.0.0", "192.168.1.10", "example.com", "", "::1", "::"])
def test_ecoute_refusee_hors_bouclage_avant_d_ouvrir_la_socket(hote):
    with pytest.raises(serveur.HoteRefuse):
        serveur.creer_serveur(hote, 0, "")
    assert serveur.main(["--hote", hote]) == 2


def test_ecoute_acceptee_sur_le_bouclage_avec_port_libre():
    assert serveur.exiger_hote_d_ecoute("localhost") == "127.0.0.1"
    with demarrer("") as a, demarrer("") as b:
        assert a.server_address[0] == "127.0.0.1" and a.server_address[1] > 0
        assert a.server_address[1] != b.server_address[1], "deux instances = deux ports libres"


def test_main_refuse_un_defaut_inconnu(capsys):
    assert serveur.main(["--defauts", "nimporte"]) == 2
    assert "nimporte" in capsys.readouterr().err


def _requete_simulee(adresse_client: str, en_tete_host: str | None):
    """Un gestionnaire sans socket, pour contrôler le refus d'un client NON loopback (impossible à produire en vrai
    depuis un test qui n'écoute que sur 127.0.0.1)."""
    gestionnaire = object.__new__(serveur._Requete)
    gestionnaire.client_address = (adresse_client, 54321)
    gestionnaire.headers = {} if en_tete_host is None else {"Host": en_tete_host}
    return gestionnaire


@pytest.mark.parametrize(
    ("client", "hote", "autorise"),
    [
        ("127.0.0.1", "127.0.0.1:8010", True),
        ("127.0.0.1", "localhost:8010", True),
        ("::1", "[::1]:8010", True),
        ("203.0.113.9", "127.0.0.1:8010", False),   # client distant
        ("192.168.1.20", "127.0.0.1:8010", False),  # client du réseau local
        ("127.0.0.1", "evil.example", False),        # navigateur détourné par un nom de domaine tiers
        ("127.0.0.1", "evil.example:8010", False),
        ("127.0.0.1", None, False),                  # pas d'en-tête Host
    ],
)
def test_controle_des_routes_banc(client, hote, autorise):
    assert _requete_simulee(client, hote)._client_autorise() is autorise


def test_routes_banc_refusees_si_l_hote_n_est_pas_de_bouclage():
    """De bout en bout : la requête réelle part de 127.0.0.1 mais annonce un hôte tiers → 403, état intact."""
    with demarrer("") as srv:
        nav = frais(srv.url)
        nav.post("/clients/nouveau", {"nom": "Dupont SARL", "ville": ""})
        port = srv.server_address[1]
        for methode, chemin, corps in (
            ("POST", "/__reset", b""),
            ("GET", "/__etat", None),
            ("POST", "/__defauts", b'{"defauts": ["total_faux"]}'),
            ("GET", "/__defauts", None),
        ):
            connexion = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connexion.putrequest(methode, chemin, skip_host=True)
            connexion.putheader("Host", "evil.example")
            connexion.putheader("Content-Length", str(len(corps or b"")))
            connexion.endheaders(corps or b"")
            reponse = connexion.getresponse()
            assert reponse.status == 403, f"{methode} {chemin}"
            reponse.read()
            connexion.close()
        assert len(etat(srv.url)["enregistrements"]) == 1, "le reset refusé n'a rien effacé"
        assert srv.defauts.liste() == [], "la bascule refusée n'a rien activé"


# ── Le calcul : référence INDÉPENDANTE (fractions exactes, arrondi écrit à la main) ──────────────────────────


def _demi_vers_le_haut(valeur: Fraction) -> Fraction:
    """Au centime, demi-centime vers le haut, sans `Decimal` ni flottant (valeurs positives)."""
    return Fraction(math.floor(valeur * 100 + Fraction(1, 2)), 100)


def _reference(lignes: list[tuple[str, int]], pct: str) -> tuple[Fraction, Fraction, Fraction, Fraction, Fraction]:
    sous_total = sum((_demi_vers_le_haut(Fraction(prix) * quantite) for prix, quantite in lignes), Fraction(0))
    remise = _demi_vers_le_haut(sous_total * Fraction(pct) / 100)
    ht = sous_total - remise
    tva = _demi_vers_le_haut(ht * Fraction(18, 100))
    return sous_total, remise, ht, tva, ht + tva


# (lignes, remise %, sous-total, remise, HT, TVA, TTC) — les valeurs attendues sont calculées À LA MAIN.
CAS_DE_CALCUL = [
    pytest.param([("49.90", 2), ("9.95", 1)], "0", "109.75", "0.00", "109.75", "19.76", "129.51", id="spec-panier"),
    pytest.param([("9.95", 1)], "10", "9.95", "1.00", "8.95", "1.61", "10.56", id="remise-demi-centime"),
    pytest.param([("25.25", 1)], "0", "25.25", "0.00", "25.25", "4.55", "29.80", id="tva-demi-centime"),
    pytest.param([("49.90", 0)], "0", "0.00", "0.00", "0.00", "0.00", "0.00", id="quantite-zero"),
    pytest.param(
        [("159.00", 3), ("79.99", 2), ("12.00", 1)], "12.5", "648.98", "81.12", "567.86", "102.21", "670.07",
        id="plusieurs-lignes-remise-decimale",
    ),
    pytest.param([("9.95", 1)], "100", "9.95", "9.95", "0.00", "0.00", "0.00", id="remise-totale"),
]


@pytest.mark.parametrize(("lignes", "pct", "sous", "remise", "ht", "tva", "ttc"), CAS_DE_CALCUL)
def test_calcul_numeriquement_juste(lignes, pct, sous, remise, ht, tva, ttc):
    totaux = calcul.calculer([(Decimal(p), q) for p, q in lignes], Decimal(pct))
    attendu = tuple(Decimal(v) for v in (sous, remise, ht, tva, ttc))
    assert (totaux.sous_total, totaux.remise, totaux.total_ht, totaux.tva, totaux.total_ttc) == attendu
    # La référence à fractions (aucun code commun avec `calcul`) doit donner la même chose que les valeurs à la main.
    assert _reference(lignes, pct) == tuple(Fraction(v) for v in (sous, remise, ht, tva, ttc))


def test_calcul_panier_vide_et_formats():
    assert calcul.calculer([], Decimal("0")).total_ttc == Decimal("0.00")
    assert calcul.formater_montant(Decimal("1234.5")) == "1234,50 €"
    assert calcul.formater_pourcentage(Decimal("10")) == "10"
    assert calcul.formater_pourcentage(Decimal("12.50")) == "12,5"
    assert calcul.majorer_un_pour_cent(Decimal("129.51")) == Decimal("130.81")
    assert calcul.majorer_un_pour_cent(Decimal("0.00")) == Decimal("0.00")


@pytest.mark.parametrize("texte", ["", "abc", "-1", "1.5", "100", "²", "  "])
def test_quantite_invalide_refusee(texte):
    with pytest.raises(ValueError, match="quantité"):
        calcul.analyser_quantite(texte)


@pytest.mark.parametrize("texte", ["-1", "100,01", "abc", "NaN", "Infinity", "1e400"])
def test_remise_invalide_refusee(texte):
    with pytest.raises(ValueError, match="remise"):
        calcul.analyser_remise(texte)


def test_remise_valide_accepte_virgule_et_vide():
    assert calcul.analyser_remise("12,5") == Decimal("12.5")
    assert calcul.analyser_remise("") == Decimal("0")
    assert calcul.analyser_remise(" 100 ") == Decimal("100")


# ── Pages réalistes (ce qu'un agent verra en inspectant) ─────────────────────────────────────────────────────


def test_pages_realistes_etiquettes_roles_et_erreurs_dans_le_dom():
    with demarrer("") as srv:
        anonyme = Navigateur(srv.url)
        _, accueil, url = anonyme.get("/")
        assert url.endswith("/connexion")
        assert re.search(r'<label for="identifiant">Identifiant</label>\s*<input[^>]*id="identifiant"', accueil)
        assert re.search(r'<label for="mot-de-passe">Mot de passe</label>\s*<input[^>]*type="password"', accueil)
        assert '<html lang="fr">' in accueil and "<title>Connexion" in accueil
        assert anonyme.get("/produits")[2].endswith("/connexion"), "page protégée sans session"
        assert anonyme.get("/commande/CMD-0001")[2].endswith("/connexion")

        nav = frais(srv.url)
        produits = nav.get("/produits")[1]
        assert 'role="search"' in produits and '<nav aria-label="Navigation principale">' in produits
        assert "<caption>Liste des produits</caption>" in produits and 'scope="col"' in produits
        assert re.search(r'<label for="recherche">Rechercher un produit</label>', produits)

        formulaire = nav.get("/clients/nouveau")[1]
        champ = re.search(r'<input[^>]*id="nom"[^>]*>', formulaire).group(0)
        assert "required" in champ and 'aria-required="true"' in champ
        assert "maxlength" not in champ, "sinon le navigateur tronquerait la saisie et le refus n'aurait jamais lieu"
        assert "novalidate" in formulaire, "sinon le navigateur bloquerait le champ vide avant le serveur"
        assert "40 caractères" in formulaire

        refus = nav.post("/clients/nouveau", {"nom": "", "ville": ""})[1]
        assert '<p id="erreur-nom" class="erreur" role="alert">Le nom est obligatoire.</p>' in refus
        assert 'aria-invalid="true"' in refus and "aria-describedby=\"aide-nom erreur-nom\"" in refus

        nav.post("/panier/ajouter", {"produit": "P002", "quantite": "1"})
        panier = nav.get("/panier")[1]
        assert "<caption>Récapitulatif</caption>" in panier and '<label for="remise">Remise (%)</label>' in panier
        assert "Valider la commande" in panier and "Recalculer" in panier


def test_message_erreur_absent_retire_tout_element_d_erreur():
    with demarrer("message_erreur_absent") as srv:
        nav = frais(srv.url)
        refus = nav.post("/clients/nouveau", {"nom": "", "ville": ""})[1]
        assert "<h1>Nouveau client</h1>" in refus
        assert "erreur-nom" not in refus and "role=\"alert\"" not in refus and "aria-invalid" not in refus


def test_quantites_aux_limites_du_panier():
    with demarrer("") as srv:
        nav = frais(srv.url)
        _, corps, _ = nav.post("/panier/ajouter", {"produit": "P001", "quantite": "0"})
        assert "La quantité doit être un entier entre 1 et 99." in corps
        assert etat(srv.url)["panier"]["lignes"] == []
        nav.post("/panier/ajouter", {"produit": "P001", "quantite": "99"})
        _, corps, _ = nav.post("/panier/ajouter", {"produit": "P001", "quantite": "1"})
        assert "ne peut pas dépasser 99" in corps
        assert etat(srv.url)["panier"]["lignes"][0]["quantite"] == 99
        assert nav.post("/panier/ajouter", {"produit": "P999", "quantite": "1"})[0] == 404


def test_un_refus_de_mise_a_jour_ne_change_rien():
    with demarrer("") as srv:
        nav = frais(srv.url)
        nav.post("/panier/ajouter", {"produit": "P005", "quantite": "2"})
        _, corps, _ = nav.post("/panier/mettre-a-jour", {"quantite_P005": "7", "remise": "150"})
        assert "La remise doit être comprise entre 0 et 100." in corps
        assert etat(srv.url)["panier"] == {
            "lignes": [{"produit": "P005", "nom": "Câble HDMI", "quantite": 2, "prix_unitaire": "9.95"}],
            "remise_pct": "0",
        }, "ni la quantité 7 ni la remise 150 ne doivent avoir été retenues"


def test_deconnexion_efface_la_session():
    with demarrer("") as srv:
        nav = frais(srv.url)
        assert nav.post("/deconnexion")[2].endswith("/connexion")
        assert nav.get("/produits")[2].endswith("/connexion")


def test_pages_pures_echappent_le_html():
    page = pages.client_cree("testeur", "<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


# ── Cohérence du catalogue, des specs, des attendus et de apps.yaml ──────────────────────────────────────────


def _yaml(chemin: Path) -> dict:
    return yaml.safe_load(chemin.read_text(encoding="utf-8"))


def _specs() -> set[str]:
    return {p.stem for p in SPECS.glob("*.md")}


def test_nombre_et_forme_des_specs():
    noms = _specs()
    # 2026-10-20 (IT-3e) : 11 avec le contrôle d'accès (classes de valeurs, défaut à la limite).
    assert 8 <= len(noms) <= 11
    for nom in noms:
        texte = (SPECS / f"{nom}.md").read_text(encoding="utf-8")
        for section in ("## Contexte technique", "## Besoin", "## Parcours", "## Critère de réussite"):
            assert section in texte, f"{nom} : section « {section} » manquante"
    assert sum(1 for n in noms if n.startswith("panier_")) >= 2, "au moins 2 specs portent sur le calcul du total"
    assert "commande_persistance_serveur" in noms, "au moins 1 spec porte sur la persistance côté serveur"


def test_attendus_ne_citent_que_des_defauts_et_des_specs_existants():
    attendus = _yaml(SPECS / "attendus.yaml")
    specs = _specs()
    assert set(attendus["sain"]) == specs, "chaque spec a un attendu sur l'application saine, et seulement elles"
    assert set(attendus["sain"].values()) == {"passed"}
    assert set(attendus["defauts"]) == set(defauts.CODES), "chaque défaut a au moins un cas qui doit le détecter"
    for code, cas in attendus["defauts"].items():
        assert cas, f"{code} : aucun cas ne le détecte — ajouter la spec qui le couvre, jamais retirer le défaut"
        assert set(cas) <= specs, f"{code} cite une spec inexistante : {sorted(set(cas) - specs)}"
        assert set(cas.values()) == {"failed"}


def test_apps_yaml_decrit_l_application_telle_qu_elle_est():
    app = _yaml(SPECS / "apps.yaml")["apps"]["boutique_locale"]
    assert app["hote"] == "127.0.0.1"
    assert set(app["defauts"]) == set(defauts.CODES)
    assert app["variable_defauts"] == serveur.ENV_DEFAUTS
    compte = app["comptes"][0]
    assert (compte["identifiant"], compte["mot_de_passe"]) == (serveur.IDENTIFIANT_TEST, serveur.MOT_DE_PASSE_TEST)
    assert "python -m banc.app_web.serveur" in app["lancement"]


def test_chaque_defaut_est_documente():
    for code, defaut in defauts.CATALOGUE.items():
        assert defaut.code == code and defaut.description.endswith(".") and defaut.observable
    assert defauts.analyser("") == frozenset() and defauts.analyser(None) == frozenset()
    with pytest.raises(defauts.DefautInconnu):
        defauts.analyser("total_faux,fautedefrappe")
    with pytest.raises(defauts.DefautInconnu):
        defauts.DefautsActifs().actif("fautedefrappe")
