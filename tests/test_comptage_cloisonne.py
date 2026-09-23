"""Lot 01 du plan de fiabilité du verdict (2026-09-23, F1) — comptages cloisonnés au scénario.

Le défaut corrigé : `search_count([])` compare TOUT le modèle, jamais seulement ce que CE
scénario a produit. Sur une instance partagée, un tiers qui crée pendant que le scénario échoue
donne un faux `conforme` ; un tiers qui crée EN PLUS du scénario donne un faux `non_conforme`.

Tests déterministes sans Odoo : un faux `context` reproduit `context.odoo.env[model]` avec des
ids explicites (`_FakeModel`/`_Context` de `test_comptage_falsifiable.py`, réutilisés ici).
"""

from __future__ import annotations

import pytest

from behave_runtime.steps_library._base_helpers import (
    check_count_increased_by_one,
    check_count_not_increased,
    memorize_record_count,
)
from tests.test_comptage_falsifiable import (
    MODEL,
    _Context,
    _FakeOdoo,
    _installer_shim_features_environment,
)


# ── LE défaut corrigé : un tiers ne doit JAMAIS faire gagner le scénario ─────────────────────

def test_GARDE_tiers_cree_pendant_que_le_scenario_echoue_ne_passe_pas_a_tort():
    """Le scénario a posé un jeton de tentative (« … rendue unique … ») pour le champ `name`,
    mais SA création n'a jamais abouti (silence applicatif, cf. le refus mesuré en run réel le
    23/09) — SEUL un tiers, sans rapport, crée un enregistrement pendant ce temps. Le marqueur ne
    trouve rien qui le porte : la création du scénario reste PROUVÉE ABSENTE, quel que soit ce
    qu'un tiers a produit à côté.

    ⚠️ Preuve du défaut sur L'ANCIEN CODE (avant ce lot) : `check_count_increased_by_one`
    comparait `search_count([]) == initial + 1` — le tiers fait passer le compte global de 10 à
    11, EXACTEMENT la condition qui faisait `PASSER` l'ancien code À TORT (faux `conforme`).
    Rejoué avec l'ancien corps de fonction (commande ci-dessous, sortie collée dans le rapport de
    lot) : `search_count([]) == 11` est vrai, aucune AssertionError n'est levée — le scénario
    « réussit » sans avoir rien créé lui-même.
    """
    ctx = _Context(count=10, champs={})
    memorize_record_count(ctx, MODEL)
    # Le scénario a rempli "name" avec un jeton, mais RIEN ne le porte encore.
    ctx._tp_derniere_valeur_unique = ("name", "jeton-scenario-x1")
    # Le tiers crée l'id 11, SANS le jeton du scénario (un enregistrement banal, sans rapport).
    ctx.odoo = _FakeOdoo(ids=[*range(1, 11), 11], champs={11: {"name": "Ticket du tiers"}})

    with pytest.raises(AssertionError):
        check_count_increased_by_one(ctx, MODEL)


# ── Scénario + tiers, avec et sans marqueur ───────────────────────────────────────────────────

def test_scenario_cree_1_tiers_cree_1_avec_marqueur_isole_le_bon_id():
    """Deux créations DEPUIS le relevé (12, 13) ; seule 13 porte le jeton du scénario — le
    marqueur doit isoler EXACTEMENT celle-là, jamais les deux, jamais la mauvaise."""
    _installer_shim_features_environment()
    ctx = _Context(count=11, champs={})
    ctx.created = {}
    memorize_record_count(ctx, MODEL)
    ctx._tp_derniere_valeur_unique = ("name", "jeton-scenario-x2")
    ctx.odoo = _FakeOdoo(
        ids=[*range(1, 12), 12, 13],
        champs={12: {"name": "Création du tiers, sans rapport"},
               13: {"name": "Titre saisi par le scénario jeton-scenario-x2"}})

    check_count_increased_by_one(ctx, MODEL)

    assert ctx.last_record_ids == [13]
    assert ctx.created == {MODEL: [13]}


def test_scenario_cree_1_tiers_cree_1_sans_marqueur_echoue_avec_2_creations():
    """Sans marqueur pour départager, deux créations concurrentes restent une AMBIGUÏTÉ signalée
    — jamais un succès par défaut sur la première ou la dernière trouvée."""
    ctx = _Context(count=11)
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=13)  # ids 12 et 13 créés depuis le relevé, sans marqueur

    with pytest.raises(AssertionError, match="2 créations détectées"):
        check_count_increased_by_one(ctx, MODEL)


