"""Serveur de l'application web à défauts injectables du banc d'agents (lot Q2-b).

Lancement : `python -m banc.app_web.serveur --defauts total_faux` (ou `TP_DEFAUTS=total_faux`). Stdlib seulement
(`http.server.ThreadingHTTPServer`), état EN MÉMOIRE, aucun fichier écrit.

⚠️ LOOPBACK UNIQUEMENT, à deux endroits. (1) À l'écoute : tout hôte qui n'est pas une adresse de bouclage est REFUSÉ
avant d'ouvrir la socket (`0.0.0.0` exposerait des défauts faits pour se tromper à tout le réseau). (2) Au contrôle :
les routes `/__*` (remise à zéro, état serveur, bascule des défauts) refusent un client dont l'adresse n'est pas de
bouclage ET une requête dont l'en-tête `Host` n'est pas de bouclage (garde-fou contre un navigateur détourné vers
ce serveur par un nom de domaine tiers). Les identifiants ci-dessous sont des valeurs de TEST fixes, déclarées dans
`specs/banc_local/apps.yaml` ; ils ne protègent rien.

Routes de l'application : /connexion, /deconnexion, /produits, /panier(/ajouter|/mettre-a-jour), /clients,
/clients/nouveau, /commande/confirmer, /commande/<numéro>, /commandes, /acces. Routes du banc : POST /__reset, GET /__etat,
GET|POST /__defauts. `/__etat` ne dit JAMAIS quels défauts sont actifs (l'agent ne doit pas pouvoir le lire par
l'oracle) : seul `GET /__defauts`, réservé au harnais, le fait.
"""

from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import os
import secrets
import sys
import threading
from decimal import Decimal
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import calcul, defauts as catalogue_defauts, pages

# Valeurs de TEST fixes (voir `specs/banc_local/apps.yaml`, vérifiées par tests/test_app_banc_web.py).
IDENTIFIANT_TEST = "testeur"
MOT_DE_PASSE_TEST = "motdepasse-test"
# Étape 4 (A70) : un second compte, pour prouver qu'un cas « joué en tant que lecteur » l'est vraiment (la page dit qui est
# connecté). Mêmes droits que « testeur » : le banc ne mesure pas encore les droits par rôle.
IDENTIFIANT_LECTEUR = "lecteur"
MOT_DE_PASSE_LECTEUR = "motdepasse-lecteur"
_UTILISATEURS = {IDENTIFIANT_TEST: MOT_DE_PASSE_TEST, IDENTIFIANT_LECTEUR: MOT_DE_PASSE_LECTEUR}
ENV_DEFAUTS = "TP_DEFAUTS"
COOKIE_SESSION = "tp_session"
TAILLE_CORPS_MAX = 64 * 1024


class HoteRefuse(ValueError):
    """Un hôte d'écoute qui n'est pas de bouclage : l'application refuse de démarrer."""


def est_hote_loopback(hote: str) -> bool:
    """Vrai pour `127.0.0.0/8`, `::1`, `::ffff:127.x` et le nom `localhost` ; faux pour tout le reste, y compris du bruit.

    Sert à l'écoute (hôte demandé), au contrôle de l'adresse du client et à celui de l'en-tête `Host`. Un nom de domaine
    quelconque n'est JAMAIS résolu ici (une résolution DNS pourrait pointer vers du bouclage à la demande d'un tiers).
    """
    brut = (hote or "").strip().strip("[]").split("%", 1)[0]
    if brut.lower() == "localhost":
        return True
    try:
        adresse = ipaddress.ip_address(brut)
    except ValueError:
        return False
    if isinstance(adresse, ipaddress.IPv6Address) and adresse.ipv4_mapped is not None:
        adresse = adresse.ipv4_mapped
    return adresse.is_loopback


