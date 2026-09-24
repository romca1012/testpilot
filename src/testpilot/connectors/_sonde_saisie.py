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
- **INTERCEPTION réseau (`page.route`) : toute requête d'écriture (POST/PUT/PATCH/DELETE) est
  ABANDONNÉE avant de partir — le serveur n'en reçoit AUCUNE** — et interrompt la sonde sur ce
  formulaire, marqué « sauvegarde automatique détectée, pas de sonde ». (La première version ne
  faisait que SURVEILLER : la requête partait, un brouillon pouvait être enregistré au nom d'un
  utilisateur réel — mesuré en vrai navigateur : 1 POST reçu par le serveur.) Le bruit de fond
  d'Odoo (bus de notification) est laissé passer : c'est une lecture, pas une sauvegarde ;
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
# Après CHAQUE saisie, on laisse la boucle Playwright traiter les évènements réseau : la requête
# émise par la saisie reste EN ATTENTE (jamais envoyée) tant que le gestionnaire d'interception n'a
# pas tourné ; sans ce délai, la saisie suivante s'enchaînerait avant de savoir qu'il faut s'arrêter.
_SETTLE_MS = 40
# Un select masqué (widget de remplacement) ne doit pas bloquer la sonde 30 s : échec rapide.
_SELECT_TIMEOUT_MS = 2000

_METHODES_ECRITURE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_METHODES_RPC_LECTURE = frozenset({"read", "search_read", "search", "search_count", "name_search",
                                   "name_get", "fields_get"})
# Bruit de fond d'Odoo (bus de notification, battement de session) : pas une sauvegarde.
# `/web/session/` n'est PAS ignoré en bloc (revue du lot 12) : `POST /web/session/destroy` est une
# déconnexion, une vraie écriture. Seuls les deux battements de session en lecture le sont.
_MARQUE_NAVIGATION = "NAVIGATION "
_ARRIERE_PLAN = ("/longpolling", "/websocket", "/bus/", "/web/webclient/",
                 "/web/session/check", "/web/session/get_session_info")
_TYPES_SONDABLES = ("text", "tel", "search", "email", "url", "number")
_CHAMPS_MAX = 12
_RETENU_MAX = 120

_JS_CHAMPS = """() => Array.from(document.querySelectorAll('input')).filter(el => {
    const t = (el.getAttribute('type') || 'text').toLowerCase();
    return %s.includes(t) && !el.readOnly && !el.disabled
        && (el.name || el.id)
        && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
}).map(el => el.name || el.id)""" % list(_TYPES_SONDABLES)

_JS_SELECTS = """() => Array.from(document.querySelectorAll('select')).filter(
    el => (el.name || el.id) && !el.disabled).map(
    el => ({nom: el.name || el.id, options: Array.from(el.options).map(o => o.value)}))"""

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


def _methode_rpc(requete) -> str:
    """Le champ `params.method` du corps JSON-RPC, ou `''` s'il est absent ou illisible."""
    try:
        corps = requete.post_data_json
        return str(((corps or {}).get("params") or {}).get("method") or "")
    except Exception:
        return ""


def _est_ecriture_reelle(requete) -> bool:
    try:
        if str(requete.method).upper() not in _METHODES_ECRITURE:
            return False
        chemin = urlparse(str(requete.url)).path
    except Exception:
        return True  # doute = on s'arrête
    if any(chemin.startswith(p) for p in _ARRIERE_PLAN):
        return False
    # Le client Odoo lit en POST (`/web/dataset/call_kw`) : mesuré le 2026-09-24, un `res.users/read`
    # a interrompu la sonde à tort (2 essais sur 12). On juge la MÉTHODE du corps JSON-RPC, jamais le
    # suffixe d'URL (cosmétique sur les Odoo récents) ; corps illisible ou méthode inconnue = écriture.
    if chemin.startswith("/web/dataset/call_kw") and _methode_rpc(requete) in _METHODES_RPC_LECTURE:
        return False
    return True


def _est_navigation(requete) -> bool:
    try:
        return bool(requete.is_navigation_request())
    except Exception:
        return False


def _sans_fragment(url) -> str:
    return str(url or "").split("#", 1)[0]


