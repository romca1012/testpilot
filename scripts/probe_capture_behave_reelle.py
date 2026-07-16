"""Sonde : POURQUOI le marqueur [TP_FIELD_FALLBACK] n'atteint pas le parseur en run réel ?

Le re-run du cas 2 (exécutions 5 et 6) a montré que B fonctionne mais que `field_fallbacks` reste
vide, alors que le test de garde de B+ passe. Contradiction → une des deux mesures ment.

Variable isolée ici : `environment.py`. Le test de garde lance Behave SANS `environment.py` ;
`BehaveRunner._assemble` en copie TOUJOURS un. Or Behave capture stdout/stderr/logging et ne les
recrache pas sur un scénario vert.

Dispositif : on assemble l'aire d'exécution avec le VRAI `BehaveRunner._assemble` (vrai
environment.py, vraie bibliothèque de steps, vrai .feature du cas 2), puis on lance Behave
plusieurs fois en ne changeant QUE les drapeaux de capture. Répond à deux questions d'un coup :
  1. le repli a-t-il seulement lieu en run réel (le marqueur est-il émis) ?
  2. quel réglage le laisse remonter jusqu'au parseur ?

⚠️ Exécute réellement des scénarios contre Odoo (lent). Aucun écrit en base : ce script ne passe
pas par l'API, il ne persiste aucune exécution.

Usage : PYTHONUTF8=1 python scripts/probe_capture_behave_reelle.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from testpilot.execution.behave_result import extract_field_fallbacks
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.api.services.run_service import resolve_connection
from testpilot.store.db import get_initialized_db
from testpilot import config

CASE_ID = 2
MODULE = "validation_champ_requis"

# On ne teste QUE le scénario [Erreur] : il est VERT et il traverse le step partagé
# `je laisse le champ "Raison de la demande" vide` → leave_field_empty → resolve_field_name.
# C'est exactement le cas de l'exigence (repli + succès).
SCENARIO = "Erreur"

VARIANTES = [
    ("temoin (drapeaux actuels du runner)", []),
    ("--no-logcapture", ["--no-logcapture"]),
    ("--no-capture --no-capture-stderr", ["--no-capture", "--no-capture-stderr"]),
]


def main() -> None:
    conn = get_initialized_db(config.DB_PATH)
    env_extra = resolve_connection(conn, CASE_ID)
    conn.close()

    import os
    env = {**os.environ, **env_extra}

    runner = BehaveRunner()
    for label, flags in VARIANTES:
        run_dir = Path(tempfile.mkdtemp(prefix="tp_probe_capture_"))
        try:
            # VRAI assemblage : environment.py + bibliothèque + steps générés + .feature.
            runner._assemble(run_dir, MODULE, runner.generated_dir / f"{MODULE}.feature")
            assert (run_dir / "environment.py").exists(), "environment.py doit être là (conditions réelles)"

            cmd = [sys.executable, "-m", "behave", "--lang", "fr",
                   "-f", "json", "-o", str(run_dir / "r.json"),
                   "--name", SCENARIO] + flags + [f"{MODULE}.feature"]
            proc = subprocess.run(cmd, cwd=str(run_dir), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=600, env=env)
            combined = f"{proc.stdout}\n{proc.stderr}"
            fallbacks = extract_field_fallbacks(combined)
            print(f"{label:38} exit={proc.returncode} log={len(combined):>6}c "
                  f"marqueur={'OUI' if fallbacks else 'non'}")
            for f in fallbacks:
                print("      >", f[:120])
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    print()
    print("=" * 72)
    print("LECTURE")
    print("  Si le témoin est 'non' et --no-capture 'OUI' : le repli A LIEU, mais Behave l'avale")
    print("  avec les drapeaux actuels → B+ est aveugle en run réel, et le test de garde (qui")
    print("  omet environment.py) ne reproduit PAS les conditions réelles.")


if __name__ == "__main__":
    main()
