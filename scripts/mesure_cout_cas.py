"""Mesure du §9 : ce qu'un cas coûte réellement — lu au ledger, pas estimé.

    PYTHONUTF8=1 python scripts/mesure_cout_cas.py

Lit `cost_ledger` (la seule trace réelle) et confronte le total par cas au §9 du brief
(« moins de 1 € pour un nouveau cas de test »). Aucun appel LLM : ce script ne dépense rien,
il ne fait que lire ce qui a déjà été payé.

⚠️ CE QUE CE SCRIPT NE PEUT PAS FAIRE : mesurer un cas à 2 réparations. Aucun n'existe — le
ledger n'a **qu'une seule** réparation réelle. Le chiffre « $1,0319 » qui circule est une
**extrapolation** (génération + 2 × la réparation mesurée), jamais une mesure. Le script le dit
au lieu de le maquiller en donnée.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot import config  # noqa: E402


def main() -> None:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 78)
    print("MESURE DU §9 — « moins de 1 € par nouveau cas de test »")
    print(f"Plafond : {config.BUDGET_PER_CASE_EUR:.2f} EUR x {config.EUR_USD_RATE} = "
          f"${config.BUDGET_PER_CASE_USD:.4f}")
    print("=" * 78)

    lignes = list(conn.execute(
        "SELECT c.id, c.execution_id, c.phase, c.model, c.cost_usd, c.source, e.test_case_id"
        " FROM cost_ledger c LEFT JOIN execution e ON e.id = c.execution_id ORDER BY c.id"))

    if not lignes:
        print("\n⚠️  LEDGER VIDE — rien n'a jamais été mesuré. Aucune conclusion possible.")
        return

    print("\n-- Lignes réelles du ledger " + "-" * 50)
    for r in lignes:
        print(f"  #{r['id']:<3} cas {str(r['test_case_id'] or '?'):<3} "
              f"{r['phase']:<11} {r['model']:<28} ${r['cost_usd']:.4f}  ({r['source']})")

    print("\n-- Total par cas " + "-" * 61)
    totaux = list(conn.execute(
        "SELECT e.test_case_id AS cas, ROUND(SUM(c.cost_usd), 6) AS total, COUNT(*) AS n"
        " FROM cost_ledger c JOIN execution e ON e.id = c.execution_id"
        " GROUP BY e.test_case_id ORDER BY total DESC"))
    for r in totaux:
        pct = 100 * r["total"] / config.BUDGET_PER_CASE_USD
        etat = "OK" if r["total"] <= config.BUDGET_PER_CASE_USD else "DEPASSE"
        print(f"  cas {r['cas']:<3} ${r['total']:.4f}  =  {pct:5.1f} % du §9   "
              f"({r['n']} appel(s))  [{etat}]")

    # Décomposition par phase — le total sans l'explication n'apprend rien.
    print("\n-- Détail par phase " + "-" * 58)
    for r in conn.execute(
            "SELECT c.phase, COUNT(*) AS n, ROUND(SUM(c.cost_usd), 6) AS total,"
            " ROUND(AVG(c.cost_usd), 6) AS moy FROM cost_ledger c GROUP BY c.phase"):
        print(f"  {r['phase']:<12} {r['n']} appel(s)   total ${r['total']:.4f}   "
              f"moyenne ${r['moy']:.4f}")

    gen = conn.execute(
        "SELECT AVG(cost_usd) AS m, COUNT(*) AS n FROM cost_ledger WHERE phase='generation'"
    ).fetchone()
    rep = conn.execute(
        "SELECT AVG(cost_usd) AS m, COUNT(*) AS n FROM cost_ledger WHERE phase='repair'"
    ).fetchone()

    print("\n" + "=" * 78)
    print("CALIBRAGE DU GARDE-FOU (§6/§11.2) — contre les chiffres ci-dessus")
    print("=" * 78)
    print(f"  Plafond réparations/cas configuré : "
          f"${config.REPAIR_COST_LIMIT_PER_CASE_USD:.4f}")
    print(f"  Budget tentatives par défaut      : {config.REPAIR_BUDGET_DEFAULT}")

    if gen["n"]:
        marge = config.BUDGET_PER_CASE_USD - gen["m"]
        print(f"\n  §9 ${config.BUDGET_PER_CASE_USD:.4f} − génération mesurée ${gen['m']:.4f} "
              f"= ${marge:.4f} pour TOUTES les réparations du cas")
        verdict = "OK" if config.REPAIR_COST_LIMIT_PER_CASE_USD <= marge else "TROP HAUT"
        print(f"  → plafond configuré ${config.REPAIR_COST_LIMIT_PER_CASE_USD:.4f} : [{verdict}]")

    if rep["n"]:
        pire = config.REPAIR_BUDGET_DEFAULT * rep["m"]
        print(f"\n  Pire cas au budget par défaut : {config.REPAIR_BUDGET_DEFAULT} x "
              f"${rep['m']:.4f} = ${pire:.4f}")
        verdict = "OK" if pire <= config.REPAIR_COST_LIMIT_PER_CASE_USD else "DEPASSE LE PLAFOND"
        print(f"  → contre le plafond ${config.REPAIR_COST_LIMIT_PER_CASE_USD:.4f} : [{verdict}]")
        if gen["n"]:
            total = gen["m"] + pire
            v = "OK" if total <= config.BUDGET_PER_CASE_USD else "DEPASSE LE §9"
            print(f"  → cas complet extrapolé : ${gen['m']:.4f} + ${pire:.4f} = ${total:.4f}"
                  f"  ({100 * total / config.BUDGET_PER_CASE_USD:.1f} % du §9)  [{v}]")

    print("\n" + "=" * 78)
    print("CE QUI N'EST PAS MESURÉ — à lire avant de citer un chiffre")
    print("=" * 78)
    print(f"  • Réparations réellement mesurées : {rep['n'] or 0}. Un cas à 2 réparations"
          " n'existe pas en base :")
    print("    tout chiffre pour 2 tentatives est une EXTRAPOLATION (n x la moyenne), pas une"
          " mesure.")
    print("  • Les 5 réparations d'avant le correctif de comptabilité (v7→v11) n'ont laissé"
          " AUCUNE trace :")
    print("    elles sont irrécupérables.")
    print("  • Le coût unitaire d'une réparation a CHANGÉ depuis sa mesure : elle a été mesurée"
          " avec")
    print("    dry_runner=None, donc 2 appels LLM par tentative (l'écriture + un tour perdu).")
    print("    Le dry-run étant branché, le chemin heureux n'en fait plus qu'UN. Le vrai chiffre"
          " est")
    print("    probablement PLUS BAS — non mesuré, à reprendre au prochain rejeu réel.")

    conn.close()


if __name__ == "__main__":
    main()