def _garde_reseau(ecritures: list):
    """Gestionnaire d'interception : abandonne toute écriture ET toute navigation, laisse passer le
    reste.

    Une NAVIGATION pendant la sonde (un `<select onchange="location=…">` de langue, de devise, de tri)
    est un GET que la garde d'écriture laissait partir : effet de bord possible sur la session
    authentifiée, et sonde des champs de la page d'ARRIVÉE attribuée à la route d'origine (revue du
    lot 12). Elle est abandonnée avant d'atteindre le serveur et interrompt la sonde, comme une
    écriture — D10 bis : « ni clic ni navigation après saisie »."""
    def garde(route):
        requete = route.request
        if _est_ecriture_reelle(requete):
            ecritures.append(f"{requete.method} {requete.url}")
            route.abort()
        elif _est_navigation(requete):
            ecritures.append(f"{_MARQUE_NAVIGATION}{requete.method} {requete.url}")
            route.abort()
        else:
            route.continue_()
    return garde


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
        # Interception ouverte APRÈS le chargement : seules les requêtes provoquées par NOTRE saisie
        # comptent (un POST de suivi au chargement n'est pas une sauvegarde de brouillon).
        jetable.route("**/*", _garde_reseau(ecritures))
        base, dependants, complet = _options_selects_ou_vide(jetable), set(), True
        try:
            dependants |= _changer_les_selects(jetable, base, ecritures)
        except Exception:
            complet = False
        noms = [] if ecritures else list(jetable.evaluate(_JS_CHAMPS))[:_CHAMPS_MAX]
        for nom in noms:
            if ecritures:
                break
            try:
                resultat["champs"][nom] = _sonder_champ(jetable, nom, ecritures)
            except Exception as exc:
                # Un champ qui se laisse mal sonder ne doit pas faire perdre les autres (mesuré le
                # 2026-09-24 sur retenue_garantie/1 : un `type=number` a fait échouer tout le
                # formulaire, donc aussi les champs texte qui suivaient).
                resultat["champs"][nom] = {"sondes": {}, "exemple_stable": None,
                                           "erreur": str(exc)[:120]}
        if not ecritures and complet:
            try:
                apres = {n["nom"]: n["options"] for n in jetable.evaluate(_JS_SELECTS)}
                dependants |= {n for n, opts in base.items() if apres.get(n) != opts}
            except Exception:
                complet = False
        # Indépendant SEULEMENT si observé complet et inchangé : par défaut on n'affirme jamais qu'un
        # select est exhaustif (défaut sûr, D11 : refuser à tort coûte du budget, revue du lot 12).
        resultat["selects"] = {n: {"independant": bool(complet and not ecritures
                                                       and n not in dependants)} for n in base}
        _marquer_interruption(resultat, ecritures)
    except Exception as exc:  # perception best-effort : jamais fatale
        if ecritures:
            # Une écriture ou une navigation abandonnée peut laisser la page dans un état où la
            # lecture suivante lève (page d'erreur, contexte détruit) : c'est une INTERRUPTION
            # (défaut sûr, aucune sonde), pas une erreur de la sonde.
            _marquer_interruption(resultat, ecritures)
            resultat.setdefault("selects", {})
        else:
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


def _marquer_interruption(resultat: dict, ecritures: list) -> None:
    if not ecritures:
        return
    resultat["statut"] = "interrompue"
    if ecritures[0].startswith(_MARQUE_NAVIGATION):
        resultat["raison"] = ("navigation détectée, pas de sonde : "
                              + ecritures[0][len(_MARQUE_NAVIGATION):][:120])
    else:
        resultat["raison"] = "sauvegarde automatique détectée, pas de sonde : " + ecritures[0][:120]


def _options_selects_ou_vide(page) -> dict:
    """`{nom: [valeurs d'option]}` des `<select>` de la page, ou `{}` si la lecture échoue."""
    try:
        return {n["nom"]: n["options"] for n in page.evaluate(_JS_SELECTS)}
    except Exception:
        return {}


