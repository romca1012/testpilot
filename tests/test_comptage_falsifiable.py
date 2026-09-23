"""Décision 0011 — un comptage sans point de comparaison ÉCHOUE, il ne passe pas en silence.

Avant : `memorize_record_count` avalait son exception (`warn`), et `check_count_*` faisait
`warn` + `return` quand le snapshot manquait → le `@then` passait sans rien vérifier. Chaîne de
faux-négatif muette aux deux bouts (§4.2 « jamais déclaratif », §4.4 « faux-négatif
inacceptable »), dans les helpers les PLUS réutilisés de la bibliothèque (0003).

Tests déterministes sans Odoo : un faux `context` reproduit juste `context.odoo.env[model]
.search_count([])`.
"""

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

from behave_runtime.steps_library._base_helpers import (
    _COUNT_SNAPSHOT_STEP,
    check_count_increased_by_one,
    check_count_not_increased,
    memorize_record_count,
)
from testpilot import config
from testpilot.generation import steps_library


def _installer_shim_features_environment():
    """Même shim que `test_behave_harness.py` : rend `features.environment` importable, pour
    que le `from features.environment import register_created` (import différé, dans
    `_capturer_dernier_enregistrement`) résolve sans dépendre d'un vrai run Behave."""
    spec = importlib.util.spec_from_file_location(
        "environment", config.BEHAVE_RUNTIME_DIR / "environment.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["environment"] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeModel:
    """`count=N` reproduit l'ancien comportement (ids `1..N`, count global) pour ne PAS toucher
    les corps des tests existants (§F1, 2026-09-23 : seule cette doublure change d'interface,
    jamais les assertions qu'elle sert). `ids=`/`champs=` explicites pour les scénarios
    multi-acteurs (tiers concurrent) de `test_comptage_cloisonne.py`, où le "plus grand id
    existant" ne suffit plus à représenter deux créateurs distincts."""

    def __init__(self, count=0, ids=None, boom=False, champs=None):
        self._ids = list(ids) if ids is not None else list(range(1, count + 1))
        self._boom = boom
        self._champs = champs or {}  # {id: {champ: valeur}} — pour l'affinage par marqueur

    def with_context(self, **_kw):
        return self

    def search_count(self, _domain):
        if self._boom:
            raise RuntimeError("connexion RPC perdue")
        return len(self._ids)

    def search(self, domain=(), order=None, limit=None, **_kw):
        """Présent sur le vrai modèle odoorpc — `_crees_par_ce_scenario`/`memorize_record_count`
        s'en servent pour cloisonner au scénario (§F1, 2026-09-23), plus qu'un `count` brut."""
        if self._boom:
            raise RuntimeError("connexion RPC perdue")
        ids = list(self._ids)
        for condition in domain:
            champ, op, valeur = condition
            if champ == "id" and op == ">":
                ids = [i for i in ids if i > valeur]
            elif op == "like":
                ids = [i for i in ids if valeur in str(self._champs.get(i, {}).get(champ, ""))]
        if order == "id desc":
            ids = sorted(ids, reverse=True)
        if limit is not None:
            ids = ids[:limit]
        return ids


class _FakeEnv:
    def __init__(self, count=0, ids=None, boom=False, champs=None):
        self._m = _FakeModel(count=count, ids=ids, boom=boom, champs=champs)

    def __getitem__(self, _model):
        return self._m


class _FakeOdoo:
    def __init__(self, count=0, ids=None, boom=False, champs=None):
        self.env = _FakeEnv(count=count, ids=ids, boom=boom, champs=champs)


class _Context:
    def __init__(self, count=0, ids=None, boom=False, champs=None):
        self.odoo = _FakeOdoo(count=count, ids=ids, boom=boom, champs=champs)


MODEL = "helpdesk.ticket"


# ── Sans snapshot : ÉCHEC, jamais un passage muet ────────────────────────────

@pytest.mark.parametrize("verif", [check_count_not_increased, check_count_increased_by_one])
def test_comptage_sans_snapshot_echoue(verif):
    """LE cas du défaut : le @then était appelé sans que rien n'ait été mesuré avant."""
    with pytest.raises(AssertionError) as exc:
        verif(_Context(count=5), MODEL)
    # Le message doit être ACTIONNABLE : dire quel step manque, pas juste « ça a raté ».
    assert "point de comparaison" in str(exc.value)
    assert "est enregistré pour comparaison" in str(exc.value)
    assert MODEL in str(exc.value)


def test_le_step_cite_dans_le_message_existe_vraiment():
    """Un message qui nomme un step inexistant enverrait le lecteur dans le mur."""
    assert _COUNT_SNAPSHOT_STEP in {s.label for s in steps_library.catalogue()}


# ── Avec snapshot : le comportement utile est INTACT ─────────────────────────

def test_snapshot_puis_augmentation_de_1_passe():
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=11)          # l'action a créé un enregistrement
    check_count_increased_by_one(ctx, MODEL)


