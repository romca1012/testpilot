"""Ce que ce cas a DÉJÀ appris — pour que la boucle cesse de racheter les mêmes correctifs.

⚠️ **Le défaut que ça ferme** (`0018`, volet non soldé). `0018` a corrigé l'**adoption** d'une
version : le progrès partiel n'est plus jeté. Mais la **connaissance**, elle, se perdait toujours.
Chaque tentative reconstruisait son prompt de zéro — catalogue complet, fichier de steps entier —
sans rien savoir de ce que les tentatives précédentes avaient déjà établi, ni dans la même
session, ni entre deux rejeux. La base portait pourtant tout : `repair_attempt` a la signature
d'échec, la cause et l'issue de chaque tentative depuis toujours. **Personne ne la relisait.**

Ce module ne crée aucune table et ne mesure rien de neuf : il **agrège ce qui existe** et le rend
lisible par l'agent.

⚠️ **Faits RUNTIME seulement — jamais la prose de l'agent** (arbitrage du porteur, 2026-08-03).
`repair_attempt.what_was_tried` et `test_case_version.change_summary` sont des textes écrits par
le LLM. `repair_agent._failure_report` porte déjà la doctrine inverse dans sa docstring : *« on ne
lui souffle pas de diagnostic … lui transmettre sa propre conclusion l'enfermerait dans une piste
qui peut être fausse — le cas 6 l'a montré »*. Réinjecter sa prose passée ancrerait cette piste
fausse **à travers les sessions**, ce qui est pire que dans une seule. Ces colonnes restent
destinées à l'humain.

⚠️ **Cette section va dans le MESSAGE UTILISATEUR, jamais dans le prompt système.**
`build_repair_prompt` est aujourd'hui identique pour tous les cas : son bloc `cache_control` est
donc partagé entre tous les cas et toutes les tentatives. Y injecter une mémoire par cas rendrait
chaque prompt système unique et **détruirait le cache pour tout le monde** — bien plus cher que ce
que la mémoire fait économiser. Un test verrouille cette propriété.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Plafonds. Chaque section de prompt est payée à CHAQUE tour de la boucle ReAct : la discipline
# de taille est la même que celle de `prompt._MAX_ROUTES`. Au-delà, on garde les plus RÉCENTS.
_MAX_REGLES = 12
_MAX_TENTATIVES = 4
_MAX_CARACTERES = 1600


@dataclass(frozen=True)
class FaitDeReparation:
    """Une tentative passée, décrite par ses SIGNAUX — jamais par ce que l'agent en a dit."""

    version_id: int
    signature: str          # `failure_signature` — dérivée du runtime (cf. repair_circuit)
    cause: str              # `cause_category`
    origine: str            # `defect_origin`
    quand: str


def _fait(ligne: dict) -> FaitDeReparation:
    return FaitDeReparation(
        version_id=int(ligne.get("version_id") or 0),
        signature=str(ligne.get("failure_signature") or ""),
        cause=str(ligne.get("cause_category") or ""),
        origine=str(ligne.get("defect_origin") or ""),
        quand=str(ligne.get("created_at") or "")[:10],
    )


def collecter(conn, *, case_id: int, project_id: int | None, routes=()):
    """Les règles apprises pertinentes + l'historique de réparation du cas.

    Best-effort de bout en bout : une mémoire indisponible ne doit **jamais** empêcher une
    réparation de se lancer. On préfère un agent moins informé qu'un cas bloqué.
    """
    from testpilot.generation import regles_apprises as ra
    from testpilot.store.repositories import RepairRepo

    try:
        regles = ra.charger(project_id)
    except Exception:
        logger.warning("[mémoire] règles apprises illisibles — on continue sans", exc_info=True)
        regles = []

    if routes:
        from testpilot.generation import domain_model
        pertinentes = [r for r in regles
                       if any(domain_model._meme_route(r.route, str(u))
                              or domain_model._meme_route(str(u), r.route) for u in routes)]
        # Un filtre qui ne garde RIEN est probablement un filtre trop strict (les routes du
        # scénario ne sont pas toujours celles du refus) : on retombe sur tout plutôt que de
        # taire une règle utile.
        regles = pertinentes or regles

    try:
        faits = [_fait(l) for l in RepairRepo(conn).historique_pour_cas(case_id)]
    except Exception:
        logger.warning("[mémoire] historique de réparation illisible — on continue sans",
                       exc_info=True)
        faits = []

    return regles[-_MAX_REGLES:], faits[:_MAX_TENTATIVES]


def _section_refus(regles) -> list[str]:
    if not regles:
        return []
    lignes = ["### Valeurs que l'application a REFUSÉES (faits mesurés, pas des suppositions)"]
    for r in regles:
        if r.type_contrainte == "valueMissing":
            continue    # traité à part : ce n'est pas une valeur refusée, c'est une exigence
        detail = f" ({r.type_contrainte}"
        detail += f", `{r.valeur_contrainte}`)" if r.valeur_contrainte else ")"
        vu = f" — vu {r.occurrences}×" if r.occurrences > 1 else ""
        lignes.append(f"- `{r.route}` · `{r.champ}` : {r.valeur_refusee!r} refusée{detail}{vu}"
                      + (f" — « {r.preuve} »" if r.preuve else ""))
    if len(lignes) == 1:
        return []
    lignes.append("→ Le résolveur ne reproduira plus ces valeurs. N'en écris pas non plus.")
    return lignes + [""]


def _section_obligatoires(regles) -> list[str]:
    manquants = sorted({(r.route, r.champ) for r in regles
                        if r.type_contrainte == "valueMissing"})
    if not manquants:
        return []
    lignes = ["### Champs devenus OBLIGATOIRES à la soumission (absents du crawl)"]
    lignes += [f"- `{route}` · `{champ}`" for route, champ in manquants]
    lignes.append("→ Un choix fait plus haut les rend requis. N'en conclus pas que l'annuaire "
                  "est faux.")
    return lignes + [""]


def _section_tentatives(faits) -> list[str]:
    if not faits:
        return []
    lignes = [f"### Tentatives précédentes sur ce cas ({len(faits)})"]
    for f in faits:
        lignes.append(f"- v{f.version_id} ({f.quand}) : `{f.signature}` → {f.origine or 'inconnu'}")

    # ⚠️ L'information la PLUS utile du bloc, et elle est intégralement dérivée du runtime : une
    # signature qui se répète prouve que ce qui a été tenté n'a RIEN changé au signal d'échec.
    signatures = [f.signature for f in faits if f.signature]
    repetee = next((s for s in signatures if signatures.count(s) > 1), "")
    if repetee:
        lignes.append(f"⚠️ La signature `{repetee}` s'est répétée {signatures.count(repetee)}× : "
                      f"ce qui a été tenté ces fois-là n'a rien changé au signal d'échec. "
                      f"Change d'angle.")
    return lignes + [""]


def as_prompt_section(regles, faits) -> str:
    """La mémoire, rendue pour l'agent. `''` quand il n'y a rien à dire — donc coût nul.

    Plafonnée en dur : une mémoire qui grossit sans limite finirait par coûter plus cher que les
    redécouvertes qu'elle évite.
    """
    corps = _section_refus(regles) + _section_obligatoires(regles) + _section_tentatives(faits)
    if not corps:
        return ""
    texte = "\n".join(["## Ce qui a DÉJÀ été mesuré sur ce cas — ne le redécouvre pas", ""] + corps)
    if len(texte) > _MAX_CARACTERES:
        texte = texte[:_MAX_CARACTERES].rstrip() + "\n… (mémoire tronquée)"
    return texte.rstrip()
