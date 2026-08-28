"""`scripts/sauvegarder.py` — rétention, et LA preuve qu'une sauvegarde restaure VRAIMENT.

⚠️ **Pourquoi ce fichier existe.** Une fonction `restaurer()` qui n'a jamais été exercée par un
test de bout en bout est une HYPOTHÈSE, pas une garantie — le genre d'écart que ce projet refuse
ailleurs (§7 du brief : pas de suppression sans copie récupérable ; decisions/0023 : ne rien
prétendre qu'on n'a pas mesuré). `test_cycle_sauvegarde_puis_restauration_complet` fait donc le
tour complet : une VRAIE base (`get_initialized_db`), de VRAIES données écrites par les dépôts
existants (pas des lignes SQL à la main), sauvegarde, PERTE réelle du fichier original, restauration
depuis la sauvegarde, puis comparaison — pas seulement « le fichier existe », mais que les données
qu'on avait écrites sont identiques après le cycle complet.
"""
from __future__ import annotations

import sqlite3

import pytest

from scripts.sauvegarder import _purger_anciennes, lister_sauvegardes, restaurer, sauvegarder
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo


def _creer_fichier(chemin, contenu: bytes = b"x") -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(contenu)


def _creer_base_sqlite(chemin, valeur: str = "contenu original") -> None:
    """Une VRAIE base SQLite minimale — `sauvegarder()` copie désormais via l'API `backup()`
    (sauvegarde « à chaud »), qui exige un fichier source réellement ouvrable par SQLite, pas
    n'importe quel octet (voir `scripts.sauvegarder._copier_a_chaud`)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(chemin))
    try:
        conn.execute("CREATE TABLE t (valeur TEXT)")
        conn.execute("INSERT INTO t (valeur) VALUES (?)", (valeur,))
        conn.commit()
    finally:
        conn.close()


def _lire_valeur(chemin) -> str:
    conn = sqlite3.connect(str(chemin))
    try:
        return conn.execute("SELECT valeur FROM t").fetchone()[0]
    finally:
        conn.close()


# ── Sauvegarde : garde d'entrée, nommage, rétention ──────────────────────────────────────────

def test_sauvegarder_refuse_une_source_absente(tmp_path):
    with pytest.raises(FileNotFoundError):
        sauvegarder(source=tmp_path / "absente.db", dossier=tmp_path / "sauvegardes")


def test_sauvegarder_produit_une_copie_horodatee_et_conserve_loriginal(tmp_path):
    source = tmp_path / "testpilot.db"
    _creer_base_sqlite(source, "contenu original")
    dossier = tmp_path / "sauvegardes"

    cible = sauvegarder(source=source, dossier=dossier, garder=10)

    assert cible.exists()
    assert _lire_valeur(cible) == "contenu original"
    assert cible.parent == dossier
    assert cible.name.startswith("testpilot.db.sauvegarde-")
    assert source.exists()  # la sauvegarde ne DÉPLACE pas la source, elle la COPIE
    assert _lire_valeur(source) == "contenu original"


def test_purge_anciennes_garde_exactement_les_n_plus_recentes(tmp_path):
    """Rétention explicite : au-delà de `garder`, les plus ANCIENNES (triées par horodatage dans
    le nom) disparaissent — jamais une croissance sans fin, jamais les plus récentes."""
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    horodatages = [f"2026082{i}-000000" for i in range(8)]  # 8 sauvegardes, du plus ancien au +récent
    for h in horodatages:
        _creer_fichier(dossier / f"testpilot.db.sauvegarde-{h}")

    retirees = _purger_anciennes(dossier, "testpilot.db", garder=3)

    restantes = lister_sauvegardes(dossier, "testpilot.db")
    prefixe = "testpilot.db.sauvegarde-"
    assert [p.name[len(prefixe):] for p in restantes] == horodatages[-3:]
    assert len(retirees) == 5
    for f in retirees:
        assert not f.exists()


def test_sauvegarder_applique_la_retention_a_chaque_appel(tmp_path):
    source = tmp_path / "testpilot.db"
    dossier = tmp_path / "sauvegardes"
    _creer_fichier(dossier / "testpilot.db.sauvegarde-20260101-000000")
    _creer_fichier(dossier / "testpilot.db.sauvegarde-20260102-000000")
    _creer_base_sqlite(source, "etat courant")

    sauvegarder(source=source, dossier=dossier, garder=2)

    restantes = lister_sauvegardes(dossier, "testpilot.db")
    assert len(restantes) == 2  # les 2 anciennes + celle du jour = 3, retention à 2 → la + vieille part
    assert "20260101" not in restantes[0].name + restantes[1].name


def test_purge_refuse_garder_zero_ou_negatif(tmp_path):
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    with pytest.raises(ValueError):
        _purger_anciennes(dossier, "testpilot.db", garder=0)


# ── Restauration : garde d'entrée ─────────────────────────────────────────────────────────────

def test_restaurer_refuse_une_sauvegarde_absente(tmp_path):
    with pytest.raises(FileNotFoundError):
        restaurer(tmp_path / "inexistante.sauvegarde", destination=tmp_path / "cible.db")


def test_restaurer_cree_le_dossier_parent_de_la_destination(tmp_path):
    source_sauvegarde = tmp_path / "backup.db"
    _creer_fichier(source_sauvegarde, b"donnees")
    destination = tmp_path / "nouveau_dossier" / "restauree.db"

    cible = restaurer(source_sauvegarde, destination=destination)

    assert cible == destination
    assert destination.read_bytes() == b"donnees"


# ── LE test qui compte : le cycle complet, sur une vraie base ───────────────────────────────

def test_cycle_sauvegarde_puis_restauration_complet(tmp_path):
    """Base réelle → écriture réelle (dépôts) → sauvegarde → PERTE du fichier original →
    restauration → mêmes données. La preuve qu'une sauvegarde restaure VRAIMENT, pas l'hypothèse."""
    db_path = tmp_path / "testpilot.db"
    dossier_sauvegardes = tmp_path / "sauvegardes"

    # 1. Une vraie base, avec de vraies données écrites via les dépôts existants (pas du SQL brut).
    conn = get_initialized_db(db_path)
    projet_id = ProjectRepo(conn).create(name="Portail de test", description="cycle sauvegarde")
    module_id = ModuleRepo(conn).create(project_id=projet_id, name="Module A", description="")
    cas_id = CaseRepo(conn).create(module_id=module_id, title="Cas nominal", description="",
                                   origin="manual_converted", author="test")
    conn.close()

    # 2. Sauvegarde.
    fichier_sauvegarde = sauvegarder(source=db_path, dossier=dossier_sauvegardes, garder=10)
    assert fichier_sauvegarde.exists()

    # 3. Perte RÉELLE : le fichier original disparaît (corruption simulée par suppression pure).
    db_path.unlink()
    assert not db_path.exists()

    # 4. Restauration depuis la sauvegarde.
    restaurer(fichier_sauvegarde, destination=db_path)
    assert db_path.exists()

    # 5. Les données sont IDENTIQUES — comparées via les mêmes dépôts, pas juste « le fichier existe ».
    conn2 = get_initialized_db(db_path)
    try:
        projets = ProjectRepo(conn2).list_all()
        assert len(projets) == 1
        assert projets[0]["id"] == projet_id
        assert projets[0]["name"] == "Portail de test"

        modules = ModuleRepo(conn2).list_for_project(projet_id)
        assert len(modules) == 1
        assert modules[0]["name"] == "Module A"

        cas_restaure = CaseRepo(conn2).get(cas_id)
        assert cas_restaure is not None
        assert cas_restaure["title"] == "Cas nominal"
    finally:
        conn2.close()


def test_cycle_de_restauration_detecte_une_corruption_pas_seulement_une_absence(tmp_path):
    """Restaurer doit aussi réparer une base CORROMPUE (fichier remplacé par du bruit), pas
    seulement un fichier absent — les deux sont des « pertes de données » au sens du brief."""
    db_path = tmp_path / "testpilot.db"
    dossier_sauvegardes = tmp_path / "sauvegardes"

    conn = get_initialized_db(db_path)
    ProjectRepo(conn).create(name="Avant corruption", description="")
    conn.commit()
    conn.close()

    fichier_sauvegarde = sauvegarder(source=db_path, dossier=dossier_sauvegardes, garder=10)

    # Corruption : le fichier existe toujours, mais n'est plus une base SQLite valide.
    db_path.write_bytes(b"\x00\x01\x02 ceci n'est plus une base SQLite")
    with pytest.raises(sqlite3.DatabaseError):
        raw = sqlite3.connect(str(db_path))
        try:
            raw.execute("SELECT * FROM project").fetchall()
        finally:
            raw.close()

    restaurer(fichier_sauvegarde, destination=db_path)

    conn2 = get_initialized_db(db_path)
    try:
        projets = ProjectRepo(conn2).list_all()
        assert [p["name"] for p in projets] == ["Avant corruption"]
    finally:
        conn2.close()
