"""Sauvegarde AUTOMATIQUE de la base, déclenchée AVANT toute migration qui va réellement écrire.

⚠️ **Ce que ce fichier empêche de revenir.** Jusqu'ici, la seule protection contre une migration
qui tourne mal était une consigne écrite (`docs/DEPLOIEMENT*` : « sauvegardez avant de mettre à
jour ») — une discipline HUMAINE, oubliable, et jamais vérifiée par aucun test. Ce fichier fige
trois comportements dans le CODE de démarrage (`get_initialized_db`), pas seulement dans la doc :

1. une base NEUVE ne produit aucune copie (rien à perdre) ;
2. une base DÉJÀ À JOUR n'en produit pas non plus à chaque redémarrage (sinon `data/` grossirait
   sans fin, exactement l'écart documenté et assumé de `data/executions/` — qu'on ne répète pas
   pour les sauvegardes) ;
3. une base qui va RÉELLEMENT migrer est sauvegardée D'ABORD, et si la copie échoue, la migration
   est REFUSÉE plutôt que jouée sans filet — testé en simulant un disque en panne.
"""
from __future__ import annotations

import sqlite3

import pytest

from testpilot.store import db as db_mod
from testpilot.store.db import _SCHEMA_VERSION, get_initialized_db


def _fichiers_de_sauvegarde(dossier):
    return sorted(dossier.glob("*.avant-migration-*"))


def _forcer_version_anterieure(chemin, version: int) -> None:
    """Rouvre une base déjà à la cible et lui fait croire qu'elle est restée à `version`.

    Permet de tester le déclenchement de la sauvegarde SANS reconstruire un schéma legacy complet
    en SQL brut : la migration 38 (`_migrate_38_connector_version`) est idempotente — rejouée sur
    une base qui a déjà la colonne, elle ne fait rien — donc « base en version 37 » peut être
    simulée en rabaissant seulement le `PRAGMA user_version`, sans rien changer au contenu réel.
    """
    raw = sqlite3.connect(str(chemin))
    try:
        raw.execute(f"PRAGMA user_version = {version}")
        raw.commit()
    finally:
        raw.close()


def test_base_neuve_ne_produit_aucune_sauvegarde(tmp_path):
    """Le fichier n'existe pas encore : rien à copier, et `path.exists()` avant `connect()` doit
    le voir ainsi — un test qui vérifierait l'existence APRÈS `connect()` se tromperait, puisque
    ouvrir une connexion SQLite sur un chemin absent crée le fichier vide."""
    chemin = tmp_path / "neuve.db"
    assert not chemin.exists()

    conn = get_initialized_db(chemin)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    finally:
        conn.close()

    assert _fichiers_de_sauvegarde(tmp_path) == []


def test_base_a_jour_ne_produit_aucune_sauvegarde_au_redemarrage(tmp_path):
    """Deux ouvertures successives d'une base déjà à la cible (le cas courant : chaque redémarrage
    du serveur) ne doivent produire AUCUNE copie — sinon `data/` grossirait à chaque redémarrage,
    pour un bénéfice nul (rien ne migre)."""
    chemin = tmp_path / "ajour.db"
    get_initialized_db(chemin).close()
    assert _fichiers_de_sauvegarde(tmp_path) == []  # premier démarrage : base neuve, déjà couvert

    get_initialized_db(chemin).close()  # second démarrage : base DÉJÀ à jour cette fois
    assert _fichiers_de_sauvegarde(tmp_path) == []


def test_base_ancienne_est_sauvegardee_avant_la_migration(tmp_path):
    """Le coeur du dispositif : une base qui va réellement migrer est copiée AVANT, avec le nom
    `{fichier}.avant-migration-{version_de_départ}-{horodatage}`, et la copie contient l'état
    D'AVANT la migration (pas un instantané d'après-coup)."""
    chemin = tmp_path / "ancienne.db"
    get_initialized_db(chemin).close()
    _forcer_version_anterieure(chemin, _SCHEMA_VERSION - 1)

    conn = get_initialized_db(chemin)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    finally:
        conn.close()

    sauvegardes = _fichiers_de_sauvegarde(tmp_path)
    assert len(sauvegardes) == 1
    prefixe = f"ancienne.db.avant-migration-{_SCHEMA_VERSION - 1}-"
    assert sauvegardes[0].name.startswith(prefixe)
    horodatage = sauvegardes[0].name[len(prefixe):]
    assert len(horodatage) == len("20260828-104308") and horodatage[8] == "-"

    # La copie fige bien l'état D'AVANT : elle doit rouvrir sur l'ANCIENNE version.
    raw = sqlite3.connect(str(sauvegardes[0]))
    try:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION - 1
    finally:
        raw.close()


def test_echec_de_la_copie_refuse_la_migration(tmp_path, monkeypatch):
    """Disque plein / permission refusée pendant la copie : la migration ne doit PAS avoir lieu —
    mieux vaut un démarrage bloqué, bruyamment journalisé, qu'une base migrée sans aucun filet."""
    chemin = tmp_path / "sans_filet.db"
    get_initialized_db(chemin).close()
    _forcer_version_anterieure(chemin, _SCHEMA_VERSION - 1)

    def _copie_qui_echoue(*args, **kwargs):
        raise OSError("disque plein (simulé)")

    monkeypatch.setattr(db_mod.shutil, "copy2", _copie_qui_echoue)

    with pytest.raises(OSError):
        get_initialized_db(chemin)

    # Aucune sauvegarde partielle, et surtout : la base n'a PAS été migrée.
    assert _fichiers_de_sauvegarde(tmp_path) == []
    raw = sqlite3.connect(str(chemin))
    try:
        assert raw.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION - 1
    finally:
        raw.close()
