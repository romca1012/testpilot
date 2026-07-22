"""Une Spécification RÉSIDUELLE ne doit jamais bloquer une génération (2026-07-22).

⚠️ **Le défaut, mesuré sur le banc.** La mesure s'est arrêtée sur :

    ce module a déjà une spécification « Création d'une demande de remboursement… »

…alors que cette Spécification n'avait **ni cas ni document** : une enveloppe vide, laissée par une
suppression **antérieure** au nettoyage automatique. Le nettoyage à la suppression ne fait que
prévenir les nouveaux fantômes ; il n'efface pas ceux d'avant.

**C'est la troisième fois que le banc bute sur sa propre non-rejouabilité.** Un instrument de
mesure qu'on ne peut pas relancer ne mesure aucune évolution — il ne dit rien du tout. Le corriger
n'est donc pas du confort : c'est réparer l'instrument.

La correction est **rétroactive et auto-guérissante** : au lieu d'une migration de balayage, le
résidu est récupéré le jour où son titre est réclamé. Aucun fantôme, présent ou passé, ne peut
bloquer.

⚠️ **La borne** : une Spécification qui porte un DOCUMENT est un actif, même sans aucun cas — on
peut vouloir en regénérer. Elle doit survivre, et donc continuer de refuser son titre.
"""

import pytest

from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseGroupRepo, CaseRepo, DuplicateName, ModuleRepo, ProjectRepo,
)


@pytest.fixture()
def conn(tmp_path):
    c = get_initialized_db(tmp_path / "t.db")
    yield c
    c.close()


@pytest.fixture()
def module_id(conn):
    pid = ProjectRepo(conn).create(name="P", connector_type="odoo", base_url="http://x",
                                   database="d", username="u", password="p")
    return ModuleRepo(conn).create(project_id=pid, name="M")


TITRE = "Création d'une demande de remboursement avec tous les champs obligatoires"


def _cas(conn, module_id, titre):
    return CaseRepo(conn).create_manual(module_id=module_id, title=titre)


# ── La règle du résidu, en un seul endroit ───────────────────────────────────

def test_une_enveloppe_AUTOMATIQUE_vide_EST_un_residu(conn, module_id):
    gid = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, auto_enveloppe=True)

    assert CaseGroupRepo(conn).est_residu(gid) is True


def test_une_specification_VIDE_mais_VOULUE_n_est_PAS_un_residu(conn, module_id):
    """⚠️ **Le piège dans lequel je suis tombé le 2026-07-22.** Ma première version ne regardait
    que le vide : une Spécification tout juste créée depuis l'écran — vide, forcément — devenait
    récupérable, et créer un homonyme l'**effaçait en silence** au lieu de refuser le doublon.
    Quatre tests existants l'ont attrapé. « Vide » ne veut pas dire « jetable » : c'est la
    PROVENANCE qui décide."""
    gid = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE)

    assert CaseGroupRepo(conn).est_residu(gid) is False


def test_une_specification_PORTANT_UN_DOCUMENT_n_est_pas_un_residu(conn, module_id):
    """Un document est un actif : il survit à ses cas, on peut vouloir en regénérer."""
    gid = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, auto_enveloppe=True,
                                     spec_content="# Le document métier\nRègles…")

    assert CaseGroupRepo(conn).est_residu(gid) is False


def test_une_specification_QUI_PORTE_DES_CAS_n_est_pas_un_residu(conn, module_id):
    gid = CaseGroupRepo(conn).create(module_id=module_id, title="Porteuse", auto_enveloppe=True)
    cid = _cas(conn, module_id, "un cas")
    conn.execute("UPDATE test_case SET group_id=? WHERE id=?", (gid, cid))
    conn.commit()

    assert CaseGroupRepo(conn).est_residu(gid) is False


def test_un_espace_blanc_ne_compte_PAS_comme_un_document(conn, module_id):
    """Sinon un document « vide » invisible bloquerait éternellement un titre."""
    gid = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, auto_enveloppe=True,
                                     spec_content="   \n\t ")

    assert CaseGroupRepo(conn).est_residu(gid) is True


def test_un_cas_genere_cree_une_enveloppe_MARQUEE_automatique(conn, module_id):
    """La provenance doit être posée à la source, sinon la règle n'a rien à lire."""
    cid = _cas(conn, module_id, "Cas auto-enveloppé")

    gid = conn.execute("SELECT group_id FROM test_case WHERE id=?", (cid,)).fetchone()[0]
    assert conn.execute("SELECT auto_enveloppe FROM case_group WHERE id=?",
                        (gid,)).fetchone()[0] == 1


