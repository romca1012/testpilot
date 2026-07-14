"""Runner Behave réel — assemble une aire d'exécution isolée puis lance le sous-processus.

C'est l'implémentation concrète du ``DryRunner`` injecté au pilier generation : ``dry_run``
valide le parsing (``--dry-run``, sans navigateur ni Odoo), ``real_run`` exécute pour de vrai.

Chaque run est assemblé dans un dossier temporaire jetable :
    <tmp>/environment.py, <tmp>/steps/<bibliothèque + steps générés>, <tmp>/<module>.feature
ce qui isole les runs et garde ``behave_runtime/generated`` à sa place (sortie de generation).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from testpilot import config
from testpilot.execution.behave_result import BehaveResult, parse_behave_json

logger = logging.getLogger(__name__)


class BehaveRunner:
    def __init__(self, *, runtime_dir: Path | None = None, generated_dir: Path | None = None,
                 steps_library_dir: Path | None = None, dry_timeout: int | None = None,
                 real_timeout: int | None = None):
        self.runtime_dir = runtime_dir or config.BEHAVE_RUNTIME_DIR
        self.generated_dir = generated_dir or config.GENERATED_DIR
        self.steps_library_dir = steps_library_dir or config.STEPS_LIBRARY_DIR
        self.dry_timeout = dry_timeout or config.BEHAVE_DRY_TIMEOUT_SECONDS
        self.real_timeout = real_timeout or config.BEHAVE_REAL_TIMEOUT_SECONDS

    def dry_run(self, module_name: str) -> BehaveResult:
        return self._run(module_name, dry_run=True)

    def real_run(self, module_name: str) -> BehaveResult:
        return self._run(module_name, dry_run=False)

    # ── Interne ───────────────────────────────────────────────────────────────
    def _run(self, module_name: str, dry_run: bool) -> BehaveResult:
        feature_src = self.generated_dir / f"{module_name}.feature"
        if not feature_src.exists():
            return BehaveResult(success=False, returncode=-1, dry_run=dry_run,
                                raw_stderr=f".feature introuvable : {feature_src}")

        run_dir = Path(tempfile.mkdtemp(prefix=f"tp_behave_{module_name}_"))
        try:
            self._assemble(run_dir, module_name, feature_src)
            json_path = run_dir / "result.json"
            cmd = [sys.executable, "-m", "behave", "--lang", "fr",
                   "-f", "json", "-o", str(json_path), f"{module_name}.feature"]
            if dry_run:
                cmd.append("--dry-run")
            timeout = self.dry_timeout if dry_run else self.real_timeout
            try:
                proc = subprocess.run(cmd, cwd=str(run_dir), capture_output=True, text=True,
                                      encoding="utf-8", errors="replace", timeout=timeout)
            except subprocess.TimeoutExpired:
                return BehaveResult(success=False, returncode=-2, dry_run=dry_run,
                                    raw_stderr=f"Timeout ({timeout}s) lors du run behave")
            json_output = json_path.read_text(encoding="utf-8") if json_path.exists() else ""
            return parse_behave_json(json_output, proc.returncode, dry_run=dry_run,
                                     combined_log=f"{proc.stdout}\n{proc.stderr}")
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def _assemble(self, run_dir: Path, module_name: str, feature_src: Path) -> None:
        """Recopie environment.py, la bibliothèque de steps + les steps générés, et le .feature."""
        env_src = self.runtime_dir / "environment.py"
        if env_src.exists():
            shutil.copy2(env_src, run_dir / "environment.py")

        steps_dir = run_dir / "steps"
        steps_dir.mkdir()
        (steps_dir / "__init__.py").write_text("", encoding="utf-8")
        if self.steps_library_dir.exists():
            for lib in self.steps_library_dir.glob("*.py"):
                shutil.copy2(lib, steps_dir / lib.name)
        gen_steps = self.generated_dir / f"{module_name}_steps.py"
        if gen_steps.exists():
            shutil.copy2(gen_steps, steps_dir / gen_steps.name)

        shutil.copy2(feature_src, run_dir / f"{module_name}.feature")
