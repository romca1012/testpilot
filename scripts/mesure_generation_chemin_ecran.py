"""Mesure RÉELLE du coût de génération sur le chemin ÉCRAN, et comparaison au chiffre CLI.

    PYTHONUTF8=1 python scripts/mesure_generation_chemin_ecran.py

⚠️ **CE SCRIPT DÉPENSE DE L'ARGENT** (~$0,45 attendu) et **écrit dans la VRAIE base** : il crée
un cas réel via la vraie route HTTP. C'est le prix d'une mesure réelle — une mesure simulée ne
prouverait rien. Sauvegarder la base avant :

    cp data/testpilot.db data/testpilot.db.pre-mesure-generation.bak

Ce qu'on mesure et pourquoi : le §9 (« moins de 1 € par cas ») était jugé sur **$0,4529**, mesuré
via la **CLI**. Or les utilisateurs passent par l'écran, et ce chemin n'écrivait rien au ledger
(corrigé : migration 12 + branchement). On vérifie donc que le chemin réel coûte bien ce qu'on
croyait — et on recalibre si ça diverge.

Le cas créé est un **artefact de mesure** : le nettoyer ou l'assumer est une décision du porteur
(cf. la leçon du ménage du 2026-07-16 — les scripts de preuve écrivent dans la vraie base, c'est
ce qui rend leurs preuves réelles, et ça laisse des déchets).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from testpilot import config  # noqa: E402
from testpilot.api.app import app  # noqa: E402
from testpilot.store.db import get_initialized_db  # noqa: E402
from testpilot.store.repositories import CostRepo  # noqa: E402

MODULE_ID = 1
TITRE = "Mesure cout generation ecran (demande materiel)"

# ⚠️ **LA MÊME SPEC QUE LA RÉFÉRENCE CLI**, et c'est tout l'enjeu de la mesure.
# Premier essai (2026-07-17) : `validation_champ_requis.md` → $0,1058, soit −76 % vs la CLI. J'ai
# failli conclure « le chemin écran coûte moins cher ». **C'était faux** : cette spec fait 3 323
# car. contre 9 951 pour `demande_materiel`, et produit 3 522 car. de steps contre 15 312. L'écart
# mesurait la TAILLE DU TRAVAIL, pas le chemin — une comparaison entre deux specs différentes ne
# dit rien du chemin. Comparer le chemin exige la même entrée.
SPEC = Path("specs/demande_materiel.md").read_text(encoding="utf-8")

# Le chiffre de référence, mesuré via la CLI le 2026-07-15 sur CETTE spec (ledger #1,
# exécution 1 : 10 itérations, 15 312 car. de steps produits).
GENERATION_CLI_USD = 0.452856


def main() -> None:
    print("=" * 78)
    print("MESURE RÉELLE — coût de génération sur le chemin ÉCRAN (POST /api/modules/…/cases)")
    print("=" * 78)
    print(f"  Référence CLI connue : ${GENERATION_CLI_USD:.4f}")
    print(f"  §9                   : ${config.BUDGET_PER_CASE_USD:.4f}")
    print(f"  Plafond génération   : ${config.COST_LIMIT_PER_RUN_USD:.2f} "
          f"(≈ {config.COST_LIMIT_PER_RUN_USD / config.EUR_USD_RATE:.2f} EUR)")
    print()

    client = TestClient(app)
    print(f"POST /api/modules/{MODULE_ID}/cases  (spec → analyse → génération → gate)")
    resp = client.post(f"/api/modules/{MODULE_ID}/cases",
                       json={"spec_content": SPEC, "title": TITRE, "author": "mesure-cout"})
    print("  HTTP :", resp.status_code)
    if resp.status_code != 202:
        print("  ÉCHEC :", resp.text[:400])
        return

    job_id = resp.json()["job_id"]
    job = client.get(f"/api/modules/jobs/{job_id}").json()
    print("  job  :", job["status"], "| case_id =", job["case_id"])
    if job["status"] != "done":
        print("  ERREUR :", (job.get("error") or "")[:600])
        # Utile quand même : le coût d'un échec doit être au ledger (§4.6 appliqué à l'argent).
        print("  → on lit le ledger malgré tout : une génération ratée a coûté aussi.")

    case_id = job.get("case_id")
    conn = get_initialized_db(config.DB_PATH)
    repo = CostRepo(conn)

    print()
    print("-- Ce que le ledger a enregistré " + "-" * 45)
    if case_id is None:
        print("  aucun cas créé — voir le log serveur (la dépense est signalée, pas imputée)")
        conn.close()
        return

    lignes = repo.breakdown_for_case(case_id)
    if not lignes:
        print("  ⚠️  RIEN. Le chemin écran ne trace toujours pas son coût — le §9 y est aveugle.")
        conn.close()
        return

    for r in lignes:
        print(f"  {r['phase']:<11} {r['model']:<28} ${r['cost_usd']:.4f}  ({r['calls']} ligne(s))")

    total = repo.total_for_case_usd(case_id)
    par_phase = {r["phase"]: r["cost_usd"] for r in lignes}
    generation = par_phase.get("generation", 0.0)
    analyse = par_phase.get("analysis", 0.0)

    print()
    print("=" * 78)
    print("COMPARAISON — chemin écran vs référence CLI")
    print("=" * 78)
    ecart = generation - GENERATION_CLI_USD
    pct = (100 * ecart / GENERATION_CLI_USD) if GENERATION_CLI_USD else 0
    print(f"  génération (écran) : ${generation:.4f}")
    print(f"  génération (CLI)   : ${GENERATION_CLI_USD:.4f}")
    print(f"  écart              : {ecart:+.4f} USD  ({pct:+.1f} %)")
    print()
    print(f"  analyse (JAMAIS mesurée avant ce jour) : ${analyse:.4f}")
    print(f"  TOTAL création du cas                  : ${total:.4f}"
          f"  = {100 * total / config.BUDGET_PER_CASE_USD:.1f} % du §9")

    print()
    print("-- Ce que ça dit du plafond de génération " + "-" * 36)
    marge_9 = config.BUDGET_PER_CASE_USD - total
    print(f"  Reste pour les réparations : ${marge_9:.4f}")
    print(f"  Plafond réparations configuré : ${config.REPAIR_COST_LIMIT_PER_CASE_USD:.4f}"
          f"  [{'OK' if config.REPAIR_COST_LIMIT_PER_CASE_USD <= marge_9 else 'TROP HAUT'}]")
    print(f"  COST_LIMIT_PER_RUN_USD actuel : ${config.COST_LIMIT_PER_RUN_USD:.2f}"
          f"  → {config.COST_LIMIT_PER_RUN_USD / total:.1f}x le coût réel mesuré")

    print()
    print("  ⚠️  RÉSERVE : 2 échantillons (1 CLI, 1 écran), sur la MÊME spec ou presque. Un LLM")
    print("      n'est pas déterministe, et une spec plus lourde coûtera plus. Tout plafond")
    print("      calibré au plus juste ferait échouer la création d'un cas plus gros.")

    conn.close()


if __name__ == "__main__":
    main()
