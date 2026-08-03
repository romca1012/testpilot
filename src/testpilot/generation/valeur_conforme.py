"""Synthèse DÉTERMINISTE d'une valeur recevable par un champ, à partir de ses contraintes.

⚠️ **Pourquoi ce module existe** — la re-mesure du 2026-07-22 (cas 45-52) l'a prouvé : donner les
contraintes au LLM dans le prompt (`prompt._section_champs_requis`) ne suffit **pas**. L'annuaire
connaît le motif `\\d{7}`, le prompt l'impose en majuscules, et le LLM écrit quand même
« FAC-TEST-001 ». Un LLM est bon pour le SENS, mauvais pour la FORME. On arrête donc de lui
demander de produire la valeur : une couche déterministe la fabrique en lisant l'annuaire.

C'est le composant 2 du §2bis (« le déterministe garantit la forme »). Il n'appelle **aucun
modèle**, ne touche **aucun réseau** : donné un champ, il rend une valeur qui satisfait ses
contraintes mesurées — ou lève `ValeurNonSynthetisable` s'il n'y arrive pas (le composant A, à
l'exécution, reste le filet pour les règles JavaScript qu'aucun crawl statique ne voit — §2bis).

Forme d'entrée = celle exposée par `domain_model.formulaires_requis()` :
`{"name", "tag", "type", "visible", "label", "contraintes": {...}, "options": [...]}`.
⚠️ **Les bornes de `contraintes` sont des CHAÎNES** (`"min": "0"`, `"maxlength": "25"`) — telles
que le crawl les a lues dans le HTML.
"""

from __future__ import annotations

import re
import warnings
from datetime import date, timedelta


class ValeurNonSynthetisable(ValueError):
    """Aucune valeur déterministe ne peut être garantie recevable pour ce champ.

    ⚠️ Classe DÉDIÉE (même raison que `InvalidOptionValueError` en 0019) : elle nomme un état
    précis — « la donnée n'a pas pu être fabriquée » — que le résolveur peut attraper pour
    déléguer, plutôt qu'un `ValueError` nu ambigu.
    """


# ── Motif regex → valeur minimale qui le satisfait ───────────────────────────
#
# ⚠️ Portée VOLONTAIREMENT bornée : on ne résout pas une regex arbitraire, seulement la famille
# réellement mesurée sur le portail (répétition de classes de caractères : `\d{7}`, `\d{9} \d{5}`,
# `[A-Za-z0-9]{8,11}`, `\+?[0-9\s\-\(\)]{10,}`…). Toute valeur produite est RE-VÉRIFIÉE par
# `re.fullmatch` avant d'être rendue : si le générateur se trompe, il lève au lieu de mentir.

def _char_pour_classe(classe: str) -> str:
    """Un caractère GARANTI membre de la classe `[...]`. Préfère un chiffre, puis une lettre."""
    if "0-9" in classe or r"\d" in classe:
        return "1"
    if "a-z" in classe or "A-Z" in classe:
        return "A"
    for c in classe:
        if c not in "\\-^":
            return c
    return "0"


_ECHAPPE = {"d": "1", "w": "A", "s": " "}  # \d → un chiffre, \w → alphanum, \s → une espace


def valeur_pour_motif(motif: str) -> str:
    """Une chaîne minimale qui satisfait `motif` (motif HTML `pattern`, donc ancré full-match).

    Lève `ValeurNonSynthetisable` si le résultat ne passe pas `re.fullmatch` — le générateur ne
    couvre pas tout, et il vaut mieux le dire que rendre une valeur qui sera refusée à l'exécution.
    """
    out: list[str] = []
    i, n = 0, len(motif)
    while i < n:
        ch = motif[i]
        if ch in "^$":  # ancres HTML implicites — rien à émettre
            i += 1
            continue
        if ch == "\\":
            unite = _ECHAPPE.get(motif[i + 1], motif[i + 1])  # \+ → '+', \- → '-', etc.
            i += 2
        elif ch == "[":
            j = motif.index("]", i)
            unite = _char_pour_classe(motif[i + 1:j])
            i = j + 1
        else:
            unite = ch  # littéral (chiffre, lettre, espace, '+' non échappé…)
            i += 1
        rep = 1
        if i < n and motif[i] in "{?*+":
            if motif[i] == "{":
                j = motif.index("}", i)
                rep = int(motif[i + 1:j].split(",")[0])  # {7}→7, {8,11}→8, {10,}→10
                i = j + 1
            else:
                rep = 0 if motif[i] == "*" else 1  # ? et + → 1 (représentant valide), * → 0
                i += 1
        out.append(unite * rep)
    valeur = "".join(out)
    if not re.fullmatch(motif, valeur):
        raise ValeurNonSynthetisable(f"motif non couvert : {motif!r} → {valeur!r} ne matche pas")
    return valeur


