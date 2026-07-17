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
    """Signature d'un état d'échec, dérivée du RUNTIME seul (docs/PRINCIPES.md, principe 1).

    Deux runs qui échouent de la même façon produisent la même signature — c'est ce qui permet
    de détecter l'absence de progrès (stall). Vide s'il n'y a aucun échec.

    ⚠️ **Cette signature indexait sur `scenario_name`** — le nom du scénario, **écrit par
    l'agent** dans le `.feature`. Or l'agent réécrit le fichier entier à chaque tentative :
    **renommer un scénario suffisait à changer la signature**, donc à masquer l'absence de
    progrès et à laisser le budget brûler sur un test qui n'avance pas. Le garde-fou dépendait
    du composant qu'il encadre.

    Les trois composantes sont maintenant produites par le runtime, jamais par l'agent :
      - la **cause** (`dominant_category`) — décidée par le type d'exception depuis `0015` ;
      - les **types d'exception** réellement levés — Python/Playwright/odoorpc les écrivent ;
      - le **nombre** d'échecs — un fait de comptage, insensible à un renommage.

    Contrepartie assumée : la signature est plus GROSSIÈRE. Deux échecs différents de même cause,
    même type et même nombre se ressemblent désormais → un stall peut être détecté à tort. C'est
    la direction SÛRE : un faux stall arrête la réparation (on garde la version approuvée), là où
    un stall manqué dépense pour rien. §4.4 tolère le faux positif, pas le faux négatif.
    """
    if not failures:
        return ""
    cause = dt.dominant_category(failures) or dt.UNKNOWN
    types = sorted({t for t in (dt.exception_type(dt.runtime_error_text(f)) for f in failures) if t})
    return f"{cause}:{'+'.join(types) or 'sans-type'}:{len(failures)}"


@dataclass
class CircuitState:
    """État accumulé de la boucle de réparation pour un cas.

    ⚠️ **Le stall est INATTEIGNABLE avec la configuration par défaut** (constaté le 2026-07-17,
    non corrigé ici). `repair_service` passe `max_iterations = budget` du gate, dont le défaut est
    **2** (`REPAIR_BUDGET_DEFAULT`), alors que `stall_limit` vaut **3**
    (`REPAIR_STALL_LIMIT`) : `evaluate` coupe sur le plafond d'itérations bien avant que
    `repeat_count` puisse atteindre 3. **Le stall ne se déclenche qu'à partir d'un budget ≥ 4.**

    Ce n'est pas un bug — c'est un garde-fou **décoratif** dans le cas nominal, du même genre que
    le `position` de `0006` ou les chemins de rapport de la migration 7. On le documente plutôt
    que d'ajuster une constante sans mesure ; la signature ci-dessus est corrigée pour que le
    garde soit CORRECT le jour où un relecteur accorde un budget plus large.
    """
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
