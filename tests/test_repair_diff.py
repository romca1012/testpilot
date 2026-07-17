"""`0017` — rayon d'explosion d'une réparation, signalé au gate (détective, jamais bloquant).

L'agent réécrit le fichier ENTIER pour corriger un step : il peut abîmer du code qui marchait.
Mesuré le 2026-07-17 (cas 1) : l'échec était dans un step de baseline RPC, l'agent a réécrit
l'authentification au passage et l'a cassée. Rien ne le voyait — `reserved_steps` bloque la
collision de libellés, pas la réécriture d'un voisin.

⚠️ Ces tests portent autant sur les FAUX POSITIFS que sur les vrais : cette garde doit produire
la mesure qui dira, plus tard, si un blocage se justifie. Une garde qui crie tout le temps ne
mesure rien.
"""

from __future__ import annotations

from testpilot.generation import repair_diff

AUTH = '''from behave import given


@given("je suis authentifie")
def step_auth(context):
    """Authentification."""
    context.page.goto("/web/login")
    context.page.locator("input[name='login']").fill(context.user, force=True)


@given('le compteur de "{model}" est enregistre')
def step_baseline(context, model):
    context.baseline = context.odoo.env[model].search_count([])
'''

# Seul `step_baseline` change — la correction légitime, ciblée.
CIBLEE = AUTH.replace(
    "    context.baseline = context.odoo.env[model].search_count([])",
    "    context.baseline = len(context.odoo.env[model].search_read([], ['id']))")

# `step_baseline` est corrigé ET `step_auth` réécrit au passage — le défaut du cas 1.
LARGE = CIBLEE.replace(
    "    context.page.locator(\"input[name='login']\").fill(context.user, force=True)",
    "    context.page.fill(\"[name='login']\", context.user)")

# Le scénario d'auth a disparu avec son step : le dry-run n'y verrait RIEN.
AMPUTEE = '''from behave import given


@given('le compteur de "{model}" est enregistre')
def step_baseline(context, model):
    context.baseline = context.odoo.env[model].search_count([])
'''


# ── Ce que la garde doit voir ─────────────────────────────────────────────────

def test_une_reparation_qui_reecrit_un_step_voisin_est_signalee():
    """LE cas du 2026-07-17 : l'auth réécrite alors que l'échec était ailleurs."""
    warnings = repair_diff.blast_radius(AUTH, LARGE)
    touches = {w["step"] for w in warnings}
    assert "je suis authentifie" in touches, (
        "le step d'auth a été réécrit alors que l'échec portait sur la baseline — c'est "
        "exactement ce que cette garde existe pour montrer")
    assert all(w["kind"] == repair_diff.BODY_CHANGED for w in warnings)


def test_un_step_supprime_est_signale():
    """Le trou que le dry-run ne peut PAS voir : plus de `.feature` qui le réclame, donc rien
    d'`undefined` — la couverture recule en silence."""
    warnings = repair_diff.blast_radius(AUTH, AMPUTEE)
    assert [w["kind"] for w in warnings] == [repair_diff.STEP_REMOVED]
    assert warnings[0]["step"] == "je suis authentifie"
    assert "DISPARU" in warnings[0]["message"]


def test_le_resume_dit_l_essentiel_en_une_phrase():
    # `LARGE` est le défaut du cas 1 : la baseline corrigée (légitime) ET l'auth réécrite
    # (le dégât). Les deux steps ont bougé — et c'est précisément le chiffre qui doit alerter :
    # 2 steps touchés pour 1 échec.
    assert repair_diff.resume(AUTH, LARGE) == (
        "Réparation : 2 step(s) réécrit(s) sur 2 — rayon d'explosion à vérifier.")
    # Une correction ciblée, elle, n'en touche qu'un : le contraste est le message.
    assert repair_diff.resume(AUTH, CIBLEE) == (
        "Réparation : 1 step(s) réécrit(s) sur 2 — rayon d'explosion à vérifier.")


# ── Anti-faux-positif : la garde doit se taire quand il n'y a rien à dire ─────

def test_une_correction_CIBLEE_ne_signale_que_le_step_corrige():
    """La réparation idéale : un seul step touché. La garde doit le dire, et rien de plus."""
    warnings = repair_diff.blast_radius(AUTH, CIBLEE)
    assert [w["step"] for w in warnings] == ['le compteur de "{model}" est enregistre']


def test_un_fichier_identique_ne_signale_rien():
    assert repair_diff.blast_radius(AUTH, AUTH) == []
    assert repair_diff.resume(AUTH, AUTH) == ""


