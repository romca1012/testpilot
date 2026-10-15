"""« Qu'attend-on ? » — ce que le PROJET déclare de l'écriture de ses valeurs (lot PT-03, décisions A8 et A24).

Réglages déclarés par une personne dans l'onglet « Valeurs attendues » des paramètres de test, jamais par l'agent. Aucune
base toute faite (A38, porteur, 2026-10-15) : l'outil ne propose pas de monnaie du projet — une valeur attendue sans unité
face à un montant affiché ne conclut pas (A24).

- l'ÉCRITURE DES NOMBRES de l'application (« 1 234,56 », « 1,234.56 » ou « 1.234,56 ») : elle tranche une valeur
  AFFICHÉE que l'outil refuse de deviner (« 1,234 »), pour les séparateurs qu'elle nomme et eux seuls. Vide = rien de
  déclaré : une écriture ambiguë reste non concluante.

Sans réglage, rien ne change (règle R1 du plan). Module pur : aucune I/O.
"""
from __future__ import annotations

# Transmises au sous-processus Behave. DUPLIQUÉES dans `behave_runtime/steps_library/_base_helpers.py` (le harnais ne dépend
# pas de ce paquet) — test d'accord : `tests/test_valeurs_du_projet.py`.
ENV_FORMAT_NOMBRE = "TESTPILOT_PROJET_FORMAT_NOMBRE"
# Ces variables viennent du PROJET ou de personne. Le sous-processus hérite de l'environnement du serveur et relit le
# fichier `.env` : une variable absente y prendrait la valeur qui s'y trouverait, et l'écriture des nombres d'un projet qui
# n'a rien déclaré serait décidée par l'installation, sans son administrateur (revue du 2026-10-13). Le lanceur
# (`BehaveRunner._subprocess_env`) les pose donc VIDES quand le projet ne les fournit pas.
# Les unités AJOUTÉES par le projet (« palette », avec ses autres écritures « palettes », « Palettes ») : une liste JSON
# `[{"nom": …, "ecritures": […]}]`, lue par le constat « le nombre affiché … vaut … » pour reconnaître la même unité sous
# plusieurs écritures. Aucune conversion.
ENV_UNITES = "TESTPILOT_PROJET_UNITES"
JAMAIS_HERITEES = (ENV_FORMAT_NOMBRE, ENV_UNITES)

# Clé enregistrée (séparateur de milliers, puis séparateur décimal) -> ce que l'écran montre : un EXEMPLE d'écriture, plus
# parlant qu'un nom. Énumération FERMÉE : contrainte `ck_project_format_nombre` (migration 62).
LIBELLES_FORMAT_NOMBRE = {"espace_virgule": "1 234,56", "virgule_point": "1,234.56", "point_virgule": "1.234,56"}

def normaliser_format(format_nombre: str | None) -> str:
    return (format_nombre or "").strip().lower()


def erreurs(format_nombre: str | None) -> list[str]:
    """Pourquoi cette valeur serait refusée (liste vide = acceptée). Vide est toujours accepté : rien de déclaré."""
    refus = []
    if normaliser_format(format_nombre) and normaliser_format(format_nombre) not in LIBELLES_FORMAT_NOMBRE:
        refus.append(f"écriture des nombres inconnue : « {format_nombre} »")
    return refus


def env(project: dict | None) -> dict[str, str]:
    """Les variables de connexion d'un projet pour le sous-processus Behave : seul ce qui est DÉCLARÉ et valide y figure
    (une valeur enregistrée mais inconnue — base éditée à la main — n'en fait pas partie). Ce que le projet ne déclare pas
    n'est pas pour autant laissé au hasard : voir `JAMAIS_HERITEES`."""
    p = project or {}
    variables = {}
    format_nombre = normaliser_format(p.get("format_nombre"))
    if format_nombre in LIBELLES_FORMAT_NOMBRE:
        variables[ENV_FORMAT_NOMBRE] = format_nombre
    return variables


def referentiel() -> dict:
    """Ce que l'écran propose : les écritures de nombres, avec leur libellé."""
    return {"formats_nombre": [{"cle": cle, "libelle": libelle} for cle, libelle in LIBELLES_FORMAT_NOMBRE.items()]}


def env_des_unites(unites: list[dict] | None) -> dict[str, str]:
    """La variable transmise au sous-processus pour les unités ajoutées du projet. Aucune unité = aucune variable (le
    lanceur la pose alors vide, `JAMAIS_HERITEES`)."""
    import json

    declarees = [{"nom": u["nom"], "ecritures": list(u.get("ecritures") or [])} for u in (unites or [])]
    return {ENV_UNITES: json.dumps(declarees, ensure_ascii=False)} if declarees else {}
