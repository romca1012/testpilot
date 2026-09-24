"""Helpers réutilisables — ZÉRO décorateur Behave.

Chaque module *steps.py importe les helpers dont il a besoin
et les encapsule dans ses propres @given/@when/@then.
"""

import json
import logging
import os
import sys
import time
import warnings
import re
from urllib.parse import parse_qsl
from dataclasses import asdict, dataclass
from playwright.sync_api import TimeoutError as PlaywrightTimeout, expect

logger = logging.getLogger(__name__)

# ⚠️ Import PLAT, AU NIVEAU MODULE — jamais différé à l'intérieur d'une fonction (bug RÉEL mesuré
# en run, Sapian, 2026-09-22 : `ModuleNotFoundError: No module named '_adaptive_resolution'`).
# Behave n'ajoute `steps/` à `sys.path` que PENDANT la phase de chargement des définitions de
# steps (`load_step_definitions`) — un import DIFFÉRÉ, déclenché PENDANT l'exécution d'un
# scénario (bien après cette phase), échoue silencieusement car `steps/` n'y est plus. `_base_helpers`
# lui-même EST chargé pendant cette phase (`_odoo_steps.py`/`_generic_steps.py` l'importent au
# niveau module) : un import ICI, au niveau module, hérite du même moment favorable. Optionnel
# (`None` si absent) : la collecte dry-run n'exige pas le paquet applicatif complet.
try:
    import _adaptive_resolution
except ImportError:
    _adaptive_resolution = None

# Marqueur du repli « libellé → nom technique » (décision 0007). Émis dans le log pour la
# visibilité en mode dev (§5). ⚠️ NE PAS s'en servir pour remonter le repli au rapport : Behave
# capture stdout/stderr/logging et ne les recrache PAS sur un scénario VERT dès qu'un
# environment.py est présent — ce que le runner assemble TOUJOURS. C'est le fichier sidecar
# ci-dessous qui porte le repli jusqu'au rapport (phase B+).
FIELD_FALLBACK_MARKER = "[TP_FIELD_FALLBACK]"

# Chemin du fichier où consigner les replis, posé par BehaveRunner dans l'env du sous-processus.
# Nom DUPLIQUÉ côté runner (l'importer d'ici tirerait Playwright dans la couche API) : l'accord
# des deux valeurs est tenu par test (test_field_resolution).
FIELD_FALLBACK_FILE_ENV = "TP_FIELD_FALLBACK_FILE"


def _record_field_fallback(message: str) -> None:
    """Consigne un repli dans le fichier sidecar, s'il y en a un de désigné.

    Pourquoi un fichier plutôt que le log : le log NE SORT PAS d'un scénario vert (capture de
    Behave), or le scénario vert est exactement le cas que ce signal doit couvrir — champ
    réellement renommé → le repli le retrouve par libellé → le run passe au vert → la régression
    serait absorbée sans témoin (verdict 0007 n°2). Le fichier ne dépend d'aucun routage de Behave.

    Hors run behave (tests unitaires, appel direct), aucune variable n'est posée : on ne fait rien.
    Une trace ne doit jamais faire échouer un test — d'où le `except OSError` silencieux.
    """
    path = os.environ.get(FIELD_FALLBACK_FILE_ENV)
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(message.replace("\n", " ") + "\n")
    except OSError:
        pass


# Chemin du fichier où consigner CHAQUE résolution de `locate_field` (pas seulement les replis) —
# plan de consolidation, étape 1.2. Nom DUPLIQUÉ côté `execution/behave_result.py`, même raison et
# même test d'accord que `FIELD_FALLBACK_FILE_ENV`/`REGLES_REFUS_FILE_ENV` ci-dessus.
SELECTOR_TIER_FILE_ENV = "TP_SELECTOR_TIER_FILE"


def _record_selector_tier(ident: str, tier: str) -> None:
    """Consigne QUEL palier de `locate_field` a résolu ce champ, pour détecter une DÉRIVE d'un run
    à l'autre (§1.2 du plan de consolidation, audit « Le pari Mabl/Testim » 2026-09-15).

    ⚠️ **Contrairement à `_record_field_fallback`, appelé sur TOUS les paliers, y compris `name`.**
    Un repli n'est intéressant qu'une fois qu'il s'est produit ; une dérive, elle, se lit en
    comparant le palier d'AUJOURD'HUI à celui d'HIER — il faut donc le palier « name » (le cas
    silencieux, le plus fréquent) tout autant que les replis, sinon la comparaison n'aurait rien
    à quoi se raccrocher pour la toute première dérive d'un champ jusque-là stable.

    Même discipline que le sidecar des replis : un fichier, jamais le log (absent d'un scénario
    vert), jamais bloquant (`except OSError` silencieux), rien n'est posé hors d'un run Behave.
    """
    path = os.environ.get(SELECTOR_TIER_FILE_ENV)
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ident": ident, "tier": tier}, ensure_ascii=False) + "\n")
    except OSError:
        pass


# Chemin du fichier où consigner les libellés de menu APPRIS par le repli adaptatif de
# `navigate_menu` (Lot 2 du plan de fiabilisation, 2026-09-23). Nom DUPLIQUÉ côté
# `execution/behave_result.py`, même raison et même test d'accord que les sidecars ci-dessus.
MENU_LEARNED_FILE_ENV = "TP_MENU_APPRIS_FILE"


def _record_menu_appris(segment_original: str, libelle_reel: str, menu_path: str) -> None:
    """Consigne quel libellé RÉEL a permis de franchir un segment de menu que `navigate_menu`
    ne trouvait pas tel quel (Lot 2, 2026-09-23 — ferme la boucle laissée ouverte par
    « Chantier F » : le repli adaptatif retrouvait déjà le bon libellé pour CE run, mais rien ne
    le renvoyait vers la génération, qui reproposait indéfiniment le même libellé faux).

    Même discipline que les sidecars ci-dessus : un fichier, jamais le log (absent d'un scénario
    vert), jamais bloquant (`except OSError` silencieux), rien n'est posé hors d'un run Behave.
    """
    path = os.environ.get(MENU_LEARNED_FILE_ENV)
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"segment_original": segment_original, "libelle_reel": libelle_reel,
                 "menu_path": menu_path}, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ── Les règles APPRISES d'un refus (§5bis n°1) ───────────────────────────────
#
# Chemin du fichier où consigner les refus MESURÉS pendant le run, posé par BehaveRunner dans
# l'env du sous-processus. Nom DUPLIQUÉ côté runner pour la même raison que
# `FIELD_FALLBACK_FILE_ENV` (l'importer d'ici tirerait Playwright dans la couche API) : l'accord
# des deux valeurs est tenu par test.
REGLES_REFUS_FILE_ENV = "TP_REGLES_REFUS_FILE"

# Un run bavard ne doit pas produire un fichier illisible : au-delà, on s'arrête. Le même refus
# se répète de toute façon à chaque scénario, et la déduplication se fait à la relecture.
_MAX_REFUS_PAR_RUN = 20
_refus_consignes = 0

# Les drapeaux de `ValidityState`, dans l'ordre où on les interroge — du plus INFORMATIF (une
# contrainte machine lisible) au plus creux. `customError` est le dernier : quand il tombe, le
# navigateur n'expose AUCUNE contrainte, seulement sa phrase. C'est le cas des règles écrites en
# JavaScript, que le crawl statique ne verra jamais.
_DRAPEAUX_VALIDITE = (
    ("patternMismatch", "pattern"),
    ("tooLong", "maxLength"),
    ("tooShort", "minLength"),
    ("rangeOverflow", "max"),
    ("rangeUnderflow", "min"),
    ("stepMismatch", "step"),
    ("typeMismatch", "type"),
    ("badInput", ""),
    ("valueMissing", ""),
    ("customError", ""),
)

# La même liste, pour la sonde JS — dérivée de la précédente : un seul endroit décide.
_DRAPEAUX_JS = "[" + ",".join(f"'{nom}'" for nom, _ in _DRAPEAUX_VALIDITE) + "]"


def _refus_depuis_sonde(route, champ, origine="navigateur"):
    """Un champ rapporté par une sonde → un `RefusMesure`, ou `None` s'il n'apprend rien.

    Le drapeau retenu est le PREMIER de `_DRAPEAUX_VALIDITE` que le navigateur a levé — l'ordre
    va du plus informatif (une contrainte machine qu'on peut relire) au plus creux. La valeur de
    contrainte est lue sur la propriété DOM correspondante, jamais devinée dans le message.
    """
    nom = (champ.get("nom") or "").strip()
    if not nom or nom == "?":
        return None      # un champ sans `name` n'est pas ré-identifiable au run suivant
    leves = champ.get("drapeaux") or []
    type_contrainte, propriete = next(
        ((d, p) for d, p in _DRAPEAUX_VALIDITE if d in leves), ("customError", ""))
    return RefusMesure(
        route=route,
        champ=nom,
        type_contrainte=type_contrainte,
        valeur_contrainte=str(champ.get(propriete) or "") if propriete else "",
        valeur_refusee=str(champ.get("valeur") or ""),
        origine=origine,
        preuve=str(champ.get("msg") or ""),
    )


@dataclass(frozen=True)
class RefusMesure:
    """Un refus de l'application, MESURÉ — la matière de la règle apprise (§5bis n°1).

    ⚠️ **Aucun champ n'est rédigé par le LLM, ni déduit d'un texte qu'il aurait écrit.** `route`
    vient de l'URL, `champ` de l'attribut `name`, `type_contrainte` d'un drapeau de `ValidityState`
    posé par le moteur du navigateur, `valeur_contrainte` de la propriété DOM correspondante.
    `preuve` porte le message du navigateur ou de l'application : il est **informatif**, et
    n'entre jamais dans l'identité d'une règle (principe 1).
    """

    route: str
    champ: str
    type_contrainte: str
    valeur_contrainte: str = ""
    valeur_refusee: str = ""
    origine: str = "navigateur"
    preuve: str = ""
    # Lot 12 (2026-09-24) : ce que le champ a RETENU, en champ structuré (avant : seulement dans
    # le texte de `preuve`, inexploitable par machine). Vide hors filtre de saisie.
    valeur_retenue: str = ""


def _route_courante(page) -> str:
    """L'URL de la page, normalisée comme l'annuaire — best-effort, jamais lève.

    Import différé : la bibliothèque doit s'importer à la collecte (dry-run) sans exiger le paquet
    `testpilot`. Sans lui, on rend le chemin brut plutôt que rien — une route grossière vaut mieux
    qu'un refus perdu.
    """
    url = getattr(page, "url", "") or ""
    try:
        from testpilot.generation import domain_model
        return domain_model.normaliser_route(url)
    except Exception:
        return url


def _consigner_refus(refus) -> None:
    """Écrit les refus mesurés dans le fichier sidecar, s'il y en a un de désigné.

    Même raison qu'un sidecar pour les replis de champ : le log NE SORT PAS d'un scénario capturé
    par Behave, et un mécanisme dont le signal peut se perdre selon la configuration de
    journalisation n'est pas un mécanisme. Hors run behave (test unitaire, appel direct), aucune
    variable n'est posée : on ne fait rien.

    **Une trace ne fait jamais échouer un scénario** — d'où le `except OSError` muet.
    """
    global _refus_consignes
    path = os.environ.get(REGLES_REFUS_FILE_ENV)
    if not path or not refus:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            for mesure in refus:
                if _refus_consignes >= _MAX_REFUS_PAR_RUN:
                    return
                handle.write(json.dumps(asdict(mesure), ensure_ascii=False,
                                        sort_keys=True) + "\n")
                _refus_consignes += 1
    except (OSError, TypeError):
        pass


def lever_donnee_refusee(message, refus=()):
    """Consigne le refus PUIS lève — le seul endroit qui construit un `DonneeRefuseeError` appris.

    Un seul site de construction : sinon un jour un `raise` oublierait de consigner, et la règle
    ne serait jamais apprise **sans que rien ne le montre**.
    """
    _consigner_refus(refus)
    raise DonneeRefuseeError(message, refus=refus)


# ── OdooRPC helpers ──────────────────────────────────────────────────────────

def record_exists(env, model, field, value):
    ids = env[model].search([(field, "=", value)])
    return ids


def record_exists_contains(env, model, field, value):
    m = re.search(r'"([^"]+)"', field)
    actual_field = m.group(1) if m else field.strip()
    return env[model].search([(actual_field, "ilike", value)])


def field_equals(env, model, record_id, field, expected):
    record = env[model].browse(record_id)
    actual = record.read([field])[0][field]
    assert str(actual) == expected, (
        f"Champ '{field}' dans '{model}' : attendu '{expected}', obtenu '{actual}'."
    )


def field_not_empty(env, model, record_id, field):
    record = env[model].browse(record_id)
    value = record.read([field])[0][field]
    assert value not in (False, None, "", []), f"Le champ '{field}' est vide."


def no_duplicate(env, model, field, value):
    ids = env[model].search([(field, "=", value)])
    assert len(ids) <= 1, (
        f"Doublon détecté dans '{model}' : {len(ids)} enregistrements avec {field}='{value}'."
    )


def no_partial_record(env, model, field):
    ids = env[model].search([(field, "in", [False, ""])])
    assert not ids, f"Enregistrements avec '{field}' vide dans '{model}' : {ids}"


def field_m2o_equals(env, model, record_id, field, expected):
    Model = env[model]
    record_data = Model.browse(record_id).read([field])[0]
    actual = record_data[field]
    if isinstance(actual, (list, tuple)) and len(actual) > 0:
        related_id = actual[0]
        field_info = Model.fields_get([field])
        related_model_name = field_info[field]["relation"]
        related_data = env[related_model_name].browse(related_id).read(["name"])[0]
        actual_name = related_data["name"]
    else:
        actual_name = str(actual)
    assert actual_name == expected, (
        f"Champ '{field}' : attendu '{expected}', obtenu '{actual_name}' (display: {actual})"
    )


def field_m2o_contains(env, model, record_id, field, partial):
    Model = env[model]
    record_data = Model.browse(record_id).read([field])[0]
    actual = record_data[field]
    if isinstance(actual, (list, tuple)) and len(actual) > 0:
        related_id = actual[0]
        field_info = Model.fields_get([field])
        related_model_name = field_info[field]["relation"]
        related_data = env[related_model_name].browse(related_id).read(["name"])[0]
        actual_name = related_data["name"]
    else:
        actual_name = str(actual)
    assert partial in actual_name, (
        f"Champ '{field}' : '{partial}' introuvable dans '{actual_name}' (display: {actual})"
    )


# ── Playwright / navigateur helpers ──────────────────────────────────────────

def playwright_login(context):
    """Même connexion UI pour l'exécution et la perception du générateur."""
    from testpilot.connectors.odoo_login import playwright_login as login
    return login(context)


def navigate(context, url):
    full_url = url if url.startswith("http") else f"{context.odoo_url.rstrip('/')}{url}"
    if context.page.url in ("about:blank", ""):
        playwright_login(context)
    # domcontentloaded (fiable) au lieu de networkidle : l'interaction suivante auto-attendra sa cible.
    context.page.goto(full_url, wait_until="domcontentloaded")