def test_un_step_AJOUTE_n_est_pas_une_regression():
    """Ajouter un step ne casse rien : le signaler serait une alerte inventée."""
    ajoute = AUTH + '\n\n@given("un nouveau step")\ndef step_neuf(context):\n    pass\n'
    assert repair_diff.blast_radius(AUTH, ajoute) == []


def test_les_commentaires_et_l_indentation_ne_comptent_pas():
    """On compare le CODE (AST), pas le texte : un commentaire ajouté n'est pas une réécriture."""
    commente = AUTH.replace('    """Authentification."""',
                            '    """Authentification."""\n    # ajout inoffensif')
    assert repair_diff.blast_radius(AUTH, commente) == []


def test_sans_version_precedente_lisible_la_garde_se_tait():
    """Pas de « avant » exploitable → rien à comparer → aucun cri."""
    assert repair_diff.blast_radius("", LARGE) == []
    assert repair_diff.blast_radius("ceci n'est pas du python (", LARGE) == []


def test_un_apres_illisible_ne_fait_pas_planter_la_garde():
    """Un fichier cassé est déjà rattrapé par le dry-run — la garde ne doit pas lever."""
    warnings = repair_diff.blast_radius(AUTH, "def (((")
    assert all(w["kind"] == repair_diff.STEP_REMOVED for w in warnings)


# ── Le contrat de sortie : le MÊME bandeau que le lint 0008 C ────────────────

def test_le_format_est_celui_des_lint_warnings():
    """Même contrat que `assertion_lint.lint_steps` : c'est le même bandeau qui les affiche."""
    from testpilot.api import schemas

    for w in repair_diff.blast_radius(AUTH, LARGE):
        assert set(w) == {"step", "line", "kind", "message"}
        schemas.LintWarning(**w)      # doit se sérialiser tel quel


# ── Au GATE : signalé, jamais bloquant (arbitrage du porteur) ─────────────────

def test_le_gate_signale_le_rayon_d_explosion_sans_jamais_bloquer(tmp_path, monkeypatch):
    """Preuve API : le bandeau remonte, et `allowed` n'est pas touché (invariant §4.3).

    Même régime que le lint `0008` C : bloquer automatiquement exigerait d'abord de mesurer le
    taux de faux positifs — c'est cette garde qui produira la mesure.
    """
    from fastapi.testclient import TestClient

    from testpilot import config as cfg
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo

    db = tmp_path / "g.db"
    monkeypatch.setattr(cfg, "DB_PATH", db)
    conn = get_initialized_db(db)
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas")
    v1 = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                  feature_content="# f", steps_content=AUTH, created_by="ia")
    v2 = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                  feature_content="# f", steps_content=LARGE,
                                  created_by="repair-agent")
    CaseRepo(conn).set_current_version(cid, v2)
    # Version APPROUVÉE : le gate autorise — la garde ne doit rien y changer.
    ReviewRepo(conn).create(test_case_id=cid, version_id=v2, decision="approved", reviewer="qa")
    conn.close()

    from testpilot.api.app import app
    gate = TestClient(app).get(f"/api/cases/{cid}").json()["gate"]

    assert gate["allowed"] is True, "la garde est DÉTECTIVE : elle ne touche jamais `allowed`"
    kinds = {w["kind"] for w in gate["lint_warnings"]}
    assert repair_diff.BODY_CHANGED in kinds
    assert "je suis authentifie" in {w["step"] for w in gate["lint_warnings"]}
    assert v1  # la version d'avant sert de référence


def test_une_version_NON_reparee_ne_declenche_aucun_signalement(tmp_path, monkeypatch):
    """Anti-faux-positif : une version écrite par la génération n'a pas de « avant » à comparer.

    Sans ce filtre, chaque re-génération crierait « rayon d'explosion » — la garde deviendrait du
    bruit et personne ne la lirait.
    """
    from fastapi.testclient import TestClient

    from testpilot import config as cfg
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo

    db = tmp_path / "h.db"
    monkeypatch.setattr(cfg, "DB_PATH", db)
    conn = get_initialized_db(db)
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas2")
    VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                             feature_content="# f", steps_content=AUTH, created_by="ia")
    v2 = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                  feature_content="# f", steps_content=LARGE, created_by="ia")
    CaseRepo(conn).set_current_version(cid, v2)
    ReviewRepo(conn).create(test_case_id=cid, version_id=v2, decision="approved", reviewer="qa")
    conn.close()

    from testpilot.api.app import app
    gate = TestClient(app).get(f"/api/cases/{cid}").json()["gate"]
    assert not [w for w in gate["lint_warnings"] if w["kind"] in
                (repair_diff.BODY_CHANGED, repair_diff.STEP_REMOVED)]
