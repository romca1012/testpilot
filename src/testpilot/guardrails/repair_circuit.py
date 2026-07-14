"""Disjoncteur de la boucle de réparation ReAct (§6) — logique pure.

Décide quand ARRÊTER de tenter de réparer un test qui échoue, en combinant trois signaux,
dont le dernier n'est activable que depuis la livraison du pilier verdict :

1. plafond d'itérations dur (``MAX_ITERATIONS``) — cap de sécurité ;
2. stall : ``REPAIR_STALL_LIMIT`` tentatives CONSÉCUTIVES sans progrès (même signature
   d'échec) — on tourne en rond ;
3. origine du défaut (``verdict/defect_origin``) — le signal métier :
   - ``vrai_bug``      → on ARRÊTE et on remonte le constat (réparer un vrai bug n'a pas
                         de sens : l'app répond faux, ce n'est pas le test qui est cassé) ;
   - ``indetermine``   → on ARRÊTE pour CONFIRMATION HUMAINE (asymétrie §5) ;
   - ``test_a_reparer`` → réparation autorisée, tant que ni le stall ni le plafond ne coupent.

Aucune I/O : la boucle agent enregistre chaque tentative via ``CircuitState.record`` puis
consomme la décision de ``evaluate``. Réévaluer sans enregistrer est sans effet de bord.
"""

from __future__ import annotations

from dataclasses import dataclass

from testpilot import config
from testpilot.verdict import defect_origin as do
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict.defect_origin import DefectVerdict

# Issues du disjoncteur.
CONTINUE = "continue"
RESOLVED = "resolved"
REAL_BUG = "real_bug"
NEEDS_CONFIRMATION = "needs_confirmation"
STALLED = "stalled"
MAX_ITERATIONS_REACHED = "max_iterations"


def failure_signature(failures) -> str:
    """Signature stable d'un état d'échec : cause dominante + scénarios concernés.

    Deux runs qui échouent de la même façon produisent la même signature — c'est ce qui
    permet de détecter l'absence de progrès (stall). Vide s'il n'y a aucun échec.
    """
    if not failures:
        return ""
    cause = dt.dominant_category(failures) or dt.UNKNOWN
    scenarios = sorted({getattr(f, "scenario_name", "") for f in failures})
    return f"{cause}:{','.join(scenarios)}"


@dataclass
class CircuitState:
    """État accumulé de la boucle de réparation pour un cas."""
    stall_limit: int = config.REPAIR_STALL_LIMIT
    max_iterations: int = config.MAX_ITERATIONS
    iterations: int = 0
    last_signature: str = ""
    repeat_count: int = 0  # tentatives consécutives portant la MÊME signature

    def record(self, signature: str) -> None:
        """Enregistre une tentative : incrémente le compteur, suit la répétition d'échec."""
        self.iterations += 1
        if signature and signature == self.last_signature:
            self.repeat_count += 1
        else:
            self.repeat_count = 1
            self.last_signature = signature

    @property
    def stalled(self) -> bool:
        return self.repeat_count >= self.stall_limit


@dataclass
class CircuitDecision:
    should_continue: bool
    outcome: str
    reason: str
    defect_verdict: DefectVerdict | None = None


def evaluate(state: CircuitState, failures) -> CircuitDecision:
    """Décide de poursuivre ou couper la réparation (lecture seule sur ``state``)."""
    verdict = do.diagnose(failures)
    if verdict is None:
        # Plus aucun échec : le test passe, la réparation a atteint son but.
        return CircuitDecision(False, RESOLVED, "plus aucun échec — réparation terminée")

    # Le signal métier prime : un vrai bug se remonte tel quel, un indéterminé se confirme.
    if verdict.defect_origin == do.VRAI_BUG:
        return CircuitDecision(False, REAL_BUG,
                               "vrai bug détecté — remontée du constat, aucune réparation", verdict)
    if verdict.defect_origin == do.INDETERMINE:
        return CircuitDecision(False, NEEDS_CONFIRMATION,
                               "origine indéterminée — confirmation humaine requise avant de poursuivre",
                               verdict)

    # À partir d'ici : test_a_reparer. On respecte les caps de sécurité.
    if state.iterations >= state.max_iterations:
        return CircuitDecision(False, MAX_ITERATIONS_REACHED,
                               f"plafond d'itérations atteint ({state.iterations}/{state.max_iterations})",
                               verdict)
    if state.stalled:
        return CircuitDecision(False, STALLED,
                               f"aucun progrès après {state.repeat_count} tentatives identiques", verdict)
    return CircuitDecision(True, CONTINUE, "test à réparer — nouvelle tentative autorisée", verdict)
