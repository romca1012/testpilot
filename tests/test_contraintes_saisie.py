"""Contraintes de SAISIE — la 9ᵉ cause mesurée, et la plus perfide (2026-07-21).

⚠️ **Elle ne produit pas une erreur technique : elle produit un FAUX VERDICT.** Les huit causes
précédentes faisaient tomber le scénario avec une trace lisible ; celle-ci le laisse se dérouler
proprement jusqu'au bout, puis conclut « l'application est non conforme » — alors que
l'application a parfaitement raison.

Mesuré sur `/remboursement/{id}` : le champ `code_client1` porte `pattern="\\d{7}"` (sept chiffres,
exactement). Le test généré y écrivait « TEST_REMB_CLI001 ». Le navigateur **refuse la
soumission** — validation HTML native, silencieuse côté Playwright. Rien n'est créé. L'assertion
de création échoue. Verdict : `non_conforme`.

**C'est la donnée du test qui est invalide, pas l'application.** Un outil de test qui accuse à
tort est pire qu'un outil qui ne teste rien : il détruit la confiance dans ses propres verdicts.

Le correctif suit le motif habituel — *l'annuaire savait, personne ne transmettait* (9ᵉ
occurrence) — en trois couches, testées ici :
1. le crawl CAPTURE les contraintes (`pattern`, `minlength`/`maxlength`, `min`/`max`, `accept`) ;
2. `formulaires_requis` les EXPOSE ;
3. le prompt les DIT, en impératif, avec la conséquence.
"""

import json
import re
from pathlib import Path

import pytest

from testpilot.analysis.plan import TestPlan
from testpilot.generation import domain_model, prompt as pm

ANNUAIRE_REEL = Path("data/domain/projet-1.json")


def _plan(routes):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"],
                    portal_routes=routes, risks=[], connector_type="odoo", cost_usd=0.0,
                    raw_spec="SPEC", entry_url=routes[0] if routes else "")


def _modele(champs):
    return {"mesure_le": "2026-07-21", "pages": {"/form/{id}": {"champs": champs}},
            "transitions": {}, "onglets_internes": {}}


def _champ(name, **kw):
    base = {"name": name, "required": True, "tag": "input", "type": "text", "visible": True}
    return {**base, **kw}


# ── Couche 2 : l'annuaire EXPOSE les contraintes ──────────────────────────────

def test_les_contraintes_traversent_formulaires_requis():
    """La donnée manquante, à la source. `formulaires_requis` est le seul passage entre
    l'annuaire et la génération : ce qu'il n'expose pas n'existe pas pour l'agent."""
    modele = _modele([_champ("code_client1", contraintes={"pattern": r"\d{7}"},
                             label="Code client")])

    requis = domain_model.formulaires_requis(modele, ["/form/{id}"])[0]["requis"][0]

    assert requis["contraintes"] == {"pattern": r"\d{7}"}
    assert requis["label"] == "Code client"


def test_un_champ_sans_contrainte_expose_un_dictionnaire_vide_pas_None():
    """Le consommateur fait `if contraintes:` — `None` marcherait, mais un type stable évite
    d'avoir à s'en souvenir."""
    modele = _modele([_champ("nom")])

    requis = domain_model.formulaires_requis(modele, ["/form/{id}"])[0]["requis"][0]

    assert requis["contraintes"] == {}
    assert requis["label"] == ""


# ── Couche 3 : le prompt DIT la contrainte, et sa conséquence ────────────────

def test_le_prompt_donne_le_MOTIF_exact():
    """Le cas mesuré. Sans le motif, l'agent ne peut pas deviner « sept chiffres »."""
    modele = _modele([_champ("code_client1", contraintes={"pattern": r"\d{7}"},
                             label="Code client")])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert r"`\d{7}`" in s, "le motif doit être donné VERBATIM, pas paraphrasé"
    assert "EXACTEMENT" in s


def test_le_prompt_donne_le_LIBELLE_visible():
    """Le nom technique (`code_client1`) ne dit pas ce qu'on attend ; le libellé, si."""
    modele = _modele([_champ("montant_remb", type="number", label="Montant du remboursement")])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "Montant du remboursement" in s


def test_le_prompt_DIT_LA_CONSEQUENCE_pas_seulement_la_regle():
    """⚠️ Le cœur du correctif. Une règle sans conséquence se négocie ; une règle dont l'agent
    sait qu'elle produit un faux verdict ne se négocie plus. C'est la leçon des 8 causes
    précédentes : dire *pourquoi* a mieux marché que dire *quoi*."""
    modele = _modele([_champ("code_client1", contraintes={"pattern": r"\d{7}"})])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "bloque la soumission" in s
    assert "à tort" in s, "l'agent doit savoir que l'erreur accuse l'application injustement"


@pytest.mark.parametrize("contraintes, attendu", [
    ({"maxlength": "11"}, "11 caractères maximum"),
    ({"minlength": "8"}, "8 caractères minimum"),
    ({"minlength": "8", "maxlength": "11"}, "entre 8 et 11 caractères"),
    ({"min": "0"}, "valeur ≥ 0"),
    ({"max": "100"}, "valeur ≤ 100"),
    ({"min": "0", "max": "100"}, "valeur entre 0 et 100"),
    ({"accept": ".pdf,.png"}, "fichier de type .pdf,.png"),
])
def test_chaque_forme_de_contrainte_est_rendue(contraintes, attendu):
    """Les bornes ne sont pas décoratives : `min=0` sur un montant interdit un test à -50 qui
    croirait tester un refus applicatif."""
    modele = _modele([_champ("c", contraintes=contraintes)])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert attendu in s


