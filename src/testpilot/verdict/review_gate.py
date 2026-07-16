"""Gate de relecture humaine (§4) — logique pure, sans aucune I/O terminal.

Règle : la version courante d'un cas généré par l'IA doit être approuvée en relecture
AVANT sa première exécution. L'approbation porte sur la VERSION : un ré-run de la même
version approuvée ne redemande rien ; une nouvelle version (spec évoluée → re-génération)
repasse par le gate. L'interaction (afficher le Gherkin, demander oui/non) est faite par
la CLI, qui appelle ``submit_review`` puis ``evaluate_gate``.
"""

from __future__ import annotations

from dataclasses import dataclass

from testpilot.verdict.status import EXEC_SUCCESS


@dataclass
class GateDecision:
    allowed: bool
    needs_review: bool
    reason: str


def evaluate_gate(review_repo, version_id: int) -> GateDecision:
    """Décide si la version courante peut être exécutée (lecture seule)."""
    if review_repo.is_version_approved(version_id):
        return GateDecision(allowed=True, needs_review=False, reason="version approuvée en relecture")
    latest = review_repo.latest_for_version(version_id)
    if latest and latest["decision"] == "rejected":
        return GateDecision(allowed=False, needs_review=True,
                            reason="version rejetée en relecture — corriger puis re-générer")
    return GateDecision(allowed=False, needs_review=True,
                        reason="relecture humaine obligatoire avant la première exécution")


def submit_review(review_repo, *, case_id: int, version_id: int, approved: bool,
                  reviewer: str, comment: str = "",
                  repair_budget: int | None = None) -> GateDecision:
    """Enregistre la décision de relecture et renvoie l'état du gate qui en découle.

    `repair_budget` : tentatives de réparation que cette approbation autorise (décision 0014,
    option C). `None` → le défaut de configuration. Réparer exige d'exécuter, et le gate est le
    seul à pouvoir autoriser une exécution (§4.3) : c'est donc lui qui porte cette autorisation.
    """
    review_repo.create(test_case_id=case_id, version_id=version_id,
                       decision="approved" if approved else "rejected",
                       reviewer=reviewer, comment=comment, repair_budget=repair_budget)
    return evaluate_gate(review_repo, version_id)


def validation_status_after_run(prev_status: str, execution_status: str) -> str:
    """Transition du statut de validation d'un cas après une exécution (§5).

    « Validé » = joué en entier sans interruption technique (exécution=success), quel que
    soit le statut fonctionnel : un test qui tourne et détecte un vrai bug reste un test
    validé. Un échec technique ne valide pas le cas — son statut précédent est conservé.
    """
    return "validated" if execution_status == EXEC_SUCCESS else prev_status
