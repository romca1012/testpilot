"""Sonde de saisie (lot 12, décision D10 bis, 2026-09-24) — OBSERVER le format qu'un champ retient.

⚠️ **Pourquoi une sonde, et pas seulement des attributs HTML.** Mesuré sur le portail Sapian
(`/retenue_garantie`, champ `numero_facture1`) : le crawl donne `pattern`, `maxlength` et `title` à
`None`. Le masque est un filtre JavaScript à la saisie (« FAC-TEST-001 » → « 001 », « 1234567
7654321 » → « 1234567/7654321 ») et la règle métier une `customError`. Lire les attributs n'aurait
RIEN révélé : seul le COMPORTEMENT se mesure — on tape une chaîne de sonde, on relit ce que le
champ a retenu et ce que le navigateur en dit (`validity`, `validationMessage`), sans jamais
soumettre.

⚠️ **Écrire sans soumettre n'est pas sans risque** (le back-office Odoo sauvegarde en quittant un
formulaire, y compris via `beforeunload` ; certaines applications enregistrent des brouillons en
tapant). D'où les garde-fous, TOUS obligatoires :

- une page JETABLE, ouverte pour la sonde seule, jamais la page persistante de l'exploration ;
  fermée avec `run_before_unload=False` (jamais de `beforeunload`) ;
- ni clic ni navigation après une saisie ;
- surveillance réseau pendant la sonde : toute requête POST/PUT/PATCH interrompt la sonde sur ce
  formulaire, marqué « sauvegarde automatique détectée, pas de sonde » ;
- aucune sonde sur le back-office Odoo (`/web#…`, `/odoo/…`) : un enregistrement existant y est
  interdit, et sur un formulaire de création les appels `onchange` (POST) ne se distinguent pas
  d'un enregistrement — conservateur, à rouvrir avec un banc (lot 04) ;
- aucune sonde si le garde-fou anti-production (`ODOO_ENV=prod`) est actif.

⚠️ **Un exemple n'est valable que s'il est STABLE** : retapé, il ressort identique ET valide.
Sinon on ne transmet que les faits bruts (écrit → retenu), jamais un format à moitié compris.

Module de perception : best-effort, ne lève jamais (une sonde qui plante ne doit jamais faire
échouer l'exploration).
"""

from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Trois chaînes : si le masque n'accepte que des chiffres, une chaîne mêlée n'apprend presque rien.
# ⚠️ **La longueur est NEUTRE (30), jamais choisie d'après un masque connu** : une sonde réglée sur
# les groupes de 7 du portail Sapian ne vaudrait rien pour des groupes de 4 (carte) ou de 2
# (téléphone), et la mesure du lot serait optimiste par construction. Le groupe complet se trouve
# par la RECHERCHE BORNÉE de `_chercher_exemple_stable`, quelle que soit sa taille.
CHAINES_SONDE = (
    ("lettres", "abcdefgh"),
    ("chiffres", "123456789012345678901234567890"),
    ("melange", "AB 12-cd 34"),
)
# Saisies AJOUTÉES au plus, pour la recherche d'un exemple valide et stable (sans soumission).
_ESSAIS_RECHERCHE_MAX = 30
# Après CHAQUE saisie, on laisse la boucle Playwright traiter les évènements réseau : sans ça, la
# requête émise par la saisie n'est vue qu'au tour suivant — la saisie suivante partirait avant
# l'interruption (mesuré en vrai navigateur : 2 brouillons au lieu d'1). Au plus UNE requête
# d'écriture peut donc encore partir avant la détection : limite inhérente, documentée.
_SETTLE_MS = 40

_METHODES_ECRITURE = frozenset({"POST", "PUT", "PATCH"})
# Bruit de fond d'Odoo (bus de notification, battement de session) : pas une sauvegarde.
_ARRIERE_PLAN = ("/longpolling", "/websocket", "/bus/", "/web/webclient/", "/web/session/")
_TYPES_SONDABLES = ("text", "tel", "search", "email", "url", "number")
_CHAMPS_MAX = 12
_RETENU_MAX = 120

