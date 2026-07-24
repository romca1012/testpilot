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
"""

import itertools
import sqlite3

import pytest

from testpilot.verdict.status import (
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
    sql_statut,
    statut_de_test,
)

EXECUTIONS = [EXEC_SUCCESS, EXEC_TECHNICAL_ERROR, EXEC_NOT_EXECUTED, None]
FONCTIONNELS = [FUNC_CONFORME, FUNC_NON_CONFORME, FUNC_INDETERMINE, FUNC_NOT_EVALUATED,
                FUNC_DONNEE_INVALIDE, None]


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
    (EXEC_SUCCESS, FUNC_NOT_EVALUATED, STATUT_PASSED),
    (None, None, STATUT_UNTESTED),
])
def test_la_projection_des_deux_axes(execution, fonctionnel, attendu):
    assert statut_de_test(execution, fonctionnel) == attendu


def test_le_fonctionnel_PRIME_sur_l_execution():
    """Un test qui a techniquement tourné mais trouvé un écart est `failed`, pas `passed` :
    confondre les deux axes est exactement ce que le §5 interdit."""
    assert statut_de_test(EXEC_SUCCESS, FUNC_NON_CONFORME) == STATUT_FAILED


# ── Les deux formes ne peuvent pas diverger ──────────────────────────────────

def test_la_forme_SQL_donne_le_MEME_resultat_sur_TOUTES_les_combinaisons():
    """⚠️ Le test qui justifie l'existence de ce fichier.

    Deux implémentations d'une même règle divergent toujours — la seule question est quand, et
    combien de temps avant qu'on s'en aperçoive. Ici, la divergence est impossible à ignorer :
    24 combinaisons comparées une à une.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (ex TEXT, fo TEXT)")
    for ex, fo in itertools.product(EXECUTIONS, FONCTIONNELS):
        conn.execute("INSERT INTO t VALUES (?,?)", (ex, fo))
    conn.commit()

    requete = f"SELECT ex, fo, {sql_statut('ex', 'fo')} AS statut FROM t"
    ecarts = []
    for ex, fo, statut_sql in conn.execute(requete):
        attendu = statut_de_test(ex, fo)
        if statut_sql != attendu:
            ecarts.append(f"({ex!r}, {fo!r}) : SQL={statut_sql!r} ≠ Python={attendu!r}")
    conn.close()

    assert not ecarts, "les deux formes de la règle divergent :\n" + "\n".join(ecarts)


def test_toute_combinaison_rend_un_statut_CONNU():
    """Aucune paire ne doit produire une étiquette hors liste : un statut inconnu n'aurait ni
    libellé ni couleur à l'écran, et s'afficherait comme une valeur brute."""
    connus = {STATUT_PASSED, STATUT_FAILED, STATUT_RETEST, STATUT_BLOCKED, STATUT_UNTESTED}
    for ex, fo in itertools.product(EXECUTIONS, FONCTIONNELS):
        assert statut_de_test(ex, fo) in connus, f"({ex}, {fo})"