# ── Règle lisible (attribut `title`) → indice de forme ───────────────────────
#
# ⚠️ Best-effort sur du TEXTE FRANÇAIS formulaire. C'est le pis-aller quand le HTML ne porte pas
# de `pattern` structuré (souvent une règle JavaScript, cf. le plafond du §2bis) : mieux qu'un
# texte de test générique qui serait refusé, sans prétendre à l'exhaustivité.

_MOTS_NOMBRE = {"un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
                "huit": 8, "neuf": 9, "dix": 10}


def _n_chiffres_depuis_regle(regle: str) -> int | None:
    """« groupes de sept chiffres » / « à 9 chiffres » → 7 / 9. `None` si pas d'indice."""
    m = re.search(r"(\d+)\s*chiffres", regle)
    if m:
        return int(m.group(1))
    for mot, valeur in _MOTS_NOMBRE.items():
        if re.search(rf"\b{mot}\s+chiffres", regle, re.IGNORECASE):
            return valeur
    return None


# Un IBAN FR de test au checksum VALIDE (mod-97) — une valeur inventée « FR00… » serait rejetée par
# une validation de checksum, qu'elle soit HTML ou JavaScript.
_IBAN_FR_VALIDE = "FR7630006000011234567890189"

# Direction d'une contrainte de date exprimée en toutes lettres.
_DATE_FUTUR = ("ultérieure", "ulterieure", "postérieure", "posterieure", "plus récente",
               "plus recente", "supérieure", "superieure")


def _borne_num(v) -> float | None:
    """La borne `min`/`max` en nombre si elle est numérique, sinon `None` (placeholder `date_now`,
    chaîne vide… — même garde que `prompt._borne_exploitable`, pour ne pas répéter le bruit capté)."""
    try:
        return float(str(v))
    except (TypeError, ValueError):
        return None


# ── Ce que les REFUS ont appris (§5bis n°1) ──────────────────────────────────
#
# Le crawl ne voit que le HTML ; une règle posée en JavaScript lui échappe par construction. Ce
# que l'exécution a mesuré (une valeur refusée, une classe de caractères qu'un filtre conserve)
# vient donc restreindre ce que le résolveur a le droit de produire — sans jamais contredire ce
# que le crawl a réellement mesuré.

# Combien de valeurs différentes tenter avant de renoncer. Borné : si 5 valeurs déterministes,
# toutes conformes aux contraintes connues, sont refusées, le problème n'est pas le tirage — c'est
# qu'une règle nous échappe encore. On le DIT (verdict `indetermine`) au lieu de tâtonner.
_MAX_VARIANTES = 5

# « uniquement des chiffres » et ses variantes → la classe que le champ accepte. Lu dans le
# message de l'APPLICATION (comme `regle_lisible`, qui porte déjà l'attribut `title`), jamais
# dans un texte écrit par l'agent.
_CLASSE_DEPUIS_REGLE = (
    (r"(uniquement|que)\s+des\s+chiffres", r"\d"),
    (r"chiffres\s+(uniquement|seulement)", r"\d"),
    (r"(uniquement|que)\s+des\s+lettres", r"[A-Za-z]"),
)


def _classe_depuis_regle(regle: str) -> str:
    """La classe de caractères imposée par une règle écrite en français, ou `''`."""
    for motif, classe in _CLASSE_DEPUIS_REGLE:
        if re.search(motif, regle or "", re.IGNORECASE):
            return classe
    return ""


def _respecte(classe: str, valeur: str) -> bool:
    """`valeur` n'est-elle faite que de caractères de `classe` ?

    Une classe qu'on ne sait pas compiler n'interdit **rien** : le mécanisme est détectif, pas
    bloquant — une donnée mal formée en base ne doit jamais empêcher un test de tourner.
    `warnings.catch_warnings` est là parce qu'une classe douteuse déclenche un `FutureWarning`
    avant même de lever, et qu'un avertissement dans la sortie de test est du bruit qu'on finit
    par ne plus lire.
    """
    if not valeur:
        return False
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            return re.fullmatch(f"(?:{classe})+", valeur) is not None
    except (re.error, FutureWarning, DeprecationWarning):
        return True


