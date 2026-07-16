"""Sonde : en RUN RÉEL, le marqueur [TP_FIELD_FALLBACK] atteint-il seulement le parseur ?

Le re-run du cas 2 (exécution 5) a montré que B fonctionne (plus de timeout sur le champ, les
scénarios avancent) mais que `field_fallbacks` reste VIDE. Deux lectures à départager, et une
seule est vraie :
  (a) le marqueur n'arrive PAS dans `combined_log` → Behave l'avale en conditions réelles, et le
      test de garde ne reproduit pas ces conditions → B+ est aveugle ;
  (b) le marqueur EST dans `combined_log` mais `extract_field_fallbacks` le rate → bug d'extraction.

Dispositif : on intercepte `parse_behave_json` pour vidanger le `combined_log` BRUT sur disque
avant tout traitement, puis on exécute le cas 2. On lit ensuite le log, on ne présume rien (§8.5).

Usage : PYTHONUTF8=1 python scripts/probe_marqueur_run_reel.py
"""

from pathlib import Path

from fastapi.testclient import TestClient

from testpilot.execution import behave_result as br
from testpilot.execution import behave_runner as brunner

CASE_ID = 2
OUT = Path("data/_probe_marqueur")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    original = br.parse_behave_json
    calls = []

    def spy(json_output, returncode, dry_run=False, combined_log=""):
        idx = len(calls)
        path = OUT / f"combined_log_{idx}_{'dry' if dry_run else 'real'}.txt"
        path.write_text(combined_log or "", encoding="utf-8")
        calls.append((path, dry_run, len(combined_log or "")))
        return original(json_output, returncode, dry_run=dry_run, combined_log=combined_log)

    # Le runner importe la fonction par NOM dans son module : patcher les deux points d'usage.
    br.parse_behave_json = spy
    brunner.parse_behave_json = spy
    try:
        from testpilot.api.app import app
        client = TestClient(app)
        print("Exécution du cas", CASE_ID, "…")
        resp = client.post(f"/api/cases/{CASE_ID}/runs")
        print("HTTP :", resp.status_code)
        if resp.status_code != 202:
            print("ÉCHEC :", resp.text[:300]); return
        eid = resp.json()["execution_id"]
        ex = client.get(f"/api/executions/{eid}").json()
        print("execution_id :", eid, "|", ex.get("execution_status"))
        print("field_fallbacks via API :", ex.get("field_fallbacks"))
    finally:
        br.parse_behave_json = original
        brunner.parse_behave_json = original

    print()
    print("=" * 72)
    print("LOGS BRUTS CAPTÉS (avant tout traitement)")
    for path, dry_run, size in calls:
        blob = path.read_text(encoding="utf-8")
        present = "[TP_FIELD_FALLBACK]" in blob
        print(f"   {path.name:34} dry={dry_run!s:5} {size:>7} car.  marqueur={'OUI' if present else 'non'}")
        if present:
            for ln in blob.splitlines():
                if "TP_FIELD_FALLBACK" in ln:
                    print("      >", ln[:160])

    print()
    print("=" * 72)
    print("VERDICT DE LA SONDE")
    real = [c for c in calls if not c[1]]
    if not real:
        print("   Aucun run réel intercepté — le dry-run a dû échouer.")
        return
    blob = real[-1][0].read_text(encoding="utf-8")
    if "[TP_FIELD_FALLBACK]" in blob:
        print("   (b) Le marqueur EST dans combined_log → l'extraction est en cause.")
        print("       extract_field_fallbacks() rend :", br.extract_field_fallbacks(blob))
    else:
        print("   (a) Le marqueur N'EST PAS dans combined_log → Behave l'avale en run réel.")
        print("       Le test de garde ne reproduit donc PAS les conditions réelles : B+ est aveugle.")
        print("       Indices à lire dans le log capté :")
        for needle in ("LOG_WARNING", "LOG_", "Captured logging", "resolve_field_name"):
            print(f"         {needle!r:22} présent ? {needle in blob}")


if __name__ == "__main__":
    main()