def exiger_hote_d_ecoute(hote: str) -> str:
    """L'hôte d'écoute à utiliser (IPv4 de bouclage) ou `HoteRefuse`. `localhost` devient `127.0.0.1` (pas de DNS)."""
    if not est_hote_loopback(hote):
        raise HoteRefuse(f"hôte « {hote} » refusé : l'application du banc n'écoute que sur le bouclage (127.0.0.1)")
    if hote.strip().lower() == "localhost":
        return "127.0.0.1"
    adresse = ipaddress.ip_address(hote.strip().strip("[]"))
    if adresse.version != 4:
        raise HoteRefuse(f"hôte « {hote} » refusé : seule l'écoute IPv4 de bouclage est prise en charge (127.0.0.1)")
    return str(adresse)


def _hote_de_l_entete(valeur: str | None) -> str | None:
    """`127.0.0.1:8010` → `127.0.0.1` ; `[::1]:8010` → `::1` ; absent → None."""
    if not valeur:
        return None
    valeur = valeur.strip()
    if valeur.startswith("["):
        return valeur[1:].split("]", 1)[0]
    return valeur.rsplit(":", 1)[0] if valeur.count(":") == 1 else valeur


class Etat:
    """L'état serveur en mémoire — remis à zéro par `POST /__reset`. Les défauts n'en font PAS partie."""

    def __init__(self) -> None:
        self.remettre_a_zero()

    def remettre_a_zero(self) -> None:
        self.sessions: dict[str, str] = {}   # jeton → identifiant connecté
        self.panier: dict[str, int] = {}
        self.remise_pct = Decimal("0")
        self.clients: list[dict] = []
        self.commandes: list[dict] = []
        # Pages de confirmation déjà montrées : distinctes de `commandes` (la vérité) pour que le défaut
        # `etat_non_enregistre` puisse afficher une confirmation SANS rien conserver.
        self.confirmations: dict[str, dict] = {}
        self.prochaine_commande = 1
        self.prochain_client = 1

    def vue_json(self) -> dict:
        """Ce que rend `/__etat` : les trois listes que les specs vérifient, jamais les défauts ni les sessions."""
        return {
            "commandes": [_commande_json(c) for c in self.commandes],
            "panier": {
                "lignes": [
                    {
                        "produit": ident,
                        "nom": calcul.PAR_IDENT[ident].nom,
                        "quantite": quantite,
                        "prix_unitaire": f"{calcul.PAR_IDENT[ident].prix:.2f}",
                    }
                    for ident, quantite in self.panier.items()
                ],
                "remise_pct": f"{self.remise_pct.normalize():f}",
            },
            "enregistrements": [dict(c) for c in self.clients],
        }


def _commande_json(commande: dict) -> dict:
    return {
        cle: (f"{valeur:.2f}" if isinstance(valeur, Decimal) else valeur)
        for cle, valeur in commande.items()
        if cle != "lignes"
    } | {
        "lignes": [
            {cle: (f"{v:.2f}" if isinstance(v, Decimal) else v) for cle, v in ligne.items()}
            for ligne in commande["lignes"]
        ]
    }


class ServeurBanc(ThreadingHTTPServer):
    """`ThreadingHTTPServer` sur le bouclage, porteur de l'état et des défauts partagés par les requêtes."""

    daemon_threads = True

    def __init__(self, hote: str = "127.0.0.1", port: int = 0, defauts: frozenset[str] = frozenset()) -> None:
        hote = exiger_hote_d_ecoute(hote)  # AVANT d'ouvrir la socket
        self.etat = Etat()
        self.defauts = catalogue_defauts.DefautsActifs(defauts)
        self.verrou = threading.RLock()
        super().__init__((hote, port), _Requete)

    @property
    def url(self) -> str:
        return f"http://{self.server_address[0]}:{self.server_address[1]}"


