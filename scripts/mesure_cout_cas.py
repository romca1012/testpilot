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
from testpilot.store.repositories import CostRepo  # noqa: E402


def main() -> None:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 78)
    print("MESURE DU §9 — « moins de 1 € par nouveau cas de test »")
    print(f"Plafond : {config.BUDGET_PER_CASE_EUR:.2f} EUR x {config.EUR_USD_RATE} = "
          f"${config.BUDGET_PER_CASE_USD:.4f}")
    print("=" * 78)

    # ⚠️ On lit `test_case_id` DIRECTEMENT (migration 12), jamais par `JOIN execution` : une
    # génération n'a pas d'exécution, la jointure la rendrait invisible. Ce script faisait
    # justement cette erreur — il affichait « cas ? » pour tout ce qui vient de l'écran.
    lignes = list(conn.execute(
        "SELECT id, test_case_id, execution_id, phase, model, cost_usd, source"
        " FROM cost_ledger ORDER BY id"))

    if not lignes:
        print("\n⚠️  LEDGER VIDE — rien n'a jamais été mesuré. Aucune conclusion possible.")
        return

    print("\n-- Lignes réelles du ledger " + "-" * 50)
    for r in lignes:
        cas = r["test_case_id"]
        # Un `?` ici n'est plus un artefact d'affichage : c'est une dépense ORPHELINE, qui
        # échappe au §9. À signaler, pas à masquer.
        marque = str(cas) if cas is not None else "?!"
        print(f"  #{r['id']:<3} cas {marque:<3} "
              f"{r['phase']:<11} {r['model']:<28} ${r['cost_usd']:.4f}  ({r['source']})")
    orphelines = [r for r in lignes if r["test_case_id"] is None]
    if orphelines:
        print(f"\n  ⚠️  {len(orphelines)} ligne(s) SANS cas rattaché "
              f"(${sum(r['cost_usd'] for r in orphelines):.4f}) — invisibles au §9.")

    # ⚠️ DEUX MÉTRIQUES, DEUX QUESTIONS — les confondre fabrique une alarme fausse, et c'est
    # arrivé : le cas 1 affichait « 107 % du §9 [DEPASSE] » alors que le §9 est tenu à 11 %.
    #   création = analyse + génération  → CE QUI SE COMPARE AU §9 (le brief dit « nouveau cas »)
    #   total    = tout depuis toujours  → télémétrie de debug, JAMAIS comparée au seuil
    print("\n-- Par cas : CRÉATION (le §9) vs RUN (exécution, SANS seuil) vs TOTAL " + "-" * 8)
    print(f"  {'cas':<5} {'création':>10} {'% du §9':>9}  {'':<8} {'run (exéc.)':>12}  {'total vie':>10}")
    repo = CostRepo(conn)
    cas_ids = [r["cas"] for r in conn.execute(
        "SELECT DISTINCT test_case_id AS cas FROM cost_ledger WHERE test_case_id IS NOT NULL"
        " ORDER BY test_case_id")]
    for cid in cas_ids:
        creation = repo.creation_cost_usd(cid)
        run = repo.run_cost_usd(cid)
        total = repo.total_for_case_usd(cid)
        pct = 100 * creation / config.BUDGET_PER_CASE_USD
        etat = "OK" if creation <= config.BUDGET_PER_CASE_USD else "DEPASSE LE §9"
        print(f"  {cid:<5} ${creation:>9.4f} {pct:>8.1f} %  [{etat:<6}] ${run:>11.4f}  ${total:>9.4f}")
    print("\n  Le §9 se juge sur la CRÉATION. Le RUN (réparations) est SUIVI mais SANS seuil cible")
    print("  — on mesure d'abord, on calibrera après plusieurs runs de cas distincts. Un run PROPRE")
    print("  coûte $0 (aucun LLM) : Behave/Playwright/odoorpc et le diagnostic ne dépensent rien.")

    # Décomposition par phase — le total sans l'explication n'apprend rien.
    print("\n-- Détail par phase " + "-" * 58)
    for r in conn.execute(
            "SELECT c.phase, COUNT(*) AS n, ROUND(SUM(c.cost_usd), 6) AS total,"
            " ROUND(AVG(c.cost_usd), 6) AS moy FROM cost_ledger c GROUP BY c.phase"):
        print(f"  {r['phase']:<12} {r['n']} appel(s)   total ${r['total']:.4f}   "
              f"moyenne ${r['moy']:.4f}")

    # ⚠️ **On ne MOYENNE PAS les générations.** Le ledger en mêle deux RÉGIMES : celles d'avant
    # les garde-fous (2026-07-15, l'agent réinventait tout : 15 312 car. de steps → $0,4529) et
    # celles d'après (catalogue 0003 + notes 0012 + contrat 0007 A1 : 1 973 car. → ~$0,105, avec
    # PLUS de couverture). Leur moyenne ($0,22) ne décrit aucun régime réel — c'est un chiffre
    # qui n'est jamais arrivé. On montre donc le DERNIER (ce que ça coûte aujourd'hui) et le PIRE
    # (ce sur quoi un plafond se calibre).
    gen_dernier = conn.execute(
        "SELECT cost_usd, created_at FROM cost_ledger WHERE phase='generation'"
        " ORDER BY id DESC LIMIT 1"
    ).fetchone()
    gen_pire = conn.execute(
        "SELECT MAX(cost_usd) AS m, COUNT(*) AS n FROM cost_ledger WHERE phase='generation'"
    ).fetchone()
    ana_dernier = conn.execute(
        "SELECT cost_usd FROM cost_ledger WHERE phase='analysis' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    rep = conn.execute(
        "SELECT AVG(cost_usd) AS m, COUNT(*) AS n FROM cost_ledger WHERE phase='repair'"
    ).fetchone()

    print("\n" + "=" * 78)
    print("CALIBRAGE DES GARDE-FOUS (§6/§11.2) — contre les chiffres ci-dessus")
    print("=" * 78)
    print(f"  Plafond génération / run     : ${config.COST_LIMIT_PER_RUN_USD:.4f}")
    print(f"  Plafond réparations / cas    : ${config.REPAIR_COST_LIMIT_PER_CASE_USD:.4f}")
    print(f"  Budget tentatives par défaut : {config.REPAIR_BUDGET_DEFAULT}")

    if gen_dernier:
        actuel = float(gen_dernier["cost_usd"])
        quand = str(gen_dernier["created_at"])[:10]
        pire = float(gen_pire["m"])
        print(f"\n  Génération — DERNIÈRE au ledger : ${actuel:.4f}   (mesurée le {quand})")
        print(f"  Génération — PIRE au ledger     : ${pire:.4f}")
        # ⚠️ Le ledger peut ne plus contenir AUCUNE mesure du régime actuel : les artefacts de la
        # mesure du chemin écran (cas 7/8) ont été retirés du référentiel sur décision du porteur,
        # et leurs lignes sont parties avec — un coût rattaché à un cas supprimé est un mensonge.
        # Sans ce garde-fou, on lirait « dernière mesure : $0,4529 » et on conclurait que c'est le
        # coût d'aujourd'hui. C'est le coût d'AVANT les garde-fous.
        if quand < "2026-07-17":
            print("\n  ⚠️  CETTE MESURE EST D'AVANT LES GARDE-FOUS — ce n'est PAS le coût actuel.")
            print("      Régime actuel MESURÉ le 2026-07-17 (chemin écran, spec demande_materiel) :")
            print("        analyse $0,0157 + génération $0,1050 = $0,1207 = 11 % du §9")
            print("      Même spec : 1 973 car. de steps contre 15 312, et PLUS de couverture")
            print("      (4 scénarios / 44 assertions contre 3). Le catalogue (0003), les notes")
            print("      (0012) et le contrat {field} (0007 A1) ont divisé la génération par ~4.")
            print("      Ces chiffres vivent dans tests/test_repair_cost_cap.py (gardés par test)")
            print("      et se reproduisent : scripts/mesure_generation_chemin_ecran.py (~$0,12).")
        v = "OK" if config.COST_LIMIT_PER_RUN_USD > pire else "COUPERAIT UNE GÉNÉRATION CONNUE"
        print(f"\n  → plafond ${config.COST_LIMIT_PER_RUN_USD:.2f} vs pire mesurée : [{v}]")

    if rep["n"]:
        cout_rep = config.REPAIR_BUDGET_DEFAULT * rep["m"]
        print(f"\n  Réparations au budget par défaut : {config.REPAIR_BUDGET_DEFAULT} x "
              f"${rep['m']:.4f} = ${cout_rep:.4f}")
        v = "OK" if cout_rep <= config.REPAIR_COST_LIMIT_PER_CASE_USD else "DEPASSE LE PLAFOND"
        print(f"  → contre le plafond ${config.REPAIR_COST_LIMIT_PER_CASE_USD:.4f} : [{v}]")

        if gen_dernier and ana_dernier:
            creation = float(gen_dernier["cost_usd"]) + float(ana_dernier["cost_usd"])
            total = creation + cout_rep
            v = "OK" if total <= config.BUDGET_PER_CASE_USD else "DEPASSE LE §9"
            print(f"\n  CAS COMPLET au régime d'aujourd'hui :")
            print(f"    création (analyse + génération) = ${creation:.4f}"
                  f"   ({100 * creation / config.BUDGET_PER_CASE_USD:.0f} % du §9)")
            print(f"    + 2 réparations                 = ${total:.4f}"
                  f"   ({100 * total / config.BUDGET_PER_CASE_USD:.0f} % du §9)  [{v}]")

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