def _valeur_pour_classe(classe: str, champ: dict) -> str:
    """Une valeur faite UNIQUEMENT de caractères de `classe`, longue de ce que le champ tolère.

    La longueur reprend les signaux déjà connus, dans le même ordre que `_premier_candidat` :
    un nombre de chiffres énoncé dans la règle, sinon `minlength`, sinon 8 — assez pour la
    plupart des identifiants, et rogné par `maxlength` s'il existe.
    """
    contraintes = champ.get("contraintes") or {}
    unite = _char_pour_classe(classe.strip("\\")) if classe.startswith("[") \
        else _ECHAPPE.get(classe.lstrip("\\"), "1")
    longueur = (_n_chiffres_depuis_regle(contraintes.get("regle_lisible") or "")
                or _borne_num(contraintes.get("minlength")) or 8)
    maxlen = _borne_num(contraintes.get("maxlength"))
    if maxlen is not None:
        longueur = min(longueur, maxlen)
    return unite * max(1, int(longueur))


def _variantes(base: str, champ: dict):
    """Des valeurs ALTERNATIVES à `base`, toujours conformes aux contraintes connues.

    On ne « bruite » pas au hasard : on fait varier le remplissage en gardant la forme. Pour un
    `pattern`, on incrémente le chiffre de bourrage (`1111111` → `2222222`) puis on re-vérifie par
    `re.fullmatch` — exactement ce que fait déjà `valeur_pour_motif`. Une variante qui ne passe
    pas la vérification n'est pas proposée : mieux vaut renoncer que produire un faux.
    """
    contraintes = champ.get("contraintes") or {}
    motif = contraintes.get("pattern") or ""
    for n in range(2, _MAX_VARIANTES + 1):
        if motif:
            candidat = re.sub(r"\d", str(n % 10), base)
            if candidat != base and re.fullmatch(motif, candidat):
                yield candidat
            continue
        suffixe = str(n)
        maxlen = _borne_num(contraintes.get("maxlength"))
        candidat = base + suffixe
        if maxlen is not None and len(candidat) > maxlen:
            candidat = base[:max(0, int(maxlen) - len(suffixe))] + suffixe
        if candidat != base:
            yield candidat


# ── Le point d'entrée ────────────────────────────────────────────────────────

def valeur_pour(champ: dict) -> str:
    """Une valeur DÉTERMINISTE garantie recevable par `champ`, ou `ValeurNonSynthetisable`.

    ⚠️ **Sans règle apprise, le comportement est INCHANGÉ** : le premier candidat proposé est
    exactement la valeur que ce module produisait avant (`_premier_candidat`). L'apprentissage ne
    fait que **retirer** des possibilités déjà réfutées par l'application — il n'en invente aucune.

    `champ` peut porter deux clés supplémentaires, posées par `regles_apprises.fusionner` :
    `valeurs_interdites` (des valeurs que l'application a REFUSÉES pour de vrai) et
    `contraintes.classe_conservee` (la classe qu'un filtre JavaScript laisse passer).
    """
    interdites = {str(v) for v in (champ.get("valeurs_interdites") or ())}

    # ⚠️ **Un champ à OPTIONS RÉELLES est traité à part, et c'est `0019` qui l'impose** : on ne
    # produit JAMAIS une valeur qui ne figure pas dans la liste. Une règle apprise peut écarter
    # une option refusée — elle ne peut pas en inventer une. Sans cette borne, une classe apprise
    # (`\d`) faisait proposer « 11111111 » sur un `<select>` : exactement la valeur inventée que
    # `0019` a corrigée. (Trouvé par le test de garde, pas à la relecture.)
    options = [str(o) for o in (champ.get("options") or []) if str(o).strip()]
    if options:
        for option in options:
            if option not in interdites:
                return option
        raise ValeurNonSynthetisable(
            f"champ {champ.get('name')!r} : TOUTES les options réelles ({len(options)}) ont été "
            f"refusées par l'application. On n'en invente pas — cas à instruire.")

    classe = ((champ.get("contraintes") or {}).get("classe_conservee")
              or _classe_depuis_regle((champ.get("contraintes") or {}).get("regle_lisible") or ""))

    base = _premier_candidat(champ)
    # Une classe apprise (filtre JS, ou règle en français) que le candidat historique ne respecte
    # pas : on ne se contente pas de le REFUSER, on PRODUIT une valeur conforme. C'est le cas
    # `tva_intracommunautaire` — aucune contrainte HTML, le repli texte donnait « TestPilot », et
    # le navigateur le refusait à chaque rejeu.
    if classe and not _respecte(classe, base):
        base = _valeur_pour_classe(classe, champ)

    for candidat in (base, *_variantes(base, champ)):
        if candidat in interdites:
            continue
        if classe and not _respecte(classe, candidat):
            continue
        return candidat

    raise ValeurNonSynthetisable(
        f"champ {champ.get('name')!r} : toutes les valeurs déterministes que je sais produire ont "
        f"déjà été REFUSÉES par l'application (ou violent une règle apprise à l'exécution). "
        f"Une contrainte nous échappe encore — cas à instruire, pas un défaut applicatif.")


