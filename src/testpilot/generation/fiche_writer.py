"""L'IA PROPOSE la fiche de calcul d'un cas où un calcul a été détecté (étape 7, décisions A108 et A110 du porteur).

Un appel de plus, seulement pour ces cas (§9 : mesuré à l'étape 8). La proposition est présentée sur l'écran de validation ;
elle n'est jamais utilisée sans le choix d'une personne, qui la complète si besoin (dates des taux, exemple chiffré).

Ce que l'IA fait : comprendre ce qui est testé — l'inventaire des éléments qui influencent le résultat, chacun avec sa source
dans la spécification — puis écrire les étapes du calcul avec les seules opérations du calculateur. Ce qu'elle ne fait
jamais : calculer une valeur, dater un taux, inventer un exemple que la spécification ne donne pas (un exemple calculé avec
sa propre formule ne prouverait rien). Ces manques sont dits dans `a_confirmer`.

La réponse est normalisée puis relue par `parametres/calcul.valider_fiche(..., proposition=True)` : une proposition mal
formée est écartée, jamais réparée par devinette.
"""

from __future__ import annotations

import logging

from testpilot.parametres import calcul

logger = logging.getLogger(__name__)

FICHES_PROPOSEES_MAX = 5

_SYSTEM = ("Tu prépares des fiches de calcul pour un outil de test. Tu ne calcules JAMAIS une valeur toi-même : tu décris "
           "le calcul, le programme le fera. Tu réponds en français.")

_TEXTE = {"type": "string"}
_ETAPE = {
    "type": "object",
    "properties": {
        "resultat": _TEXTE,
        "operation": {"type": "string", "enum": list(calcul.OPERATIONS)},
        "termes": {"type": "array", "items": _TEXTE},
        "valeur": _TEXTE, "par": _TEXTE, "de": _TEXTE, "taux": _TEXTE, "limite": _TEXTE,
        "decimales": {"type": "integer"}, "mode": _TEXTE,
        "tranches": {"type": "array", "items": {"type": "object", "properties": {"jusqu_a": _TEXTE, "taux": _TEXTE},
                                                "required": ["jusqu_a", "taux"], "additionalProperties": False}},
        "gauche": _TEXTE, "comparateur": _TEXTE, "droite": _TEXTE, "alors": _TEXTE, "sinon": _TEXTE,
    },
    "required": ["resultat", "operation", "termes", "valeur", "par", "de", "taux", "limite", "decimales", "mode",
                 "tranches", "gauche", "comparateur", "droite", "alors", "sinon"],
    "additionalProperties": False,
}
_FICHE = {
    "type": "object",
    "properties": {
        "nom": _TEXTE, "resultat": _TEXTE, "unite": _TEXTE,
        "elements": {"type": "array", "items": {
            "type": "object",
            "properties": {"nom": _TEXTE, "valeur": _TEXTE, "source": _TEXTE},
            "required": ["nom", "valeur", "source"], "additionalProperties": False}},
        "etapes": {"type": "array", "items": _ETAPE},
        "exemples": {"type": "array", "items": {
            "type": "object",
            "properties": {"entrees": {"type": "array", "items": {
                "type": "object", "properties": {"nom": _TEXTE, "valeur": _TEXTE},
                "required": ["nom", "valeur"], "additionalProperties": False}},
                "attendu": _TEXTE},
            "required": ["entrees", "attendu"], "additionalProperties": False}},
        "a_confirmer": {"type": "array", "items": _TEXTE},
    },
    "required": ["nom", "resultat", "unite", "elements", "etapes", "exemples", "a_confirmer"],
    "additionalProperties": False,
}
_SCHEMA = {"type": "object", "properties": {"calculs": {"type": "array", "items": _FICHE}},
           "required": ["calculs"], "additionalProperties": False}