# ── Le blocage du banc, reproduit puis fermé ─────────────────────────────────

def test_un_RESIDU_ne_bloque_plus_le_titre(conn, module_id):
    """⚠️ LE test. Exactement la situation qui a arrêté la mesure du 2026-07-22."""
    fantome = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, auto_enveloppe=True)

    nouveau = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE)

    assert nouveau != fantome
    reste = conn.execute("SELECT COUNT(*) FROM case_group WHERE id=?", (fantome,)).fetchone()[0]
    assert reste == 0, "le résidu doit être récupéré, pas laissé en double"


def test_une_specification_VOULUE_refuse_TOUJOURS_le_doublon(conn, module_id):
    """⚠️ La borne la plus importante : le doublon reste une ERREUR (409 côté API), il ne devient
    jamais un effacement silencieux. Un titre déjà pris par un humain le reste."""
    CaseGroupRepo(conn).create(module_id=module_id, title=TITRE)

    with pytest.raises(DuplicateName, match="déjà une spécification"):
        CaseGroupRepo(conn).create(module_id=module_id, title=TITRE)


def test_le_titre_reste_REFUSE_quand_la_specification_porte_un_document(conn, module_id):
    """La borne. Sans elle, la correction détruirait un actif au lieu d'un déchet."""
    CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, auto_enveloppe=True,
                               spec_content="# Document")

    with pytest.raises(DuplicateName, match="déjà une spécification"):
        CaseGroupRepo(conn).create(module_id=module_id, title=TITRE)


def test_le_titre_reste_REFUSE_quand_la_specification_porte_des_cas(conn, module_id):
    gid = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, auto_enveloppe=True)
    cid = _cas(conn, module_id, "un cas")
    conn.execute("UPDATE test_case SET group_id=? WHERE id=?", (gid, cid))
    conn.commit()

    with pytest.raises(DuplicateName):
        CaseGroupRepo(conn).create(module_id=module_id, title=TITRE)


def test_la_recuperation_est_LOCALE_a_son_module(conn, module_id):
    """L'unicité est par module : un résidu d'un autre module ne concerne personne."""
    autre = ModuleRepo(conn).create(project_id=1, name="Autre")
    ailleurs = CaseGroupRepo(conn).create(module_id=autre, title=TITRE, auto_enveloppe=True)

    CaseGroupRepo(conn).create(module_id=module_id, title=TITRE)

    survit = conn.execute("SELECT COUNT(*) FROM case_group WHERE id=?", (ailleurs,)).fetchone()[0]
    assert survit == 1, "on ne touche pas au module voisin"


def test_renommer_vers_le_titre_d_un_residu_est_possible(conn, module_id):
    """`update` passe par le même contrôle : un fantôme ne doit pas bloquer un renommage."""
    fantome = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, auto_enveloppe=True)
    autre = CaseGroupRepo(conn).create(module_id=module_id, title="Provisoire",
                                       spec_content="# doc")

    CaseGroupRepo(conn).update(autre, title=TITRE)

    assert conn.execute("SELECT title FROM case_group WHERE id=?",
                        (autre,)).fetchone()[0] == TITRE
    assert conn.execute("SELECT COUNT(*) FROM case_group WHERE id=?",
                        (fantome,)).fetchone()[0] == 0


# ── Cohérence avec la suppression (une seule règle, deux appelants) ──────────

def test_supprimer_le_dernier_cas_emporte_l_enveloppe(conn, module_id):
    """Non-régression : le nettoyage à la suppression continue de fonctionner, et il s'appuie
    désormais sur la MÊME règle que la création. Deux copies divergeraient en silence."""
    cid = _cas(conn, module_id, "Cas auto-enveloppé")
    gid = conn.execute("SELECT group_id FROM test_case WHERE id=?", (cid,)).fetchone()[0]
    assert gid is not None

    CaseRepo(conn).delete(cid)

    assert conn.execute("SELECT COUNT(*) FROM case_group WHERE id=?", (gid,)).fetchone()[0] == 0


def test_supprimer_le_dernier_cas_PRESERVE_une_specification_documentee(conn, module_id):
    gid = CaseGroupRepo(conn).create(module_id=module_id, title="Documentée",
                                     spec_content="# Le document")
    cid = _cas(conn, module_id, "un cas")
    conn.execute("UPDATE test_case SET group_id=? WHERE id=?", (gid, cid))
    conn.commit()

    CaseRepo(conn).delete(cid)

    assert conn.execute("SELECT COUNT(*) FROM case_group WHERE id=?", (gid,)).fetchone()[0] == 1
