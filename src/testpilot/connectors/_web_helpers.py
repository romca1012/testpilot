"""Perception UI PURE, partagée entre TOUS les connecteurs web (Odoo, générique, …).

Extrait de ``connectors/odoo.py`` (audit multi-connecteurs, 2026-09-08) : ces fonctions
n'ont jamais rien eu de spécifique à Odoo — elles lisent une page RENDUE (formulaire, lien,
réponse HTTP), jamais l'API RPC. Les dupliquer dans chaque nouveau connecteur aurait fait
deux endroits où corriger un bug d'extraction de formulaire (ex. un type de champ mal
reconnu) sans que le second ne le sache jamais.

``odoo.py`` réexporte ``build_probe_url``/``extract_form`` pour ne pas casser les imports
existants (``from testpilot.connectors.odoo import build_probe_url, extract_form``).
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

# Champs de formulaire à ignorer : jetons techniques, pas des champs métier.
_IGNORED_FIELD_PREFIXES = ("_",)
_IGNORED_FIELD_NAMES = {"csrf_token"}


def build_probe_url(base_url: str, path_pattern: str, sample_id: int | None = None) -> str:
    """Construit l'URL absolue à sonder. Pur (aucun réseau).

    ``{id}`` dans le motif est substitué par ``sample_id`` s'il est fourni.
    """
    pattern = path_pattern or "/"
    if "{id}" in pattern and sample_id is not None:
        pattern = pattern.replace("{id}", str(sample_id))
    elif "{id}" in pattern:
        pattern = pattern.replace("{id}", "")
    return urljoin(base_url.rstrip("/") + "/", pattern.lstrip("/"))


def extract_form(page) -> dict:
    """Extrait champs + mécanisme de soumission d'une page rendue. Pur vis-à-vis du réseau.

    ``page`` est un objet duck-typé (Playwright Page ou fake de test) exposant
    ``query_selector_all`` / ``query_selector``. Retour :
    ``{fields:[{name,required,type}], submission:{mechanism,endpoint,trigger_selector}}``.
    """
    fields: list[dict] = []
    seen: set[str] = set()
    for el in page.query_selector_all("input, select, textarea"):
        name = el.get_attribute("name") or el.get_attribute("id") or ""
        if not name or name in seen:
            continue
        if name in _IGNORED_FIELD_NAMES or name.startswith(_IGNORED_FIELD_PREFIXES):
            continue
        seen.add(name)
        tag = (el.get_attribute("__tag__") or "").lower()  # fake de test
        input_type = el.get_attribute("type") or tag or "text"
        fields.append({
            "name": name,
            "required": el.get_attribute("required") is not None,
            "type": input_type,
        })
        if hasattr(el, 'evaluate'):
            fields[-1].update(el.evaluate('''el => ({
                tag: el.tagName.toLowerCase(),
                label: el.labels?.[0]?.textContent?.trim() || el.getAttribute('aria-label') || '',
                visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
                options: el.tagName === 'SELECT' ? Array.from(el.options).map(
                    o => [o.value, o.textContent.trim()]) : [],
                min: el.getAttribute('min'), max: el.getAttribute('max'),
                maxlength: el.getAttribute('maxlength'), pattern: el.getAttribute('pattern'),
                minlength: el.getAttribute('minlength'), inputmode: el.getAttribute('inputmode'),
                placeholder: el.getAttribute('placeholder'), title: el.getAttribute('title'),
                data_mask: el.getAttribute('data-mask'),
                inputmask: el.getAttribute('data-inputmask') || el.getAttribute('inputmask')
            })'''))

    submission = _detect_submission(page)
    html = page.query_selector('html')
    return {"fields": fields, "submission": submission,
            "url": getattr(page, 'url', ''),
            "language": html.get_attribute('lang') or '' if html else ''}


def _detect_submission(page) -> dict:
    """Déduit le mécanisme de soumission : endpoint du <form> + sélecteur déclencheur."""
    form = page.query_selector("form")
    endpoint = form.get_attribute("action") if form else ""
    trigger = page.query_selector("button[type='submit'], input[type='submit'], button.btn-primary")
    trigger_selector = ""
    if trigger is not None:
        name = trigger.get_attribute("name")
        # Ne pas inventer un bouton submit si seul un bouton JS a été observé.
        trigger_selector = f"[name='{name}']" if name else ''
        if not name and trigger.get_attribute('type') == 'submit':
            trigger_selector = "button[type='submit'], input[type='submit']"
    return {
        "mechanism": "button_click" if trigger is not None else "unknown",
        "endpoint": endpoint or "",
        "trigger_selector": trigger_selector,
    }


class ConnexionGeneriqueImpossibleError(Exception):
    """Ni le schéma à UN écran (identifiant + mot de passe ensemble) ni celui à DEUX écrans
    (identifiant seul, puis mot de passe sur l'écran suivant) n'a permis de repérer un formulaire
    de connexion exploitable — étape 3.1 du plan de consolidation (2026-09-15, audit « Le pari
    Mabl/Testim »). Le cas le plus probable est un SSO/un second facteur (2FA), tous deux hors du
    périmètre d'une détection générique par champs de formulaire : un jeton de session externe ou
    un code à usage unique ne sont pas des données que `user`/`password` peuvent fournir.

    ⚠️ **Une classe DÉDIÉE, plutôt qu'un retour `False` silencieux comme avant cette étape** — un
    échec d'authentification à ce stade laissait l'exploration/la perception continuer SANS
    connexion, sans que rien ne dise pourquoi, ce qui produit un annuaire ou une inspection de
    formulaire mesurée sur la mauvaise page (celle de connexion) sans le moindre signal distinct
    d'un « pas de connexion nécessaire ici » légitime.
    """


def _ressemble_a_un_premier_ecran_de_connexion(page) -> bool:
    """Un écran minimal — EXACTEMENT un champ texte/email, plus un contrôle de soumission — pas
    n'importe quelle page qui porte un champ texte quelconque (recherche, newsletter…).

    ⚠️ **Ce garde existe pour éviter un FAUX POSITIF du schéma à deux écrans** (étape 3.1) : sans
    lui, la détection soumettrait n'importe quel champ texte/email trouvé sur une page SANS mot de
    passe, en pariant qu'il s'agit d'un premier écran de connexion — un pari qui se paierait cher
    sur une page de recherche ou d'inscription à une newsletter. Un vrai premier écran de connexion
    à deux étapes (ex. Google, Microsoft) est délibérément minimal ; ce n'est pas le cas d'une page
    de contenu ordinaire qui porte un champ texte parmi d'autres.
    """
    champs = page.query_selector_all("input[type='email'], input[type='text']")
    if len(champs) != 1:
        return False
    return page.query_selector("button, input[type='submit']") is not None


def tenter_connexion_generique(page, user: str, password: str) -> bool:
    """Détection de connexion GÉNÉRIQUE (pas de convention d'URL à connaître, à la différence
    d'Odoo) — partagée entre ``GenericWebConnector`` (exécution) et le crawl générique
    (exploration, audit multi-connecteurs 2026-09-08) : les deux affrontent le même problème,
    « repérer un formulaire de connexion sur une page qu'on n'a jamais vue ».

    **Schéma à UN écran** (historique, comportement inchangé) : un mot de passe est l'identifiant
    le plus fiable d'un formulaire de connexion — on cherche ``input[type=password]``, on prend le
    premier champ texte/email de la PAGE comme identifiant (scope volontairement simple, pas un
    `closest('form')` — un premier jet à affiner si un formulaire réel la met en défaut), on
    remplit et on valide.

    **Schéma à DEUX écrans** (étape 3.1 du plan de consolidation, 2026-09-15 — de nombreuses
    applications SaaS modernes, ex. Google/Microsoft, demandent l'identifiant seul avant de
    révéler le mot de passe sur un second écran) : si aucun mot de passe n'apparaît mais que la
    page RESSEMBLE à un premier écran minimal (`_ressemble_a_un_premier_ecran_de_connexion`), on
    soumet l'identifiant seul puis on cherche le mot de passe sur l'écran suivant. Ni l'un ni
    l'autre schéma ne matchant (SSO/2FA) → `ConnexionGeneriqueImpossibleError`, explicite et
    distincte, plutôt qu'un échec silencieux dans un état ambigu.

    Identifiant/mot de passe VIDES, ou aucun indice de formulaire de connexion sur la page : on
    considère l'application accessible sans connexion et on continue tel quel — mieux vaut
    explorer sans authentification que de bloquer sur une hypothèse de connexion fausse.

    Retourne ``True`` si une tentative a réellement été soumise (jamais si la page ou les
    identifiants ne s'y prêtaient pas).
    """
    if not user or not password:
        return False

    champ_mdp = page.query_selector("input[type='password']")
    if champ_mdp is not None:
        champ_identifiant = page.query_selector("input[type='email'], input[type='text']")
        if champ_identifiant is None:
            logger.warning("[connexion-générique] mot de passe détecté sans champ identifiant"
                            " — connexion non tentée")
            return False
        champ_identifiant.fill(user, force=True)
        champ_mdp.fill(password, force=True)
        champ_mdp.press("Enter")
        page.wait_for_load_state("networkidle")
        return True

    if not _ressemble_a_un_premier_ecran_de_connexion(page):
        return False  # pas d'indice de connexion du tout : comportement historique inchangé

    champ_identifiant_seul = page.query_selector("input[type='email'], input[type='text']")
    champ_identifiant_seul.fill(user, force=True)
    champ_identifiant_seul.press("Enter")
    page.wait_for_load_state("networkidle")

    champ_mdp_ecran_suivant = page.query_selector("input[type='password']")
    if champ_mdp_ecran_suivant is None:
        raise ConnexionGeneriqueImpossibleError(
            "aucun champ mot de passe trouvé après soumission de l'identifiant sur "
            f"{getattr(page, 'url', '?')} — probablement un SSO/second facteur (2FA), hors du "
            "périmètre de cette détection générique.")
    champ_mdp_ecran_suivant.fill(password, force=True)
    champ_mdp_ecran_suivant.press("Enter")
    page.wait_for_load_state("networkidle")
    return True


# ── Lire un message d'erreur réellement affiché (2026-09-16 — audit « Le pari Mabl/Testim »,
# amendement §4.3-bis étendu) ─────────────────────────────────────────────────────────────────
#
# ⚠️ **Pourquoi ceci existe.** Un cas généré affirmait qu'un compte verrouillé affiche « Sorry,
# this user has been locked out. » — l'application affiche en réalité « Epic sadface: Sorry,
# this user has been locked out. ». L'agent avait DEVINÉ ce texte depuis sa mémoire d'entraînement
# au lieu de l'observer : rien dans le pipeline de génération ne lit jamais le DOM réel avant
# d'écrire une assertion sur un texte affiché (`inspect_page_form`/`discover_route` n'observent
# que la STRUCTURE des formulaires, jamais leur CONTENU). Playwright Codegen — l'outil officiel
# équivalent — ne demande JAMAIS ce texte à l'auteur : il lit l'`innerText` réel de l'élément visé
# au moment de l'enregistrement. On applique le même principe ici : observer avant d'écrire.

_SELECTEURS_MESSAGE_ERREUR = (
    '[role="alert"], .error, .alert-danger, .is-invalid, '
    ".o_notification.border-danger, [class*='s_website_form_field'].o_has_error"
)
# ⚠️ MÊME liste, au caractère près, que `behave_runtime/steps_library/_base_helpers.py::
# validation_error_inline` — validée contre DEUX applications réelles distinctes (SauceDemo :
# `[role="alert"]` ; the-internet.herokuapp.com : `.error`), durcie le 2026-09-14 après un faux
# négatif réel. Dupliquée ici plutôt qu'importée : `_base_helpers` vit hors du paquet `testpilot`
# (voir `OdooConnector.crawl_relogin_hook`, même contrainte) et n'est chargeable qu'après un
# montage de `sys.path` que ce module, appelé bien plus tôt (génération), n'a aucune raison de
# faire. Toute évolution de cette liste doit être reportée dans les deux fichiers.


def lire_message_erreur_visible(page) -> str:
    """Le texte du premier message d'erreur VISIBLE et NON VIDE, ou `""` si aucun ne l'est.

    ⚠️ **Un élément peut matcher le sélecteur, être visible, ET n'avoir aucun texte** — vérifié en
    conditions réelles sur SauceDemo (2026-09-16) : la bannière d'erreur s'y compose de plusieurs
    éléments `.error`/`[role="alert"]` imbriqués, dont un conteneur vide et le bouton « X » de
    fermeture (lui aussi visible, lui aussi sans texte) AVANT le `<h3 data-test="error">` qui
    porte le vrai message. S'arrêter au premier élément VISIBLE, sans regarder s'il a du texte,
    aurait rendu une chaîne vide au lieu du message réel — on continue donc tant que le texte lu
    est vide, jamais seulement tant que l'élément est invisible.

    Best-effort, jamais fatal : un élément qui disparaît entre le comptage et la lecture est
    ignoré, pas une exception qui remonte."""
    candidats = page.locator(_SELECTEURS_MESSAGE_ERREUR)
    for i in range(min(candidats.count(), 8)):
        try:
            candidat = candidats.nth(i)
            if not candidat.is_visible():
                continue
            texte = candidat.inner_text().strip()
            if texte:
                return texte
        except Exception:
            continue
    return ""


def tenter_connexion_et_lire_resultat(page, user: str, password: str) -> dict:
    """Remplit et soumet le formulaire de connexion avec CES identifiants précis (utile/erroné/
    verrouillé...), puis rend ce qui s'affiche VRAIMENT — pour que l'agent de génération vérifie
    un message avant de l'écrire dans une assertion, au lieu de le deviner.

    Rend toujours un dict, jamais une exception : `error` porte la raison si l'identification a
    échoué (SSO/2FA détecté, aucun formulaire trouvé, identifiants vides) — l'appelant reste alors
    sans donnée observée, exactement comme avant l'ajout de cette fonction.
    """
    try:
        soumis = tenter_connexion_generique(page, user, password)
    except ConnexionGeneriqueImpossibleError as exc:
        return {"submitted": False, "url": getattr(page, "url", ""), "message": "", "error": str(exc)}
    if not soumis:
        return {"submitted": False, "url": getattr(page, "url", ""), "message": "",
                "error": "aucun formulaire de connexion détecté sur cette page, ou identifiants vides"}
    return {"submitted": True, "url": page.url, "message": lire_message_erreur_visible(page), "error": ""}


# ── Soumettre un VRAI formulaire de calibration (2026-09-16 — amendement §4.3-bis étendu) ──────
#
# ⚠️ **Réservé aux formulaires qu'un connecteur sait aussi ANNULER.** Contrairement à
# `tenter_connexion_et_lire_resultat` (une connexion ne crée jamais de donnée, on peut la
# retenter à l'infini), soumettre un formulaire métier CRÉE potentiellement un enregistrement
# réel. Cette fonction n'est donc appelée que par un connecteur qui a les moyens de nettoyer
# derrière lui (Odoo, RPC `delete`) — jamais par le connecteur générique, qui n'a aucune garantie
# de suppression et refuse explicitement (`GenericWebConnector.attempt_form_submission`).

_SELECTEURS_MESSAGE_CONFIRMATION = _SELECTEURS_MESSAGE_ERREUR + ", .alert, .alert-success, .o_notification"
# ⚠️ Contrairement à `_SELECTEURS_MESSAGE_ERREUR`, `.alert` NU (sans qualificatif) est INCLUS ici
# volontairement : `validation_error_inline` l'exclut parce qu'il cherche SPÉCIFIQUEMENT une
# erreur (un `.alert` de succès y serait un faux positif). Ici, on veut n'IMPORTE QUEL message
# réellement affiché, succès ou erreur — c'est l'appelant (le test généré) qui décide ensuite ce
# que ce texte doit valoir, pas cette fonction.


def lire_message_confirmation_visible(page) -> str:
    """Comme `lire_message_erreur_visible`, élargi aux messages de SUCCÈS — l'issue attendue
    après soumission d'un formulaire de calibration n'est pas forcément une erreur."""
    candidats = page.locator(_SELECTEURS_MESSAGE_CONFIRMATION)
    for i in range(min(candidats.count(), 8)):
        try:
            candidat = candidats.nth(i)
            if not candidat.is_visible():
                continue
            texte = candidat.inner_text().strip()
            if texte:
                return texte
        except Exception:
            continue
    return ""


def soumettre_formulaire_et_lire_resultat(page, valeurs: dict) -> dict:
    """Remplit CES champs (par nom technique) sur le formulaire réel, le soumet, et rend ce qui
    s'affiche VRAIMENT. Ne nettoie RIEN (aucun accès RPC ici) : c'est à l'appelant — le seul à
    savoir identifier et supprimer ce qui vient d'être créé — de s'en charger après coup.

    Rend toujours un dict, jamais une exception. `error` porte la raison si aucun des champs
    fournis n'a été trouvé, ou si aucun déclencheur de soumission n'a été détecté.
    """
    trouves = 0
    for nom, valeur in valeurs.items():
        champ = page.query_selector(f"[name='{nom}']")
        if champ is None:
            continue
        champ.fill(str(valeur), force=True)
        trouves += 1
    if not trouves:
        return {"submitted": False, "url": getattr(page, "url", ""), "message": "",
                "error": "aucun des champs fournis n'a été trouvé sur cette page"}

    declencheur = _detect_submission(page).get("trigger_selector") or ""
    bouton = page.query_selector(declencheur) if declencheur else None
    if bouton is None:
        return {"submitted": False, "url": getattr(page, "url", ""), "message": "",
                "error": "aucun déclencheur de soumission détecté sur cette page"}

    bouton.click()
    page.wait_for_load_state("networkidle")
    return {"submitted": True, "url": page.url,
           "message": lire_message_confirmation_visible(page), "error": ""}


def http_probe(url: str) -> dict:
    """Sonde HTTP HEAD→GET. Isolée pour être surchargée hors-ligne en test.

    ⚠️ **Bug corrigé (2026-09-11, SauceDemo sur /dev).** La branche `HTTPError` RENDAIT
    immédiatement dès le HEAD, sans jamais essayer le GET annoncé par le nom de la fonction
    (« HEAD→GET ») — seule la branche `URLError`/`OSError`, elle, `continue`ait vers le GET.
    Beaucoup de serveurs (WAF, certains hébergeurs statiques) répondent 405 « Method Not Allowed »
    à un HEAD tout en servant très bien le GET correspondant : `discover_route` (outil LLM de la
    passe technique) rapportait alors une route comme cassée alors qu'elle ne l'était pas — l'IA
    prend cette observation pour un fait mesuré (§6), pas une supposition, donc une fausse alerte
    ici pouvait faire échouer ou mal orienter toute une génération. Même filet qu'`URLError` :
    on tente le GET avant de conclure quoi que ce soit, et seul l'échec du DERNIER moyen essayé
    devient le verdict rendu.
    """
    methodes = ("HEAD", "GET")
    dernier_statut, dernier_motif = 0, ""
    for i, method in enumerate(methodes):
        est_dernier = i == len(methodes) - 1
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return {"url": url, "status": resp.status, "method": method, "note": "accessible"}
        except urllib.error.HTTPError as exc:
            dernier_statut, dernier_motif = exc.code, (exc.reason or "réponse HTTP d'erreur")
            if est_dernier:
                return {"url": url, "status": dernier_statut, "method": method, "note": dernier_motif}
            continue
        except (urllib.error.URLError, OSError) as exc:
            dernier_statut, dernier_motif = 0, str(getattr(exc, "reason", exc))
            if est_dernier:
                return {"url": url, "status": 0, "method": method,
                        "note": f"injoignable : {dernier_motif}"}
            continue
    return {"url": url, "status": dernier_statut, "method": methodes[-1], "note": dernier_motif}
