"""Sonde de PREUVE : capture le traceback COMPLET du scénario en échec.

Pourquoi ce script existe : la chaîne de production tronque l'erreur AVANT qu'on puisse la
lire (`behave_result.py` coupe traceback_summary à 300 et raw à 500, `run_service` coupe
error_summary à 500). Le verdict `wrong_field_name` est donc cohérent avec l'hypothèse mais
ne la prouve pas : le mot-clé « timeout » suffit à y aboutir (defect_taxonomy.py), et
n'importe quel timeout produirait le même verdict. On rejoue donc le scénario en gardant le
result.json intact pour voir QUEL sélecteur échoue réellement.

Usage : PYTHONUTF8=1 python scripts/probe_traceback_complet.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from testpilot.api.services.run_service import resolve_connection
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.store.db import get_initialized_db
from testpilot import config

CASE_ID = 2
MODULE = "validation_champ_requis"
SCENARIO = "Erreur"  # le plus court des deux scénarios en échec


def main() -> None:
    conn = get_initialized_db(config.DB_PATH)
    connection = resolve_connection(conn, CASE_ID)
    conn.close()

    runner = BehaveRunner(connection=connection)
    run_dir = Path(tempfile.mkdtemp(prefix="tp_probe_"))
    feature_src = runner.generated_dir / f"{MODULE}.feature"
    runner._assemble(run_dir, MODULE, feature_src)

    json_path = run_dir / "result.json"
    cmd = [sys.executable, "-m", "behave", "--lang", "fr",
           "-f", "tp_json_formatter:FullJSONFormatter", "-o", str(json_path),
           "-n", SCENARIO, f"{MODULE}.feature"]
    print("run_dir :", run_dir)
    print("cmd     :", " ".join(cmd))
    print("=" * 72)
    proc = subprocess.run(cmd, cwd=str(run_dir), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600,
                          env=runner._subprocess_env())
    print("returncode :", proc.returncode)

    data = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else []
    for feat in data:
        for el in feat.get("elements", []):
            print()
            print("=" * 72)
            print("SCÉNARIO :", el.get("name"), "|", el.get("status"))
            for st in el.get("steps", []):
                res = st.get("result") or {}
                status = res.get("status", "—")
                if status in ("passed", "skipped", "untested"):
                    continue
                print("-" * 72)
                print("STEP EN ÉCHEC :", st.get("keyword"), st.get("name"))
                print("STATUS        :", status)
                err = res.get("error_message")
                if isinstance(err, (list, tuple)):
                    err = "\n".join(str(x) for x in err)
                print("ERREUR COMPLÈTE (non tronquée) :")
                print(err or "(vide)")

    print()
    print("=" * 72)
    print("STDOUT (queue) :")
    print(proc.stdout[-2000:])
    print("run_dir conservé pour inspection :", run_dir)


if __name__ == "__main__":
    main()
