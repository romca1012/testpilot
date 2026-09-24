"""Le STATUT DE LECTURE — une règle, deux formes, et la preuve qu'elles ne divergent pas.

**Ce qui a été corrigé le 2026-07-24.** La projection des deux axes du §5 en une étiquette unique
(`passed` / `failed` / `retest` / `blocked` / `untested`) vivait **uniquement en TypeScript**.
Filtrer une liste par statut côté serveur — ce qu'exige la pagination — aurait donc obligé à la
réécrire en SQL : deux implémentations de la même règle, qui divergent le jour où l'une évolue,
et dont l'écart est **invisible** puisque les deux « marchent ».

La règle a été déplacée dans `verdict/status.py`. Il en reste malgré tout **deux formes** — une
fonction Python et une expression SQL — parce qu'on ne peut pas filtrer 2 000 lignes en Python
sans les charger. Ce fichier existe pour que ces deux formes ne puissent pas se contredire :
il les compare sur **toutes** les combinaisons possibles.

**Étendu à l'exécution MANUELLE.** La règle a gagné une troisième entrée : le statut SAISI par un
humain qui a joué le test à la main. Il ne se mélange pas aux deux axes, il les court-circuite —
saisir « passed » ne doit jamais faire croire qu'une machine a mesuré `success`/`conforme`. La
comparaison Python ↔ SQL couvre donc maintenant cette entrée aussi, y compris ses valeurs
*refusées* (`untested`, inconnue), qui doivent laisser la dérivation reprendre la main.
"""

import itertools
import sqlite3

import pytest

from testpilot.verdict.status import (
    EXEC_BLOCKED,
    EXEC_NOT_EXECUTED,
    EXEC_SUCCESS,
    EXEC_TECHNICAL_ERROR,
    FUNC_CONFORME,
    FUNC_DONNEE_INVALIDE,
    FUNC_INDETERMINE,
    FUNC_NON_CONFORME,
    FUNC_NOT_EVALUATED,
    STATUT_BLOCKED,
    STATUT_FAILED,
    STATUT_PASSED,
    STATUT_RETEST,
    STATUT_UNTESTED,
    STATUTS_MANUELS,
    sql_statut,
    statut_de_test,
)

EXECUTIONS = [EXEC_SUCCESS, EXEC_TECHNICAL_ERROR, EXEC_BLOCKED, EXEC_NOT_EXECUTED, None]
FONCTIONNELS = [FUNC_CONFORME, FUNC_NON_CONFORME, FUNC_INDETERMINE, FUNC_NOT_EVALUATED,
                FUNC_DONNEE_INVALIDE, None]
# Les valeurs REFUSÉES comptent autant que les acceptées : c'est sur elles que les deux formes
# risquent le plus de diverger (un `<> ''` côté SQL laisserait passer 'untested' et 'bidon').
MANUELS = [None, "", *STATUTS_MANUELS, STATUT_UNTESTED, "n_importe_quoi"]


# ── La règle elle-même ───────────────────────────────────────────────────────

@pytest.mark.parametrize("execution,fonctionnel,attendu", [
    (EXEC_SUCCESS, FUNC_CONFORME, STATUT_PASSED),
    (EXEC_SUCCESS, FUNC_NON_CONFORME, STATUT_FAILED),
    # ⚠️ Le 4ᵉ verdict ne devient JAMAIS `failed` : ce serait accuser l'application alors que
    # c'est la donnée du test qui était irrecevable. Ni `passed` : rien n'a été prouvé.
    (EXEC_SUCCESS, FUNC_DONNEE_INVALIDE, STATUT_RETEST),
    (EXEC_SUCCESS, FUNC_INDETERMINE, STATUT_RETEST),
    (EXEC_NOT_EXECUTED, FUNC_INDETERMINE, STATUT_UNTESTED),
    (EXEC_TECHNICAL_ERROR, FUNC_NOT_EVALUATED, STATUT_BLOCKED),
    # Lot 02 (D1) : `blocked` AVANT la règle `indetermine → retest`.
    (EXEC_BLOCKED, FUNC_INDETERMINE, STATUT_BLOCKED),
    (EXEC_BLOCKED, FUNC_NOT_EVALUATED, STATUT_BLOCKED),
    (EXEC_BLOCKED, FUNC_NON_CONFORME, STATUT_FAILED),  # un constat surface toujours
    (EXEC_SUCCESS, FUNC_NOT_EVALUATED, STATUT_PASSED),
    (None, None, STATUT_UNTESTED),
])
def test_la_projection_des_deux_axes(execution, fonctionnel, attendu):
    assert statut_de_test(execution, fonctionnel) == attendu


def test_le_fonctionnel_PRIME_sur_l_execution():
    """Un test qui a techniquement tourné mais trouvé un écart est `failed`, pas `passed` :
    confondre les deux axes est exactement ce que le §5 interdit."""
    assert statut_de_test(EXEC_SUCCESS, FUNC_NON_CONFORME) == STATUT_FAILED


# ── Le statut SAISI À LA MAIN court-circuite, il ne se mélange pas ───────────

