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
def conn(tmp_path, monkeypatch):
    from testpilot import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
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
    # ⚠️ Depuis la suppression douce (2026-07-24), le résidu récupéré part à la corbeille au lieu
    # d'être détruit — §7 ne fait pas d'exception pour les détails techniques. Ce qui compte est
    # inchangé : il ne doit plus être VISIBLE, sinon l'arbre montrerait deux fois le même titre.
    assert CaseGroupRepo(conn).get(fantome) is None
    titres = [g["title"] for g in CaseGroupRepo(conn).list_for_module(module_id)]
    assert titres.count(TITRE) == 1, "le résidu doit être récupéré, pas laissé en double"


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

    survit = 1 if CaseGroupRepo(conn).get(ailleurs) else 0
    assert survit == 1, "on ne touche pas au module voisin"


def test_renommer_vers_le_titre_d_un_residu_est_possible(conn, module_id):
    """`update` passe par le même contrôle : un fantôme ne doit pas bloquer un renommage."""
    fantome = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, auto_enveloppe=True)
    autre = CaseGroupRepo(conn).create(module_id=module_id, title="Provisoire",
                                       spec_content="# doc")

    CaseGroupRepo(conn).update(autre, title=TITRE)

    assert CaseGroupRepo(conn).get(autre)["title"] == TITRE
    assert CaseGroupRepo(conn).get(fantome) is None   # récupéré → à la corbeille (§7)


# ── Cohérence avec la suppression (une seule règle, deux appelants) ──────────

def test_supprimer_le_dernier_cas_emporte_l_enveloppe(conn, module_id):
    """Non-régression : le nettoyage à la suppression continue de fonctionner, et il s'appuie
    désormais sur la MÊME règle que la création. Deux copies divergeraient en silence."""
    cid = _cas(conn, module_id, "Cas auto-enveloppé")
    gid = conn.execute("SELECT group_id FROM test_case WHERE id=?", (cid,)).fetchone()[0]
    assert gid is not None

    CaseRepo(conn).delete(cid)

    # ⚠️ Depuis la suppression douce (2026-07-24), la LIGNE reste — et c'est voulu (§7). Ce qui
    # comptait n'a pas changé : l'enveloppe ne doit plus être visible nulle part.
    assert CaseGroupRepo(conn).get(gid) is None
    assert CaseGroupRepo(conn).list_for_module(module_id) == []


def test_le_CYCLE_COMPLET_est_rejouable(conn, module_id):
    """Créer → supprimer → **recréer le même titre**, trois fois. C'est ce que fait le banc à
    chaque campagne, et aucun test ne parcourait ce cycle en entier.

    ⚠️ **Honnêteté sur ce que ce test vaut** : vérifié par sabotage, il **n'aurait PAS attrapé** le
    défaut du 2026-07-22. Sur une base neuve, `CaseRepo.create` pose la provenance correctement dès
    la création — le cycle passe donc, bug ou pas. Le défaut ne vivait que dans la **reprise de
    l'existant**, et c'est `test_la_reprise_reconnait_une_enveloppe_A_SON_TITRE` qui le tient.

    Il garde sa valeur de garde du cycle nominal ; il ne faut simplement pas lui prêter une
    couverture qu'il n'a pas. **Un test dont on surestime la portée est pire qu'un test absent** :
    on croit le terrain couvert.
    """
    for tour in range(3):
        cid = _cas(conn, module_id, TITRE)
        CaseRepo(conn).delete(cid)
        # Aucune enveloppe VISIBLE ne doit rester — c'est elle qui bloquait la regénération du
        # même titre. (La ligne subsiste à la corbeille : suppression douce, §7.)
        visibles = [g for g in CaseGroupRepo(conn).list_for_module(module_id)
                    if g["title"] == TITRE]
        assert visibles == [], f"tour {tour + 1} : une enveloppe fantôme est restée"


def test_supprimer_le_dernier_cas_PRESERVE_une_specification_documentee(conn, module_id):
    gid = CaseGroupRepo(conn).create(module_id=module_id, title="Documentée",
                                     spec_content="# Le document")
    cid = _cas(conn, module_id, "un cas")
    conn.execute("UPDATE test_case SET group_id=? WHERE id=?", (gid, cid))
    conn.commit()

    CaseRepo(conn).delete(cid)

    assert CaseGroupRepo(conn).get(gid) is not None   # une spec DOCUMENTÉE survit à ses cas


# ── La reprise de l'existant (migration 18) ──────────────────────────────────

def test_la_reprise_reconnait_une_enveloppe_A_SON_TITRE(conn, module_id):
    """⚠️ La leçon de la migration 17 : ne pas classer sur l'état INSTANTANÉ quand une SIGNATURE
    stable existe. Une enveloppe porte le titre exact de son cas — vrai que le cas existe ou non.

    Ici on simule une base d'avant la colonne : provenance perdue, cas encore présent. La 17
    l'aurait déclarée « délibérée » pour toujours ; la 18 la reconnaît."""
    from testpilot.store.db import _migrate_18_corriger_provenance_enveloppes

    cid = _cas(conn, module_id, TITRE)
    gid = conn.execute("SELECT group_id FROM test_case WHERE id=?", (cid,)).fetchone()[0]
    conn.execute("UPDATE case_group SET auto_enveloppe = 0 WHERE id=?", (gid,))  # comme la 17
    conn.commit()

    _migrate_18_corriger_provenance_enveloppes(conn)

    assert conn.execute("SELECT auto_enveloppe FROM case_group WHERE id=?",
                        (gid,)).fetchone()[0] == 1
    CaseRepo(conn).delete(cid)
    assert CaseGroupRepo(conn).get(gid) is None      # invisible (ligne conservée, §7)


def test_la_reprise_NE_TOUCHE_PAS_une_specification_documentee(conn, module_id):
    from testpilot.store.db import _migrate_18_corriger_provenance_enveloppes

    gid = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE, spec_content="# Document")

    _migrate_18_corriger_provenance_enveloppes(conn)

    assert conn.execute("SELECT auto_enveloppe FROM case_group WHERE id=?",
                        (gid,)).fetchone()[0] == 0


def test_la_reprise_NE_TOUCHE_PAS_une_specification_a_PLUSIEURS_cas(conn, module_id):
    """Plusieurs cas sous un même conteneur, c'est le modèle VOULU (un document, N cas) —
    l'inverse exact d'une enveloppe 1:1."""
    from testpilot.store.db import _migrate_18_corriger_provenance_enveloppes

    gid = CaseGroupRepo(conn).create(module_id=module_id, title=TITRE)
    for titre in ("cas nominal", "cas d'erreur"):
        cid = _cas(conn, module_id, titre)
        conn.execute("UPDATE test_case SET group_id=? WHERE id=?", (gid, cid))
    conn.commit()

    _migrate_18_corriger_provenance_enveloppes(conn)

    assert conn.execute("SELECT auto_enveloppe FROM case_group WHERE id=?",
                        (gid,)).fetchone()[0] == 0
