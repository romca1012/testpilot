"""La mémoire de réparation — la boucle cesse de racheter ce qu'elle sait déjà (`0018`, volet 2).

`0018` a corrigé l'ADOPTION d'une version (le progrès partiel n'est plus jeté). La CONNAISSANCE,
elle, se perdait toujours : chaque tentative repartait aveugle, et redécouvrait — en le repayant —
ce qu'une tentative précédente avait établi. La base portait pourtant tout depuis le début.

Deux propriétés sont verrouillées ici, et elles comptent autant l'une que l'autre :

1. la mémoire **arrive** jusqu'à l'agent, y compris d'une session à la suivante ;
2. elle ne contient **aucun texte écrit par l'agent**, et ne casse **pas le cache de prompt**.
"""

from __future__ import annotations

import pytest

from testpilot.generation import memoire_reparation as mr
from testpilot.generation import regles_apprises as ra
from testpilot.generation import repair_agent
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    ModuleRepo,
    ProjectRepo,
    RepairRepo,
    VersionRepo,
)


def _regle(**kw) -> ra.RegleApprise:
    base = dict(route="/fournisseur/creation", champ="tva_intracommunautaire",
                type_contrainte="patternMismatch", valeur_contrainte=r"\d{9}",
                valeur_refusee="TestPilot", origine="navigateur",
                preuve="uniquement des chiffres", premiere_le="", derniere_le="",
                occurrences=1)
    base.update(kw)
    return ra.RegleApprise(**base)


def _fait(**kw) -> mr.FaitDeReparation:
    base = dict(version_id=7, signature="broken_test_code:TypeError:3",
                cause="broken_test_code", origine="test_a_reparer", quand="2026-08-01")
    base.update(kw)
    return mr.FaitDeReparation(**base)


# ── Ce que la section dit ────────────────────────────────────────────────────

def test_GARDE_les_valeurs_refusees_arrivent_dans_la_section():
    section = mr.as_prompt_section([_regle()], [])
    assert "tva_intracommunautaire" in section
    assert "TestPilot" in section
    assert "/fournisseur/creation" in section


def test_GARDE_la_repetition_d_une_signature_est_DITE_a_l_agent():
    """L'information la plus utile du bloc, et elle est 100 % dérivée du runtime.

    ⚠️ Elle existait en base depuis toujours ; personne ne la relisait. Une signature répétée
    prouve que ce qui a été tenté n'a RIEN changé au signal d'échec.
    """
    section = mr.as_prompt_section([], [_fait(version_id=7), _fait(version_id=9)])
    assert "s'est répétée 2×" in section
    assert "Change d'approche" in section


def test_deux_signatures_differentes_ne_declenchent_PAS_l_avertissement():
    section = mr.as_prompt_section([], [_fait(version_id=7, signature="a"),
                                        _fait(version_id=9, signature="b")])
    assert "répétée" not in section


def test_un_champ_devenu_obligatoire_est_dit_SANS_devenir_une_contrainte():
    """`valueMissing` est remonté à l'agent comme un FAIT, mais n'est jamais une règle.

    « refusé vide une fois » ne veut pas dire « toujours obligatoire » — un choix fait plus haut
    peut le rendre requis. Le dire évite de chercher ; l'affirmer serait une invention.
    """
    regle = _regle(champ="motif_avoir", type_contrainte="valueMissing",
                   valeur_contrainte="", valeur_refusee="", preuve="")
    section = mr.as_prompt_section([regle], [])
    assert "OBLIGATOIRES" in section
    assert "motif_avoir" in section


def test_sans_rien_a_dire_la_section_est_VIDE():
    """Coût nul quand il n'y a rien à transmettre — la section n'apparaît pas du tout."""
    assert mr.as_prompt_section([], []) == ""


def test_la_memoire_est_PLAFONNEE():
    regles = [_regle(champ=f"champ_{i}", valeur_refusee=f"valeur_{i}" * 20) for i in range(50)]
    faits = [_fait(version_id=i, signature=f"sig_{i}") for i in range(30)]
    section = mr.as_prompt_section(regles, faits)
    assert len(section) <= mr._MAX_CARACTERES + 40


# ── Principe 1 : aucun texte de l'agent ──────────────────────────────────────

