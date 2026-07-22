"""Helpers réutilisables — ZÉRO décorateur Behave.

Chaque module *steps.py importe les helpers dont il a besoin
et les encapsule dans ses propres @given/@when/@then.
"""

import logging
import os
import sys
import time
import warnings
import re
from playwright.sync_api import TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

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


def record_count_not_increased(env, model, initial_count):
    current = env[model].search_count([])
    assert current <= initial_count, (
        f"Nombre d'enregistrements dans '{model}' a augmenté ({initial_count} → {current})."
    )


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
    login_url = f"{context.odoo_url.rstrip('/')}/web/login?db={context.odoo_db}"
    context.page.goto(login_url, wait_until="domcontentloaded")
    context.page.wait_for_selector("input[name='login']", state="attached", timeout=15000)
    context.page.locator("input[name='login']").fill(context.odoo_user, force=True)
    context.page.locator("input[name='password']").fill(context.odoo_password, force=True)
    context.page.locator("input[name='password']").press("Enter")
    # Post-condition CONCRÈTE d'un login réussi : on a QUITTÉ la page de login (session établie).
    # Remplace `networkidle`, que le bus long-polling d'Odoo ne stabilise jamais.
    context.page.wait_for_url(lambda url: "/web/login" not in url, timeout=15000)


def navigate(context, url):
    full_url = url if url.startswith("http") else f"{context.odoo_url.rstrip('/')}{url}"
    if context.page.url in ("about:blank", ""):
        playwright_login(context)
    # domcontentloaded (fiable) au lieu de networkidle : l'interaction suivante auto-attendra sa cible.
    context.page.goto(full_url, wait_until="domcontentloaded")