class _Requete(BaseHTTPRequestHandler):
    server: ServeurBanc
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence : le banc écrit ses résultats, pas son journal d'accès
        pass

    # ── Réponses ────────────────────────────────────────────────────────────────────────────────────────────
    def _envoyer(self, code: int, corps: str | bytes, type_: str = "text/html; charset=utf-8", entetes=None) -> None:
        octets = corps.encode("utf-8") if isinstance(corps, str) else corps
        self.send_response(code)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(octets)))
        self.send_header("Cache-Control", "no-store")
        for cle, valeur in (entetes or {}).items():
            self.send_header(cle, valeur)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(octets)

    def _json(self, code: int, donnees: dict) -> None:
        self._envoyer(code, json.dumps(donnees, ensure_ascii=False), "application/json; charset=utf-8")

    def _rediriger(self, cible: str, entetes=None) -> None:
        self._envoyer(303, b"", "text/plain", {"Location": cible, **(entetes or {})})

    # ── Entrées ─────────────────────────────────────────────────────────────────────────────────────────────
    def _lire_corps(self) -> bytes:
        """Lit TOUJOURS le corps de la requête, même d'une route qui l'ignore : la connexion HTTP/1.1 est réutilisée
        par le navigateur et un corps non lu serait pris pour le début de la requête suivante."""
        try:
            longueur = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            longueur = 0
        return self.rfile.read(min(max(longueur, 0), TAILLE_CORPS_MAX))

    def _corps(self) -> bytes:
        return self._octets

    def _formulaire(self) -> dict[str, str]:
        analyse = parse_qs(self._corps().decode("utf-8", "replace"), keep_blank_values=True)
        return {cle: valeurs[0] for cle, valeurs in analyse.items()}

    def _session_ouverte(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie") or "")
        morceau = cookie.get(COOKIE_SESSION)
        return morceau is not None and morceau.value in self.server.etat.sessions

    def _utilisateur(self) -> str:
        """L'identifiant de la session ouverte (affiché « Connecté en tant que … »)."""
        morceau = SimpleCookie(self.headers.get("Cookie") or "").get(COOKIE_SESSION)
        return self.server.etat.sessions.get(morceau.value, IDENTIFIANT_TEST) if morceau else IDENTIFIANT_TEST

    def _client_autorise(self) -> bool:
        """Contrôle des routes `/__*` : adresse du client ET en-tête Host de bouclage (voir l'en-tête du module)."""
        if not est_hote_loopback(self.client_address[0]):
            return False
        hote = _hote_de_l_entete(self.headers.get("Host"))
        return hote is not None and est_hote_loopback(hote)

    # ── Aiguillage ──────────────────────────────────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        self._aiguiller("GET")

    def do_POST(self) -> None:
        self._aiguiller("POST")

    def _aiguiller(self, methode: str) -> None:
        chemin = urlsplit(self.path).path
        self._octets = self._lire_corps()
        if chemin.startswith("/__"):
            if not self._client_autorise():
                return self._json(403, {"erreur": "routes /__* réservées au bouclage"})
            with self.server.verrou:
                return self._banc(methode, chemin)
        with self.server.verrou:
            self._application(methode, chemin)

    # ── Routes du banc (/__*) ───────────────────────────────────────────────────────────────────────────────
    def _banc(self, methode: str, chemin: str) -> None:
        etat, defauts = self.server.etat, self.server.defauts
        if chemin == "/__reset" and methode == "POST":
            self._corps()
            etat.remettre_a_zero()
            # A75 (2026-10-20) : la remise à zéro le DIT — TestPilot n'accepte que cette réponse comme preuve.
            return self._json(200, {"ok": True, "remis_a_zero": True})
        if chemin == "/__etat" and methode == "GET":
            return self._json(200, etat.vue_json())
        if chemin == "/__defauts" and methode == "GET":
            return self._json(200, {"defauts": defauts.liste(), "disponibles": list(catalogue_defauts.CODES)})
        if chemin == "/__defauts" and methode == "POST":
            try:
                demande = json.loads(self._corps().decode("utf-8") or "{}")
                nouveaux = catalogue_defauts.analyser(demande.get("defauts"))
            except (ValueError, AttributeError) as erreur:  # JSON illisible, pas un objet, code inconnu
                return self._json(400, {"erreur": str(erreur)})
            defauts.remplacer(nouveaux)
            return self._json(200, {"defauts": defauts.liste()})
        self._json(404, {"erreur": "route inconnue"})

    # ── Routes de l'application ─────────────────────────────────────────────────────────────────────────────
    def _application(self, methode: str, chemin: str) -> None:
        etat = self.server.etat
        if chemin == "/connexion":
            return self._connexion(methode)
        if chemin == "/":
            return self._rediriger("/produits" if self._session_ouverte() else "/connexion")
        if not self._session_ouverte():
            if chemin in _ROUTES_CONNUES or chemin.startswith("/commande/"):
                return self._rediriger("/connexion")
            return self._envoyer(404, pages.introuvable(None))
        moi = self._utilisateur()
        if chemin == "/deconnexion" and methode == "POST":
            self._corps()
            cookie = SimpleCookie(self.headers.get("Cookie") or "")
            etat.sessions.pop(cookie[COOKIE_SESSION].value, None)
            return self._rediriger(
                "/connexion", {"Set-Cookie": f"{COOKIE_SESSION}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"}
            )
        if chemin == "/produits" and methode == "GET":
            return self._produits(moi)
        if chemin == "/panier" and methode == "GET":
            return self._envoyer(200, self._page_panier(moi))
        if chemin == "/panier/ajouter" and methode == "POST":
            return self._panier_ajouter(moi)
        if chemin == "/panier/mettre-a-jour" and methode == "POST":
            return self._panier_mettre_a_jour(moi)
        if chemin == "/clients" and methode == "GET":
            return self._envoyer(200, pages.clients(moi, etat.clients))
        if chemin == "/clients/nouveau":
            return self._client_nouveau(methode, moi)
        if chemin == "/commande/confirmer" and methode == "POST":
            return self._commande_confirmer(moi)
        if chemin.startswith("/commande/") and methode == "GET":
            commande = etat.confirmations.get(chemin.removeprefix("/commande/"))
            if commande is not None:
                return self._envoyer(200, pages.commande_confirmee(moi, commande))
        if chemin == "/commandes" and methode == "GET":
            return self._envoyer(200, pages.commandes(moi, etat.commandes))
        if chemin == "/acces":
            return self._acces(methode, moi)
        self._envoyer(404, pages.introuvable(moi))

    def _connexion(self, methode: str) -> None:
        etat, defauts = self.server.etat, self.server.defauts
        if methode == "GET":
            if self._session_ouverte():
                return self._rediriger("/produits")
            return self._envoyer(200, pages.connexion())
        if methode != "POST":
            return self._envoyer(405, pages.introuvable(None))
        champs = self._formulaire()
        identifiant = champs.get("identifiant", "")
        mot_de_passe = champs.get("mot_de_passe", "")
        attendu = next((m for u, m in _UTILISATEURS.items() if hmac.compare_digest(identifiant.encode(), u.encode())), None)
        bon_identifiant = attendu is not None
        bon_mot_de_passe = bon_identifiant and hmac.compare_digest(mot_de_passe.encode(), attendu.encode())
        if bon_identifiant and (bon_mot_de_passe or defauts.actif("login_accepte_tout")):
            jeton = secrets.token_hex(16)
            etat.sessions[jeton] = identifiant
            return self._rediriger(
                "/produits", {"Set-Cookie": f"{COOKIE_SESSION}={jeton}; Path=/; HttpOnly; SameSite=Lax"}
            )
        self._envoyer(200, pages.connexion("Identifiant ou mot de passe incorrect.", identifiant))

    def _produits(self, moi: str) -> None:
        recherche = parse_qs(urlsplit(self.path).query).get("q", [""])[0]
        if self.server.defauts.actif("filtre_ignore"):
            trouves = list(calcul.PRODUITS)
        else:
            aiguille = recherche.strip().casefold()
            trouves = [p for p in calcul.PRODUITS if aiguille in p.nom.casefold()]
        self._envoyer(200, pages.produits(moi, trouves, recherche.strip()))

    # ── Panier ──────────────────────────────────────────────────────────────────────────────────────────────
    def _totaux(self) -> dict:
        """Les totaux AFFICHÉS : le calcul sain, puis le défaut `total_faux` s'il est actif (sur le TTC seulement)."""
        etat = self.server.etat
        totaux = calcul.calculer(
            ((calcul.PAR_IDENT[i].prix, q) for i, q in etat.panier.items()), etat.remise_pct
        )
        ttc = totaux.total_ttc
        if self.server.defauts.actif("total_faux"):
            ttc = calcul.majorer_un_pour_cent(ttc)
        return {
            "sous_total": totaux.sous_total,
            "remise_pct": totaux.remise_pct,
            "remise": totaux.remise,
            "total_ht": totaux.total_ht,
            "tva": totaux.tva,
            "total_ttc": ttc,
        }

    def _lignes(self) -> list[dict]:
        return [
            {
                "ident": ident,
                "nom": calcul.PAR_IDENT[ident].nom,
                "prix": calcul.PAR_IDENT[ident].prix,
                "quantite": quantite,
                "total": calcul.arrondir(calcul.PAR_IDENT[ident].prix * quantite),
            }
            for ident, quantite in self.server.etat.panier.items()
        ]

    def _page_panier(self, moi: str, erreur: str | None = None, remise_saisie: str | None = None) -> str:
        etat = self.server.etat
        remise = f"{etat.remise_pct.normalize():f}".replace(".", ",") if remise_saisie is None else remise_saisie
        return pages.panier(moi, self._lignes(), self._totaux(), remise, erreur)

    def _panier_ajouter(self, moi: str) -> None:
        etat = self.server.etat
        champs = self._formulaire()
        ident = champs.get("produit", "")
        if ident not in calcul.PAR_IDENT:
            return self._envoyer(404, pages.introuvable(moi))
        try:
            quantite = calcul.analyser_quantite(champs.get("quantite", ""))
            if etat.panier.get(ident, 0) + quantite > calcul.QUANTITE_MAX:
                raise ValueError(f"La quantité totale d'un produit ne peut pas dépasser {calcul.QUANTITE_MAX}.")
        except ValueError as erreur:
            return self._envoyer(200, pages.produits(moi, calcul.PRODUITS, "", str(erreur)))
        etat.panier[ident] = etat.panier.get(ident, 0) + quantite
        self._rediriger("/panier")

    def _panier_mettre_a_jour(self, moi: str) -> None:
        etat = self.server.etat
        champs = self._formulaire()
        nouvelles: dict[str, int] = {}
        try:
            for ident in etat.panier:
                texte = champs.get(f"quantite_{ident}")
                if texte is None:
                    nouvelles[ident] = etat.panier[ident]
                    continue
                quantite = calcul.analyser_quantite(texte, minimum=0)
                if quantite > 0:  # 0 retire la ligne
                    nouvelles[ident] = quantite
            remise = calcul.analyser_remise(champs.get("remise", ""))
        except ValueError as erreur:
            # Un refus ne change RIEN : ni quantités ni remise (le critère « le total reste » en dépend).
            return self._envoyer(200, self._page_panier(moi, str(erreur), champs.get("remise", "")))
        etat.panier = nouvelles
        etat.remise_pct = remise
        self._rediriger("/panier")

    # ── Clients ─────────────────────────────────────────────────────────────────────────────────────────────
    def _client_nouveau(self, methode: str, moi: str) -> None:
        etat, defauts = self.server.etat, self.server.defauts
        if methode == "GET":
            return self._envoyer(200, pages.client_formulaire(moi))
        if methode != "POST":
            return self._envoyer(405, pages.introuvable(moi))
        champs = self._formulaire()
        nom = champs.get("nom", "").strip()
        ville = champs.get("ville", "").strip()
        erreur = None
        if nom == "" and not defauts.actif("validation_absente"):
            erreur = "Le nom est obligatoire."
        elif len(nom) > calcul.NOM_CLIENT_MAX:
            erreur = f"Le nom ne doit pas dépasser {calcul.NOM_CLIENT_MAX} caractères."
        if erreur is not None:
            sans_message = defauts.actif("message_erreur_absent")
            return self._envoyer(
                200, pages.client_formulaire(moi, nom, ville, erreur, afficher_message=not sans_message)
            )
        if not defauts.actif("etat_non_enregistre"):
            etat.clients.append({"id": etat.prochain_client, "nom": nom, "ville": ville})
        etat.prochain_client += 1
        self._envoyer(200, pages.client_cree(moi, nom))

    # ── Contrôle d'accès (IT-3e : classes de valeurs, défaut à la limite) ───────────────────────────────────────
    def _acces(self, methode: str, moi: str) -> None:
        if methode == "GET":
            return self._envoyer(200, pages.acces_formulaire(moi))
        if methode != "POST":
            return self._envoyer(405, pages.introuvable(moi))
        champs = self._formulaire()
        client, age_saisi = champs.get("client", "").strip(), champs.get("age", "").strip()
        age = calcul.lire_age(age_saisi)
        if age is None:
            return self._envoyer(200, pages.acces_formulaire(moi, client, age_saisi, calcul.MESSAGE_AGE_INVALIDE))
        limite = calcul.AGE_MIN - 1 if self.server.defauts.actif("limite_age_decalee") else calcul.AGE_MIN
        self._envoyer(200, pages.acces_resultat(moi, client, age >= limite, calcul.MESSAGE_ACCES_REFUSE))

    # ── Commandes ───────────────────────────────────────────────────────────────────────────────────────────
    def _commande_confirmer(self, moi: str) -> None:
        etat, defauts = self.server.etat, self.server.defauts
        self._corps()
        if not etat.panier:
            return self._envoyer(200, self._page_panier(moi, "Le panier est vide."))
        totaux = self._totaux()
        commande = {
            "numero": f"CMD-{etat.prochaine_commande:04d}",
            "lignes": [
                {
                    "produit": ligne["ident"],
                    "nom": ligne["nom"],
                    "quantite": ligne["quantite"],
                    "prix_unitaire": ligne["prix"],
                    "total_ligne": ligne["total"],
                }
                for ligne in self._lignes()
            ],
            **totaux,
        }
        commande["remise_pct"] = f"{totaux['remise_pct'].normalize():f}"
        etat.prochaine_commande += 1
        etat.confirmations[commande["numero"]] = commande
        if not defauts.actif("etat_non_enregistre"):
            etat.commandes.append(commande)
        etat.panier = {}
        etat.remise_pct = Decimal("0")
        self._envoyer(200, pages.commande_confirmee(moi, commande))


_ROUTES_CONNUES = frozenset(
    {
        "/produits", "/panier", "/panier/ajouter", "/panier/mettre-a-jour", "/clients", "/clients/nouveau",
        "/commande/confirmer", "/commandes", "/deconnexion", "/acces",
    }
)


def creer_serveur(hote: str = "127.0.0.1", port: int = 0, defauts=None) -> ServeurBanc:
    """Un serveur prêt à `serve_forever()`. `defauts` : texte « a,b », liste de codes ou None → variable TP_DEFAUTS."""
    if defauts is None:
        defauts = os.environ.get(ENV_DEFAUTS, "")
    return ServeurBanc(hote, port, catalogue_defauts.analyser(defauts))


def main(argv: list[str] | None = None) -> int:
    analyseur = argparse.ArgumentParser(description="Application web locale à défauts injectables (banc d'agents web).")
    analyseur.add_argument("--hote", default="127.0.0.1", help="bouclage uniquement (défaut 127.0.0.1)")
    analyseur.add_argument("--port", type=int, default=0, help="0 = port libre choisi à l'ouverture (défaut)")
    analyseur.add_argument(
        "--defauts", default=None, help=f"codes séparés par des virgules (défaut : variable {ENV_DEFAUTS})"
    )
    args = analyseur.parse_args(argv)
    try:
        serveur = creer_serveur(args.hote, args.port, args.defauts)
    except (HoteRefuse, catalogue_defauts.DefautInconnu) as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 2
    actifs = ", ".join(serveur.defauts.liste()) or "aucun (application saine)"
    print(f"Banc web : {serveur.url}  — défauts actifs : {actifs}", flush=True)
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
