"""Formatter JSON de Behave, complété du message d'erreur des steps « errored ».

POURQUOI CE FICHIER EXISTE (ne pas le supprimer comme un doublon du formatter natif) :

Behave ≥ 1.3 distingue ``Status.failed`` (assertion métier) de ``Status.error`` (exception
inattendue : HTTPError, TimeoutError Playwright…). Or son formatter JSON n'écrit le message
que dans le premier cas :

    if step.error_message and step.status == Status.failed:   # ← 'error' exclu

Résultat : toute erreur technique arrivait dans le rapport SANS message → la taxonomie ne
pouvait que conclure « unknown », et chaque ``technical_error`` restait opaque (§5). Le
message existe pourtant côté Behave (``Step._process_error`` fait ``self.error_message = …``),
il n'était simplement jamais sérialisé.

Ce formatter réutilise le formatter natif et n'ajoute que le cas manquant, en CHAÎNE (le
natif découpe en liste dès qu'il y a un saut de ligne ; le parser normalise les deux).
"""

from behave.formatter.json import JSONFormatter
from behave.model_core import Status


class FullJSONFormatter(JSONFormatter):
    """JSON natif + ``error_message`` pour les steps en erreur / erreur de hook."""

    name = "json_full"
    description = "JSON de Behave, error_message inclus pour les steps error/hook_error"

    def result(self, step):
        # Le formatter natif incrémente ``_step_index`` : on capture l'index avant.
        index = self._step_index
        super().result(step)
        if step.error_message and step.status != Status.failed:
            steps = self.current_feature_element["steps"]
            steps[index]["result"]["error_message"] = step.error_message