def test_le_nouvel_enregistrement_est_enregistre_pour_nettoyage():
    """`write_test_plan` (100 % steps du catalogue) n'a aucun Python custom pour appeler
    `register_created` — sans ce câblage, chaque scénario qui passe par « augmente de 1 »
    laisserait ses données sur la cible réelle. Avec `count=10` puis `count=11`, le SEUL id qui
    apparaît au-delà du relevé (§F1, domaine `id > 10`) est `11` : c'est ce que
    `_capturer_dernier_enregistrement` doit relayer à `register_created`."""
    _installer_shim_features_environment()
    ctx = _Context(count=10)
    ctx.created = {}
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=11)
    check_count_increased_by_one(ctx, MODEL)

    assert ctx.created == {MODEL: [11]}


def test_un_enregistrement_preexistant_verifie_par_ailleurs_n_est_jamais_enregistre():
    """Garde anti-régression inverse : seule la voie « augmente de 1 » (comptage PROUVÉ) doit
    déclencher `register_created`. Un `context` sans `.created` (les steps « … existe dans le
    modèle … » n'en posent pas) ne doit jamais lever — le best-effort documenté doit tenir."""
    _installer_shim_features_environment()
    ctx = _Context(count=10)  # pas de ctx.created : simule un contexte qui n'en a jamais eu besoin
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=11)
    check_count_increased_by_one(ctx, MODEL)  # ne doit pas lever malgré l'AttributeError interne

    assert ctx.last_record_ids == [11]


def test_snapshot_puis_augmentation_inattendue_echoue():
    """§F1 (2026-09-23) : deux créations DEPUIS le relevé, sans marqueur de tentative pour les
    départager, sont une AMBIGUÏTÉ signalée — jamais une simple comparaison `12 != 11` : c'est
    exactement le message que le lot demande (« … créations détectées … impossible de
    distinguer »), pas l'ancien « devrait être 11, obtenu 12 »."""
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=12)          # deux créations : le test DOIT échouer
    with pytest.raises(AssertionError, match="2 créations détectées"):
        check_count_increased_by_one(ctx, MODEL)


def test_snapshot_puis_pas_daugmentation_passe():
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    check_count_not_increased(ctx, MODEL)


def test_snapshot_puis_creation_indue_echoue():
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=11)
    with pytest.raises(AssertionError, match="créé.*malgré l'attente d'aucune création"):
        check_count_not_increased(ctx, MODEL)


# ── Le POSEUR de snapshot n'avale plus son erreur ────────────────────────────

def test_snapshot_impossible_echoue_a_la_pose():
    """Avant, l'exception était avalée : aucun snapshot posé, puis le @then passait en silence.
    Échouer ICI met la cause sous les yeux, là où elle est compréhensible."""
    with pytest.raises(AssertionError) as exc:
        memorize_record_count(_Context(count=0, boom=True), MODEL)
    assert "connexion RPC perdue" in str(exc.value)      # la cause d'origine est conservée
    assert "ne prouveraient rien" in str(exc.value)      # et l'enjeu est dit


# ── Garde du MOTIF, pas seulement des cas trouvés ────────────────────────────

def test_aucun_warn_puis_return_dans_les_helpers():
    """`warnings.warn(...)` suivi d'un `return` = un échec déguisé en succès.

    C'est le motif exact de 0011 : un test qui ne peut plus rien prouver continue quand même.
    Garde le fichier entier, pas les trois fonctions corrigées.
    """
    src = Path("behave_runtime/steps_library/_base_helpers.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    coupables = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for bloc in ast.walk(fn):
            corps = getattr(bloc, "body", None)
            if not isinstance(corps, list):
                continue
            for i, stmt in enumerate(corps[:-1]):
                est_warn = (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                            and getattr(stmt.value.func, "attr", "") == "warn")
                if est_warn and isinstance(corps[i + 1], ast.Return):
                    coupables.append(fn.name)
    assert not coupables, (
        f"`warn` + `return` dans {coupables} : un avertissement n'échoue pas un test. "
        f"Si la vérification ne peut pas se faire, il faut ÉCHOUER (0011), pas continuer.")
