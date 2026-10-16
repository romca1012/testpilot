"""Décisions A43 et A45 (porteur, 2026-10-16) — l'IA peut-elle ÉCRIRE dans l'application de ce projet pendant la génération ?

A43 : « L'IA peut agir sur cette application » (`project.calibration_writes_enabled`) est coché par défaut, partout.
A45 (revue d'A43, bloquant) : la protection de la production n'agit que pour toute l'installation (`ODOO_ENV=prod`),
jamais projet par projet. Un projet Odoo peut viser une vraie base de production sans que rien ne le dise : pour lui, la
case seule ne suffit plus, il faut AUSSI qu'il se déclare « instance de test » (`project.instance_de_test`, éteint par
défaut). Le web garde sa propre seconde condition, déjà en place : aucun essai sans adresse de remise à zéro (D26,
`generation/tools/essai.construire`), et son connecteur refuse toute soumission de formulaire.

A47 : la déclaration vaut pour UNE application — changer le connecteur, l'adresse ou la base la retire
(`api/routes/projects.update_project`).

Un connecteur inconnu (ou vide) est traité comme Odoo : la règle la plus stricte, jamais la plus permissive.
Pur : lit le dictionnaire du projet, aucune I/O.
"""

from __future__ import annotations


def ia_peut_ecrire(projet: dict | None) -> bool:
    """Vrai seulement si le projet autorise l'IA à agir ET, hors web, se déclare instance de test."""
    projet = projet or {}
    if not projet.get("calibration_writes_enabled"):
        return False
    if (projet.get("connector_type") or "").strip().lower() == "web":
        return True
    return bool(projet.get("instance_de_test"))
