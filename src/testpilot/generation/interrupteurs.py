"""Interrupteurs d'environnement du chantier « qualité des agents » (lot Q3-a).

⚠️ **Pourquoi des interrupteurs.** Tout ce qui change ce que l'API Anthropic REÇOIT (définitions
d'outils, prompt système) change le comportement de l'agent, donc doit pouvoir être MESURÉ avant
d'être activé (docs/SOURCES-DE-REFERENCE-AGENTS.md §4.3, banc du lot Q2). Chaque interrupteur est :

- **désactivé par défaut** : sans variable, ce que l'API reçoit est strictement identique, octet
  pour octet, à ce qui était envoyé avant Q3-a (garde : `tests/test_tools_strict_q3a.py`) ;
  Exception, décision A46 (porteur, 2026-10-16, après les mesures M1 et ciblée) : la génération avec
  données de test (`TESTPILOT_VARIABLES_DE_TEST`, `TESTPILOT_CAS_DIT_SES_DONNEES`) est ALLUMÉE par
  défaut — un `0` (ou `false`, `non`, `off`) explicite l'éteint. Sans variables de test déclarées par
  le projet, ce que l'API reçoit reste identique à avant ;
- **lu à chaque appel** (jamais figé à l'import) : un banc peut comparer deux configurations dans
  le même processus, un test peut le basculer sans recharger de module.

Module PUR : aucune I/O hors lecture de `os.environ`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

ENV_TOOLS_STRICT = "TESTPILOT_TOOLS_STRICT"
ENV_PROMPT_HYPOTHESES = "TESTPILOT_PROMPT_HYPOTHESES"
ENV_TOOLS_DESCRIPTIONS_V2 = "TESTPILOT_TOOLS_DESCRIPTIONS_V2"
ENV_REGLES_CONNECTEUR = "TESTPILOT_REGLES_CONNECTEUR"
ENV_STEP_NOMBRE = "TESTPILOT_STEP_NOMBRE"
ENV_VARIABLES_DE_TEST = "TESTPILOT_VARIABLES_DE_TEST"
ENV_CAS_DIT_SES_DONNEES = "TESTPILOT_CAS_DIT_SES_DONNEES"
ENV_FORME_ORACLE = "TESTPILOT_FORME_ORACLE"
ENV_LIGNES_PROPOSEES = "TESTPILOT_LIGNES_PROPOSEES"
ENV_CONTROLE_FIN_ECRITURE = "TESTPILOT_CONTROLE_FIN_ECRITURE"
ENV_ESSAI_TOUS_CONNECTEURS = "TESTPILOT_ESSAI_TOUS_CONNECTEURS"
ENV_GENERATION_PAR_COMPTE = "TESTPILOT_GENERATION_PAR_COMPTE"
ENV_IA_INFORMEE = "TESTPILOT_IA_INFORMEE"

_VRAI = frozenset({"1", "true", "yes", "oui", "on"})
_ALLUMES_PAR_DEFAUT = frozenset({ENV_VARIABLES_DE_TEST, ENV_CAS_DIT_SES_DONNEES})
_FAUX = frozenset({"0", "false", "no", "non", "off"})


def _actif(nom: str, env: Mapping[str, str] | None) -> bool:
    source = os.environ if env is None else env
    return str(source.get(nom, "")).strip().lower() in _VRAI


def _allume_par_defaut(nom: str, env: Mapping[str, str] | None) -> bool:
    """A46 : absent ou vide = allumé ; seule une valeur d'extinction explicite l'éteint."""
    source = os.environ if env is None else env
    return str(source.get(nom, "")).strip().lower() not in _FAUX


def tools_strict_actif(env: Mapping[str, str] | None = None) -> bool:
    """Mode strict de l'API (`strict: true`) sur les outils critiques + `input_examples`."""
    return _actif(ENV_TOOLS_STRICT, env)


def prompt_hypotheses_actif(env: Mapping[str, str] | None = None) -> bool:
    """Phrase du PILIER 4 qui demande `hypotheses_non_verifiees` — et exposition du champ à l'API."""
    return _actif(ENV_PROMPT_HYPOTHESES, env)


def descriptions_v2_actif(env: Mapping[str, str] | None = None) -> bool:
    """Descriptions d'outils réécrites au standard Anthropic (quoi, quand, quand non, limites)."""
    return _actif(ENV_TOOLS_DESCRIPTIONS_V2, env)


def regles_connecteur_actif(env: Mapping[str, str] | None = None) -> bool:
    """Règles par connecteur (`Connector.rules()`) et section « comptes » dès le compte principal (lot Q3, D20)."""
    return _actif(ENV_REGLES_CONNECTEUR, env)