def _premier_candidat(champ: dict) -> str:
    """La valeur historique de ce module — inchangée, et rendue en premier.

    Ordre de décision, du signal le plus fort au plus faible :
    options réelles → motif `pattern` → indice de la règle lisible → type (number/date/email/tel/
    fichier) → IBAN → longueur → repli texte générique.
    """
    contraintes = champ.get("contraintes") or {}
    typ = (champ.get("type") or "").lower()
    tag = (champ.get("tag") or "").lower()
    regle = contraintes.get("regle_lisible") or ""

    # 1. Une liste d'options : on n'INVENTE jamais une valeur (leçon 0019). La 1ʳᵉ option réelle.
    options = [o for o in (champ.get("options") or []) if str(o).strip()]
    if options:
        return str(options[0])

    # 1bis. Un `<select>` SANS option sélectionnable (liste vide, ou peuplée en JavaScript après
    # le crawl) : on ne peut rien y mettre de valide. On le DIT, au lieu d'inventer « TestPilot »
    # qui déclenchait une `InvalidOptionValueError` trompeuse (mesuré au rejeu 2026-07-23, `agence`).
    if tag == "select":
        raise ValeurNonSynthetisable(
            f"select sans option sélectionnable (champ {champ.get('name')!r}) — liste vide ou "
            "peuplée dynamiquement : rien de déterministe à y mettre")

    # 2. Un champ fichier : la valeur est un NOM de fichier (le résolveur téléverse via attach_file).
    if typ == "file":
        return "piece-jointe.pdf"

    # 2bis. Une case à cocher requise se COCHE (« oui » → `fill_field` la coche). Mesuré sur
    # `/sinistre_client` (cas 52) : `info_sinistre_ids` est une case obligatoire ; toute autre
    # valeur la DÉcocherait, et la soumission resterait bloquée.
    if typ == "checkbox":
        return "oui"

    # 3. Le motif exact : le signal le plus fiable. `\d{7}` → « 1234567 ».
    if contraintes.get("pattern"):
        return valeur_pour_motif(contraintes["pattern"])

    # 4. Pas de motif, mais la règle lisible dit un nombre de chiffres (règle souvent JS).
    n = _n_chiffres_depuis_regle(regle)
    if n:
        return "1" * n

    # 5. IBAN : reconnu à la règle, produit avec un checksum valide.
    if "iban" in regle.lower():
        return _IBAN_FR_VALIDE

    # 6. Nombre : un montant positif qui respecte `min` et le pas décimal.
    if typ == "number" or tag == "number":
        mini = _borne_num(contraintes.get("min"))
        base = max(10.0, mini if mini is not None else 0.0)
        pas = str(contraintes.get("step") or "")
        return f"{base:.2f}" if "." in pas else str(int(base))

    # 7. Date : format ISO, dans la direction imposée par la règle (défaut = aujourd'hui).
    if typ == "date":
        if any(mot in regle.lower() for mot in _DATE_FUTUR):
            return (date.today() + timedelta(days=30)).isoformat()
        return date.today().isoformat()

    # 8. Types HTML dédiés.
    if typ == "email":
        return "test@example.com"
    if typ == "tel":
        return "+33123456789"

    # 9. Longueur : un texte alphanumérique borné par min/maxlength.
    maxlen = _borne_num(contraintes.get("maxlength"))
    minlen = _borne_num(contraintes.get("minlength"))
    texte = "TestPilot"
    if minlen is not None and len(texte) < minlen:
        texte = (texte + "0" * int(minlen))[:int(minlen)]
    if maxlen is not None and len(texte) > maxlen:
        texte = texte[:int(maxlen)]
    return texte