@pytest.mark.parametrize("borne", ["date_now", "{{ today }}", "", "N/A"])
def test_une_borne_INEXPLOITABLE_est_tue(borne):
    """⚠️ Mesuré sur `/creance_douteux` : `<input type="date" max="date_now">` — un placeholder de
    gabarit qui a fui non résolu dans le HTML de l'application testée. Le navigateur l'ignore.

    Le transmettre produirait « valeur ≤ date_now » : une consigne impossible à satisfaire, sur un
    champ pourtant valide. Une mesure fidèle n'oblige pas à répéter le bruit qu'elle a capté."""
    modele = _modele([_champ("date_proc", type="date", contraintes={"max": borne})])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CONTRAINTE :" not in s
    assert borne not in s or not borne


@pytest.mark.parametrize("borne", ["0", "100", "-5.5", "2026-01-31"])
def test_une_borne_EXPLOITABLE_passe(borne):
    """Le garde-fou ne doit pas jeter les bornes légitimes avec le bruit."""
    modele = _modele([_champ("c", contraintes={"max": borne})])

    assert f"valeur ≤ {borne}" in pm._section_champs_requis(_plan(["/form/{id}"]), modele)


def test_le_motif_survit_meme_si_la_borne_est_inexploitable():
    """Écarter une borne ne doit pas emporter les autres contraintes du même champ."""
    modele = _modele([_champ("c", contraintes={"pattern": r"\d{7}", "max": "date_now"})])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert r"`\d{7}`" in s
    assert "date_now" not in s


def test_aucun_bruit_quand_le_formulaire_est_sans_contrainte():
    """Une alerte présente partout n'alerte plus nulle part."""
    modele = _modele([_champ("nom"), _champ("prenom")])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CONTRAINTE :" not in s
    assert "bloque la soumission" not in s


def test_un_champ_CACHE_contraint_n_encombre_pas_la_consigne():
    """Un champ injecté par le serveur n'est pas saisi par l'agent : sa contrainte ne le
    concerne pas. (Cohérence avec la 5ᵉ cause — champs requis cachés.)"""
    modele = _modele([
        _champ("visible_1"),
        _champ("cache", visible=False, contraintes={"pattern": r"\d{7}"}),
    ])

    s = pm._section_champs_requis(_plan(["/form/{id}"]), modele)

    assert "CONTRAINTE :" not in s


# ── Couche 1 + bout-en-bout : sur l'annuaire RÉEL ─────────────────────────────

def _modele_reel():
    if not ANNUAIRE_REEL.exists():
        pytest.skip("annuaire réel absent")
    return json.loads(ANNUAIRE_REEL.read_text(encoding="utf-8"))


def test_le_crawl_a_bien_CAPTURE_le_motif_qui_a_fausse_le_verdict():
    """La preuve que la couche 1 fonctionne, sur le champ exact qui a produit le faux
    `non_conforme`. Si ce test tombe, c'est que le crawl a régressé — et les faux verdicts
    reviendront sans bruit."""
    modele = _modele_reel()

    page = next((i for r, i in modele["pages"].items() if r.startswith("/remboursement")), None)
    if page is None:
        pytest.skip("route /remboursement absente de l'annuaire")
    champ = next(c for c in page["champs"] if c["name"] == "code_client1")

    assert champ.get("contraintes", {}).get("pattern"), "le motif doit être capturé"
    assert re.fullmatch(champ["contraintes"]["pattern"], "1234567"), "7 chiffres doivent passer"
    assert not re.fullmatch(champ["contraintes"]["pattern"], "TEST_REMB_CLI001"), (
        "la valeur qui a produit le faux verdict doit être rejetée par le motif")


def test_bout_en_bout_le_prompt_REEL_de_remboursement_porte_la_contrainte():
    """Du crawl jusqu'au prompt, sans script intermédiaire : c'est ce que l'agent lira."""
    modele = _modele_reel()
    if not any(r.startswith("/remboursement") for r in modele["pages"]):
        pytest.skip("route /remboursement absente de l'annuaire")

    s = pm._section_champs_requis(_plan(["/remboursement/{id}"]), modele)

    assert "code_client1" in s
    assert "CONTRAINTE" in s
    assert "bloque la soumission" in s


def test_l_identite_d_accessibilite_est_capturee_sur_l_annuaire_reel():
    """`role` + `label` : la base du composant « résolveur » (§2bis). On vérifie que la mesure
    les porte VRAIMENT — un annuaire enrichi à moitié donnerait un faux sentiment d'avance."""
    modele = _modele_reel()

    champs = [c for i in modele["pages"].values() for c in (i.get("champs") or [])]
    avec_role = [c for c in champs if c.get("role")]
    avec_label = [c for c in champs if c.get("label")]

    assert len(avec_role) > len(champs) * 0.5, (
        f"seulement {len(avec_role)}/{len(champs)} champs ont un rôle — ré-explorer le projet")
    assert avec_label, "aucun libellé capturé — ré-explorer le projet"