def test_un_statut_saisi_a_la_main_PRIME_sur_les_deux_axes():
    """Un humain qui constate « bloqué » sur un cas dont la dernière mesure disait « conforme »
    doit voir « bloqué ». Sinon l'exécution manuelle ne servirait à rien : elle serait écrasée
    par une mesure que l'humain vient précisément de contredire."""
    assert statut_de_test(EXEC_SUCCESS, FUNC_CONFORME, STATUT_BLOCKED) == STATUT_BLOCKED


def test_un_cas_JAMAIS_mesure_par_la_machine_a_quand_meme_un_statut():
    """Le cas d'usage qui justifie toute l'exécution manuelle : un cas non automatisable n'a
    aucune mesure (pas d'axes du tout), et son résultat vient entièrement de l'humain."""
    assert statut_de_test(None, None, STATUT_PASSED) == STATUT_PASSED


@pytest.mark.parametrize("manuel", [None, "", STATUT_UNTESTED, "n_importe_quoi"])
def test_un_statut_manuel_REFUSE_laisse_la_derivation_reprendre(manuel):
    """⚠️ `untested` n'est pas saisissable : le saisir serait indiscernable de « pas encore de
    résultat ». Une valeur inconnue ne doit pas davantage devenir une étiquette — sans quoi elle
    s'afficherait brute, sans libellé ni couleur. Dans les deux cas, les axes reprennent la main.
    """
    assert statut_de_test(EXEC_SUCCESS, FUNC_NON_CONFORME, manuel) == STATUT_FAILED


def test_sans_statut_manuel_le_comportement_est_INCHANGE():
    """Le 3ᵉ paramètre est optionnel et arrive en dernier : les ~6 appelants existants n'ont pas
    bougé, et doivent continuer à rendre exactement ce qu'ils rendaient."""
    for ex, fo in itertools.product(EXECUTIONS, FONCTIONNELS):
        assert statut_de_test(ex, fo) == statut_de_test(ex, fo, None)


def test_la_forme_SQL_SANS_statut_manuel_est_identique_a_l_ancienne():
    """Même garde, côté SQL : `sql_statut(a, b)` ne doit pas avoir changé d'un caractère, sinon
    les requêtes existantes (filtre de la liste des cas) changeraient de comportement en silence."""
    assert sql_statut("ex", "fo") == sql_statut("ex", "fo", None)


# ── Les deux formes ne peuvent pas diverger ──────────────────────────────────

def test_la_forme_SQL_donne_le_MEME_resultat_sur_TOUTES_les_combinaisons():
    """⚠️ Le test qui justifie l'existence de ce fichier.

    Deux implémentations d'une même règle divergent toujours — la seule question est quand, et
    combien de temps avant qu'on s'en aperçoive. Ici, la divergence est impossible à ignorer :
    240 combinaisons comparées une à une (5 exécutions × 6 fonctionnels × 8 statuts manuels) — `blocked`
    (lot 02, D1) compris : sa règle doit exister DANS LES DEUX FORMES.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (ex TEXT, fo TEXT, de TEXT)")
    for ex, fo, de in itertools.product(EXECUTIONS, FONCTIONNELS, MANUELS):
        conn.execute("INSERT INTO t VALUES (?,?,?)", (ex, fo, de))
    conn.commit()

    requete = f"SELECT ex, fo, de, {sql_statut('ex', 'fo', 'de')} AS statut FROM t"
    ecarts = []
    for ex, fo, de, statut_sql in conn.execute(requete):
        attendu = statut_de_test(ex, fo, de)
        if statut_sql != attendu:
            ecarts.append(f"({ex!r}, {fo!r}, {de!r}) : SQL={statut_sql!r} ≠ Python={attendu!r}")
    conn.close()

    assert not ecarts, "les deux formes de la règle divergent :\n" + "\n".join(ecarts)


def test_toute_combinaison_rend_un_statut_CONNU():
    """Aucune combinaison ne doit produire une étiquette hors liste : un statut inconnu n'aurait
    ni libellé ni couleur à l'écran, et s'afficherait comme une valeur brute. Le statut manuel
    est inclus — c'est justement lui qui peut porter n'importe quoi si la base est corrompue."""
    connus = {STATUT_PASSED, STATUT_FAILED, STATUT_RETEST, STATUT_BLOCKED, STATUT_UNTESTED}
    for ex, fo, de in itertools.product(EXECUTIONS, FONCTIONNELS, MANUELS):
        assert statut_de_test(ex, fo, de) in connus, f"({ex}, {fo}, {de})"


def test_untested_n_est_PAS_saisissable():
    """La liste des statuts manuels est le contrat que la base (CHECK) et l'écran de saisie
    doivent respecter. `untested` doit en être absent : sinon un humain pourrait saisir « non
    testé », une ligne qui n'affirme rien et qu'on ne saurait pas distinguer d'une absence de
    résultat."""
    assert STATUT_UNTESTED not in STATUTS_MANUELS
    assert set(STATUTS_MANUELS) == {STATUT_PASSED, STATUT_FAILED, STATUT_RETEST, STATUT_BLOCKED}
