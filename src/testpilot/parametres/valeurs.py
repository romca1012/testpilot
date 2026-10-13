"""« Qu'attend-on ? » — ce que le PROJET déclare de l'écriture de ses valeurs (lot PT-03, décisions A8 et A24).

Deux réglages, déclarés par une personne dans l'onglet « Valeurs attendues » des paramètres de test, jamais par l'agent :

- la MONNAIE du projet (code ISO 4217) : quand un test attend « 129,51 » sans unité et que l'écran affiche un montant, la
  valeur attendue est lue dans cette monnaie (A24). Vide = rien de déclaré : le constat ne conclut pas ;
- l'ÉCRITURE DES NOMBRES de l'application (« 1 234,56 », « 1,234.56 » ou « 1.234,56 ») : elle tranche une valeur
  AFFICHÉE que l'outil refuse de deviner (« 1,234 »), pour les séparateurs qu'elle nomme et eux seuls. Vide = rien de
  déclaré : une écriture ambiguë reste non concluante.

Sans réglage, rien ne change (règle R1 du plan). Module pur : aucune I/O.
"""
from __future__ import annotations

# Transmises au sous-processus Behave. DUPLIQUÉES dans `behave_runtime/steps_library/_base_helpers.py` (le harnais ne dépend
# pas de ce paquet) — test d'accord : `tests/test_valeurs_du_projet.py`.
ENV_DEVISE = "TESTPILOT_PROJET_DEVISE"
ENV_FORMAT_NOMBRE = "TESTPILOT_PROJET_FORMAT_NOMBRE"
# Ces variables viennent du PROJET ou de personne. Le sous-processus hérite de l'environnement du serveur et relit le
# fichier `.env` : une variable absente y prendrait la valeur qui s'y trouverait, et la monnaie d'un projet qui n'a rien
# déclaré serait décidée par l'installation, sans son administrateur (revue du 2026-10-13). Le lanceur
# (`BehaveRunner._subprocess_env`) les pose donc VIDES quand le projet ne les fournit pas.
# Les unités AJOUTÉES par le projet (« palette », avec ses autres écritures « palettes », « Palettes ») : une liste JSON
# `[{"nom": …, "ecritures": […]}]`, lue par le constat « le nombre affiché … vaut … » pour reconnaître la même unité sous
# plusieurs écritures. Aucune conversion.
ENV_UNITES = "TESTPILOT_PROJET_UNITES"
JAMAIS_HERITEES = (ENV_DEVISE, ENV_FORMAT_NOMBRE, ENV_UNITES)

# Clé enregistrée (séparateur de milliers, puis séparateur décimal) -> ce que l'écran montre : un EXEMPLE d'écriture, plus
# parlant qu'un nom. Énumération FERMÉE : contrainte `ck_project_format_nombre` (migration 62).
LIBELLES_FORMAT_NOMBRE = {"espace_virgule": "1 234,56", "virgule_point": "1,234.56", "point_virgule": "1.234,56"}

# Codes ISO 4217 en circulation — DUPLIQUÉS de `behave_runtime/steps_library/_lecture_nombre.py::_CODES_ISO` (même test
# d'accord) : une monnaie que le lecteur ne sait pas reconnaître à l'écran ne peut pas être déclarée par un projet.
CODES_DEVISE = frozenset("""
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC
    CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR
    ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK
    MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE
    SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VED VES VND VUV WST XAF XCD XCG XOF
    XPF YER ZAR ZMW ZWG
""".split())


def normaliser_devise(devise: str | None) -> str:
    return (devise or "").strip().upper()


def normaliser_format(format_nombre: str | None) -> str:
    return (format_nombre or "").strip().lower()


def erreurs(devise: str | None, format_nombre: str | None) -> list[str]:
    """Pourquoi ces deux valeurs seraient refusées (liste vide = acceptées). Vide est toujours accepté : rien de déclaré."""
    refus = []
    if normaliser_devise(devise) and normaliser_devise(devise) not in CODES_DEVISE:
        refus.append(f"monnaie inconnue : « {devise} » (un code à trois lettres est attendu, par exemple EUR)")
    if normaliser_format(format_nombre) and normaliser_format(format_nombre) not in LIBELLES_FORMAT_NOMBRE:
        refus.append(f"écriture des nombres inconnue : « {format_nombre} »")
    return refus


def env(project: dict | None) -> dict[str, str]:
    """Les variables de connexion d'un projet pour le sous-processus Behave : seul ce qui est DÉCLARÉ et valide y figure
    (une valeur enregistrée mais inconnue — base éditée à la main — n'en fait pas partie). Ce que le projet ne déclare pas
    n'est pas pour autant laissé au hasard : voir `JAMAIS_HERITEES`."""
    p = project or {}
    variables = {}
    devise, format_nombre = normaliser_devise(p.get("devise")), normaliser_format(p.get("format_nombre"))
    if devise in CODES_DEVISE:
        variables[ENV_DEVISE] = devise
    if format_nombre in LIBELLES_FORMAT_NOMBRE:
        variables[ENV_FORMAT_NOMBRE] = format_nombre
    return variables


def referentiel() -> dict:
    """Ce que l'écran propose : les monnaies déclarables et les écritures de nombres, avec leur libellé."""
    return {"devises": sorted(CODES_DEVISE),
            "formats_nombre": [{"cle": cle, "libelle": libelle} for cle, libelle in LIBELLES_FORMAT_NOMBRE.items()]}


def env_des_unites(unites: list[dict] | None) -> dict[str, str]:
    """La variable transmise au sous-processus pour les unités ajoutées du projet. Aucune unité = aucune variable (le
    lanceur la pose alors vide, `JAMAIS_HERITEES`)."""
    import json

    declarees = [{"nom": u["nom"], "ecritures": list(u.get("ecritures") or [])} for u in (unites or [])]
    return {ENV_UNITES: json.dumps(declarees, ensure_ascii=False)} if declarees else {}