def click_first_actionable(page, candidats, *, quoi, timeout=8000, ident: str = ""):
    """Clique le PREMIER candidat qui devient ACTIONNABLE — l'attente est ancrée sur l'ÉLÉMENT,
    jamais sur le réseau.

    Généralisé depuis `click_button`. `candidats` est une liste de sélecteurs CSS (`str`) et/ou de
    `Locator` déjà construits (ex. `page.get_by_role(...)`, pour garder la correspondance par nom
    accessible). Pour chacun, `loc.first.click(timeout=…)` s'appuie sur l'**auto-attente
    d'actionnabilité** de Playwright (visible + stable + activé + reçoit les events) — ce qui
    couvre un widget rendu en JS *après* l'arrivée sur la page.

    ⚠️ **On NE garde JAMAIS par `count()`.** `count()` lit le DOM à l'instant t sans rien attendre :
    sur un onglet/bouton construit en JuS, il renvoie 0 et fait échouer AVANT que Playwright ait pu
    attendre — c'est l'anti-motif que ce helper remplace (cause plausible du timeout d'exec 30 :
    un `get_by_role("tab")` cherché sur un onglet pas encore rendu).

    Budget borné et réparti : chaque candidat reçoit au moins 2 s ; le total ne dépasse pas
    `max(2000, timeout/len)`·len. Tous les candidats épuisés → dernier recours ADAPTATIF si `ident`
    est fourni (« Chantier F », même mécanisme que `locate_field`/`navigate_menu` — mesuré en run
    réel, Sapian, 2026-09-22 : un sous-menu résolu par repli adaptatif menait à un bouton dont le
    libellé exact/rôle Playwright ne matchait aucun candidat CSS codé en dur). Sans `ident`
    (défaut), comportement STRICTEMENT inchangé. Tout épuisé → `ElementIntrouvableError` qui nomme
    `quoi` ET l'URL — pour que le diagnostic porte la vraie cause, pas un « introuvable » trompeur.
    """
    par_candidat = max(2000, timeout // max(1, len(candidats)))
    for c in candidats:
        loc = page.locator(c) if isinstance(c, str) else c
        try:
            loc.first.click(timeout=par_candidat)
            return
        except PlaywrightTimeout:
            continue
    if ident:
        resolu = _repli_adaptatif(page, ident, quoi)
        if resolu is not None:
            resolu.click(timeout=par_candidat)
            return
    raise ElementIntrouvableError(f"{quoi} : aucun élément actionnable sur {page.url}")


def _chemin_sans_fragment(url: str) -> str:
    """Le chemin (+ requête) d'une URL, SANS son fragment `#…`."""
    return url.split("#", 1)[0]


# Clés du fragment Odoo (16 / 17.0 : `/web#action=…&menu_id=…&model=…&view_type=…`) dont le
# changement désigne une AUTRE vue, donc une navigation. `id` en est volontairement absent :
# l'apparition ou le changement de la seule clé `id` (même `model`) est une SAUVEGARDE — la vue
# reste la même, le contrôle de soumission doit s'exécuter.
_CLES_FRAGMENT_NAVIGATION = ("action", "menu_id", "model", "view_type")


def _est_navigation(avant: str, apres: str) -> bool:
    """Ce clic a-t-il fait CHANGER DE PAGE ou de VUE ? (§F7, 2026-09-23/24)

    | transition d'URL                                                  | contrôle exécuté |
    |-------------------------------------------------------------------|------------------|
    | chemin différent (`/en/servicemetiers` → `/en/mutation/67`)       | non              |
    | chemin `/odoo/…` (≥ 17.2) différent                               | non              |
    | même chemin, fragment `action`/`menu_id`/`model`/`view_type` change | non            |
    | même chemin, seul `id` apparaît/change (sauvegarde Odoo 16/17.0)  | oui              |
    | même chemin, fragment identique ou seulement `#` (`href="#"`)     | oui              |
    | URL strictement identique (dialogue, AJAX portail)                | oui              |

    Le fragment est lu comme une chaîne de requête (`a=1&b=2`) ; une clé absente d'un côté et
    présente de l'autre compte comme un changement.
    """
    if _chemin_sans_fragment(avant) != _chemin_sans_fragment(apres):
        return True
    frag_avant = dict(parse_qsl(avant.partition("#")[2]))
    frag_apres = dict(parse_qsl(apres.partition("#")[2]))
    return any(frag_avant.get(k) != frag_apres.get(k) for k in _CLES_FRAGMENT_NAVIGATION)


def click_button(page, label):
    """Clique le bouton/lien nommé `label`, puis vérifie une soumission bloquée — **seulement si
    ce clic n'a pas fait CHANGER DE PAGE** (§F7, 2026-09-23).

    ⚠️ **Le défaut mesuré en campagne réelle** (cas 95, projet Sapian portail, 23/09) :
    `verifier_soumission_non_bloquee` inspectait les formulaires de la page COURANTE après
    N'IMPORTE QUEL clic — y compris un `<a href="/en/mutation/67">` de navigation vers une étape
    suivante d'un formulaire multi-écrans. Sur la page de DESTINATION, tous les champs sont
    encore vides et donc « invalides » au sens HTML5 : le contrôle accusait à tort le jeu de
    données du test alors qu'aucune soumission n'avait été tentée.

    ⚠️ **Pourquoi le chemin d'URL, pas le type d'élément cliqué.** Sondé en direct sur les 3 cas
    réels avant de choisir ce signal (jamais deviné) : le bouton « Envoyer » d'un formulaire
    portail Sapian est lui-même un `<a href="#" role="button">` (pas un `<button type=submit>`),
    et le bouton d'enregistrement du back-office Odoo (OWL) est un `<button type="button">` HORS
    de tout `<form>` — aucune règle basée sur la balise/le type de l'élément ne les distingue
    correctement du cas fautif. Seul le changement de CHEMIN d'URL (hors fragment) sépare
    proprement les trois : le lien de navigation du cas 95 change de chemin, les deux autres
    (soumission AJAX portail, sauvegarde back-office en SPA) ne changent jamais le chemin.

    ⚠️ **Angle mort corrigé le 2026-09-24** : sur Odoo 16 / 17.0 la navigation du back-office ne
    change QUE le fragment (`/web#action=A` → `/web#action=B`, chemin identique) — voir
    `_est_navigation` pour la règle exacte (table transition → contrôle) et l'exception `id`.
    ⚠️ **Limite** : la garde lit `page.url` juste après le clic ; si la navigation n'est pas encore
    validée à cet instant, le contrôle tourne sur l'ancienne page (comme avant le lot, sans
    régression) et le faux `donnee_invalide` peut réapparaître par intermittence.
    """
    avant = page.url
    click_first_actionable(page, [
        page.get_by_role("button", name=label, exact=True),
        page.get_by_role("link", name=label, exact=True),
        page.get_by_role("button", name=label, exact=False),
        page.get_by_role("link", name=label, exact=False),
        f':is(a, button, input[type="submit"]):has-text("{label}")',
    ], quoi=f"Bouton '{label}'", ident=label)
    if not _est_navigation(avant, page.url):
        verifier_soumission_non_bloquee(page)


def _marquer(page, attribut: str, nom: str) -> None:
    """Ajoute `nom` à un ensemble porté par la PAGE elle-même (une page = un scénario, cycle de
    vie posé par `environment.py`) — aucun risque de fuite d'un scénario à l'autre."""
    ensemble = getattr(page, attribut, None)
    if ensemble is None:
        ensemble = set()
        setattr(page, attribut, ensemble)
    ensemble.add(nom)


def _champs_vides_voulus(page) -> set:
    """Les champs qu'UN SCÉNARIO a laissés vides EXPRÈS (`je laisse le champ … vide`) — c'est
    précisément ce que le test veut voir refusé, jamais une preuve de donnée de test fautive."""
    return getattr(page, "_tp_champs_vides_intentionnels", None) or set()


def _champs_fichiers_deja_remplis(page) -> set:
    """Les champs fichier auxquels on a réellement joint un fichier AVANT le clic — voir
    `verifier_soumission_non_bloquee` pour pourquoi ça compte."""
    return getattr(page, "_tp_champs_fichiers_remplis", None) or set()


def marquer_scenario_attend_un_refus(page) -> None:
    """Désigne CE scénario comme n'attendant AUCUNE création — posé par `environment.py`
    (2026-08-07), qui lit les steps du scénario AVANT qu'il ne commence.

    ⚠️ **Pourquoi au niveau du SCÉNARIO, et pas seulement par champ.** Le premier correctif
    (`_champs_vides_voulus`/`_champs_fichiers_deja_remplis`) ne couvrait que deux mécanismes
    précis (`je laisse le champ … vide`, `je joins un fichier …`). Mesuré le MÊME jour sur
    `/mutation_payeur` : un scénario qui renseigne un `code_client1` VOLONTAIREMENT trop court
    (`je renseigne le champ … avec la valeur …`, pas un champ vide) tombait dans le même piège —
    aucun mécanisme de marquage par champ ne couvre une valeur invalide écrite en toutes lettres.

    Un scénario qui affirme `… n'a pas augmenté` (jamais `augmente de 1`) DIT, structurellement,
    qu'il n'attend RIEN de créé — c'est la définition même d'un scénario négatif dans ce dépôt
    (vérifié sur `behave_runtime/generated/` : 31 scénarios sur 69 portent cette assertion,
    aucun ne porte les deux). Peu importe alors PAR QUEL champ le navigateur refuse : c'est
    exactement ce que le scénario est venu vérifier, jamais une preuve de donnée fautive.
    """
    page._tp_scenario_attend_un_refus = True


def _scenario_attend_un_refus(page) -> bool:
    return bool(getattr(page, "_tp_scenario_attend_un_refus", False))


def verifier_soumission_non_bloquee(page) -> None:
    """Le navigateur a-t-il REFUSÉ d'envoyer le formulaire ? — le contrôle qui empêche le faux
    verdict au lieu de l'expliquer après coup.

    ⚠️ **Pourquoi APRÈS le clic, et pas avant.** C'était mon erreur d'analyse, corrigée par une
    sonde sur le portail réel (2026-07-22). Sur `/fournisseur/creation`, le champ
    `tva_intracommunautaire` est **valide avant le clic** — aucun `pattern`, aucun `title`, rien.
    Après le clic il devient invalide : *« Le numéro de TVA doit contenir uniquement des
    chiffres. »* La règle est posée par `setCustomValidity()` **dans le gestionnaire de
    soumission**. Elle n'existe pas avant. Une vérification « avant envoi » ne l'aurait jamais vue.

    Après le clic, en revanche, le navigateur a tout évalué et **nomme** ce qui cloche :
    - `valueMissing` — un champ devenu obligatoire par un choix précédent (champs conditionnels) ;
    - `patternMismatch` — un format non respecté ;
    - `customError` — une règle métier posée en JavaScript, dont c'est la SEULE trace.

    ⚠️ **Ce que ça change pour le verdict.** Sans ce contrôle, la soumission n'a pas lieu, rien
    n'est créé, l'assertion de comptage échoue, et le test conclut **« l'application est non
    conforme »**. C'est l'accusation injuste qu'on traque depuis le début. Ici on échoue
    immédiatement, en disant l'inverse : **c'est notre jeu de données qui est refusé**.

    ⚠️ **Borné aux boutons qui SOUMETTENT.** `click_button` sert aussi à naviguer, ouvrir un
    onglet, dérouler une section. Un champ invalide ailleurs dans la page ne doit pas faire échouer
    un clic qui n'a rien à voir : on ne regarde que si un formulaire s'est **réellement opposé** à
    son propre envoi, et on se tait dans tous les autres cas.

    ⚠️ **Deux exceptions, mesurées le 2026-08-07 sur `/retenue_garantie` (cas 124 et 125).**
    Un scénario NÉGATIF (« le formulaire refuse une demande sans tel document ») laisse un champ
    vide EXPRÈS via `je laisse le champ … vide` — c'est justement ce que le test veut voir refusé,
    jamais une preuve que SON jeu de données est fautif. Sans exclusion, ce contrôle levait
    `DonneeRefuseeError` sur le champ que le scénario ciblait lui-même, empêchant l'assertion
    `Alors une erreur de validation est affichée` de jamais se prononcer — aucun de ces scénarios
    négatifs n'aurait jamais pu conclure « conforme ».
    Deuxième exception, sur le MÊME run : `copy_invoice_part` (un champ « ajouter des fichiers »)
    portait bien un fichier valide juste avant le clic — c'est le clic LUI-MÊME qui l'a vidé (JS du
    portail, mesuré en direct : `filesCount` passe de 1 à 0 entre le clic et cette lecture). Ce
    n'est pas notre donnée qui est en cause, c'est un effet de bord de l'application sur un champ
    qu'on avait pourtant correctement rempli.
    Les deux sont donc EXCLUS de ce qui peut lever un refus ici — l'assertion `Then` du scénario
    reste seule juge de ce qui s'est réellement passé.
    """
    try:
        invalides = page.evaluate("""() => {
            // On ne parle QUE des formulaires qui refusent leur propre soumission.
            const formulaires = Array.from(document.querySelectorAll('form'))
                .filter(f => f.checkValidity && !f.checkValidity());
            if (!formulaires.length) return [];
            const out = [];
            for (const f of formulaires) {
                for (const el of f.querySelectorAll('input, select, textarea')) {
                    if (el.willValidate && !el.checkValidity()) {
                        out.push({nom: el.name || el.id || '?',
                                  // 120 et non 40 : cette valeur devient une règle APPRISE, et
                                  // une valeur tronquée serait interdite sous une forme qui n'a
                                  // jamais été soumise — donc jamais reconnue au run suivant.
                                  valeur: String(el.value || '').slice(0, 120),
                                  msg: el.validationMessage || '',
                                  manquant: el.validity.valueMissing === true,
                                  drapeaux: DRAPEAUX.filter(d => el.validity[d] === true),
                                  pattern: el.pattern || '',
                                  maxLength: el.maxLength > 0 ? String(el.maxLength) : '',
                                  minLength: el.minLength > 0 ? String(el.minLength) : '',
                                  max: el.max || '', min: el.min || '',
                                  step: el.step || '', type: el.type || ''});
                    }
                }
            }
            return out.slice(0, 6);
        }""".replace("DRAPEAUX", _DRAPEAUX_JS)) or []
    except Exception:
        return  # un contrôle de sûreté ne fait jamais tomber un scénario par lui-même
    if not invalides:
        return

    if _scenario_attend_un_refus(page):
        # Ce scénario n'attend justement AUCUNE création (`… n'a pas augmenté`, jamais
        # `augmente de 1`) — peu importe PAR QUEL champ le navigateur a refusé, c'est
        # exactement ce qu'il est venu vérifier. Ses propres `Then` restent seuls juges.
        return

    vides_voulus = _champs_vides_voulus(page)
    remplis_avant = _champs_fichiers_deja_remplis(page)
    invalides = [c for c in invalides
                if c["nom"] not in vides_voulus and c["nom"] not in remplis_avant]
    if not invalides:
        return  # rien à signaler : soit le champ que LE SCÉNARIO teste lui-même, soit un champ
                 # qu'on avait bien rempli avant le clic (voir docstring, 2026-08-07)

    manquants = [c["nom"] for c in invalides if c["manquant"]]
    details = " · ".join(
        f"{c['nom']}" + (f" (={c['valeur']!r})" if c["valeur"] else "") + f" : {c['msg']}"
        for c in invalides)
    indice = ""
    if manquants:
        # Cas mesuré sur `/remboursement` : choisir `motif = "avoir"` rend 4 champs obligatoires
        # qui ne l'étaient pas au moment du crawl. L'annuaire les donnait « non requis » — et le
        # prompt disait même de NE PAS les remplir. Le dire explicitement évite de rechercher.
        indice = (f"\n{len(manquants)} champ(s) OBLIGATOIRE(S) non renseigné(s) : "
                  f"{', '.join(manquants)}. Un choix fait plus haut (liste déroulante, case) a "
                  f"pu les rendre obligatoires alors qu'ils ne l'étaient pas au départ.")
    route = _route_courante(page)
    refus = [m for m in (_refus_depuis_sonde(route, c) for c in invalides) if m]
    lever_donnee_refusee(
        f"LE NAVIGATEUR A REFUSÉ D'ENVOYER le formulaire : {len(invalides)} champ(s) invalide(s) "
        f"— {details}.{indice}\n"
        f"⚠️ L'APPLICATION N'EST PAS EN CAUSE : c'est le jeu de données du test qui est "
        f"irrecevable. Corrige ces valeurs, ne conclus pas à un défaut applicatif.", refus)


def resolve_field_name(page, ident):
    """Nom technique (`name`) du champ à cibler, à partir de `ident`.

    Tolérance décidée en 0007 : `ident` peut être l'attribut HTML `name` (cas nominal) OU — parce
    que l'agent de génération raisonne parfois en libellé UI — le LIBELLÉ humain du champ.
    Stratégie : `name` d'abord (sélecteur exact, le plus fiable) ; à défaut, on résout `ident`
    comme un libellé et on lit le `name` du contrôle associé.

    Le repli est **toujours TRACÉ** (jamais silencieux) : sans ça, un champ réellement renommé
    côté application serait retrouvé par son libellé et la régression passerait inaperçue
    (§4.6 / §5). Deux canaux, complémentaires et non redondants : le **log** pour la visibilité
    en mode dev, le **fichier sidecar** pour remonter jusqu'au rapport même sur un run vert
    (phase B+ — le log, lui, n'y survit pas).
    """
    if page.locator(f'[name="{ident}"]').count() > 0:
        return ident
    labelled = page.get_by_label(ident, exact=False)
    if labelled.count() > 0:
        resolved = labelled.first.get_attribute("name")
        if resolved:
            message = (f"champ '{ident}' introuvable par attribut name ; résolu via son libellé "
                       f"-> name='{resolved}'. Paramètre le step par le nom technique du champ.")
            logger.warning("%s %s", FIELD_FALLBACK_MARKER, message)  # mode dev (§5)
            _record_field_fallback(message)                          # jusqu'au rapport (B+)
            return resolved
    return ident  # ni name ni libellé exploitable : on laisse échouer en aval (message d'origine)


def locate_field(page, ident, *, timeout=8000):
    """Résout un champ vers un `Locator` DIRECTEMENT utilisable — remplace, pour les appelants qui
    n'ont besoin QUE de l'élément (pas de reconstruire un sélecteur combiné derrière), la stratégie
    `resolve_field_name` (`name` d'abord, seul repli : le libellé humain).

    ⚠️ **Cascade alignée sur la doc officielle Playwright/Testing Library** (recherche 2026-09-14,
    demandée par le porteur) : « privilégier les attributs qui reflètent la façon dont
    l'utilisateur ET les technologies d'assistance perçoivent la page » — `name`/classe CSS sont
    explicitement déconseillés en dernier recours seulement dans la hiérarchie officielle,
    `data-test`/`data-testid` juste avant. Odoo a besoin de `name` pour sa soumission de
    formulaire classique côté serveur ; une SPA moderne (React, Vue…) n'a souvent AUCUNE raison
    d'en poser un sur un contrôle qui ne soumet rien (filtre, tri) — d'où les bugs réels mesurés
    cette session (cas C39 : le tri du catalogue SauceDemo n'a ni `name` ni libellé, seulement
    une classe CSS et un `data-test` ; cas C45 : mécanisme voisin sur la sélection de produit).

    ⚠️ **Adaptation délibérée, pas copie aveugle de la hiérarchie officielle** : celle-ci vise un
    humain qui écrit un test en pensant « ce que je VOIS » (rôle, libellé, texte, EN PREMIER).
    Ici, `ident` est un identifiant TECHNIQUE extrait par l'agent depuis l'annuaire crawlé —
    « l'attribut HTML `name`, cas nominal » (0007). Le tenter d'abord comme un libellé humain
    irait chercher une correspondance approximative avant d'essayer la correspondance technique
    EXACTE, presque toujours disponible et strictement plus fiable pour CE cas d'usage. L'ordre
    retenu essaie donc les identifiants TECHNIQUES exacts d'abord (`name`, `data-test`,
    `data-testid`, classe CSS), et ne se rabat sur une interprétation « libellé humain » qu'en
    dernier recours — exactement ce que `resolve_field_name` faisait déjà pour `name` seul (0007),
    étendu ici aux conventions modernes sans `name` du tout.

    Chaque résolution qui n'est PAS un `name` exact reste **tracée**, jamais silencieuse (0007/§5) :
    un champ retrouvé par repli aujourd'hui peut disparaître demain sans que rien ne le dise.

    ⚠️ **Attend, ne lit jamais `count()` à l'instant t** (même défaut que `click_first_actionable`
    avant son propre correctif, cf. sa docstring) : un `wait_for(state="attached")` par palier,
    jamais une lecture DOM instantanée qui perdrait la course sur un champ rendu en JS après coup.

    Rend un `Locator` — potentiellement VIDE (`count() == 0`) si rien n'a matché après tous les
    paliers : à l'appelant de décider comment échouer (message nommant le champ et l'URL, cf.
    `ElementIntrouvableError`), comme il le faisait déjà avec le `name` brut rendu par
    `resolve_field_name`.
    """
    candidats_techniques = [f'[name="{ident}"]', f'[data-test="{ident}"]',
                            f'[data-testid="{ident}"]']
    tiers_techniques = ["name", "data_test", "data_testid"]
    # La classe CSS seulement si `ident` est un identifiant CSS valide — un libellé humain avec
    # espaces produirait sinon un sélecteur INVALIDE, pas juste « rien trouvé » (même garde que
    # le correctif C39 sur `select_field_value`, désormais partagée ici).
    if re.fullmatch(r"[A-Za-z_-][A-Za-z0-9_-]*", ident):
        candidats_techniques.append(f".{ident}")
        tiers_techniques.append("css_class")

    # Un SEUL budget d'attente, partagé entre tous les candidats techniques — même esprit que
    # `click_first_actionable` (un candidat qui timeout n'attend pas au détriment des suivants),
    # mais ancré sur l'ATTACHEMENT au DOM (on veut TROUVER l'élément), pas l'actionnabilité.
    try:
        page.locator(", ".join(candidats_techniques)).first.wait_for(
            state="attached", timeout=timeout)
    except PlaywrightTimeout:
        pass  # aucun candidat technique attaché à temps : on tente le libellé/placeholder ensuite
    else:
        for selecteur, tier in zip(candidats_techniques, tiers_techniques):
            loc = page.locator(selecteur)
            if loc.count() > 0:
                _record_selector_tier(ident, tier)
                if loc.count() > 1:
                    # ⚠️ Bug RÉEL mesuré en run (Sapian, 2026-09-22) : `[name="name"]` matchait
                    # PLUSIEURS éléments sur le formulaire de création d'un ticket Helpdesk — le
                    # `.first` de l'appelant (`fill_field`) a rempli un champ CACHÉ (probablement
                    # un widget technique invisible), jamais le VRAI titre affiché à l'écran ;
                    # Odoo a alors refusé silencieusement la sauvegarde (titre resté vide).
                    # Playwright a raison de fournir TOUS les candidats bruts (la course
                    # `attached` porte sur "quelque chose existe", pas "c'est le bon") — mais un
                    # utilisateur ne peut PHYSIQUEMENT PAS remplir un champ qu'il ne voit pas :
                    # `:visible` (pseudo-classe Playwright native, testée) élimine ce cas sans
                    # deviner. Repli sur `loc` tel quel si RIEN de visible (comportement
                    # STRICTEMENT inchangé pour tout candidat déjà mono-résultat).
                    loc_visible = page.locator(f"{selecteur}:visible")
                    if loc_visible.count() > 0:
                        loc = loc_visible
                # ⚠️ Un sélecteur technique peut résoudre un CONTENEUR non éditable, jamais le
                # contrôle lui-même — mesuré en conditions réelles (Sapian, 2026-09-23) : Odoo
                # pose le nom technique STABLE d'un champ sur le `<div class="o_field_widget">`
                # qui ENGLOBE le vrai contrôle, jamais sur l'`<input>`/`<textarea>` interne (qui,
                # lui, n'a souvent AUCUN `name` et un `id` volatil dépendant du nombre de widgets
                # déjà montés dans la session — un `id` capturé à la génération ne correspond
                # donc à RIEN à l'exécution, une session différente). Descend vers le premier
                # contrôle éditable réellement présent DANS l'élément résolu, jamais l'inverse
                # (un `<input>` déjà résolu n'a aucune raison d'avoir un enfant à chercher).
                tag = loc.first.evaluate("el => el.tagName.toLowerCase()")
                if tag not in ("input", "select", "textarea"):
                    interne = loc.locator("input, select, textarea")
                    if interne.count() > 0:
                        if interne.count() > 1:
                            interne_visible = interne.locator(":visible")
                            if interne_visible.count() > 0:
                                interne = interne_visible
                        message = (f"champ '{ident}' résolu par `{selecteur}` pointe un "
                                  f"conteneur ({tag}), pas un contrôle éditable ; descendu "
                                  f"vers son contrôle interne.")
                        logger.warning("%s %s", FIELD_FALLBACK_MARKER, message)
                        _record_field_fallback(message)
                        loc = interne.first if interne.count() > 1 else interne
                if selecteur != f'[name="{ident}"]':
                    message = f"champ '{ident}' introuvable par name ; résolu via `{selecteur}`."
                    logger.warning("%s %s", FIELD_FALLBACK_MARKER, message)
                    _record_field_fallback(message)
                return loc

    for nom_repli, tier, loc in (("libellé", "label", page.get_by_label(ident, exact=False)),
                                 ("placeholder", "placeholder",
                                  page.get_by_placeholder(ident, exact=False))):
        try:
            loc.first.wait_for(state="attached", timeout=2000)
        except PlaywrightTimeout:
            continue
        _record_selector_tier(ident, tier)
        message = f"champ '{ident}' introuvable par attribut technique ; résolu via son {nom_repli}."
        logger.warning("%s %s", FIELD_FALLBACK_MARKER, message)
        _record_field_fallback(message)
        return loc

    # ── Dernier recours : résolution ADAPTATIVE (« Chantier F », F.2/F.3) ──────────────────────
    # Tous les paliers déterministes ont échoué. Sans `intention` (le texte du step, posé par
    # `before_step` sur `page` — voir `environment.py`), on n'a rien à transmettre à un modèle :
    # comportement STRICTEMENT inchangé (aucun appel LLM, aucun coût, même retour qu'avant F).
    resolu = _repli_adaptatif(page, ident, getattr(page, "_tp_intention_step", ""))
    if resolu is not None:
        return resolu

    # Rien trouvé : rend le premier candidat (vide) — l'appelant échoue avec SON message, qui
    # nomme le champ et l'URL (comportement inchangé pour le cas "vraiment introuvable").
    return page.locator(candidats_techniques[0])


def _repli_adaptatif(page, ident: str, intention: str, *, valeur: str = ""):
    """Dernier recours partagé (« Chantier F », F.2/F.3) — `locate_field` (résolution de champ) ET
    `navigate_menu` (clic sur un libellé de menu) l'utilisent tous les deux : même mécanisme, deux
    points d'entrée différents (un identifiant technique de champ dans un cas, un libellé de menu
    dans l'autre), jamais dupliqué.

    Rend un `Locator` si le modèle a choisi un élément RÉEL de la page avec confiance, sinon
    `None` — jamais d'exception : à l'appelant de décider comment échouer, exactement comme avant
    que ce palier n'existe. Sans `intention`, court-circuite à zéro coût (aucun import, aucun
    appel réseau) — comportement STRICTEMENT inchangé pour tout appelant qui ne la fournit pas.
    """
    if os.environ.get('TESTPILOT_QUALIFICATION') == '1':
        return None
    if not intention or _adaptive_resolution is None:
        return None
    resolu = _adaptive_resolution.resoudre_champ_adaptatif(page, ident, intention, valeur=valeur)
    # ⚠️ Le diagnostic (succès ET échec) est toujours consigné dans le sidecar, jamais seulement
    # loggé — un `logger.warning` seul ne survit à AUCUN scénario avec ce formatter JSON custom
    # (Behave capture le logging en mémoire et ne le recrache nulle part ici, mesuré en run réel
    # le 2026-09-22 : le premier jet de ce palier était devenu totalement muet sur un vrai échec).
    diagnostic = getattr(page, "_tp_dernier_diagnostic_adaptatif", "")
    if resolu is None:
        if diagnostic:
            _record_field_fallback(f"résolution adaptative de '{ident}' sans succès : {diagnostic}")
        return None
    _record_selector_tier(ident, "adaptive")
    message = (f"'{ident}' introuvable par tout palier déterministe ; résolu par résolution "
              f"ADAPTATIVE (intention : « {intention} » — {diagnostic}).")
    logger.warning("%s %s", FIELD_FALLBACK_MARKER, message)
    _record_field_fallback(message)
    return resolu


class ElementIntrouvableError(Exception):
    """Aucun élément actionnable trouvé pour l'action demandée (même famille que
    `InvalidOptionValueError`/`DonneeRefuseeError` ci-dessous — décision 0015, prolongée le
    2026-09-14, cas C45 sur SauceDemo).

    ⚠️ **Le même défaut qu'`InvalidOptionValueError`, une classe de plus dans la même famille.**
    `click_first_actionable` (et les quelques helpers qui en partagent l'esprit —
    `select_field_value`, `select_first_agence`) levaient un `AssertionError` NU quand ils ne
    trouvaient RIEN à cliquer/sélectionner : Behave l'affiche « ASSERT FAILED: »,
    `defect_taxonomy` la classe `assertion_mismatch`, et le verdict devient `non_conforme` — on
    accuse l'APPLICATION d'un défaut alors que c'est NOTRE sélecteur qui n'a rien trouvé.

    Mesuré sur le cas C45 (SauceDemo) : `select_product_in_list` ne cherchait des liens produit
    que sous `/description/`, `/product/`, `/detail/`, `/formulaire-applicatif/` — des chemins
    Odoo — quand SauceDemo route ses fiches produit en JS pur (`href="#"`). Le step échouait
    SYSTÉMATIQUEMENT, sans jamais atteindre le formulaire de paiement que le scénario testait
    réellement — et le verdict accusait pourtant ce formulaire d'un défaut de validation.

    Playwright lève déjà correctement `TimeoutError`/`PlaywrightTimeoutError`, classées
    `wrong_field_name` (voir `defect_taxonomy._EXCEPTION_TO_CAUSE`) — mais `click_first_actionable`
    CONSOMME ce `TimeoutError` par candidat pour en essayer un autre, et son message final
    consolidé (qui nomme TOUS les candidats essayés + l'URL, bien plus exploitable qu'un seul
    `TimeoutError` isolé sur le DERNIER candidat) a besoin de sa PROPRE classe pour rester
    classé du même bord technique.

    Hérite de `Exception` (PAS de `AssertionError`) : Behave ne masque le nom de la classe que
    pour `AssertionError` (« ASSERT FAILED: ») — une exception dédiée s'affiche
    « ERROR: ElementIntrouvableError: … », et `defect_taxonomy` la reconnaît au type, sans
    deviner sur un texte que l'agent (ou nous) aurait pu écrire différemment.
    """


class NavigationImpossibleError(Exception):
    """Le parcours attendu (section, page, menu) est absent — un problème de PARCOURS, pas
    l'application qui se comporte mal (même famille qu'`ElementIntrouvableError` ci-dessus).

    Utilisée par `access_portal_section` : un `AssertionError` nu classait son
    « PRÉREQUIS MANQUANT » en `assertion_mismatch` — un vrai bug applicatif présumé — alors que
    c'est un problème de PARCOURS (le test n'est jamais arrivé à la bonne page), la même famille
    que `HTTPError`, déjà classée `wrong_navigation`.
    """


class PreconditionNonRemplieError(Exception):
    """Un PRÉREQUIS d'environnement affirmé par un step de Contexte n'est pas rempli (module Odoo
    non installé, session RPC absente, utilisateur non authentifié, données résiduelles) — le test
    ne peut PAS être joué, ce n'est pas l'application qui se comporte mal (lot 02, décision D1).

    Hérite de `Exception` (PAS de `AssertionError`) : Behave ne masque le nom de la classe que pour
    `AssertionError` (« ASSERT FAILED: ») ; celle-ci s'affiche « ERROR: PreconditionNonRemplieError »
    et `defect_taxonomy` la reconnaît au TYPE — un signal posé par la bibliothèque, non ambigu par
    construction (personne d'autre ne la lève). Projetée en `blocked`, jamais en `non_conforme`.
    """


class InvalidOptionValueError(ValueError):
    """Le test passe à un `<select>` une valeur que l'application n'offre pas (décision `0019`).

    ⚠️ **Une classe DÉDIÉE, et c'est tout l'intérêt.** `defect_taxonomy` classe sur le **type
    d'exception** (`0015`) : `InvalidOptionValueError` → `broken_test_code` → réparable **sans**
    confirmation humaine, parce que **seule** la bibliothèque partagée la lève. Le signal ne se
    déduit pas, il se **pose** — c'est la forme la plus forte du principe 1.

    **Surtout pas un `ValueError` nu** : `0015` l'a délibérément laissé hors du barème parce
    qu'**odoorpc le lève légitimement** (« aucun enregistrement » = contexte serveur manquant →
    jugement humain). Le mapper aurait fait réparer un test contre un vrai problème de données —
    le faux négatif que §4.4 déclare inacceptable. `tests/test_taxonomy_signal.py` a refusé mon
    premier jet, qui faisait exactement ça.

    Hérite de `ValueError` : un `except ValueError` existant continue de l'attraper.
    """


class DonneeRefuseeError(ValueError):
    """La DONNÉE du test a été refusée — l'application n'est PAS en cause (§2bis, 4ᵉ verdict).

    ⚠️ **Le signal du 4ᵉ verdict `donnee_invalide`, posé au lieu d'être deviné.** Trois situations
    disent la même chose : « ce n'est pas l'app qui est en défaut, c'est notre jeu de données » —
    le navigateur refuse une valeur qui viole sa validation, un filtre JS a mutilé la saisie, ou le
    test emploie le mauvais type de champ. Avant, ces cas levaient une `AssertionError` → Behave
    l'affiche « ASSERT FAILED: » → la taxonomie la classait `assertion_mismatch` → verdict
    **`non_conforme`** : on accusait l'application à tort, exactement le défaut que le §2bis traque.

    ⚠️ **Sous-classe de `ValueError`, PAS de `AssertionError`** — et c'est tout l'intérêt. Behave
    ne masque le nom de la classe QUE pour les `AssertionError` (« ASSERT FAILED: »). Une
    exception dédiée s'affiche « ERROR: DonneeRefuseeError: … » : `defect_taxonomy` la reconnaît
    au type (comme `InvalidOptionValueError` en 0019) et la projette sur `donnee_invalide`. Le
    signal se POSE, il ne se déduit pas — forme la plus forte du principe 1.

    Hérite de `ValueError` : un `except ValueError` existant continue de l'attraper.

    ⚠️ **`refus` porte le fait MESURÉ, structuré** (§5bis n°1) — mais `str(exc)` reste
    **strictement inchangé** : la taxonomie classe sur le type, Behave n'affiche que le message,
    et l'un comme l'autre ignorent cet attribut. Le payload ne franchit d'ailleurs pas la
    frontière de processus (Behave ne recrache qu'un texte) : c'est le sidecar qui le transporte.
    Il sert au test unitaire et au diagnostic local.
    """

    def __init__(self, message, refus=()):
        super().__init__(message)
        self.refus = tuple(refus)


def _options_of(select_locator):
    """Les options réelles d'un <select> : [(value, texte), …]. Lecture DOM, aucune attente."""
    return [tuple(o) for o in select_locator.evaluate(
        "el => Array.from(el.options).map(o => [o.value, (o.text || '').trim()])")]


def select_option_strict(select_locator, value, field=""):
    """`select_option` qui échoue TOUT DE SUITE et DIT pourquoi (décision 0019).

    ⚠️ **Le problème que ce helper résout n'est pas la lenteur : c'est le MENSONGE.**
    `select_option(value="new")` sur une option inexistante attend **30 secondes** puis lève :

        Locator.select_option: Timeout 30000ms exceeded.
        Call log: - waiting for locator("select[name='types_demandes']")

    Le message ne nomme que le **locator du select** — il donne à croire que **le select est
    introuvable**. Il est là, visible, activé. Playwright attendait l'**option**.

    **Toute la chaîne a cru ce message** (mesuré, rejeu du cas 1, exec 27) : `defect_taxonomy` a
    classé `ui_timeout → wrong_field_name → « Champ/sélecteur introuvable »`, et l'agent de
    réparation a cherché un problème de **sélecteur** — donc réparé à côté, et rebrûlé du budget à
    chaque tentative. C'est `0002` qui se rejoue : *le message d'erreur ne porte pas la vraie
    cause, et tout ce qui le lit se trompe dans la même direction.*

    On lit donc les options **avant** d'agir, et on lève une erreur qui nomme la cause **et les
    valeurs possibles** — l'agent reçoit alors de quoi corriger du premier coup, au lieu de deviner.

    **`InvalidOptionValueError` et non `AssertionError`** : c'est le code du test qui est faux, pas
    l'application qui se comporte mal. Et surtout pas un `ValueError` **nu** — voir la docstring
    de `InvalidOptionValueError` : odoorpc en lève légitimement, et le confondre ferait réparer un test
    contre un vrai problème de données (§4.4). Vérifié par test, pas supposé.

    Tolérant comme le reste de la bibliothèque (`0007`) : on accepte une **valeur** d'option ou son
    **libellé affiché** — l'agent peut légitimement connaître l'un ou l'autre. Un repli n'est
    jamais silencieux : il est tracé comme les autres.
    """
    options = _options_of(select_locator)
    valeurs = [v for v, _ in options]
    if value in valeurs:
        select_locator.select_option(value)
        return
    # Repli TOLÉRANT : le libellé affiché plutôt que la valeur technique (même esprit que 0007).
    for v, texte in options:
        if texte == value:
            message = (f"select '{field}' : « {value} » est le LIBELLÉ, la valeur est « {v} » "
                       f"— repli appliqué")
            logger.warning("%s %s", FIELD_FALLBACK_MARKER, message)
            _record_field_fallback(message)
            select_locator.select_option(v)
            return
    # Ni valeur ni libellé : on échoue MAINTENANT, en disant quoi utiliser.
    inventaire = ", ".join(f"{v!r} ({t})" for v, t in options) or "(aucune option)"
    raise InvalidOptionValueError(
        f"select '{field}' : la valeur {value!r} n'existe pas. Options réelles : {inventaire}. "
        f"Utilise une valeur existante — ne l'invente pas."
    )


def fill_field(page, name, value):
    # ⚠️ `locate_field` (cascade name → data-test(id) → classe CSS → libellé → placeholder)
    # remplace ici `resolve_field_name` (name → libellé SEULEMENT) — étape 2 du plan de
    # généricité (2026-09-14, après `select_field_value`) : un champ TEXTE, SELECT ou CASE À
    # COCHER sans `name` (convention Odoo, cf. `locate_field`) est maintenant trouvé, puisque les
    # branches ci-dessous agissent sur l'élément RÉSOLU (`el`), jamais sur une reconstruction
    # `[name=...]`. Seul le groupe de radios (exigence du HTML : tous ses membres PARTAGENT
    # `name`, ce n'est pas une convention Odoo) reste `name`-based ci-dessous — limite assumée,
    # pas un oubli. Le repli JS du texte, lui, a rejoint `el` à l'étape 2.1 du plan de
    # consolidation (2026-09-15) : c'était le DERNIER chemin `name`-only de cette fonction — un
    # champ sans `name` qui déclenchait ce repli (ex. `.fill()` refusé par un widget non standard)
    # échouait encore comme avant `locate_field`, exactement le trou que l'audit avait relevé.
    champ = locate_field(page, name, timeout=10000)
    if champ.count() == 0:
        raise ElementIntrouvableError(f"Champ '{name}' introuvable sur {page.url}")
    el = champ.first
    tag = el.evaluate("el => el.tagName.toLowerCase()")
    input_type = el.evaluate("el => (el.type || '').toLowerCase()")
    if tag == "select":
        select_option_strict(el, value, field=name)
    elif input_type == "radio":
        page.locator(f"input[type='radio'][name='{name}'][value='{value}']").first.check(force=True)
    elif input_type == "checkbox":
        if value.lower() in ("true", "1", "yes", "oui"):
            el.check(force=True)
        else:
            el.uncheck(force=True)
    elif input_type == "file":
        # ⚠️ Un <input type="file"> ne se remplit PAS comme du texte : le navigateur l'interdit
        # (« InvalidStateError: This input element accepts a filename »). Mesuré le 2026-07-21 :
        # c'était 2 échecs techniques sur 3 sur les formulaires à pièce jointe — et 13 des
        # 37 routes du portail en ont un, presque toujours REQUIS. L'agent ne pouvait pas
        # réussir : l'outil n'existait pas. On téléverse un vrai fichier de test.
        attach_file(page, name, value)
    else:
        # ⚠️ `.fill()` NATIF Playwright d'ABORD (bug SauceDemo, 2026-09-14) — jamais le JS brut en
        # premier recours. Mesuré en conditions réelles : `el.value = ...` + `dispatchEvent()`
        # met bien la valeur dans le DOM (Playwright la relit sans problème), mais une appli qui
        # garde son PROPRE état interne (au lieu de relire le DOM à la soumission — la plupart des
        # frameworks modernes) ne voit jamais ce changement : le clic « Login » de SauceDemo
        # traitait alors le champ comme VIDE (« Username is required » au lieu de « Username and
        # password do not match »), alors que Playwright lui-même rapportait la bonne valeur.
        # `.fill()` simule une vraie saisie au niveau du navigateur (CDP) — reconnue par n'importe
        # quel framework, contrairement à un `dispatchEvent` synthétique. Le JS brut reste un
        # REPLI, jamais supprimé : conservé pour les widgets Odoo qui l'exigeaient à l'origine
        # (aucune preuve que `.fill()` y échoue, mais aucune preuve du contraire non plus — le
        # risque de casser un chemin Odoo déjà éprouvé n'est pas à prendre sans site réel pour
        # le vérifier).
        try:
            el.fill(value)  # ⚠️ la valeur BRUTE : `.fill()` n'est pas du JS interpolé
        except Exception as exc:
            logger.warning("[fill_field] .fill() natif a échoué sur '%s' (%s) — repli JS", name,
                           type(exc).__name__)
            # ⚠️ Agit sur `el`, l'élément déjà résolu par `locate_field` — plus jamais une
            # reconstruction `document.querySelector('[name="{name}"]')` (étape 2.1, 2026-09-15) :
            # un champ atteint par data-test/data-testid/classe CSS/libellé, SANS `name` du tout,
            # tombait encore dans ce trou avant ce correctif si `.fill()` levait dessus. La valeur
            # est passée en ARGUMENT Playwright, jamais interpolée : aucun échappement manuel
            # n'est donc nécessaire (`.fill()` juste au-dessus suit déjà cette règle).
            el.evaluate(
                """(elt, val) => {
                    elt.value = val;
                    elt.dispatchEvent(new Event('input', { bubbles: true }));
                    elt.dispatchEvent(new Event('change', { bubbles: true }));
                }""", value)
        _verifier_valeur_retenue(page, el, name, value)


def _verifier_valeur_retenue(page, el, name, ecrit) -> None:
    """Le champ a-t-il GARDÉ ce qu'on a écrit ? — un contrôle sans aucune connaissance de règle.

    ⚠️ **Le défaut qu'il ferme** (mesuré le 2026-07-22 sur `/client_contentieux` et
    `/retenue_garantie`). Le champ `numero_facture1` porte un filtre JavaScript qui **supprime les
    caractères non numériques**. L'agent y écrivait `FAC-TEST-001` ; le champ retenait `001`. Trois
    chiffres au lieu des sept exigés → soumission bloquée → rien créé → verdict `non_conforme`.
    **L'application avait raison ; notre valeur avait été mutilée en silence.**

    ⚠️ **La force de ce contrôle est qu'il ne connaît RIEN.** Il ne lit ni `pattern`, ni `title`,
    ni la moindre cartographie : il compare ce qu'on a écrit à ce que le champ contient. Il attrape
    donc les filtres JavaScript, les masques de saisie et les normalisations — tout ce qu'un crawl
    statique ne verra jamais. C'est le complément exact du plafond de l'annuaire.

    ⚠️ **Il échoue TÔT et pour ce qu'il est** : « ma donnée a été refusée », pas « l'application est
    en défaut ». C'est précisément la confusion qu'on traque.

    ⚠️ **Relit `el`, l'élément déjà résolu par `locate_field`, plus jamais un `[name="{name}"]`
    reconstruit côté page** (étape 2.1 du plan de consolidation, 2026-09-15) — `page` reste un
    paramètre, mais seulement pour `_route_courante(page)` ci-dessous (situer le refus mesuré),
    jamais pour relire la valeur. Un champ résolu par data-test/data-testid/classe CSS/libellé,
    SANS `name`, échouait silencieusement ce contrôle avant ce correctif (retenu toujours `None`
    faute d'attribut `name` à retrouver — le contrôle se taisait au lieu d'attraper la mutilation).

    Tolérant sur ce qui n'est pas une mutilation : espaces de bordure, et normalisations de casse
    (certains champs majusculisent) — les signaler produirait du bruit sans défaut réel.
    """
    try:
        retenu = el.evaluate("elt => (elt ? String(elt.value) : null)")
    except Exception:
        return  # un contrôle de sûreté ne fait jamais tomber un scénario par lui-même
    if retenu is None:
        return
    attendu = str(ecrit).strip()
    if retenu.strip() == attendu or retenu.strip().lower() == attendu.lower():
        return
    # ⚠️ Tolérer un REFORMATAGE cosmétique qui n'ajoute/ne retire que des ESPACES : un IBAN
    # « FR76…189 » que le champ réaffiche « FR76 3000 …189 » reste valide, la soumission passe
    # (mesuré au rejeu 2026-07-23). Ça n'affaiblit PAS la détection d'une vraie mutilation : un
    # filtre qui SUPPRIME des caractères (« FAC-TEST-001 » → « 001 ») diffère encore une fois les
    # espaces retirés des deux côtés.
    if re.sub(r"\s+", "", retenu).lower() == re.sub(r"\s+", "", attendu).lower():
        return
    lever_donnee_refusee(
        f"Le champ « {name} » a MODIFIÉ la valeur saisie : écrit {attendu!r}, retenu {retenu!r}. "
        f"Un filtre de saisie l'a transformée — la valeur du test est donc INADAPTÉE à ce champ "
        f"(ce n'est pas un défaut de l'application). Choisis une valeur conforme à son format.",
        [RefusMesure(route=_route_courante(page), champ=name,
                     type_contrainte="filtre_saisie",
                     valeur_contrainte=_classe_conservee(attendu, retenu),
                     valeur_refusee=attendu, origine="filtre_saisie",
                     preuve=f"le champ a retenu {retenu!r}", valeur_retenue=retenu)])


# Les classes de caractères qu'un filtre de saisie peut conserver, de la plus stricte à la plus
# large. L'ordre compte : `001` s'explique par `\d` comme par `\w`, et c'est `\d` qui informe.
_CLASSES_FILTRE = ((r"\d", str.isdigit),
                   (r"[A-Za-z]", str.isalpha),
                   (r"\w", lambda c: c.isalnum() or c == "_"))


def _classe_conservee(ecrit, retenu) -> str:
    """La classe de caractères qu'un filtre a laissé passer — **seulement si elle est PROUVÉE**.

    ⚠️ Prouvée veut dire : filtrer `ecrit` sur cette classe redonne **exactement** `retenu`.
    Mesuré sur `/client_contentieux` — `FAC-TEST-001` retenu `001` : garder les chiffres de
    l'écrit redonne `001`, donc `\\d` est la règle. Si aucune classe ne reconstruit le retenu, on
    rend `''` : la valeur est noircie, mais **aucune contrainte n'est affirmée**. Deviner ici
    ferait dire à l'annuaire une règle que l'application n'a jamais énoncée.

    ⚠️ **`retenu == ''` est un cas DÉGÉNÉRÉ, pas une preuve — trouvé en run réel** (campagne 18,
    2026-08-06, champ `date_debut` de `/retenue_garantie`). Quand RIEN n'est retenu, filtrer
    `ecrit` sur N'IMPORTE QUELLE classe absente de `ecrit` redonne trivialement `''` : écrire
    « 01/01/2024 » (aucune lettre) « prouvait » `[A-Za-z]`, et le résolveur en déduisait une
    valeur de rechange faite uniquement de lettres (`AAAAAAAA`) — qui, elle aussi sans le moindre
    chiffre, « prouvait » ensuite `\\d` au tour suivant. Un champ **réellement vide en sortie**
    (masque de date, `<input type="date">` non éditable au clavier…) apprenait donc une classe
    inventée à chaque tentative, sans jamais converger — l'« absence de signal prise pour un
    signal positif » que ce projet traque partout ailleurs, glissée ici. Un retenu vide ne prouve
    RIEN sur ce qui a été filtré : on refuse la classe plutôt que d'en affirmer une par accident.
    """
    if not str(retenu).strip():
        return ""
    for motif, garde in _CLASSES_FILTRE:
        if "".join(c for c in str(ecrit) if garde(c)) == str(retenu):
            return motif
    return ""


class ResolveurIncompletError(RuntimeError):
    """Le RÉSOLVEUR n'a pas pu construire le test — l'application n'est ni jugée ni accusée.

    ⚠️ **Le verdict HONNÊTE d'un test non constructible** (raffinement 2026-07-23, cas `agence`).
    Quand le déterministe ne peut pas remplir un champ requis (liste déroulante sans option
    sélectionnable, annuaire absent, formulaire introuvable), le test n'a jamais tourné contre le
    comportement de l'application : on ne peut RIEN en conclure. Avant, une `AssertionError` faisait
    tomber ce cas en `non_conforme` — ça **accusait l'application** d'un défaut qu'on n'a pas
    observé. Une exception dédiée (ni `AssertionError`, ni `DonneeRefuseeError`) le classe en
    `technical_error / indetermine` : le test à instruire, pas l'application à blâmer.

    Sous-classe de `RuntimeError` — Behave affiche « ERROR: ResolveurIncompletError: … », la
    taxonomie la reconnaît au type (signal posé, jamais deviné — même patron que `0019`).
    """


def remplir_formulaire_valide(context, route):
    """RÉSOLVEUR DÉTERMINISTE (§2bis, composant 2) — remplit tous les champs requis VISIBLES du
    formulaire courant avec des valeurs garanties recevables, lues dans l'annuaire mesuré.

    ⚠️ **Le renversement.** Sur le chemin nominal, le LLM ne nomme plus aucun champ ni ne saisit
    aucune valeur : il dit l'INTENTION (« remplis le formulaire avec des données valides »), et
    cette couche fabrique la FORME. Les causes historiques (valeur qui viole `\\d{7}`, champ requis
    oublié, upload dans une case, option de select inventée) deviennent structurellement
    impossibles — le LLM n'a plus la main dessus. Mesuré le 2026-07-22 : c'est exactement ce que
    l'injection des contraintes dans le prompt ne suffisait PAS à garantir.

    L'annuaire est choisi par PROJET (`context.project_id`, posé par le runner) puis apparié à la
    page RÉELLE (`context.page.url`) — plus fiable que le libellé `route` du scénario, qui peut
    différer de l'URL concrète. `route` reste le repli et nourrit le message d'erreur.

    Ce que le résolveur a saisi est mémorisé sur `context.saisie_resolveur` — l'étape 3
    (vérification par l'état) s'en servira pour asserter que la donnée a réellement atterri.
    """
    # Imports DIFFÉRÉS : la bibliothèque doit s'importer à la collecte (dry-run) sans exiger le
    # paquet `testpilot` ; il n'est requis qu'à l'EXÉCUTION réelle du step (PYTHONPATH posé par
    # BehaveRunner). `testpilot.generation.__init__` est paresseux : aucun tirage d'anthropic ici.
    from testpilot.generation import domain_model
    from testpilot.generation import regles_apprises as ra
    from testpilot.generation import valeur_conforme as vc

    project_id = getattr(context, "project_id", None)
    modele = domain_model.charger_par_projet_id(project_id)
    if not modele:
        raise ResolveurIncompletError(
            f"résolveur: aucun annuaire pour ce projet (project_id={project_id!r}). "
            "Lancez l'exploration du projet avant de générer un cas nominal.")

    url = getattr(getattr(context, "page", None), "url", "") or ""
    formulaires = (domain_model.formulaires_requis(modele, [url])
                   or domain_model.formulaires_requis(modele, [route]))
    if not formulaires:
        raise ResolveurIncompletError(
            f"résolveur: formulaire introuvable dans l'annuaire pour route='{route}' "
            f"(url réelle '{url}'). L'annuaire est-il à jour pour cette page ?")

    # Ce que les REFUS précédents ont appris sur cette application (§5bis n°1). Fusionné à la
    # LECTURE, jamais écrit dans l'annuaire : le fichier du crawl reste une référence versionnée,
    # relue par un humain, seule capable de trahir une régression de l'application.
    regles = ra.charger(project_id)

    saisie = {}
    for form in formulaires:
        for champ in form["requis"]:
            if not champ.get("visible", True):
                continue  # champ requis CACHÉ (injecté serveur) : jamais saisi par l'interface (5ᵉ cause)
            champ = ra.fusionner(
                champ, ra.pour_champ(regles, form.get("route") or route, champ["name"]))
            try:
                valeur = vc.valeur_pour(champ)
            except vc.ValeurNonSynthetisable as exc:
                raise ResolveurIncompletError(
                    f"résolveur: champ requis '{champ['name']}' non synthétisable ({exc}). "
                    "Contrainte hors du périmètre déterministe — cas à instruire.") from exc
            fill_field(page=context.page, name=champ["name"], value=valeur)
            saisie[champ["name"]] = valeur

    context.saisie_resolveur = saisie


def attach_file(page, name, value=""):
    """Téléverse un fichier dans un `<input type="file">`.

    `value` sert de NOM de fichier quand il ressemble à un nom (`rib.pdf`) ; sinon on génère
    `piece-jointe-{champ}.pdf`. Le contenu est un PDF minimal mais VALIDE — un fichier vide ou
    un `.txt` déguisé peut être rejeté par une validation de type côté application, et on
    diagnostiquerait alors un faux « champ introuvable ».

    Le fichier est créé dans un répertoire temporaire du système : il n'a pas à survivre au run,
    et l'écrire dans le dépôt polluerait l'arborescence à chaque exécution.
    """
    import re
    import tempfile
    from pathlib import Path

    nom = value.strip() if re.search(r"\.[A-Za-z0-9]{2,5}$", value.strip() or "") else ""
    if not nom:
        nom = f"piece-jointe-{re.sub(r'[^A-Za-z0-9_-]+', '-', name)}.pdf"
    chemin = Path(tempfile.gettempdir()) / "testpilot-uploads" / nom
    chemin.parent.mkdir(parents=True, exist_ok=True)
    if nom.lower().endswith(".pdf"):
        # PDF minimal valide (en-tête + trailer) — accepté par un contrôle de type courant.
        chemin.write_bytes(
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n")
    else:
        chemin.write_text("Fichier de test TestPilot.\n", encoding="utf-8")

    # `locate_field` (voir `fill_field`/`select_field_value`) — un champ fichier identifié
    # SANS `name` (data-test, classe CSS, libellé) est désormais trouvé aussi.
    champ = locate_field(page, name, timeout=10000)
    if champ.count() == 0:
        raise ElementIntrouvableError(f"Champ '{name}' introuvable sur {page.url}")
    cible = champ.first

    # ⚠️ Refuser TOUT DE SUITE une cible qui n'est pas un champ fichier (2026-07-22).
    # Mesuré sur `/sinistre_client` : `info_sinistre_ids` est une CASE À COCHER dont le nom évoque
    # des documents. L'agent y a « joint un fichier » ; `set_input_files` a attendu **30 secondes**
    # un élément téléversable, puis échoué sur une trace Playwright illisible. Trente secondes
    # perdues, et un diagnostic qui ne nommait pas la vraie cause.
    #
    # Le type est connu en une milliseconde. On le lit, et on dit CE QU'IL FAUT FAIRE À LA PLACE —
    # un message d'erreur qui n'indique pas l'issue oblige à re-diagnostiquer à chaque fois.
    reel = (cible.evaluate("el => (el.type || '').toLowerCase()") or "")
    if reel != "file":
        equivalent = {
            "checkbox": f'je renseigne le champ "{name}" avec la valeur "oui"  (pour la cocher)',
            "radio": f'je renseigne le champ "{name}" avec la valeur "<option>"',
        }.get(reel, f'je renseigne le champ "{name}" avec la valeur "<valeur>"')
        # ⚠️ **N'APPREND RIEN, et c'est délibéré** (§5bis n°1). L'application n'a rien refusé :
        # c'est l'AGENT qui a employé le mauvais step sur un champ qui n'est pas un fichier. En
        # faire une « règle apprise » remplirait l'annuaire de faits sur *notre* code de test au
        # lieu de faits sur l'application — et le résolveur n'a rien à en tirer. Seul un refus
        # émis par le navigateur ou par le serveur est une mesure de l'application.
        raise DonneeRefuseeError(
            f"Le champ « {name} » n'est PAS un champ fichier (type={reel or 'inconnu'}) : on ne "
            f"peut rien y téléverser. Emploie plutôt :\n    {equivalent}")

    cible.set_input_files(str(chemin))
    # Mémorisé pour `verifier_soumission_non_bloquee` (2026-08-07) : si CE champ redevient
    # invalide après un clic, ce n'est pas notre donnée qui est en cause — on l'avait bien rempli.
    _marquer(page, "_tp_champs_fichiers_remplis", name)


def leave_field_empty(page, name):
    """Laisse un champ VIDE — pour un scénario qui teste l'omission d'un champ requis.

    ⚠️ **Ne gérait que les champs texte** (mesuré le 2026-07-21) : sur un `<select>`,
    `fill("")` lève « Element is not an <input>, <textarea> or [contenteditable] » — une erreur
    Playwright cryptique qui fait échouer techniquement un scénario par ailleurs légitime.
    Même famille que les champs fichier : le helper ignorait un type d'élément.

    Un `<select>` se vide en choisissant son option vide (`value=""`), quand elle existe. Si elle
    n'existe pas, le champ **ne PEUT pas** être laissé vide : on le dit clairement plutôt que de
    laisser une erreur de bas niveau, qu'on diagnostiquerait à tort en « champ introuvable ».
    """
    # `locate_field` (voir `fill_field`/`select_field_value`) : un champ SANS `name` (data-test,
    # classe CSS, libellé) peut aussi être laissé vide intentionnellement.
    champ = locate_field(page, name, timeout=10000)
    if champ.count() == 0:
        raise ElementIntrouvableError(f"Champ '{name}' introuvable sur {page.url}")
    el = champ.first
    # ⚠️ Marqué avec l'identifiant RÉEL (`name`, sinon `id`) — celui que
    # `verifier_soumission_non_bloquee` lira plus tard sur l'élément DEVENU invalide
    # (`el.name || el.id`), pas forcément `name` tel quel si `locate_field` l'a résolu par un
    # autre biais. Sans ça, un champ SANS `name` intentionnellement vide ne serait pas reconnu
    # comme tel, et accuserait à tort le jeu de données du scénario.
    identifiant_reel = el.evaluate("el => el.name || el.id || ''") or name
    # Mémorisé pour `verifier_soumission_non_bloquee` (2026-08-07) : CE champ vide est le sujet
    # même du test, jamais une preuve que le jeu de données du scénario est fautif.
    _marquer(page, "_tp_champs_vides_intentionnels", identifiant_reel)
    tag = el.evaluate("el => el.tagName.toLowerCase()")
    input_type = el.evaluate("el => (el.type || '').toLowerCase()")

    if tag == "select":
        valeurs = el.evaluate("el => Array.from(el.options).map(o => o.value)")
        if "" not in valeurs:
            raise ElementIntrouvableError(
                f"le champ « {name} » est une liste déroulante SANS option vide : il ne peut pas "
                f"être laissé vide. Valeurs possibles : {', '.join(v for v in valeurs if v)}")
        el.select_option("")
    elif input_type == "checkbox":
        el.uncheck(force=True)
    elif input_type == "file":
        # Un champ fichier vide = aucun fichier téléversé : c'est son état naturel, rien à faire.
        return
    else:
        el.fill("", force=True)


def select_field_value(page, value, field):
    """⚠️ Même défaut que `fill_field`, en PIRE — corrigé le 2026-07-17 (`0019`).

    L'ancien code faisait `try: select_option(value, timeout=2000) except Exception:
    select_option(label=value, timeout=5000)`. Trois problèmes, dans l'ordre de gravité :

    1. **`except Exception` avale la CAUSE.** Si les deux tentatives échouent, l'erreur finale
       parle du **libellé**, et la vraie information (« la valeur n'existe pas, voici celles qui
       existent ») est perdue. C'est le motif de `0011` : un repli silencieux qui détruit le signal.
    2. Il **attend 2 s puis 5 s** pour découvrir ce qu'une lecture du DOM donne instantanément.
    3. Il ne dit **jamais** les options réelles à celui qui doit corriger.

    `select_option_strict` lit les options d'abord : valeur OU libellé (le repli de `0007`, mais
    **tracé**, jamais muet), et sinon une erreur qui nomme les valeurs possibles.
    """
    # ⚠️ `locate_field` (cascade name → data-test(id) → classe CSS → libellé) remplace ici la
    # résolution `name`-seul de `resolve_field_name` — un `<select>` qui sert de FILTRE (tri,
    # recherche) n'a souvent AUCUN attribut `name`, ce n'est pas un champ de formulaire soumis
    # (bug réel, cas C39, SauceDemo, 2026-09-14 : `<select class="product_sort_container"
    # data-test="product-sort-container">`, sans `name` du tout — l'agent avait pourtant
    # correctement identifié le contrôle par sa classe CSS, visible dans l'annuaire).
    champ = locate_field(page, field)
    tag = champ.first.evaluate("el => el.tagName.toLowerCase()") if champ.count() > 0 else None

    if tag == "select":
        select_option_strict(champ.first, value, field=field)
        return

    # ⚠️ Champ RELATIONNEL Odoo (many2one) — `product_id`, `partner_id`… — rendu comme un
    # `<input type="text">`, jamais un `<select>` ni un lien de catalogue portail. Mesuré en
    # RUN RÉEL (Parc IT, champ `product_id`, 2026-09-18) : `select_field_value` levait
    # `ElementIntrouvableError` en cherchant un radio qui n'a jamais existé — l'ancien code
    # n'avait tout simplement AUCUNE branche pour ce widget. Vérifié EN DIRECT sur Sapian
    # (2026-09-22) avant d'écrire ce correctif : voir `select_many2one_odoo` ci-dessous.
    if tag == "input":
        select_many2one_odoo(page, champ.first, value, field=field)
        return

    # Pas de <select>/<input> : repli radio, `name` DÉLIBÉRÉMENT ICI (pas `locate_field`) — un
    # groupe de radios PARTAGE le même `name` sur tous ses membres, une EXIGENCE du HTML pour que
    # le navigateur les traite comme un seul groupe exclusif, pas une convention propre à Odoo.
    radio = page.locator(f"input[type='radio'][name='{field}'][value='{value}']")
    try:
        page.locator(f"input[type='radio'][name='{field}']").first.wait_for(
            state="attached", timeout=8000)
    except PlaywrightTimeout:
        raise ElementIntrouvableError(
            f"Champ select ou radio '{field}' introuvable sur {page.url} (valeur: '{value}')")
    if radio.count() > 0:
        radio.first.check(force=True)
        return
    # Le radio EXISTE, mais sans l'option demandée : même défaut qu'un `<select>` avec une
    # valeur absente (0019) — c'est le test qui demande une valeur inexistante, pas l'application
    # qui se comporte mal. Même classe, pour la même raison.
    raise InvalidOptionValueError(
        f"Radio '{field}' présent mais sans l'option '{value}' sur {page.url}")


def select_many2one_odoo(page, champ, value: str, *, field: str = "") -> None:
    """Sélectionne `value` dans un champ RELATIONNEL Odoo (many2one) — `product_id`,
    `partner_id`, `employee_id`… Ni `select_field_value` (select/radio) ni
    `select_product_in_list` (lien de catalogue portail) ne correspondent à ce widget : un champ
    texte qui, une fois qu'on y tape, ouvre une liste de résultats à cliquer.

    ⚠️ **Vérifié EN DIRECT sur Sapian** (formulaire « Générer des équipements », champ Produit,
    2026-09-22) — jamais deviné depuis la documentation officielle d'Odoo, qui ne descend pas à
    ce niveau de détail (vérifié aussi, `developer/reference/frontend/`, avant d'écrire quoi que
    ce soit ici) :
    1. Taper `value` CARACTÈRE PAR CARACTÈRE (`page.keyboard.type`, jamais `champ.fill()` — mesuré
       inefficace : aucune requête de recherche Odoo n'était déclenchée, la liste restait
       inchangée) déclenche la recherche.
    2. Sur CE champ précis, une boîte `.o_dialog` s'ouvre, listant des cartes `.o_kanban_record`
       cliquables — le nom du produit choisi apparaît sur la carte. Le menu déroulant compact
       (`.o-autocomplete--dropdown-menu`, standard sur un many2one plus simple) n'a pas été
       mesuré sur CE champ ; les deux formes sont tentées, la boîte de dialogue en premier car
       seule confirmée ici.

    ⚠️ **Une « Erreur d'accès » Odoo (droits insuffisants sur le modèle CIBLE du champ, ex.
    `product.template`) n'est jamais un sélecteur introuvable** — mesurée en conditions réelles :
    ce champ précis a exigé un droit Inventaire/Administrateur sur le compte de test avant de
    fonctionner. Cette fonction ne l'intercepte jamais : elle doit remonter telle quelle plutôt
    que d'être maquillée en défaut de sélecteur.

    ⚠️ **Limite assumée** : la liste peut rester non filtrée le temps que la recherche Odoo
    s'applique (mesuré : la boîte s'est parfois ouverte avec les N premiers résultats bruts avant
    filtrage) — `click_first_actionable` cherche `value` dans ce qui est déjà rendu, pas au-delà
    d'une pagination. Sur un jeu de données avec BEAUCOUP d'homonymes potentiels, préférer une
    valeur de recherche assez distinctive pour apparaître tôt dans la liste.
    """
    champ.click()
    page.keyboard.type(value, delay=20)

    dialogue = page.locator(".o_dialog")
    dropdown = page.locator(".o-autocomplete--dropdown-menu, .ui-autocomplete")
    try:
        dialogue.or_(dropdown).first.wait_for(state="visible", timeout=8000)
    except PlaywrightTimeout:
        raise ElementIntrouvableError(
            f"Champ relationnel '{field}' : aucune liste de résultats n'est apparue après la "
            f"saisie de '{value}' sur {page.url}")

    valeur_echappee = value.replace("'", "\\'")
    click_first_actionable(page, [
        f".o_dialog .o_kanban_record:has-text('{valeur_echappee}')",
        f".o_dialog tr.o_data_row:has-text('{valeur_echappee}')",
        f".o-autocomplete--dropdown-menu li:has-text('{valeur_echappee}')",
        f".ui-autocomplete .ui-menu-item:has-text('{valeur_echappee}')",
    ], quoi=f"Résultat '{value}' pour le champ relationnel '{field}'", ident=value)


_PRODUCT_PATHS = ("/description/", "/product/", "/detail/", "/formulaire-applicatif/")


def select_first_service_in_list(page):
    click_first_actionable(page,
        [f"a[href*='{p}']" for p in ("/formulaire-applicatif/", "/description/", "/product/")],
        quoi="Service dans la liste")


def select_product_in_list(page, name):
    # ⚠️ Bug réel (cas C45, SauceDemo, 2026-09-14) : `_PRODUCT_PATHS` ne connaît que des chemins
    # Odoo — SauceDemo route ses fiches produit en JS pur (`href="#"`), donc AUCUN candidat
    # n'aurait jamais pu matcher. `a:has-text(...)` en repli (sans condition sur l'`href`) est le
    # filet générique : n'importe quelle appli dont le lien produit porte le nom, peu importe sa
    # cible réelle. Testé en réel : conserve le comportement Odoo (candidats plus précis d'abord).
    click_first_actionable(page,
        [f"a[href*='{p}']:has-text('{name}')" for p in _PRODUCT_PATHS] + [f"a:has-text('{name}')"],
        quoi=f"Produit '{name}'", ident=name)


def select_product_partial(page, partial):
    # `:has-text` fait le « contient » (sous-chaîne), désormais insensible à la casse — plus
    # tolérant que l'ancien `partial in inner_text`, et surtout sans course au rendu.
    click_first_actionable(page,
        [f"a[href*='{p}']:has-text('{partial}')" for p in _PRODUCT_PATHS]
        + [f"a:has-text('{partial}')"],
        quoi=f"Produit contenant '{partial}'", ident=partial)


def click_onglet(page, name):
    click_first_actionable(page, [
        f".nav-link:has-text('{name}')", f".nav-item a:has-text('{name}')",
        f"[role='tab']:has-text('{name}')", f"li a:has-text('{name}')",
        f"a:has-text('{name}')", f"button:has-text('{name}')",
    ], quoi=f"Onglet '{name}'", ident=name)


def click_button_with_accessoires(page, label):
    click_first_actionable(page,
        [f".btn-{label}", f":is(button, a):has-text('{label}')"],
        quoi=f"Bouton '{label}' (accessoires)", ident=label)


def force_name_field(page, value):
    """Set the hidden name field using the JS native setter to bypass Odoo auto-generation.

    ⚠️ **Délibérément NON migré vers `locate_field`** (étape 2.1 du plan de consolidation,
    2026-09-15 — revu, pas oublié). Le champ ciblé (`[name="name"]`) n'est pas un identifiant
    TECHNIQUE générique que l'agent a extrait de l'annuaire — c'est une connaissance Odoo câblée
    en dur ici (Odoo auto-génère ce champ, et cette fonction existe pour contourner CETTE
    particularité précise). Migrer vers `locate_field` ne rendrait rien plus générique : sur une
    application sans cette particularité, cette fonction ne serait de toute façon jamais appelée.

    ⚠️ **`[name="name"]` résout le `<div class="o_field_widget">` englobant, pas le contrôle
    lui-même** — même trou que celui corrigé dans `locate_field` (Sapian, 2026-09-23) : le web
    client Odoo (OWL) pose le nom technique sur le conteneur, jamais sur l'`<input>`/`<textarea>`
    interne. Sans descendre dedans, `querySelector('[name="name"]')` renvoie le conteneur, dont
    aucun prototype de setter natif ne s'applique (`HTMLInputElement`/`HTMLTextAreaElement`
    exigent le VRAI élément de formulaire). Le tag réel varie aussi selon la vue (mesuré :
    `<textarea>` sur le formulaire de ticket Helpdesk) — le setter choisi doit s'adapter.
    """
    safe = value.replace("\\", "\\\\").replace("'", "\\'")
    # Ancré sur l'élément : sans cette attente, un champ rendu tardivement → `querySelector` nul →
    # le setter ne faisait RIEN, en silence (le nom restait celui auto-généré par Odoo).
    page.locator('[name="name"]').wait_for(state="attached", timeout=8000)
    page.evaluate(f"""
        (() => {{
            const conteneur = document.querySelector('[name="name"]');
            const el = conteneur && conteneur.matches('input, textarea')
                ? conteneur
                : (conteneur ? conteneur.querySelector('input, textarea') : null);
            if (el) {{
                const proto = el.tagName.toLowerCase() === 'textarea'
                    ? window.HTMLTextAreaElement.prototype
                    : window.HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
                setter.call(el, '{safe}');
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            }}
        }})()
    """)


def select_first_agence(page):
    """Sélectionne la première agence disponible dans le champ métier `agence`.

    ⚠️ **Délibérément NON migré vers `locate_field`** (étape 2.1 du plan de consolidation,
    2026-09-15 — revu, pas oublié). `agence` est un champ MÉTIER précis d'un projet Odoo/Sapian
    donné, pas un identifiant technique quelconque extrait de l'annuaire par l'agent — son nom
    technique (`name="agence"`) est connu et fixe par construction. Faire passer cette résolution
    par la cascade générique n'apporterait rien : une application sans ce champ n'appelle de toute
    façon jamais cette fonction.
    """
    select = page.locator("select[name='agence']")
    # Ancré sur l'élément (plus de `count()` instantané ni de sleep fixe).
    try:
        select.first.wait_for(state="attached", timeout=8000)
    except PlaywrightTimeout:
        raise ElementIntrouvableError(f"Champ 'agence' introuvable sur {page.url}")
    options = select.locator("option")
    for i in range(options.count()):
        val = options.nth(i).get_attribute("value")
        if val and val.strip():
            select.first.select_option(val)
            return
    raise ElementIntrouvableError(f"Aucune option disponible dans le champ 'agence' sur {page.url}")


def wait_form_submission(page):
    """Stabilisation APRÈS soumission — le SEUL point où une vraie attente RPC est justifiée
    (le serveur traite l'enregistrement avant qu'on l'asserte). `networkidle` **borné et jamais
    fatal** : le bus d'Odoo ne l'atteint pas toujours, on ne bloque donc pas au-delà de la borne
    et on ne le remplace PAS par un sleep fixe (l'attente elle-même sert de stabilisation)."""
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except PlaywrightTimeout:
        pass


def validation_error_inline(page):
    """Une erreur de validation visible dans le formulaire — plusieurs applications, plusieurs
    façons de le montrer.

    ⚠️ **Vivait dans `generic/`, sous un nom générique, mais ne reconnaissait QUE Odoo** (bug réel,
    cas C37 sur SauceDemo, 2026-09-14) : seul `s_website_form_field.o_has_error` — une classe CSS
    du website builder Odoo — était vérifié. SauceDemo affichait pourtant, au bon endroit, EXACTEMENT
    l'erreur attendue (« Epic sadface: Username is required ») — mais en `<h3 data-test="error"
    role="alert">`, jamais reconnu par ce contrôle. Le cas passait en `failed`, accusant
    l'application à tort d'un défaut qui était le nôtre — précisément ce que le porteur a demandé
    de traquer (« une incapacité de notre app de pouvoir bien tester », pas un vrai défaut).

    ⚠️ **Une seule appli corrigée ne prouve rien de générique** (rappel explicite du porteur,
    2026-09-14) : la suite de conformité (`tests/conformance/`) a rejoué ce même contrôle contre
    une SECONDE appli réelle, différente — the-internet.herokuapp.com/login, qui affiche son
    erreur en `<div class="flash error">Your username is invalid!</div>`, **sans AUCUN `role`**.
    `role="alert"` seul aurait donc échoué là aussi. D'où trois signaux, du plus universel au plus
    étroit :
    1. `[role="alert"]` — le standard WAI-ARIA (SauceDemo) ;
    2. une classe qui NOMME explicitement une erreur — `.error` (the-internet), `.alert-danger` /
       `.is-invalid` (Bootstrap, conventions très répandues) ;
    3. le motif Odoo `s_website_form_field.o_has_error`, PRÉSERVÉ tel quel.
    Volontairement PAS `.alert` seul (sans qualificatif) : une appli Bootstrap l'emploie aussi pour
    un succès ou une info — le confondre ferait passer un test qui n'a RIEN vu d'un refus.

    ⚠️ **Relu, jamais lu une seule fois (doc Playwright, audit fiabilité 2026-09-17).** La
    documentation officielle prévient explicitement : `is_visible()` appelé nu « won't wait a
    single second, it will just check the locator is there and return immediately » — à l'inverse
    des assertions officielles (`expect(...).to_be_visible()`), qui réessaient. Mais ici il n'y a
    pas UN candidat à attendre, il y en a PLUSIEURS (rôle, classe, motif Odoo) et il faut celui qui
    est VRAIMENT visible, pas juste `.first` dans l'ordre du DOM — exactement le bug déjà corrigé
    une fois dans cette fonction (un candidat présent mais cachée ne doit pas suffire). Playwright
    n'a pas d'assertion native pour « au moins un candidat parmi plusieurs devient visible » ; sa
    propre doc, pour un contrôle sur mesure, renvoie vers une boucle de relecture bornée — c'est
    `_poll_until` (déjà utilisé plus bas pour les comptages Odoo), réutilisé ici tel quel plutôt que
    dupliqué.
    """
    def _un_candidat_visible() -> bool:
        candidats = page.locator('[role="alert"], .error, .alert-danger, .is-invalid')
        for i in range(min(candidats.count(), 8)):
            try:
                if candidats.nth(i).is_visible():
                    return True
            except Exception:
                continue  # un élément qui disparaît entre le compte et la lecture : on continue
        has_error = page.locator("[class*='s_website_form_field'].o_has_error").first
        try:
            return has_error.is_visible()
        except Exception:
            return False

    trouve, _ = _poll_until(_un_candidat_visible, lambda v: v)
    if not trouve:
        raise AssertionError("Aucune erreur de validation visible dans le formulaire.")


def validation_error_notification(page):
    """⚠️ `expect(...).to_be_visible()`, pas `assert ... .is_visible()` (audit fiabilité,
    2026-09-17) : ICI un seul candidat, cas d'école de l'assertion web-first officielle de
    Playwright — elle réessaie jusqu'à son délai par défaut au lieu de constater une seule fois,
    immédiatement, avant même que la notification n'ait eu le temps de s'afficher."""
    error = page.locator(".o_notification_manager .o_notification.border-danger").first
    expect(error).to_be_visible()


def no_error_with_keywords(page, keyword1, keyword2):
    """⚠️ `[role="alert"]` ajouté (2026-09-14, garde anti-régression) : les trois autres
    sélecteurs sont déjà génériques (`.alert-danger`/`.text-danger`, convention Bootstrap
    répandue) SAUF `.o_notification.border-danger` — Odoo, mais vérifié EN PLUS des autres,
    jamais comme seul chemin (contrairement au bug d'origine de `validation_error_inline`)."""
    error_elements = page.locator(
        '[role="alert"], .alert-danger, .o_notification.border-danger, .text-danger')
    for i in range(error_elements.count()):
        error_text = error_elements.nth(i).inner_text().lower()
        assert keyword1.lower() not in error_text and keyword2.lower() not in error_text, \
            f"Erreur contenant '{keyword1}' ou '{keyword2}' trouvée : {error_text}"


# Plafond de résolutions adaptatives successives sur UN MÊME segment de `navigate_menu` (un clic
# qui n'a fait qu'ouvrir un sous-menu local, jamais naviguer) — borne le pire cas (une page dont
# aucun état ne fait jamais progresser l'URL) à un nombre fini de tours, jamais une boucle infinie.
_MAX_TENTATIVES_ADAPTATIVES_MENU = 3


def navigate_menu(context, menu_path):
    """Un menu Odoo (ex. « Parc IT / Générer des équipements ») vit dans le BACK-OFFICE — jamais
    sur la racine `context.odoo_url`, qui rend le portail applicatif custom quand l'instance en a
    un (mesuré en RUN RÉEL, staging Sapian, 2026-09-18 : la page d'accueil est le « Portail des
    services SAPIAN », sans aucune trace de « Parc IT » — le clic expirait après 8 s à chercher un
    texte absent de cet écran). `/web#action=menu` est le sélecteur d'applications STANDARD
    d'Odoo — présent sur toute instance, jamais spécifique à Sapian — qui affiche réellement les
    icônes d'applications (Discuss, Parc IT, Ventes…) dont ce step a besoin pour cliquer dessus.

    ⚠️ **Le séparateur de niveaux n'est jamais imposé nulle part** (aucune convention documentée
    dans le prompt de génération) — mesuré en RUN RÉEL (résultat #3, staging Sapian, 2026-09-18) :
    l'IA a écrit `"Parc IT / Générer des équipements"` avec `/`, alors que ce step ne coupait que
    sur `>`. Sans séparateur reconnu, TOUTE la chaîne partait comme un seul texte à chercher —
    qui n'existe nulle part tel quel, d'où le timeout. `/` ET `>` sont désormais acceptés,
    exactement comme le motif déjà appliqué à `check_step_soumission` ce matin (le comportement
    RÉEL varie, mieux vaut le tolérer qu'imposer une convention que personne ne connaît).

    ⚠️ **Repli ADAPTATIF si le libellé exact est introuvable** (mesuré en RUN RÉEL, Sapian,
    2026-09-22 : `discover_menus` avait capturé « Surveys », mais la session d'exécution affiche
    le menu en français — « Sondages » — et `get_by_text(exact=True)` timeout sur un texte qui
    n'existe simplement pas dans CETTE langue d'affichage). Même dernier recours que
    `locate_field` (`_repli_adaptatif`, « Chantier F ») : si le clic exact échoue, on montre à un
    modèle rapide les libellés RÉELLEMENT affichés sur l'écran de menu et on lui demande de
    choisir celui qui correspond à l'intention — jamais un texte inventé, uniquement un élément
    qui existe vraiment. Si lui non plus ne trouve rien, l'échec d'origine (`TimeoutError`,
    classé `wrong_navigation` par `defect_taxonomy`) remonte tel quel.

    ⚠️ **Un clic adaptatif peut n'ouvrir qu'un sous-menu, sans naviguer** (mesuré en RUN RÉEL,
    Sapian, 2026-09-22, cas C127 : l'instantané des candidats est pris AVANT l'ouverture d'un menu
    déroulant — « Tous les tickets » n'existe pas encore dans le DOM au moment de la capture, donc
    le modèle a choisi le meilleur candidat VISIBLE, le lien PARENT « Tickets », qui ouvre le
    sous-menu sans y naviguer). Un simple retry déterministe ne suffirait pas : le segment cherché
    est en anglais (« All Tickets »), l'item réel du sous-menu en français (« Tous les tickets »)
    — aucun `get_by_text(exact=True)` ne les fera jamais correspondre.

    ⚠️ **Ni l'URL seule ni un signal DOM ne suffisent à détecter la non-progression** — deux
    essais successifs, tous deux mesurés en run RÉEL (Sapian, 2026-09-22, cas C127) : l'URL SEULE
    échoue car Odoo charge une vue par défaut EN MÊME TEMPS qu'il ouvre un sous-menu (l'URL change
    sans que l'item recherché soit atteint) ; un signal de recouvrement DOM (candidats avant/après
    un clic) s'est révélé peu discriminant, l'interface commune d'Odoo (barre d'outils, filtres,
    pagination) dominant le nombre de candidats sur TOUTES les vues, quel que soit le seuil
    choisi. On demande donc DIRECTEMENT au modèle — qui a déjà vu la liste complète des candidats
    — s'il pense avoir choisi un menu/groupe générique plutôt qu'une destination finale précise
    (`menu_parent_probable`, posé sur `page._tp_dernier_choix_menu_parent` par
    `resoudre_champ_adaptatif`) et on retente sur CE MÊME segment si c'est le cas — plafonné pour
    ne jamais boucler indéfiniment.
    """
    back_office_url = f"{context.odoo_url.rstrip('/')}/web#action=menu"
    context.page.goto(back_office_url, wait_until="domcontentloaded")
    # ⚠️ **Même trou que celui corrigé sur les formulaires** (`_inspect_sync`, Sapian,
    # 2026-09-23) : la grille d'applications (`.o_app`) n'existe PAS ENCORE à `domcontentloaded`.
    # `networkidle` a été écartée ailleurs pour la même raison qu'ici (bus de longpolling Odoo) ;
    # `wait_for_selector`, best-effort, ne bloque jamais une grille qui ne se chargerait jamais.
    #
    # ⚠️ **Marge relevée à 15 s après un premier correctif insuffisant** (Sapian, 2026-09-23) :
    # une marge de 5 s avait d'abord semblé confirmée (mesuré : 0 tuile à `domcontentloaded`,
    # 25 après ~2 s dans un test isolé) — mais le clic sur « Assistance » a continué à timeout de
    # façon intermittente EN CAMPAGNE RÉELLE (plusieurs essais consécutifs sur la même cible).
    # Remesuré ensuite, à froid, juste après une campagne : 5,23 s pour que le premier chargement
    # de session rende « Assistance » attaché, contre <0,1 s sur les chargements suivants de LA
    # MÊME session — un cold-start peut donc dépasser une marge de 5 s. Chargements suivants du
    # même segment inchangés (retour quasi immédiat dès que la grille est déjà rendue une fois).
    try:
        context.page.wait_for_selector(".o_app", timeout=15000)
    except PlaywrightTimeout:
        pass
    for part in [p.strip() for p in re.split(r"[/>]", menu_path)]:
        if not part:
            continue
        for tentative in range(_MAX_TENTATIVES_ADAPTATIVES_MENU):
            try:
                context.page.get_by_text(part, exact=True).first.click(timeout=8000)
                break
            except PlaywrightTimeout:
                resolu = _repli_adaptatif(context.page, part, menu_path)
                if resolu is None:
                    raise
                resolu.click(timeout=8000)
                # Apprend, pour ce projet, le libellé RÉEL qui vient de faire franchir CE segment
                # (Lot 2, 2026-09-23) — que ce clic soit la destination finale ou seulement une
                # étape intermédiaire (menu parent) importe peu ICI : si un second clic est
                # nécessaire sur le MÊME `part` (reboucle ci-dessous), il réécrit la même clé avec
                # le libellé plus précis qu'il vient de trouver — dernier écrit gagne à la lecture
                # (`menu_appris.charger`), donc le libellé final l'emporte naturellement.
                libelle_reel = getattr(context.page, "_tp_dernier_libelle_choisi", "")
                if libelle_reel:
                    _record_menu_appris(part, libelle_reel, menu_path)
                # ⚠️ L'URL SEULE ne suffit pas (bug réel, Sapian 2026-09-22, cas C127) : cliquer
                # sur un item de menu PARENT (« Tickets ») charge SA PROPRE vue par défaut EN PLUS
                # d'ouvrir son sous-menu — l'URL change, mais l'item recherché n'est pas encore
                # atteint. Un signal DOM (recouvrement des candidats avant/après) s'était révélé
                # peu fiable ici — l'interface commune d'Odoo (barre d'outils, filtres) domine le
                # nombre de candidats sur TOUTES les vues, quel que soit le seuil choisi. On
                # demande donc DIRECTEMENT au modèle (qui a déjà vu la liste complète) s'il pense
                # avoir choisi un menu/groupe plutôt qu'une destination finale — voir
                # `page._tp_dernier_choix_menu_parent`, posé par `resoudre_champ_adaptatif`.
                menu_parent = getattr(context.page, "_tp_dernier_choix_menu_parent", False)
                if not menu_parent:
                    break  # le modèle est confiant : segment franchi
                # Sinon : probablement un menu/groupe qui vient d'ouvrir un sous-menu — reboucler
                # sur CE MÊME segment, DOM maintenant enrichi (l'item réel y est peut-être visible).
        else:
            raise ElementIntrouvableError(
                f"Menu '{part}' : {_MAX_TENTATIVES_ADAPTATIVES_MENU} résolutions adaptatives "
                f"successives sans faire progresser la navigation, sur {context.page.url}")


def access_portal_section(page, section_name):
    """Ouvre une section du portail identifiée par son intitulé VISIBLE.

    ⚠️ **Délibérément NON migré vers `locate_field`** (étape 2.1 du plan de consolidation,
    2026-09-15 — revu, pas oublié). Cette fonction résout déjà par texte visible (`get_by_text`)
    — le palier le plus proche d'un usage humain, cohérent avec la hiérarchie officielle
    Playwright/Testing Library que `locate_field` adapte pour les identifiants TECHNIQUES. Il n'y
    a ici aucun identifiant technique à essayer d'abord : `section_name` EST déjà un libellé, pas
    un `name`/`data-test` extrait de l'annuaire. La faire passer par `locate_field` ajouterait des
    paliers qui ne correspondent à rien pour ce cas d'usage, sans gagner en robustesse.
    """
    try:
        page.get_by_text(section_name, exact=False).first.click(timeout=8000)
    except PlaywrightTimeout:
        raise NavigationImpossibleError(
            f"PRÉREQUIS MANQUANT : la section '{section_name}' est absente de {page.url}."
        )


def cleanup_test_records(env, prefix, models):
    for model_name in models.split(" et du modèle "):
        Model = env[model_name.strip('"')]
        old_ids = Model.search([("name", "ilike", prefix)])
        for tid in old_ids:
            Model.unlink(tid)


# ── Comptage avant/après (décision 0011) ─────────────────────────────────────
#
# ⚠️ Ces trois fonctions formaient une chaîne de faux-négatif MUETTE AUX DEUX BOUTS :
#   1. `memorize_record_count` avalait son exception (`warn`) → aucun snapshot posé ;
#   2. `check_count_*` ne trouvait pas le snapshot → `warn` + `return` SANS asserter ;
#   3. le `@then` passait → scénario VERT qui n'avait rien vérifié.
# Un `warnings.warn` n'échoue pas un test : le verdict devenait déclaratif (§4.2) et produisait
# le faux-négatif que §4.4 déclare inacceptable. Même famille que 0010 (vérification creuse dans
# la bibliothèque partagée) et que 0007 (un repli ne doit JAMAIS être silencieux).
#
# Règle désormais : un comptage sans snapshot est un test INCOMPLET, pas un test qui passe. On
# échoue, avec un message qui nomme le step manquant.

_COUNT_SNAPSHOT_STEP = ('le nombre d\'enregistrements dans le modèle "{model}" '
                        'est enregistré pour comparaison')


def _count_attr(model: str) -> str:
    return f"_initial_count_{model.replace('.', '_')}"


def _max_id_attr(model: str) -> str:
    return f"_initial_max_id_{model.replace('.', '_')}"


def memorize_record_count(context, model):
    """Mémorise le nombre d'enregistrements du modèle (diagnostic) ET l'id maximal existant
    (preuve — §F1 du plan de fiabilité du verdict, 2026-09-23), pour comparaison après l'action.

    ⚠️ **Le comptage global seul ment sur une instance partagée** (F1, 2026-09-23) : un tiers qui
    crée pendant que CE scénario échoue produit un faux `conforme` ; un tiers qui crée pendant
    qu'il réussit produit un faux `non_conforme`. Le compte global reste relevé (diagnostic
    affiché en cas d'échec), mais la PREUVE de création devient l'id maximal, comparé plus tard
    par `_crees_par_ce_scenario` via un domaine `id > max_id` — cloisonné à ce qui apparaît
    APRÈS ce relevé précis, jamais à « combien il y en a en tout ».

    `active_test=False` sur le relevé du max id : un enregistrement que l'action testée
    archiverait aussitôt (workflow qui désactive à la création) doit compter comme créé.

    Échoue si le relevé est impossible : sans lui, toute vérification en aval serait creuse
    (cf. `_require_snapshot`/`_require_max_id`). Mieux vaut échouer ICI, où la cause est visible,
    que laisser le scénario finir au vert sans rien avoir prouvé.
    """
    try:
        setattr(context, _count_attr(model), context.odoo.env[model].search_count([]))
        derniers = context.odoo.env[model].with_context(active_test=False).search(
            [], order="id desc", limit=1)
        setattr(context, _max_id_attr(model), derniers[0] if derniers else 0)
    except Exception as exc:
        raise AssertionError(
            f"Impossible de mémoriser le nombre d'enregistrements de '{model}' : {exc}. "
            f"Sans ce point de comparaison, les vérifications de comptage ne prouveraient rien."
        ) from exc


def _require_snapshot(context, model) -> int:
    """Renvoie le comptage global initial (diagnostic), ou ÉCHOUE en nommant le step manquant.

    Ne jamais remplacer par un `return` silencieux : le `@then` appelant passerait sans rien
    vérifier, et un scénario vert affirmerait un comptage que personne n'a mesuré (§4.2/§4.4).

    ⚠️ **Conservé tel quel (AssertionError) — ne pas fusionner avec `_require_max_id`** : c'est
    ce contrat précis, éprouvé par `tests/test_comptage_falsifiable.py`, qui doit continuer à
    signaler à l'utilisateur qu'un step lui manque. Appelé EN PREMIER par les fonctions de
    contrôle, il reste le signal reçu quand `memorize_record_count` n'a jamais été invoqué.
    """
    attr = _count_attr(model)
    if not hasattr(context, attr):
        raise AssertionError(
            f"Aucun point de comparaison pour '{model}' : ce scénario vérifie un comptage sans "
            f"l'avoir mesuré avant l'action. Ajoutez le step "
            f"« {_COUNT_SNAPSHOT_STEP.format(model=model)} » avant l'action."
        )
    return getattr(context, attr)


def _require_max_id(context, model) -> int:
    """Renvoie l'id maximal relevé par `memorize_record_count` (§F1, point 5 du plan).

    ⚠️ **`RuntimeError`, jamais `AssertionError`** : contrairement à `_require_snapshot` (appelé
    en premier par les fonctions de contrôle, et qui reste le signal historique d'un step de
    relevé manquant — voir sa docstring), une absence ICI signifierait que le comptage global a
    pu être relevé mais pas l'id maximal — un état incohérent qui ne peut survenir qu'à cause
    d'une erreur d'ÉCRITURE du test (ex. un ancien `context` réutilisé hors de son scénario),
    jamais d'un comportement de l'application. Une erreur de code de test n'est pas un désaccord
    sur ce que l'application a fait : `RuntimeError` le distingue de tout `AssertionError` posé
    par un contrôle qui, lui, a vraiment observé l'application.
    """
    attr = _max_id_attr(model)
    if not hasattr(context, attr):
        raise RuntimeError(
            f"[code de test] Aucun id maximal relevé pour '{model}' : `memorize_record_count` "
            f"n'a pas été appelé (ou a échoué) avant ce contrôle."
        )
    return getattr(context, attr)


def _crees_par_ce_scenario(context, model) -> list[int]:
    """Les ids RÉELLEMENT créés par CE scénario depuis son relevé (§F1) — jamais un comptage
    global, qui voit toute activité concurrente sur une instance partagée.

    Domaine `[("id", ">", max_id)]`, `active_test=False` (un enregistrement archivé par l'action
    testée compte quand même comme une création). Affiné par le marqueur de tentative SI ET
    SEULEMENT SI un step « … rendue unique pour cette tentative » a été utilisé dans CE scénario
    (`context._tp_derniere_valeur_unique`, posé par `step_fill_unique` — `generic/_generic_steps.py`) :
    recherche alors aussi ce jeton dans le champ concerné, pour isoler l'enregistrement du
    scénario parmi d'éventuelles créations concurrentes.

    ⚠️ **N'affine JAMAIS par `create_uid`** (décision explicite du plan) : un formulaire PUBLIC
    crée avec l'utilisateur public — filtrer dessus confondrait entre eux tous les visiteurs
    anonymes ayant soumis pendant la même fenêtre, un défaut pire que celui qu'on corrige ici.

    ⚠️ **Le marqueur, quand il existe, fait FOI — même s'il réduit à ZÉRO**, pas seulement pour
    départager plusieurs candidats. C'est le SEUL rempart contre le cas résiduel qu'`id > max_id`
    seul ne peut jamais trancher : exactement UNE création concurrente, sans aucun lien avec ce
    scénario, prise à tort pour la sienne (le même faux `conforme` que ce lot corrige, version
    minimale). Si le scénario a posé un jeton et qu'AUCUN enregistrement ne le porte, c'est que
    SA création n'a pas abouti — peu importe qu'un tiers en ait produit une autre entre-temps.
    Sans marqueur du tout, ce cas précis reste indiscernable — limite assumée et validée par le
    porteur (décision D10, `docs/PLAN-FIABILITE-VERDICT-2026-09.md` §4, 2026-09-23) : `create_uid`
    le résoudrait, mais confondrait tous les visiteurs anonymes d'un formulaire public entre eux —
    un défaut pire que celui qu'on corrige.

    Best-effort seulement sur l'ÉCHEC de la recherche affinée (champ marqué absent de ce modèle —
    le jeton a été posé pour un AUTRE modèle dans un scénario multi-étapes) : dans ce cas précis,
    et LUI SEUL, on retombe sur la liste brute plutôt que de lever pour une commodité de
    désambiguïsation qui ne s'applique simplement pas ici.
    """
    max_id = _require_max_id(context, model)
    env = context.odoo.env[model].with_context(active_test=False)
    domaine = [("id", ">", max_id)]
    ids = env.search(domaine)
    marqueur = getattr(context, "_tp_derniere_valeur_unique", None)
    if marqueur:
        champ, jeton = marqueur
        try:
            return env.search(domaine + [(champ, "like", jeton)])
        except Exception:
            pass  # champ absent de CE modèle : le marqueur ne s'y applique pas, repli sur `ids`.
    return ids


# Fenêtre pendant laquelle on considère que la création asynchrone a « eu le temps de se
# stabiliser ». ⚠️ **PARTAGÉE par le comptage positif ET négatif, volontairement** : le ticket est
# créé par le NAVIGATEUR (soumission web, création asynchrone), le comptage lit par RPC — il y a un
# délai entre les deux. Le positif attend que le ticket APPARAISSE (jusqu'à ce délai) ; le négatif
# doit attendre EXACTEMENT le même délai avant de conclure « rien n'a été créé ». Deux fenêtres
# différentes rouvriraient un faux négatif : une création tardive à tort pourrait surgir après une
# fenêtre courte côté négatif mais avant la fenêtre longue côté positif (§4.4).
COUNT_SETTLE_TIMEOUT = float(os.getenv("TESTPILOT_COUNT_SETTLE_TIMEOUT", "8.0"))


def _poll_until(lire, predicat, *, timeout=None, intervalle=0.3, _clock=None, _sleep=None):
    """Relit `lire()` jusqu'à ce que `predicat(valeur)` soit vrai, ou expiration de `timeout`.

    Attente ACTIVE et BORNÉE : on sort DÈS que la condition est vraie (aucun délai gaspillé) et
    JAMAIS au-delà de `timeout` (aucune course). Remplace la lecture unique instantanée — qui, face
    à une écriture asynchrone, est toujours une course — et le sleep fixe qui la « gagnait » à
    l'aveugle. Rend `(predicat_satisfait, dernière_valeur_lue)`.

    ⚠️ `timeout`, `_clock`, `_sleep` sont résolus À L'APPEL (`None` ⇒ valeur de module) et NON
    figés en valeurs par défaut : une valeur par défaut fige la référence à la définition, si bien
    que régler `COUNT_SETTLE_TIMEOUT` ou monkeypatcher `time.sleep` n'aurait aucun effet.
    """
    timeout = COUNT_SETTLE_TIMEOUT if timeout is None else timeout
    _clock = _clock or time.monotonic
    _sleep = _sleep or time.sleep
    debut = _clock()
    valeur = lire()
    while True:
        if predicat(valeur):
            return True, valeur
        if _clock() - debut >= timeout:
            return False, valeur
        _sleep(intervalle)
        valeur = lire()


def check_count_not_increased(context, model):
    """Le négatif attend TOUTE la fenêtre : on cherche une création DE CE SCÉNARIO pendant
    `COUNT_SETTLE_TIMEOUT` ; si aucune n'apparaît, on conclut « rien créé ». Attendre moins
    laisserait passer une création tardive à tort (faux négatif, §4.4 inacceptable).

    ⚠️ **Cloisonné au scénario (§F1, 2026-09-23)** : comparait auparavant le comptage GLOBAL
    (`search_count([])`), qui accuse à tort le scénario d'une création faite par un TIERS pendant
    qu'il tourne, sur une instance partagée. `_crees_par_ce_scenario` ne voit que ce qui apparaît
    après le relevé de CE scénario (`id > max_id`), jamais l'activité d'un autre utilisateur.
    """
    _require_snapshot(context, model)  # diagnostic + garde historique (step manquant → message)
    max_id = _require_max_id(context, model)
    augmente, ids = _poll_until(
        lambda: _crees_par_ce_scenario(context, model), lambda v: len(v) > 0)
    if augmente:
        global_actuel = context.odoo.env[model].search_count([])
        raise AssertionError(
            f"Enregistrement(s) créé(s) par ce scénario dans '{model}' malgré l'attente d'aucune "
            f"création : ids {ids} (domaine [('id', '>', {max_id})]). "
            f"Comptage global (diagnostic, inclut l'activité concurrente) : {global_actuel}."
        )


# Ce que la PAGE dit quand rien n'a été créé — par ordre de force du signal.
_SELECTEURS_ERREUR = (
    ".o_notification.border-danger",   # notification Odoo
    ".alert-danger",                   # bandeau Bootstrap
    "[role='alert']",                  # rôle d'accessibilité
    ".invalid-feedback",               # message de champ Bootstrap
    ".o_has_error .text-danger",       # champ Odoo en erreur
)


# ⚠️ Le diagnostic est BORNÉ. `run_service` coupe `error_summary` à 500 caractères ; un diagnostic
# bavard se ferait amputer par la queue — donc amputer de sa conclusion, la partie qui porte le
# sens. On garde de la marge pour le constat qui le précède (« devrait être N, obtenu M »).
_DIAGNOSTIC_MAX = 380


def _borner(texte: str) -> str:
    return texte if len(texte) <= _DIAGNOSTIC_MAX else texte[:_DIAGNOSTIC_MAX - 1].rstrip() + "…"


def _refus_par_le_navigateur(page) -> list:
    """Les champs que la VALIDATION NATIVE du navigateur refuse (best-effort, ne lève JAMAIS).

    Non vide ⇒ la donnée du test est refusée par le navigateur (`pattern`, `min`, champ requis
    devenu obligatoire…) : **l'application n'est pas en cause**, c'est le signal du 4ᵉ verdict
    (`donnee_invalide`). Partagé par `diagnostic_soumission` (qui l'EXPLIQUE) et par le comptage
    (qui en fait un `DonneeRefuseeError`) — une seule sonde, deux usages.
    """
    try:
        return page.evaluate("""() => {
            const out = [];
            for (const el of document.querySelectorAll('input, select, textarea')) {
                if (el.willValidate && !el.checkValidity()) {
                    out.push({nom: el.name || el.id || '?', msg: el.validationMessage || '',
                              valeur: String(el.value || '').slice(0, 120),
                              drapeaux: DRAPEAUX.filter(d => el.validity[d] === true),
                              pattern: el.pattern || '',
                              maxLength: el.maxLength > 0 ? String(el.maxLength) : '',
                              minLength: el.minLength > 0 ? String(el.minLength) : '',
                              max: el.max || '', min: el.min || '',
                              step: el.step || '', type: el.type || ''});
                }
            }
            return out.slice(0, 5);
        }""".replace("DRAPEAUX", _DRAPEAUX_JS)) or []
    except Exception:
        return []


def _refus_serveur(context):
    """La réponse SERVEUR de la soumission (§2bis, étape 3a), capturée par `environment.py`.

    Rend un tuple `(genre, detail)` — jamais lève :
      - `("champs", "champ1, champ2")` : le serveur a nommé des champs refusés (`error_fields`).
        C'est NOTRE donnée qui viole une règle serveur (le plafond JS enfin capté) → donnee_invalide.
      - `("generique", "message")` : le serveur a refusé sans nommer de champ (`error` seul, ou
        pas d'`id`). Une saisie valide côté navigateur rejetée en silence = défaut de comportement
        de l'app (arbitrage porteur 2026-07-23) → non_conforme, message serveur affiché.
      - `("cree", id)` : le serveur a renvoyé un `id` — l'enregistrement a été créé côté serveur.
      - `None` : aucune réponse exploitable captée (le silence subsiste).
    """
    rep = getattr(context, "reponse_formulaire", None)
    if not isinstance(rep, dict):
        return None
    champs = rep.get("error_fields")
    if champs:
        noms = ", ".join(str(c) for c in champs) if isinstance(champs, (list, tuple)) \
            else ", ".join(map(str, champs)) if isinstance(champs, dict) else str(champs)
        return ("champs", noms)
    if rep.get("id"):
        return ("cree", rep["id"])
    err = rep.get("error") or rep.get("message")
    if err is not None:
        return ("generique", " ".join(str(err).split())[:200] or "(sans détail)")
    # Un dict sans id ni erreur reconnaissable : refus non nommé.
    return ("generique", "le serveur a refusé la soumission sans détail exploitable")


def _refus_serveur_mesures(page, noms) -> list:
    """Les champs que le SERVEUR a nommés, avec la valeur qu'ils portaient — best-effort.

    Le serveur nomme les champs fautifs mais ne renvoie pas ce qu'on lui avait envoyé : on relit
    la valeur dans le DOM, qui n'a pas bougé (la page n'a pas été rechargée, la soumission ayant
    échoué). Sans elle, on saurait *quel* champ est refusé sans savoir *quoi* ne plus écrire —
    et la règle apprise serait inutilisable par le résolveur.

    Un refus serveur n'AFFIRME aucune contrainte : il noircit une valeur, rien de plus. La règle
    métier derrière (« l'IBAN doit correspondre au client ») n'est ni dans le HTML ni dans la
    réponse — la deviner serait une invention.
    """
    if page is None:
        return []
    route = _route_courante(page)
    mesures = []
    for nom in [n.strip() for n in str(noms).split(",") if n.strip()][:6]:
        try:
            valeur = page.evaluate(
                "(n) => { const el = document.querySelector(`[name=\"${n}\"]`);"
                " return el ? String(el.value).slice(0, 120) : ''; }", nom) or ""
        except Exception:
            valeur = ""
        mesures.append(RefusMesure(route=route, champ=nom, type_contrainte="refus_serveur",
                                   valeur_contrainte="", valeur_refusee=valeur,
                                   origine="serveur",
                                   preuve="champ nommé par la réponse du serveur"))
    return mesures


def diagnostic_soumission(page) -> str:
    """Pourquoi la soumission n'a-t-elle rien créé ? — **lire la page au lieu d'accuser**.

    ⚠️ **Le défaut que ça corrige** (mesuré le 2026-07-22). Quand le compteur n'augmente pas, le
    test concluait « l'application est non conforme », point. Or trois causes très différentes
    produisent ce même symptôme :

    1. **le navigateur a refusé d'envoyer** — une valeur viole la validation HTML native
       (`pattern`, `min`…) : la donnée DU TEST est invalide, l'application n'y est pour rien ;
    2. **le serveur a refusé** pour une raison métier (SIRET incohérent, doublon…) : l'application
       fait exactement son travail ;
    3. **l'application est réellement en défaut** — le seul cas où le verdict est mérité.

    Les confondre, c'est accuser à tort deux fois sur trois. **Un outil de test qui accuse à tort
    est pire qu'un outil qui ne teste rien** : il détruit la confiance dans ses verdicts justes.

    ⚠️ **Ce diagnostic ne CHANGE aucun statut** — il explique. La distinction des trois cas en
    verdicts distincts est une décision de modèle (le « 4ᵉ verdict »), qui appartient au porteur.
    Ici on se contente de rapporter ce que la page dit, ce qui est déjà ce qui manquait pour
    trancher.

    ⚠️ **Best-effort ABSOLU : ne lève jamais.** Un diagnostic qui plante transformerait un échec
    fonctionnel lisible en erreur technique — il détruirait précisément l'information qu'il est
    censé apporter. Toute panne ici se solde par une chaîne vide.
    """
    try:
        # 1. La validation NATIVE du navigateur. Signal le plus décisif : si un champ est
        #    `:invalid`, l'envoi n'a jamais eu lieu — inutile de chercher plus loin côté serveur.
        invalides = _refus_par_le_navigateur(page)
        if invalides:
            details = " · ".join(f"{c['nom']} : {c['msg']}".strip(" :") for c in invalides)
            return _borner(
                "LE NAVIGATEUR A REFUSÉ D'ENVOYER le formulaire — la donnée du test viole la "
                f"validation de {len(invalides)} champ(s) : {details}. "
                "⚠️ L'application n'est PAS en cause ici.")

        # 2. Ce que le serveur a répondu, s'il a répondu quelque chose de lisible.
        for selecteur in _SELECTEURS_ERREUR:
            elements = page.locator(selecteur)
            for i in range(min(elements.count(), 3)):
                el = elements.nth(i)
                if not el.is_visible():
                    continue
                texte = " ".join((el.inner_text() or "").split())[:200]
                if texte:
                    return _borner(
                        f"L'APPLICATION A REFUSÉ la soumission et l'affiche : « {texte} ». "
                        "⚠️ Vérifier si ce refus est légitime avant de conclure au défaut.")

        return _borner(
            "REFUS SILENCIEUX : rien créé, et NI la page NI le serveur n'ont donné de raison "
            "lisible. Rejet métier légitime, défaut applicatif ou trou d'observabilité : "
            "indistinguables. Verdict honnête — l'outil NE conclut PAS à un défaut sans preuve. "
            "À instruire côté application (logs serveur du POST).")
    except Exception as exc:  # un diagnostic ne casse JAMAIS le scénario qu'il éclaire
        return f"(diagnostic de soumission indisponible : {type(exc).__name__})"


def _capturer_dernier_enregistrement(context, model, record_ids) -> None:
    """Pose `last_record_ids`/`last_record_model` sur l'enregistrement identifié par
    `_crees_par_ce_scenario`, et l'ajoute au registre de nettoyage.

    ⚠️ **Ne relit plus l'id par `order="id desc"` (§F1, 2026-09-23)** : cette relecture globale
    pouvait pointer l'enregistrement d'un TIERS créé après celui du scénario, exactement le
    défaut que le cloisonnement par `id > max_id` corrige juste avant d'arriver ici — la liste
    `record_ids` fournie par l'appelant est déjà exacte, une seconde requête « le plus récent »
    ne ferait que réintroduire la même course.

    ⚠️ **Le trou mesuré le 2026-08-07** (`/retenue_garantie`, cas 120) : un scénario nominal qui
    enchaîne « le nombre … augmente de 1 » puis « le champ … de CET enregistrement … » plantait
    sur `AttributeError: 'Context' object has no attribute 'last_record_ids'`. Seuls les steps
    « un enregistrement … existe dans le modèle … » posaient ce contexte ; l'assertion de comptage,
    qui vient pourtant de PROUVER qu'un enregistrement a été créé, ne le posait pas. Résultat :
    erreur TECHNIQUE (« à retester ») sur un scénario où l'application avait parfaitement
    fonctionné — le pire des verdicts, celui qui ne dit rien.

    ⚠️ **Best-effort, jamais bloquant** — même arbitrage que l'archivage et la capture d'écran.
    Le contrat de `check_count_increased_by_one` est le COMPTAGE, et il est déjà rempli quand on
    arrive ici : une commodité pour les steps suivants ne doit pas faire échouer un step dont
    l'assertion a réussi. Si la capture échoue, rien n'est posé — et le step suivant le dira
    clairement (« Aucun enregistrement en contexte… »), sans jamais se taire.
    """
    try:
        context.last_record_ids = record_ids
        context.last_record_model = model
        # `write_test_plan` (100 % steps du catalogue) n'a AUCUN Python custom pour appeler
        # `register_created` — sans cette ligne, chaque scénario généré par ce chemin (celui que
        # le prompt recommande désormais par défaut) laisserait ses données de test sur la cible
        # réelle. Sûr ICI, et seulement ici : `_crees_par_ce_scenario` vient de PROUVER que cet
        # enregistrement a été créé APRÈS le relevé du scénario — contrairement aux steps
        # « … existe dans le modèle … », qui peuvent pointer un enregistrement PRÉEXISTANT et
        # qu'il ne faut jamais enregistrer pour suppression.
        from features.environment import register_created
        for record_id in record_ids:
            register_created(context, model, record_id)
    except Exception:
        logger.warning("[comptage] dernier enregistrement de '%s' non capturé — les steps "
                       "« CET enregistrement » suivants le signaleront", model, exc_info=True)


def check_count_increased_by_one(context, model):
    """Le positif attend qu'EXACTEMENT UN enregistrement DE CE SCÉNARIO apparaisse (jusqu'à
    `COUNT_SETTLE_TIMEOUT`). S'il n'apparaît pas dans la fenêtre, l'assertion échoue avec le
    message d'origine — un vrai « non créé » reste détecté, seule la course disparaît.

    ⚠️ **Cloisonné au scénario (§F1, 2026-09-23)** : comparait auparavant le comptage GLOBAL
    (`search_count([]) == initial + 1`), qui produit un faux `conforme` si un tiers crée pendant
    que CE scénario échoue en réalité (le compte global « retombe juste » par coïncidence), et un
    faux `non_conforme` si un tiers crée EN PLUS du scénario (`initial + 2 ≠ initial + 1`, alors
    que le scénario a parfaitement réussi). `_crees_par_ce_scenario` ne voit que les ids créés
    après le relevé de CE scénario (`id > max_id`), affinés par le marqueur de tentative quand un
    step « … rendue unique … » l'a posé — jamais l'activité d'un tiers sur l'instance partagée.
    Plusieurs créations NON affinables restent une AMBIGUÏTÉ signalée, jamais un succès par défaut.

    ⚠️ **Le message d'échec porte le DIAGNOSTIC de la page** (2026-07-22) : « rien n'a été créé »
    est un constat, pas une explication, et c'est sur ce constat nu qu'on a accusé l'application
    à tort pendant toute une campagne de mesure. Voir `diagnostic_soumission`.
    """
    _require_snapshot(context, model)  # diagnostic + garde historique (step manquant → message)
    max_id = _require_max_id(context, model)
    ok, ids = _poll_until(
        lambda: _crees_par_ce_scenario(context, model), lambda v: len(v) >= 1)
    if ok and len(ids) == 1:
        _capturer_dernier_enregistrement(context, model, ids)
        return
    if ok and len(ids) > 1:
        # ⚠️ Plusieurs créations DEPUIS le relevé de CE scénario, et l'affinage par marqueur de
        # tentative (dans `_crees_par_ce_scenario`) n'a pas su les départager : impossible de dire
        # laquelle est celle du scénario. Une ambiguïté n'est JAMAIS un succès par défaut — même
        # motif que `record_ids` multiples ailleurs dans la bibliothèque (0007).
        global_actuel = context.odoo.env[model].search_count([])
        raise AssertionError(
            f"{len(ids)} créations détectées dans '{model}' depuis id > {max_id} (domaine "
            f"[('id', '>', {max_id})]), impossible de distinguer celle de ce scénario : "
            f"ids {ids}. Comptage global (diagnostic, inclut l'activité concurrente) : "
            f"{global_actuel}. Ajoutez un step « … rendue unique pour cette tentative » sur un "
            f"champ discriminant pour lever l'ambiguïté."
        )
    current = len(ids)  # `_poll_until` a déjà relu jusqu'à expiration : pas de nouvel appel RPC.
    page = getattr(context, "page", None)
    # ⚠️ §2bis 4ᵉ verdict — AVANT d'accuser l'application. Si rien n'a été créé PARCE QUE le
    # navigateur a refusé notre donnée (validation native), le verdict est `donnee_invalide`, pas
    # `non_conforme` : c'est notre jeu de données qui était irrecevable. Mesuré le 2026-07-22 —
    # 4 des 6 faux `non_conforme` passaient par ICI (l'assertion de comptage), pas par le clic.
    invalides = _refus_par_le_navigateur(page) if page is not None else []
    if invalides:
        # ⚠️ C'est ICI que passaient 4 des 6 faux `non_conforme` mesurés — donc le site le plus
        # rentable à faire apprendre, et celui que le plan initial avait oublié.
        route = _route_courante(page)
        lever_donnee_refusee(
            diagnostic_soumission(page),
            [m for m in (_refus_depuis_sonde(route, c) for c in invalides) if m])

    # ⚠️ §2bis étape 3a — la RÉPONSE SERVEUR, quand le navigateur n'a rien bloqué. C'est ce qui
    # lève les refus SILENCIEUX (rien créé, page muette) : la page ne dit rien, le serveur si.
    refus = _refus_serveur(context)
    if refus is not None:
        genre, detail = refus
        if genre == "champs":
            # Le serveur a nommé DES CHAMPS : c'est notre donnée qui viole une règle serveur (le
            # plafond JS enfin capté côté serveur) → donnee_invalide, l'app n'est pas en cause.
            lever_donnee_refusee(
                f"LE SERVEUR A REFUSÉ D'ENREGISTRER — champ(s) invalide(s) : {detail}. "
                f"⚠️ L'APPLICATION N'EST PAS EN CAUSE : c'est le jeu de données du test.",
                _refus_serveur_mesures(page, detail))
        if genre == "generique":
            # Refus serveur sans champ nommé, sur une saisie valide côté navigateur : l'app rejette
            # en silence une donnée recevable = défaut de comportement (arbitrage porteur 2026-07-23).
            raise AssertionError(
                f"Aucune création détectée dans '{model}' depuis id > {max_id} (domaine "
                f"[('id', '>', {max_id})]).\nLE SERVEUR A REFUSÉ la soumission sans nommer de "
                f"champ : « {detail} ». La donnée était pourtant acceptée par le navigateur.")
        # genre == "cree" : le serveur dit avoir créé (id), mais le comptage cloisonné ne le voit
        # pas — modèle différent, ou délai au-delà de la fenêtre. On tombe sur le constat ci-dessous.

    # Sinon (refus serveur affiché à l'écran, ou silence total) : constat de comptage + explication.
    global_actuel = context.odoo.env[model].search_count([])
    pourquoi = diagnostic_soumission(page) if page is not None else ""
    raise AssertionError(
        f"Aucune création détectée dans '{model}' depuis id > {max_id} (domaine "
        f"[('id', '>', {max_id})]) ; {current} trouvée(s) au lieu d'une. "
        f"Comptage global (diagnostic, inclut l'activité concurrente) : {global_actuel}."
        + (f"\n{pourquoi}" if pourquoi else ""))