def variables_de_test_actif(env: Mapping[str, str] | None = None) -> bool:
    """Lot PT-02d : l'agent reçoit les NOMS des variables du projet et peut les écrire (`generation/variables_de_test.py`).
    Allumé par défaut (A46)."""
    return _allume_par_defaut(ENV_VARIABLES_DE_TEST, env)


def cas_dit_ses_donnees_actif(env: Mapping[str, str] | None = None) -> bool:
    """Lot PT-02f (étape E2, A39) : l'IA écrit `{{nom}}` dans le texte des cas qu'elle propose ; le test technique reprend
    EXACTEMENT les variables que le cas cite (`generation/variables_de_test.du_cas`). N'a d'effet qu'avec PT-02d allumé :
    sans lui l'agent technique ne voit aucune variable, et un cas citant `{{client}}` aurait un test qui ne l'emploie pas
    (revue du 2026-10-15, bloquant). Allumé par défaut (A46)."""
    return _allume_par_defaut(ENV_CAS_DIT_SES_DONNEES, env) and variables_de_test_actif(env)


def lignes_proposees_actif(env: Mapping[str, str] | None = None) -> bool:
    """IT-3c (A53, A58, A60) : l'IA qui rédige les cas propose les lignes d'un cas — ses classes de valeurs, valeurs limites
    comprises, et le résultat attendu de chacune — pour les seules variables DÉJÀ déclarées dans le projet ; une personne
    les relit et les valide avec le cas. N'a d'effet qu'avec PT-02f (les variables montrées à l'IA des cas). Éteint
    jusqu'à sa mesure."""
    return _actif(ENV_LIGNES_PROPOSEES, env) and cas_dit_ses_donnees_actif(env)


def forme_oracle_actif(env: Mapping[str, str] | None = None) -> bool:
    """Lot VH-08 (A51) : l'agent voit la FORME des réponses de l'oracle (relevée à l'exploration et à la fin de chaque essai),
    et une requête d'oracle non déclarée est refusée à l'écriture. Éteint jusqu'à la mesure M2."""
    return _actif(ENV_FORME_ORACLE, env)


def controle_fin_ecriture_actif(env: Mapping[str, str] | None = None) -> bool:
    """Étape 2 du plan unique (A61) : quand le test passe la vérification à blanc, ses points de vigilance (ceux qui ne
    dépendent que du test, `generation/avis_du_test.py`) sont renvoyés à l'IA, qui les corrige avant de rendre la main
    (deux fois au plus). Change ce que l'API reçoit (des tours en plus) : éteint jusqu'à sa mesure (étape 3)."""
    return _actif(ENV_CONTROLE_FIN_ECRITURE, env)


def essai_tous_connecteurs_actif(env: Mapping[str, str] | None = None) -> bool:
    """Étape 4 du plan unique (A71) : l'essai « exécuter puis écrire » (lot VH-07) aussi pour Odoo — avec les mêmes conditions
    (l'IA peut agir, instance de test déclarée, adresse de remise à zéro déclarée et prouvée). Change ce que l'API reçoit
    (un outil de plus) : éteint jusqu'à sa mesure (étape 8)."""
    return _actif(ENV_ESSAI_TOUS_CONNECTEURS, env)


def generation_par_compte_actif(env: Mapping[str, str] | None = None) -> bool:
    """Étape 4, morceau 7 (A85) : l'IA écrit le test avec les écrans du compte du cas (« Joué en tant que »), relevés par
    l'exploration de ce compte — au lieu de ceux du principal — et l'essai se joue avec lui. Change ce que l'API reçoit :
    éteint jusqu'à sa mesure (étape 8)."""
    return _actif(ENV_GENERATION_PAR_COMPTE, env)


def ia_informee_actif(env: Mapping[str, str] | None = None) -> bool:
    """Étape 5 du plan unique (AV-1, AV-2, AV-5) : l'IA reçoit le VRAI type d'application (un projet web n'est plus annoncé
    « odoo », à l'analyse comme à l'écriture), la langue de l'interface et le détail des pages que le cas vise (tous leurs
    champs, boutons et liens relevés par l'exploration). Change ce que l'API reçoit : éteint jusqu'à sa mesure."""
    return _actif(ENV_IA_INFORMEE, env)


def allume(nom: str, env: Mapping[str, str] | None = None) -> bool:
    """L'interrupteur `nom` est-il allumé ? Pour un step marqué `@derriere_interrupteur("<nom>")` dans la bibliothèque.
    Même lecture que les fonctions dédiées : les interrupteurs allumés par défaut (A46) le sont ici aussi."""
    if nom in _ALLUMES_PAR_DEFAUT:
        return _allume_par_defaut(nom, env)
    return _actif(nom, env)