def _consigne(variables: list[dict] | None) -> str:
    noms = ", ".join("{{" + str(v.get("nom")) + "}}" for v in variables or []) or "aucune"
    return (
        "Pour le cas ci-dessous, prépare la fiche de chaque valeur CALCULÉE que son résultat attendu vérifie.\n"
        "1. Comprends ce qui est testé : liste TOUS les éléments qui influencent le résultat (quantités, prix, remises, "
        "taxes, devise, arrondis, seuils, tranches, dates, type de client…). Pour chacun, « source » cite la phrase de la "
        "spécification d'où il vient. Un élément dont la spécification ne dit rien : liste-le quand même, source « à "
        "fournir », et dis-le dans « a_confirmer ».\n"
        f"2. Une ENTRÉE (valeur différente d'un test à l'autre) a « valeur » vide et le NOM EXACT d'une donnée de test du "
        f"projet ({noms}). Une CONSTANTE (un taux, un plafond) a sa « valeur » telle que la spécification la donne.\n"
        "3. Les étapes n'emploient que ces opérations : " + ", ".join(calcul.OPERATIONS) + ". Un terme est le nom d'un "
        "élément, celui d'une étape précédente, ou un nombre. Les champs d'une étape qui ne servent pas restent vides "
        "(\"\", [], 0). Un arrondi dit son mode (" + ", ".join(calcul.MODES_ARRONDI) + ") ; si la spécification ne le "
        "précise pas, choisis au_plus_proche aux décimales de la devise et écris-le dans « a_confirmer ». Un calcul qui divise se "
        "termine TOUJOURS par un arrondi. Un barème dit "
        "s'il est progressif ou par_palier. Une condition : gauche, comparateur (" + " ".join(calcul.COMPARATEURS) + "), "
        "droite, alors, sinon.\n"
        "4. « exemples » : SEULEMENT les exemples chiffrés écrits dans la spécification (entrées et résultat attendu). "
        "N'en invente aucun ; s'il n'y en a pas, liste vide et « exemple chiffré à fournir » dans « a_confirmer ».\n"
        "5. Ne date jamais un taux : une personne le vérifiera. Noms en minuscules, chiffres et _ (taux_tva).")


def _normaliser(brute: dict) -> dict:
    """La réponse structurée → la forme du calculateur : champs vides retirés, condition regroupée, entrées en objet."""
    etapes = []
    for e in brute.get("etapes") or []:
        etape = {k: v for k, v in e.items() if v not in ("", [], None) and k not in ("gauche", "comparateur", "droite")}
        if e.get("operation") == "si":
            etape["condition"] = {"gauche": e.get("gauche"), "comparateur": e.get("comparateur"), "droite": e.get("droite")}
        if e.get("operation") == "arrondir":
            etape["decimales"] = e.get("decimales", 0)
        else:
            etape.pop("decimales", None)
        if e.get("operation") == "bareme":
            etape["tranches"] = [{"jusqu_a": t.get("jusqu_a") or None, "taux": t.get("taux")} for t in e.get("tranches") or []]
        etapes.append(etape)
    return {"nom": brute.get("nom"), "resultat": brute.get("resultat"), "unite": brute.get("unite"),
            "elements": [{k: v for k, v in el.items() if v not in ("", None)} for el in brute.get("elements") or []],
            "etapes": etapes,
            "exemples": [{"entrees": {x.get("nom"): x.get("valeur") for x in ex.get("entrees") or []},
                          "attendu": ex.get("attendu")} for ex in brute.get("exemples") or []],
            "a_confirmer": brute.get("a_confirmer") or []}


def proposer_les_fiches(llm, *, specification: str, cas: dict, raison: str, variables: list[dict] | None,
                        cost_tracker=None, model: str = "") -> list[dict]:
    """Les fiches proposées pour CE cas, normalisées (`valider_fiche(..., proposition=True)`) ; une proposition mal formée est
    écartée et journalisée. Ne persiste rien."""
    from testpilot import config

    contenu = (f"## Le cas\nTitre : {cas.get('title', '')}\nPréconditions : {cas.get('preconditions', '')}\nÉtapes :\n"
               + "\n".join(f"- {s}" for s in cas.get("steps") or [])
               + f"\nRésultat attendu : {cas.get('expected_result', '')}\nPourquoi un calcul : {raison}")
    reponse = llm.call_json(system_prompt=_SYSTEM, cached_prefix=f"## Spécification\n{specification}\n\n{_consigne(variables)}",
                            user_content=contenu, schema=_SCHEMA, model=model or config.MODEL_FAST, max_tokens=4000,
                            cost_tracker=cost_tracker, label="fiche_de_calcul") or {}
    fiches = []
    for brute in (reponse.get("calculs") or [])[:FICHES_PROPOSEES_MAX]:
        try:
            fiches.append(calcul.valider_fiche(_normaliser(brute), proposition=True))
        except (calcul.FicheInvalide, AttributeError, TypeError) as exc:
            logger.warning("[fiche] proposition écartée pour « %s » : %s", cas.get("title", ""), exc)
    return fiches
