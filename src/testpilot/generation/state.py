"""État mutable de la boucle et résultat final du pilier generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentState:
    """État accumulé pendant la boucle ReAct (une génération = une instance)."""
    module_name: str
    messages: list[dict] = field(default_factory=list)
    iterations: int = 0
    feature_written: bool = False
    steps_written: bool = False
    dry_run_passed: bool = False
    feature_content: str = ""
    steps_content: str = ""
    feature_path: Path | None = None
    steps_path: Path | None = None
    # Garde-fou de stall dry-run : signature du dernier ensemble d'échecs de parsing.
    last_dryrun_signature: str | None = None
    stall_count: int = 0
    stalled: bool = False
    stopped_reason: str = ""
    verified_fields: dict[str, list[str]] = field(default_factory=dict)
    # Étape 2 (A61) : contrôle de fin d'écriture — tours déjà faits et sortes de points renvoyées à l'IA.
    tours_de_controle: int = 0
    avis_envoyes: list[str] = field(default_factory=list)
    # Étape 5 (AV-7) : pourquoi une génération s'arrête sans test — les derniers refus d'outil (début du message) et le
    # dernier diagnostic d'essai à blanc. Mesuré : 5 générations sur 5 du MÊME cas sans essai à blanc passé, et rien de
    # plus que « génération sans essai à blanc passé » dans les rapports du banc pour l'instruire.
    refus_recents: list[str] = field(default_factory=list)
    dernier_dry_run: str = ""


@dataclass
class GenerationResult:
    """Sortie du pilier — assez riche pour que verdict/review_gate s'y branche."""
    success: bool
    module_name: str
    stopped_reason: str            # done | max_iterations | cost_exceeded | dry_run_stalled | error
    dry_run_passed: bool = False
    iterations: int = 0
    cost_usd: float = 0.0
    feature_path: Path | None = None
    steps_path: Path | None = None
    feature_content: str = ""
    steps_content: str = ""
    spec_hash: str = ""
    error: str = ""
    # Hand-off explicite vers le gate de relecture (§4) — jamais exécuté ici.
    awaiting_review: bool = False
    case_id: int | None = None
    version_id: int | None = None
    verified_fields: dict[str, list[str]] = field(default_factory=dict)
    observation_evidence: list[dict] = field(default_factory=list)
    generation_provenance: dict = field(default_factory=dict)
    technical_plan: dict = field(default_factory=dict)
    # Étape 5 (AV-7) : rempli seulement quand la génération n'aboutit pas — `{arret, tours, feature_ecrite, steps_ecrits,
    # refus_recents, dernier_dry_run}`. Lu par le banc (`asdict`) pour instruire les générations qui n'aboutissent pas.
    diagnostic_arret: dict = field(default_factory=dict)
