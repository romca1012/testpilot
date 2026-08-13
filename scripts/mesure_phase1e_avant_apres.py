"""Mesure avant/après de la restructuration de la bibliothèque de steps (Phase 1e du plan
« Bibliothèque de steps par connecteur »).

Rejoue les mêmes specs à travers le VRAI pipeline de génération (`build_default_deps`,
identique à `testpilot run`) — vrais appels LLM, vrai dry-run Behave/Odoo — et capture par
spec : coût USD, itérations, dry-run passé au premier essai, steps partagés réutilisés.

N'exécute QUE la génération (étapes [1/5] et [2/5] de `cli.run_pipeline`), jamais l'exécution
réelle ni le rapport : ces métriques ne demandent pas d'aller plus loin, et s'arrêter là évite
des effets de bord inutiles sur l'Odoo de test.

Écrit dans une base SQLite dédiée (jamais `data/testpilot.db`) : une mesure ne doit pas polluer
les vrais modules/cas du projet.

Usage :
    PYTHONUTF8=1 python scripts/mesure_phase1e_avant_apres.py --label avant --out avant.json
    PYTHONUTF8=1 python scripts/mesure_phase1e_avant_apres.py --label apres --out apres.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot import config  # noqa: E402
from testpilot.analysis.spec_analyzer import SpecAnalyzer  # noqa: E402
from testpilot.connectors.odoo import OdooConnector  # noqa: E402
from testpilot.connectors.runtime_env import project_env  # noqa: E402
from testpilot.execution.behave_runner import BehaveRunner  # noqa: E402
from testpilot.generation import steps_library  # noqa: E402
from testpilot.generation.agent import GenerationAgent  # noqa: E402
from testpilot.guardrails.cost_tracker import CostTracker  # noqa: E402
from testpilot.store.db import get_initialized_db  # noqa: E402
from testpilot.store.repositories import CaseRepo, ProjectRepo, VersionRepo  # noqa: E402

SPECS_DIR = Path(__file__).resolve().parent.parent / "specs" / "mesure"


def _to_regex(label: str) -> str:
    parts = [re.escape(p) for p in re.split(r"\{[^}]*\}", label)]
    return ".*?".join(parts)


def _steps_reused(feature_content: str) -> list[str]:
    """Mêmes catalogue et méthode de détection que `run_reel_0003_0006.py` : un step partagé
    est "réutilisé" si son libellé (hors placeholders) apparaît dans le .feature généré."""
    catalogue = {s.label for s in steps_library.catalogue()}
    return sorted(l for l in catalogue if re.search(_to_regex(l), feature_content))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, choices=["avant", "apres"])
    parser.add_argument("--out", required=True, help="chemin du JSON de résultats")
    parser.add_argument("--db", default=None, help="base scratch (défaut : tmp dédié au label)")
    parser.add_argument("--limit", type=int, default=None,
                        help="ne traiter que les N premières specs (essai avant lancement complet)")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else Path(f"data/_mesure_phase1e_{args.label}.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    specs = sorted(SPECS_DIR.glob("*.md"))
    if args.limit:
        specs = specs[:args.limit]
    print(f"=== Mesure '{args.label}' — {len(specs)} spec(s) — base scratch {db_path} ===")

    conn = get_initialized_db(db_path)
    project = ProjectRepo(conn).first()
    connector = OdooConnector.from_project(project)
    connector.connect()
    runner_kwargs = {"connection": project_env(project), "project_id": (project or {}).get("id")}
    # `connector_type` n'existe sur `BehaveRunner` que depuis la Phase 1b — absent sur le
    # commit "avant", ce script doit tourner identique des deux côtés de la comparaison.
    import inspect
    if "connector_type" in inspect.signature(BehaveRunner.__init__).parameters:
        runner_kwargs["connector_type"] = (project or {}).get("connector_type")
    runner = BehaveRunner(**runner_kwargs)

    resultats = []
    try:
        for spec_path in specs:
            nom = spec_path.stem
            print(f"\n--- {nom} ---")
            t0 = time.perf_counter()
            try:
                # Un CostTracker (et donc un agent/analyzer) NEUF par spec : partagé entre
                # specs, il accumule le coût de TOUTES les specs précédentes et déclenche le
                # plafond `COST_LIMIT_PER_RUN_USD` à tort dès la 5e — chaque spec doit repartir
                # de zéro, comme un vrai `testpilot run` isolé le ferait.
                analyzer = SpecAnalyzer(cost_tracker=CostTracker())
                agent = GenerationAgent(dry_runner=runner, connector=connector,
                                        case_repo=CaseRepo(conn), version_repo=VersionRepo(conn))
                plan = analyzer.analyze_spec_file(spec_path)
                gen = agent.generate(plan, title=plan.module_name, author="mesure-phase1e")
            except Exception as exc:  # une spec en échec ne doit pas perdre les autres mesures
                print(f"   ERREUR : {exc}")
                resultats.append({"spec": nom, "erreur": str(exc)})
                continue
            duree = time.perf_counter() - t0

            reused = _steps_reused(gen.feature_content) if gen.feature_content else []
            ligne = {
                "spec": nom,
                "success": gen.success,
                "dry_run_passed": gen.dry_run_passed,
                "iterations": gen.iterations,
                "cost_usd": round(gen.cost_usd + plan.cost_usd, 6),
                "cost_analysis_usd": round(plan.cost_usd, 6),
                "cost_generation_usd": round(gen.cost_usd, 6),
                "steps_reuses": len(reused),
                "steps_reuses_labels": reused,
                "steps_custom_ecrits": len(steps_library.extract_steps(gen.steps_content or "")),
                "duree_s": round(duree, 1),
                "stopped_reason": gen.stopped_reason,
            }
            resultats.append(ligne)
            print(f"   success={ligne['success']} dry_run={ligne['dry_run_passed']} "
                  f"iter={ligne['iterations']} cout=${ligne['cost_usd']:.4f} "
                  f"reuse={ligne['steps_reuses']} custom={ligne['steps_custom_ecrits']} "
                  f"({ligne['duree_s']}s)")
    finally:
        connector.disconnect()
        conn.close()

    out_path = Path(args.out)
    out_path.write_text(json.dumps({"label": args.label, "resultats": resultats}, ensure_ascii=False,
                                    indent=2), encoding="utf-8")
    print(f"\n=== Résultats écrits dans {out_path} ===")


if __name__ == "__main__":
    main()