def _changer_les_selects(page, base: dict, ecritures: list) -> set:
    """Change chaque select (dernière option réelle) et rend les selects dont les OPTIONS ont changé
    ailleurs — ceux-là dépendent d'un autre champ (pays → ville) et ne sont pas exhaustifs.

    Aucune saisie APRÈS une écriture interceptée ; une saisie qui échoue lève (l'appelant en déduit
    « observation incomplète », donc aucun select déclaré indépendant)."""
    dependants: set = set()
    if len(base) < 2:
        return dependants
    courant, depart = base, _sans_fragment(getattr(page, "url", ""))
    for nom in base:
        if ecritures:
            break
        # Un select déjà vu dépendant n'a plus rien à prouver ; et on choisit dans ses options
        # COURANTES (elles ont pu changer) : viser une option de l'état initial ferait échouer le choix.
        reelles = [o for o in courant.get(nom, []) if str(o).strip()]
        if nom in dependants or len(reelles) < 2:
            continue
        page.locator(_selecteur(nom)).first.select_option(reelles[-1], timeout=_SELECT_TIMEOUT_MS)
        page.wait_for_timeout(_SETTLE_MS)
        if not ecritures and _sans_fragment(getattr(page, "url", "")) != depart:
            # Filet : un changement d'URL qui n'a pas produit de requête (History API) est aussi
            # une navigation ; ce qu'on lirait ensuite ne serait plus la route sondée.
            ecritures.append(f"{_MARQUE_NAVIGATION}(URL changée) {page.url}")
        if ecritures:
            break
        try:
            courant = {n["nom"]: n["options"] for n in page.evaluate(_JS_SELECTS)}
        except Exception:
            # La navigation abandonnée n'a peut-être pas encore été traitée par le gestionnaire :
            # on lui laisse le temps avant de conclure à une vraie erreur.
            page.wait_for_timeout(_SETTLE_MS * 5)
            if ecritures:
                break
            raise
        dependants |= {n for n, opts in base.items() if n != nom and courant.get(n) != opts}
    return dependants


def _lire(loc) -> dict:
    lu = loc.evaluate(_JS_LIRE)
    return {"retenu": str(lu.get("valeur", ""))[:_RETENU_MAX], "valide": bool(lu.get("valide")),
            "message": str(lu.get("message", ""))[:_RETENU_MAX]}


def _sonder_champ(page, nom: str, ecritures: list) -> dict:
    loc = page.locator(_selecteur(nom)).first

    def remplir(valeur: str) -> bool:
        """`False` si le navigateur REFUSE la saisie (Playwright ne tape pas de lettres dans un
        `type=number`, par exemple) : rien n'a été écrit, la chaîne est simplement inapplicable."""
        try:
            loc.fill(valeur)
        except Exception:
            return False
        page.wait_for_timeout(_SETTLE_MS)
        return True

    sondes: dict = {}
    for libelle, chaine in CHAINES_SONDE:
        if not remplir(chaine):
            sondes[libelle] = {"ecrit": chaine, "refuse": True}
            continue
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
        if not remplir(candidat) or ecritures:
            return None
        premiere = _lire(loc)
        if not (premiere["valide"] and premiere["retenu"].strip()):
            return None
        budget[0] -= 1
        if not remplir(premiere["retenu"]) or ecritures:
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


def citer(texte, limite: int = 90) -> str:
    """Un texte venu de l'application, nettoyé, tronqué, entre « » : une DONNÉE citée, jamais une
    consigne (les guillemets internes sont retirés pour qu'il ne puisse pas « sortir » de la citation)."""
    propre = re.sub(r"\s+", " ", str(texte or "").replace("«", " ").replace("»", " ")).strip()
    if len(propre) > limite:
        propre = propre[:limite - 1].rstrip() + "…"
    return f"« {propre} »"


def resume_pour_agent(nom: str, champ: dict) -> str:
    """Une ligne d'observation par champ — texte de l'application cité comme DONNÉE, tronqué."""
    parties = []
    for libelle, s in (champ.get("sondes") or {}).items():
        if s.get("refuse"):
            continue
        if s.get("retenu") != s.get("ecrit"):
            parties.append(f"{libelle}: {citer(s.get('ecrit'), 40)} → retenu {citer(s.get('retenu'))}")
        if s.get("message"):
            parties.append(f"{libelle}: message navigateur {citer(s['message'])}")
    if not parties:
        return ""
    ligne = f"- {nom} : " + " ; ".join(parties)
    if champ.get("exemple_stable"):
        ligne += f" ; exemple stable (retapé = identique et valide) : {citer(champ['exemple_stable'])}"
    return ligne[:400]