# ── `check_count_not_increased` : mêmes garanties côté négatif ───────────────────────────────

def test_not_increased_tiers_cree_1_sans_marqueur_echoue_avec_ids_liste():
    ctx = _Context(count=10)
    memorize_record_count(ctx, MODEL)
    ctx.odoo = _FakeOdoo(count=11)  # un tiers a créé l'id 11

    with pytest.raises(AssertionError, match=r"ids \[11\]"):
        check_count_not_increased(ctx, MODEL)


def test_not_increased_avec_marqueur_et_tiers_NON_marque_passe():
    """Le scénario a posé un jeton mais n'a rien créé lui-même ; le tiers crée un enregistrement
    SANS ce jeton. `check_count_not_increased` doit passer : rien de ce que le marqueur désigne
    n'est apparu, peu importe l'activité concurrente non liée."""
    ctx = _Context(count=10, champs={})
    memorize_record_count(ctx, MODEL)
    ctx._tp_derniere_valeur_unique = ("name", "jeton-scenario-x3")
    ctx.odoo = _FakeOdoo(ids=[*range(1, 11), 11], champs={11: {"name": "Autre chose"}})

    check_count_not_increased(ctx, MODEL)  # ne doit PAS lever


# ── Enregistrement archivé (active_test=False) ────────────────────────────────────────────────

def test_un_enregistrement_archive_par_laction_testee_est_compte():
    """`active_test=False` sur le relevé du max id ET sur la recherche des créations : un
    workflow qui archive aussitôt l'enregistrement créé (ex. `active` mis à False par une
    automatisation) ne doit pas faire disparaître la preuve de création."""
    _installer_shim_features_environment()
    ctx = _Context(count=10)
    ctx.created = {}
    memorize_record_count(ctx, MODEL)
    # `_FakeModel.search` ne filtre pas sur `active` : simule un modèle dont le SEUL id nouveau
    # (11) est déjà archivé — représentatif tant que `with_context(active_test=False)` est bien
    # appelé (vérifié séparément par la garde ci-dessous, qui échouerait sinon avec `count=0`).
    ctx.odoo = _FakeOdoo(count=11)

    check_count_increased_by_one(ctx, MODEL)

    assert ctx.last_record_ids == [11]


def test_memorize_et_crees_appellent_bien_with_context_active_test_false():
    """Garde du MOTIF, pas seulement d'un cas : sans `with_context(active_test=False)`, un
    enregistrement archivé entre le relevé et le contrôle disparaîtrait des deux recherches."""
    appels = []

    class _EnvEspion:
        def __init__(self, delegue):
            self._delegue = delegue

        def with_context(self, **kw):
            appels.append(kw)
            return self._delegue

        def __getattr__(self, nom):
            return getattr(self._delegue, nom)

    ctx = _Context(count=10)
    ctx.odoo.env = type(ctx.odoo.env)(count=10)
    reel = ctx.odoo.env._m
    ctx.odoo.env = type("E", (), {"__getitem__": lambda self, m: _EnvEspion(reel)})()

    memorize_record_count(ctx, MODEL)

    assert {"active_test": False} in appels


# ── Contrôle sans relevé préalable : erreur de CODE DE TEST ──────────────────────────────────

def test_controle_sans_aucun_relevé_leve_AssertionError_historique():
    """`_require_snapshot` (appelé en premier) reste le signal historique — inchangé par ce lot,
    protégé par `test_comptage_falsifiable.py`. Vérifié ici pour mémoire, pas dupliqué."""
    with pytest.raises(AssertionError, match="point de comparaison"):
        check_count_increased_by_one(_Context(count=5), MODEL)


def test_max_id_absent_alors_que_le_compte_est_present_leve_RuntimeError():
    """§F1, point 5 : si `memorize_record_count` n'a PAS posé l'id maximal (état incohérent,
    faute d'écriture du test — ex. un ancien `context` réutilisé hors de son scénario), l'erreur
    doit être une `RuntimeError` [code de test], jamais une `AssertionError` [désaccord sur le
    comportement de l'application] : les deux causes ne doivent jamais se confondre à l'écran."""
    from behave_runtime.steps_library._base_helpers import _count_attr

    ctx = _Context(count=10)
    setattr(ctx, _count_attr(MODEL), 10)  # compte posé, id maximal PAS posé : état incohérent

    with pytest.raises(RuntimeError, match=r"\[code de test\]"):
        check_count_increased_by_one(ctx, MODEL)
