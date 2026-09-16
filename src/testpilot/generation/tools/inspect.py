"""Tools d'exploration de l'application vivante (perception boîte noire, §6).

Chaque tool délègue au ``Connector`` injecté et se dégrade proprement s'il est absent
(le pilier reste testable hors-ligne). ``summarize_submission_mechanism`` est pur : il
résume un descriptif de formulaire sans aucun accès réseau.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from testpilot.generation.tools import ToolContext, ToolOutcome

_NO_CONNECTOR = "[connecteur indisponible — impossible d'observer l'application]"


def _outcome(observation: str, ok: bool = True):
    from testpilot.generation.tools import ToolOutcome
    return ToolOutcome(observation=observation, ok=ok)


def inspect_schema(ctx: "ToolContext", model: str) -> "ToolOutcome":
    if ctx.connector is None:
        return _outcome(_NO_CONNECTOR, ok=False)
    if not model:
        return _outcome("[inspect_schema] modèle manquant", ok=False)
    schema = ctx.connector.get_schema(model)
    if not schema:
        return _outcome(f"[inspect_schema] aucun champ pour '{model}'", ok=False)
    lines = [f"Champs de `{model}` :"]
    for name, meta in list(schema.items())[:50]:
        req = "requis" if meta.get("required") else "optionnel"
        lines.append(f"- {name} ({meta.get('type', '?')}, {req})")
    return _outcome("\n".join(lines))


def query_data(ctx: "ToolContext", model: str, fields, limit: int = 3) -> "ToolOutcome":
    if ctx.connector is None:
        return _outcome(_NO_CONNECTOR, ok=False)
    if not model:
        return _outcome("[query_data] modèle manquant", ok=False)
    fields = fields or ["id", "name"]
    ids = ctx.connector.search(model, [], limit=max(1, min(limit, 10)))
    if not ids:
        return _outcome(f"[query_data] aucun enregistrement pour '{model}'")
    rows = ctx.connector.read(model, ids, fields)
    return _outcome(f"{len(rows)} enregistrement(s) de `{model}` : {rows}")


def inspect_page_form(ctx: "ToolContext", page_url: str) -> "ToolOutcome":
    if ctx.connector is None:
        return _outcome(_NO_CONNECTOR, ok=False)
    if not page_url:
        return _outcome("[inspect_page_form] URL manquante", ok=False)
    info = ctx.connector.inspect_form(page_url)
    if info.get("error"):
        return _outcome(f"[inspect_page_form] {info['error']}", ok=False)
    fields = info.get("fields", [])
    required = [f["name"] for f in fields if f.get("required")]
    submission = summarize_submission_mechanism(info.get("submission"))
    return _outcome(
        f"Formulaire {page_url} : {len(fields)} champ(s), requis={required}. "
        f"Soumission : {submission or 'inconnue'}."
    )


def discover_route(ctx: "ToolContext", path_pattern: str, sample_id: int | None = None) -> "ToolOutcome":
    if ctx.connector is None:
        return _outcome(_NO_CONNECTOR, ok=False)
    if not path_pattern:
        return _outcome("[discover_route] motif de chemin manquant", ok=False)
    info = ctx.connector.discover_route(path_pattern, sample_id)
    return _outcome(
        f"Route {info.get('url', path_pattern)} : statut={info.get('status', '?')}, "
        f"méthode={info.get('method', '?')}. {info.get('note', '')}".strip()
    )


def attempt_login(ctx: "ToolContext", username: str, password: str) -> "ToolOutcome":
    """Observe ce que l'application affiche VRAIMENT pour CES identifiants — jamais un souvenir.

    2026-09-16 (amendement §4.3-bis étendu) : avant d'écrire une assertion sur un message lié à
    une tentative de connexion (identifiants valides, mot de passe erroné, compte verrouillé...),
    APPELLE CE TOOL avec les identifiants exacts du scénario et utilise le texte RENDU — jamais
    celui que tu crois connaître. Playwright Codegen (l'outil officiel équivalent) fait exactement
    ça : il lit l'`innerText` réel plutôt que de le demander à l'auteur.
    """
    if ctx.connector is None:
        return _outcome(_NO_CONNECTOR, ok=False)
    if not username or not password:
        return _outcome("[attempt_login] identifiant et mot de passe requis", ok=False)
    resultat = ctx.connector.attempt_login(username, password)
    if resultat.get("error"):
        return _outcome(f"[attempt_login] impossible d'observer : {resultat['error']}", ok=False)
    if not resultat.get("submitted"):
        return _outcome("[attempt_login] aucun formulaire de connexion trouvé sur cette page",
                        ok=False)
    message = resultat.get("message") or ""
    if message:
        return _outcome(
            f"Après soumission de « {username} » / « {password} », l'application affiche "
            f"EXACTEMENT : {message!r} (URL résultante : {resultat.get('url', '?')}). "
            "Utilise ce texte au caractère près si ton assertion en dépend — ou une correspondance "
            "partielle stable si une partie du message est variable.")
    return _outcome(
        f"Après soumission de « {username} » / « {password} », aucun message d'erreur visible "
        f"détecté (URL résultante : {resultat.get('url', '?')}) — la connexion a probablement "
        "réussi, ou l'application affiche l'erreur autrement que par les motifs reconnus "
        "([role=\"alert\"], .error, .alert-danger...).")


def summarize_submission_mechanism(info: dict | None) -> str | None:
    """Résume un descriptif de soumission en une phrase actionnable. Pur (sans réseau)."""
    if not isinstance(info, dict):
        return None
    mechanism = info.get("mechanism")
    if not mechanism:
        return None
    endpoint = info.get("endpoint", "")
    trigger = info.get("trigger_selector", "")
    parts = [f"mécanisme={mechanism}"]
    if endpoint:
        parts.append(f"endpoint={endpoint}")
    if trigger:
        parts.append(f"déclencheur={trigger}")
    return ", ".join(parts)