def click_first_actionable(page, candidats, *, quoi, timeout=8000):
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
    `max(2000, timeout/len)`·len. Tous les candidats épuisés → `AssertionError` qui nomme `quoi`
    ET l'URL — pour que le diagnostic porte la vraie cause, pas un « introuvable » trompeur (§0002).
    """
    par_candidat = max(2000, timeout // max(1, len(candidats)))
    for c in candidats:
        loc = page.locator(c) if isinstance(c, str) else c
        try:
            loc.first.click(timeout=par_candidat)
            return
        except PlaywrightTimeout:
            continue
    raise AssertionError(f"{quoi} : aucun élément actionnable sur {page.url}")


def click_button(page, label):
    click_first_actionable(page, [
        page.get_by_role("button", name=label, exact=True),
        page.get_by_role("link", name=label, exact=True),
        page.get_by_role("button", name=label, exact=False),
        page.get_by_role("link", name=label, exact=False),
        f':is(a, button, input[type="submit"]):has-text("{label}")',
    ], quoi=f"Bouton '{label}'")
    verifier_soumission_non_bloquee(page)


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
                                  valeur: String(el.value || '').slice(0, 40),
                                  msg: el.validationMessage || '',
                                  manquant: el.validity.valueMissing === true});
                    }
                }
            }
            return out.slice(0, 6);
        }""") or []
    except Exception:
        return  # un contrôle de sûreté ne fait jamais tomber un scénario par lui-même
    if not invalides:
        return

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
    raise AssertionError(
        f"LE NAVIGATEUR A REFUSÉ D'ENVOYER le formulaire : {len(invalides)} champ(s) invalide(s) "
        f"— {details}.{indice}\n"
        f"⚠️ L'APPLICATION N'EST PAS EN CAUSE : c'est le jeu de données du test qui est "
        f"irrecevable. Corrige ces valeurs, ne conclus pas à un défaut applicatif.")


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
    name = resolve_field_name(page, name)
    safe = value.replace("\\", "\\\\").replace("'", "\\'")
    page.wait_for_selector(f'[name="{name}"]', timeout=10000, state="attached")
    el = page.locator(f'[name="{name}"]').first
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
        # Utiliser JS pour contourner les widgets Odoo et cibler le bon type d'élément
        page.evaluate(f"""
            const el = document.querySelector('textarea[name="{name}"], input[name="{name}"]');
            if (el) {{
                el.value = '{safe}';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)
        _verifier_valeur_retenue(page, name, value)


def _verifier_valeur_retenue(page, name, ecrit) -> None:
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

    Tolérant sur ce qui n'est pas une mutilation : espaces de bordure, et normalisations de casse
    (certains champs majusculisent) — les signaler produirait du bruit sans défaut réel.
    """
    try:
        retenu = page.evaluate(
            "(n) => { const el = document.querySelector(`[name=\"${n}\"]`);"
            " return el ? String(el.value) : null; }", name)
    except Exception:
        return  # un contrôle de sûreté ne fait jamais tomber un scénario par lui-même
    if retenu is None:
        return
    attendu = str(ecrit).strip()
    if retenu.strip() == attendu or retenu.strip().lower() == attendu.lower():
        return
    raise AssertionError(
        f"Le champ « {name} » a MODIFIÉ la valeur saisie : écrit {attendu!r}, retenu {retenu!r}. "
        f"Un filtre de saisie l'a transformée — la valeur du test est donc INADAPTÉE à ce champ "
        f"(ce n'est pas un défaut de l'application). Choisis une valeur conforme à son format.")


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

    page.wait_for_selector(f'[name="{name}"]', timeout=10000, state="attached")
    cible = page.locator(f'[name="{name}"]').first

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
        raise AssertionError(
            f"Le champ « {name} » n'est PAS un champ fichier (type={reel or 'inconnu'}) : on ne "
            f"peut rien y téléverser. Emploie plutôt :\n    {equivalent}")

    cible.set_input_files(str(chemin))


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
    name = resolve_field_name(page, name)
    page.wait_for_selector(f'[name="{name}"]', timeout=10000, state="attached")
    el = page.locator(f'[name="{name}"]').first
    tag = el.evaluate("el => el.tagName.toLowerCase()")
    input_type = el.evaluate("el => (el.type || '').toLowerCase()")

    if tag == "select":
        valeurs = el.evaluate("el => Array.from(el.options).map(o => o.value)")
        if "" not in valeurs:
            raise AssertionError(
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
    field = resolve_field_name(page, field)
    select = page.locator(f"select[name='{field}']")
    radio = page.locator(f"input[type='radio'][name='{field}'][value='{value}']")
    # Ancré sur l'ÉLÉMENT : on attend que le select OU le radio soit présent, au lieu d'un `count()`
    # instantané qui perd la course si le champ est rendu en JS. `count()` ne sert plus qu'à
    # BRANCHER une fois le champ là (plus une course). Plus de `wait_for_timeout` fixe.
    try:
        page.locator(
            f"select[name='{field}'], input[type='radio'][name='{field}']"
        ).first.wait_for(state="attached", timeout=8000)
    except PlaywrightTimeout:
        raise AssertionError(
            f"Champ select ou radio '{field}' introuvable sur {page.url} (valeur: '{value}')")
    if select.count() > 0:
        select_option_strict(select.first, value, field=field)
        return
    if radio.count() > 0:
        radio.first.check(force=True)
        return
    raise AssertionError(
        f"Radio '{field}' présent mais sans l'option '{value}' sur {page.url}")


_PRODUCT_PATHS = ("/description/", "/product/", "/detail/", "/formulaire-applicatif/")


def select_first_service_in_list(page):
    click_first_actionable(page,
        [f"a[href*='{p}']" for p in ("/formulaire-applicatif/", "/description/", "/product/")],
        quoi="Service dans la liste")


def select_product_in_list(page, name):
    click_first_actionable(page,
        [f"a[href*='{p}']:has-text('{name}')" for p in _PRODUCT_PATHS],
        quoi=f"Produit '{name}'")


def select_product_partial(page, partial):
    # `:has-text` fait le « contient » (sous-chaîne), désormais insensible à la casse — plus
    # tolérant que l'ancien `partial in inner_text`, et surtout sans course au rendu.
    click_first_actionable(page,
        [f"a[href*='{p}']:has-text('{partial}')" for p in _PRODUCT_PATHS],
        quoi=f"Produit contenant '{partial}'")


def click_onglet(page, name):
    click_first_actionable(page, [
        f".nav-link:has-text('{name}')", f".nav-item a:has-text('{name}')",
        f"[role='tab']:has-text('{name}')", f"li a:has-text('{name}')",
        f"a:has-text('{name}')", f"button:has-text('{name}')",
    ], quoi=f"Onglet '{name}'")


def click_button_with_accessoires(page, label):
    click_first_actionable(page,
        [f".btn-{label}", f":is(button, a):has-text('{label}')"],
        quoi=f"Bouton '{label}' (accessoires)")


def force_name_field(page, value):
    """Set the hidden name field using the JS native setter to bypass Odoo auto-generation."""
    safe = value.replace("\\", "\\\\").replace("'", "\\'")
    # Ancré sur l'élément : sans cette attente, un champ rendu tardivement → `querySelector` nul →
    # le setter ne faisait RIEN, en silence (le nom restait celui auto-généré par Odoo).
    page.locator('[name="name"]').wait_for(state="attached", timeout=8000)
    page.evaluate(f"""
        (() => {{
            const el = document.querySelector('[name="name"]');
            if (el) {{
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                setter.call(el, '{safe}');
            }}
        }})()
    """)


def select_first_agence(page):
    select = page.locator("select[name='agence']")
    # Ancré sur l'élément (plus de `count()` instantané ni de sleep fixe).
    try:
        select.first.wait_for(state="attached", timeout=8000)
    except PlaywrightTimeout:
        raise AssertionError(f"Champ 'agence' introuvable sur {page.url}")
    options = select.locator("option")
    for i in range(options.count()):
        val = options.nth(i).get_attribute("value")
        if val and val.strip():
            select.first.select_option(val)
            return
    raise AssertionError(f"Aucune option disponible dans le champ 'agence' sur {page.url}")


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
    has_error = page.locator("[class*='s_website_form_field'].o_has_error").first
    assert has_error.is_visible(), "Aucune erreur de validation visible dans le formulaire."


def validation_error_notification(page):
    error = page.locator(".o_notification_manager .o_notification.border-danger").first
    assert error.is_visible(), "Aucune notification d'erreur visible dans l'interface."


def no_error_with_keywords(page, keyword1, keyword2):
    error_elements = page.locator(".alert-danger, .o_notification.border-danger, .text-danger")
    for i in range(error_elements.count()):
        error_text = error_elements.nth(i).inner_text().lower()
        assert keyword1.lower() not in error_text and keyword2.lower() not in error_text, \
            f"Erreur contenant '{keyword1}' ou '{keyword2}' trouvée : {error_text}"


def navigate_menu(context, menu_path):
    context.page.goto(context.odoo_url, wait_until="domcontentloaded")
    for part in [p.strip() for p in menu_path.split(">")]:
        # clic auto-attendu (actionnabilité) ; pas de networkidle entre les niveaux.
        context.page.get_by_text(part, exact=True).first.click(timeout=8000)


def access_portal_section(page, section_name):
    try:
        page.get_by_text(section_name, exact=False).first.click(timeout=8000)
    except PlaywrightTimeout:
        raise AssertionError(
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


def memorize_record_count(context, model):
    """Mémorise le nombre d'enregistrements du modèle, pour comparaison après l'action.

    Échoue si le comptage est impossible : sans snapshot, toute vérification en aval serait creuse
    (cf. `_require_snapshot`). Mieux vaut échouer ICI, où la cause est visible, que laisser le
    scénario finir au vert sans rien avoir prouvé.
    """
    try:
        setattr(context, _count_attr(model), context.odoo.env[model].search_count([]))
    except Exception as exc:
        raise AssertionError(
            f"Impossible de mémoriser le nombre d'enregistrements de '{model}' : {exc}. "
            f"Sans ce point de comparaison, les vérifications de comptage ne prouveraient rien."
        ) from exc


def _require_snapshot(context, model) -> int:
    """Renvoie le snapshot initial, ou ÉCHOUE en nommant le step manquant.

    Ne jamais remplacer par un `return` silencieux : le `@then` appelant passerait sans rien
    vérifier, et un scénario vert affirmerait un comptage que personne n'a mesuré (§4.2/§4.4).
    """
    attr = _count_attr(model)
    if not hasattr(context, attr):
        raise AssertionError(
            f"Aucun point de comparaison pour '{model}' : ce scénario vérifie un comptage sans "
            f"l'avoir mesuré avant l'action. Ajoutez le step "
            f"« {_COUNT_SNAPSHOT_STEP.format(model=model)} » avant l'action."
        )
    return getattr(context, attr)


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
    """Le négatif attend TOUTE la fenêtre : on cherche une augmentation pendant `COUNT_SETTLE_TIMEOUT`
    ; si aucune n'apparaît, on conclut « rien créé ». Attendre moins laisserait passer une création
    tardive à tort (faux négatif, §4.4 inacceptable)."""
    initial = _require_snapshot(context, model)
    augmente, current = _poll_until(
        lambda: context.odoo.env[model].search_count([]), lambda c: c > initial)
    assert not augmente, (
        f"Nombre d'enregistrements dans '{model}' a augmenté ({initial} → {current})."
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
        invalides = page.evaluate("""() => {
            const out = [];
            for (const el of document.querySelectorAll('input, select, textarea')) {
                if (el.willValidate && !el.checkValidity()) {
                    out.push({nom: el.name || el.id || '?', msg: el.validationMessage || ''});
                }
            }
            return out.slice(0, 5);
        }""") or []
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

        return ("Aucun message d'erreur affiché par la page après soumission — le refus est "
                "SILENCIEUX. Rien ne permet de distinguer un rejet métier d'un défaut applicatif.")
    except Exception as exc:  # un diagnostic ne casse JAMAIS le scénario qu'il éclaire
        return f"(diagnostic de soumission indisponible : {type(exc).__name__})"


def check_count_increased_by_one(context, model):
    """Le positif attend que le ticket APPARAISSE (jusqu'à `COUNT_SETTLE_TIMEOUT`). S'il n'apparaît
    pas dans la fenêtre, l'assertion échoue avec le message d'origine — un vrai « non créé » reste
    détecté, seule la course disparaît.

    ⚠️ **Le message d'échec porte désormais le DIAGNOSTIC de la page** (2026-07-22) : « rien n'a
    été créé » est un constat, pas une explication, et c'est sur ce constat nu qu'on a accusé
    l'application à tort pendant toute une campagne de mesure. Voir `diagnostic_soumission`.
    """
    initial = _require_snapshot(context, model)
    ok, current = _poll_until(
        lambda: context.odoo.env[model].search_count([]), lambda c: c == initial + 1)
    if ok:
        return
    page = getattr(context, "page", None)
    pourquoi = diagnostic_soumission(page) if page is not None else ""
    raise AssertionError(
        f"Nombre d'enregistrements dans '{model}' devrait être {initial + 1}, obtenu {current}."
        + (f"\n{pourquoi}" if pourquoi else ""))