_JS_CHAMPS = """() => Array.from(document.querySelectorAll('input')).filter(el => {
    const t = (el.getAttribute('type') || 'text').toLowerCase();
    return %s.includes(t) && !el.readOnly && !el.disabled
        && (el.name || el.id)
        && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
}).map(el => el.name || el.id)""" % list(_TYPES_SONDABLES)

_JS_LIRE = """el => ({valeur: String(el.value), valide: el.checkValidity(),
    message: el.validationMessage || ''})"""


def url_sondable(url: str) -> tuple[bool, str]:
    """`(True, '')` si le formulaire peut être sondé, sinon `(False, raison)`. Pur."""
    if os.environ.get("ODOO_ENV") == "prod":
        return False, "garde-fou anti-production actif : aucune sonde"
    analyse = urlparse(url or "")
    if analyse.path.rstrip("/") == "/web" or analyse.path.startswith("/odoo"):
        return False, ("back-office Odoo : aucune sonde (enregistrement existant interdit, "
                       "onchange non distinguable d'une sauvegarde)")
    return True, ""


def _est_ecriture_reelle(requete) -> bool:
    try:
        if str(requete.method).upper() not in _METHODES_ECRITURE:
            return False
        chemin = urlparse(str(requete.url)).path
    except Exception:
        return True  # doute = on s'arrête
    return not any(chemin.startswith(p) for p in _ARRIERE_PLAN)


def _selecteur(nom: str) -> str:
    return '[name="%s"], [id="%s"]' % (nom.replace('"', '\\"'), nom.replace('"', '\\"'))


def sonder_formulaire(page, url: str) -> dict:
    """Sonde les champs texte du formulaire à `url`, dans une page JETABLE du contexte de `page`.

    Rend `{statut, raison, champs}` — `statut` ∈ {`ok`, `interrompue`, `ignoree`, `erreur`} ;
    `champs` : `{nom: {sondes: {libellé: {ecrit, retenu, valide, message}}, exemple_stable}}`.
    Ne lève jamais.
    """
    permis, raison = url_sondable(url)
    if not permis:
        return {"statut": "ignoree", "raison": raison, "champs": {}}
    jetable = None
    ecritures: list[str] = []
    resultat: dict = {"statut": "ok", "raison": "", "champs": {}}
    try:
        jetable = page.context.new_page()
        jetable.goto(url, wait_until="domcontentloaded")
        jetable.wait_for_timeout(300)  # laisse finir les scripts d'initialisation (tracking, etc.)
        # Écoute ouverte APRÈS le chargement : seules les requêtes provoquées par NOTRE saisie
        # comptent (un POST de suivi au chargement n'est pas une sauvegarde de brouillon).
        jetable.on("request", lambda r: ecritures.append(f"{r.method} {r.url}")
                   if _est_ecriture_reelle(r) else None)
        for nom in list(jetable.evaluate(_JS_CHAMPS))[:_CHAMPS_MAX]:
            if ecritures:
                break
            resultat["champs"][nom] = _sonder_champ(jetable, nom, ecritures)
        if ecritures:
            resultat["statut"] = "interrompue"
            resultat["raison"] = ("sauvegarde automatique détectée, pas de sonde : "
                                  + ecritures[0][:120])
    except Exception as exc:  # perception best-effort : jamais fatale
        logger.warning("[sonde de saisie] échec sur %s : %s", url, exc)
        resultat["statut"] = "erreur"
        resultat["raison"] = str(exc)[:200]
    finally:
        if jetable is not None:
            try:
                jetable.close(run_before_unload=False)
            except Exception:
                pass
    return resultat


def _lire(loc) -> dict:
    lu = loc.evaluate(_JS_LIRE)
    return {"retenu": str(lu.get("valeur", ""))[:_RETENU_MAX], "valide": bool(lu.get("valide")),
            "message": str(lu.get("message", ""))[:_RETENU_MAX]}


