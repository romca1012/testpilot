"""Détection de l'état exécutable d'un module (« Smart Run ») — jamais de LLM.

Distingue ce qu'on PEUT exécuter de ce qu'il faut (re)générer. La sonde est un
``behave --dry-run`` (via le runner injecté) : elle valide la présence ET la résolution
des steps sans rien exécuter ni dépenser. L'état ``manual`` (cas sans code Behave) est
décidé par la couche appelante à partir de la base, pas ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from testpilot import config
from testpilot.analysis.spec_analyzer import spec_hash

RUNNABLE = "runnable"
STALE = "stale"
ABSENT = "absent"
MANUAL = "manual"


@dataclass
class ModuleState:
    state: str
    scenario_count: int = 0
    undefined_steps: list[str] = field(default_factory=list)
    ambiguous_steps: list[str] = field(default_factory=list)
    spec_changed: bool = False

    @property
    def runnable(self) -> bool:
        return self.state == RUNNABLE


def module_state(runner, module_name: str, *, generated_dir: Path | None = None,
                 spec_content: str = "", prev_spec_hash: str = "") -> ModuleState:
    """Classe l'état d'un module via le système de fichiers + un dry-run.

    ``prev_spec_hash`` : empreinte de la spec d'origine (fournie par la base). Si la spec
    courante en diffère, l'état bascule en ``stale`` (le code généré est peut-être périmé).
    """
    generated_dir = generated_dir or config.GENERATED_DIR
    feature_path = generated_dir / f"{module_name}.feature"
    if not feature_path.exists():
        return ModuleState(state=ABSENT)

    result = runner.dry_run(module_name)
    undefined = list(result.undefined_steps)
    ambiguous = list(result.ambiguous_steps)

    spec_changed = bool(prev_spec_hash and spec_content.strip()
                        and prev_spec_hash != spec_hash(spec_content))

    runnable = result.success and not undefined and not ambiguous and not spec_changed
    return ModuleState(
        state=RUNNABLE if runnable else STALE,
        scenario_count=len(result.scenarios),
        undefined_steps=undefined,
        ambiguous_steps=ambiguous,
        spec_changed=spec_changed,
    )