def test_GARDE_la_memoire_ne_contient_AUCUN_texte_ecrit_par_l_agent(tmp_path):
    """⚠️ `what_was_tried` et `change_summary` sont de la PROSE de LLM.

    `_failure_report` porte déjà la doctrine : lui souffler sa propre conclusion l'enferme dans
    une piste qui peut être fausse (cas 6). La réinjecter d'une session à l'autre ancrerait cette
    piste **durablement** — pire que dans une seule session. Arbitrage du porteur, 2026-08-03.
    """
    conn = get_initialized_db(tmp_path / "m.db")
    pid = ProjectRepo(conn).create(name="P", description="")
    mid = ModuleRepo(conn).create(project_id=pid, name="M", description="")
    cid = CaseRepo(conn).create(module_id=mid, title="T", feature_slug="t")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="", steps_content="")
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    RepairRepo(conn).create(execution_id=eid, attempt_number=1,
                            failure_signature="sig:X:1", cause_category="broken_test_code",
                            defect_origin="test_a_reparer", confirmation_status="not_required",
                            what_was_tried="SENTINELLE_PROSE_DE_L_AGENT")

    _, faits = mr.collecter(conn, case_id=cid, project_id=pid)
    section = mr.as_prompt_section([], faits)

    assert "SENTINELLE_PROSE_DE_L_AGENT" not in section
    assert "sig:X:1" in section, "les signaux runtime, eux, doivent bien arriver"


# ── Le verrou de cache ───────────────────────────────────────────────────────

def test_GARDE_le_prompt_SYSTEME_de_reparation_reste_INDEPENDANT_du_cas():
    """⚠️ Ce test PASSE aujourd'hui — c'est un verrou, pas une correction.

    `build_repair_prompt` est identique pour tous les cas : son bloc `cache_control` est donc
    partagé par tous. Y injecter une mémoire par cas rendrait chaque prompt système unique et
    **détruirait le cache pour tout le monde** — bien plus cher que ce que la mémoire économise.
    Il échouerait si quelqu'un déplaçait la mémoire au mauvais endroit.
    """
    import inspect
    signature = inspect.signature(repair_agent.build_repair_prompt)
    assert "memoire" not in signature.parameters
    assert "case_id" not in signature.parameters
    assert repair_agent.build_repair_prompt() == repair_agent.build_repair_prompt()


def test_GARDE_la_memoire_arrive_dans_le_MESSAGE_utilisateur():
    rapport = repair_agent._failure_report([], [], "du code", "## MA MEMOIRE")
    assert "## MA MEMOIRE" in rapport
    # …et avant l'impératif final, qui doit rester la dernière chose lue.
    assert rapport.index("## MA MEMOIRE") < rapport.index("EN ENTIER")


def test_sans_memoire_le_rapport_est_IDENTIQUE_a_avant():
    """Aucune régression quand il n'y a rien à dire."""
    assert repair_agent._failure_report([], [], "du code") \
        == repair_agent._failure_report([], [], "du code", "")


# ── L'agrégation par CAS, le trou que rien ne comblait ───────────────────────

def test_GARDE_l_historique_traverse_les_EXECUTIONS_et_les_SESSIONS(tmp_path):
    """⚠️ Échoue sur le code d'avant : `RepairRepo` ne savait lire que par exécution.

    C'est exactement pour ça que chaque nouvelle session repartait aveugle.
    """
    conn = get_initialized_db(tmp_path / "h.db")
    pid = ProjectRepo(conn).create(name="P", description="")
    mid = ModuleRepo(conn).create(project_id=pid, name="M", description="")
    cid = CaseRepo(conn).create(module_id=mid, title="T", feature_slug="t")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                   feature_content="", steps_content="")

    for numero in (1, 2):      # deux exécutions = deux sessions de rejeu distinctes
        eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
        RepairRepo(conn).create(execution_id=eid, attempt_number=1,
                                failure_signature=f"sig-{numero}",
                                cause_category="broken_test_code",
                                defect_origin="test_a_reparer",
                                confirmation_status="not_required")

    historique = RepairRepo(conn).historique_pour_cas(cid)
    assert len(historique) == 2
    assert {l["failure_signature"] for l in historique} == {"sig-1", "sig-2"}


def test_l_historique_ne_MELANGE_PAS_deux_cas(tmp_path):
    conn = get_initialized_db(tmp_path / "h2.db")
    pid = ProjectRepo(conn).create(name="P", description="")
    mid = ModuleRepo(conn).create(project_id=pid, name="M", description="")
    ids = []
    for n in (1, 2):
        cid = CaseRepo(conn).create(module_id=mid, title=f"T{n}", feature_slug=f"t{n}")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                       feature_content="", steps_content="")
        eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
        RepairRepo(conn).create(execution_id=eid, attempt_number=1, failure_signature=f"s{n}",
                                cause_category="c", defect_origin="test_a_reparer",
                                confirmation_status="not_required")
        ids.append(cid)

    assert [l["failure_signature"] for l in RepairRepo(conn).historique_pour_cas(ids[0])] == ["s1"]


def test_collecter_ne_LEVE_JAMAIS_meme_sans_projet(tmp_path):
    """Une mémoire indisponible ne doit jamais empêcher une réparation de se lancer."""
    conn = get_initialized_db(tmp_path / "v.db")
    regles, faits = mr.collecter(conn, case_id=999, project_id=None)
    assert regles == [] and faits == []