def _sonder_champ(page, nom: str, ecritures: list) -> dict:
    loc = page.locator(_selecteur(nom)).first

    def remplir(valeur: str) -> None:
        loc.fill(valeur)
        page.wait_for_timeout(_SETTLE_MS)

    sondes: dict = {}
    for libelle, chaine in CHAINES_SONDE:
        remplir(chaine)
        if ecritures:
            break
        sondes[libelle] = {"ecrit": chaine, **_lire(loc)}
    exemple = None if ecritures else _chercher_exemple_stable(loc, sondes, ecritures, remplir)
    if not ecritures:
        # Jamais de saisie APRÈS une requête d'écriture (même pour vider le champ : un nouvel
        # évènement `input` pourrait émettre un second brouillon) — la page jetable est fermée.
        try:
            loc.fill("")
        except Exception:
            pass
    return {"sondes": sondes, "exemple_stable": exemple}


def _chercher_exemple_stable(loc, sondes: dict, ecritures: list, remplir):
    """Une valeur RETENUE par le champ qui est VALIDE (`checkValidity`) et STABLE au retapage.

    Étapes, toutes bornées à `_ESSAIS_RECHERCHE_MAX` saisies, sans soumission ni clic :
    1. les valeurs retenues déjà valides ;
    2. pour chaque valeur retenue invalide (la plus longue d'abord), retirer des caractères EN
       FIN de valeur, un par un, jusqu'à en obtenir une valide — c'est ce qui trouve le groupe
       complet d'un masque (7, 4, 2…) sans connaître sa taille.
    Un candidat n'est retenu que si, retapé tel quel, il ressort IDENTIQUE et VALIDE. `None` si
    rien n'est trouvé : mieux vaut ne rien transmettre qu'un format à moitié compris.
    """
    budget = [_ESSAIS_RECHERCHE_MAX]

    def essayer(candidat: str):
        """`retenu` si `candidat` donne une valeur valide et stable au retapage, sinon None."""
        if budget[0] < 2 or not candidat:
            return None
        budget[0] -= 1
        remplir(candidat)
        if ecritures:
            return None
        premiere = _lire(loc)
        if not (premiere["valide"] and premiere["retenu"].strip()):
            return None
        budget[0] -= 1
        remplir(premiere["retenu"])
        if ecritures:
            return None
        seconde = _lire(loc)
        if seconde["retenu"] == premiere["retenu"] and seconde["valide"]:
            return premiere["retenu"]
        return None

    retenus = [s["retenu"] for s in sondes.values() if s.get("retenu", "").strip()]
    valides = [r for r in retenus if _est_valide(sondes, r)]
    for retenu in valides:
        trouve = essayer(retenu)
        if trouve:
            return trouve
    for graine in sorted({r for r in retenus if r not in valides}, key=len, reverse=True):
        for coupe in range(1, len(graine)):
            if budget[0] < 2 or ecritures:
                return None
            trouve = essayer(graine[:-coupe])
            if trouve:
                return trouve
    return None


def _est_valide(sondes: dict, retenu: str) -> bool:
    return any(s.get("retenu") == retenu and s.get("valide") for s in sondes.values())


def resume_pour_agent(nom: str, champ: dict) -> str:
    """Une ligne d'observation par champ — texte de l'application cité comme DONNÉE, tronqué."""
    parties = []
    for libelle, s in (champ.get("sondes") or {}).items():
        if s.get("retenu") != s.get("ecrit"):
            parties.append(f"{libelle}: « {s.get('ecrit')} » → retenu « {s.get('retenu')} »")
        if s.get("message"):
            parties.append(f"{libelle}: message navigateur « {s['message']} »")
    if not parties:
        return ""
    ligne = f"- {nom} : " + " ; ".join(parties)
    if champ.get("exemple_stable"):
        ligne += f" ; exemple stable (retapé = identique et valide) : « {champ['exemple_stable']} »"
    return re.sub(r"\s+", " ", ligne)[:400]
