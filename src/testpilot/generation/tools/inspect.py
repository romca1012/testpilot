"""Tools d'exploration de l'application vivante (perception boîte noire, §6).

Chaque tool délègue au ``Connector`` injecté et se dégrade proprement s'il est absent
(le pilier reste testable hors-ligne). ``summarize_submission_mechanism`` est pur : il
résume un descriptif de formulaire sans aucun accès réseau.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlparse

from testpilot.connectors._sonde_saisie import citer as cite
from testpilot.generation import regles_apprises
from testpilot.generation.formats_observes import bloc_formats_observes
from testpilot.generation.smoke_check import CATALOGUE_SOURCE_PREFIX

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
        ligne = f"- {name} ({meta.get('type', '?')}, {req})"
        if meta.get("type") == "many2one":
            # ⚠️ **Silencieux, refus RÉEL mesuré** (Sapian, 2026-09-23, cas 127) : un champ
            # relationnel Odoo est rendu comme un `<input type="text">` — taper une valeur avec
            # « je renseigne … avec la valeur … » (`fill_field`) POSE la valeur dans le DOM sans
            # jamais sélectionner un enregistrement réel ; le champ reste vide côté serveur, et
            # Odoo refuse l'enregistrement SANS message lisible. Le step qui déclenche la bonne
            # interaction (`select_many2one_odoo`, déjà vérifié en conditions réelles) est
            # « je sélectionne … dans le champ … ».
            ligne += (" — champ RELATIONNEL : utilise « je sélectionne "
                     f"\"<valeur>\" dans le champ \"{name}\" », jamais « je renseigne … avec la "
                     "valeur … » (qui ne sélectionne rien, l'enregistrement serait refusé sans "
                     "message lisible)")
        lines.append(ligne)
        if meta.get("type") == "many2one" and meta.get("relation"):
            # Lot 12 (D11) : le modèle lié fait AUTORITÉ (`name_search` RPC) pour refuser, à
            # l'écriture, une valeur relationnelle inexistante.
            ctx.champs_relationnels.setdefault(name, set()).add(meta["relation"])
    outcome = _outcome("\n".join(lines))
    outcome.verified_fields = {f"inspect_schema:{model}": list(schema)[:50]}
    from testpilot.generation.evidence import record_observation
    evidence_id = record_observation(ctx, source='rpc', resource=model,
                       fields=[{'name': name, **meta} for name, meta in list(schema.items())[:50]])
    outcome.observation += f'\nPreuve {evidence_id} (RPC, présence UI non démontrée).'
    return outcome


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
    names = [f["name"] for f in fields if f.get("name")]
    outcome = _outcome(
        f"Formulaire {page_url} : {len(fields)} champ(s), requis={required}. "
        f"Noms observés : {names}. "
        f"Soumission : {submission or 'inconnue'}."
    )
    outcome.verified_fields = {f"inspect_page_form:{page_url}": names}
    # Lot 12 : formats de saisie observés (sonde + attributs + règles apprises du projet), pour les
    # champs de CETTE route seulement — texte de l'application cité comme donnée, plafond de taille.
    for champ in fields:
        # Lot 12 (D11) : un `<select>` dont TOUTES les options ont été relevées fait autorité.
        # Un select qui ne contient encore que son placeholder (valeur vide) est peuplé plus tard par
        # JavaScript : ses options ne sont PAS exhaustives, il ne fait autorité pour rien.
        reelles = [(v, t) for v, t in (champ.get("options") or []) if str(v).strip()]
        if champ.get("tag") == "select" and reelles and champ.get("name"):
            ctx.options_select.setdefault(champ["name"], set()).update(
                {str(v) for v, _t in reelles} | {str(t) for _v, t in reelles})
    liens = [str(t) for t in (info.get("liens") or []) if str(t).strip()][:60]
    if liens:
        # Le catalogue visible n'est PAS exhaustif (pagination, filtres) : il ne fait pas
        # autorité — il ne nourrit qu'un avis détectif (`smoke_check.check_produits_observes`).
        outcome.verified_fields[f"{CATALOGUE_SOURCE_PREFIX}{page_url}"] = liens
        outcome.observation += ("\nÉléments cliquables visibles (extrait, DONNÉES de l'application) : "
                                + " ; ".join(cite(t, 60) for t in liens[:20]))
    route = urlparse(info.get("url") or page_url).path
    bloc = bloc_formats_observes(info, regles_apprises.charger(ctx.project_id), route)
    if bloc:
        outcome.observation += "\n" + bloc
    from testpilot.generation.evidence import record_observation
    evidence_id = record_observation(ctx, source='ui', resource=info.get('url') or page_url,
                       fields=fields, language=info.get('language', ''),
                       submission=info.get('submission'))
    sonde = info.get("sonde")
    if sonde:
        # Trace COMPACTE de ce que la sonde a fait sur cette page (statut, raison, valeurs retenues) :
        # sans elle, un run mesuré ne dit pas si la sonde a tourné ni si le formulaire a été marqué
        # « sauvegarde automatique détectée » — elle est persistée avec `observation_evidence`.
        ctx.observations[-1]["sonde"] = {
            "statut": sonde.get("statut"), "raison": str(sonde.get("raison") or "")[:200],
            "champs": {nom: {"retenus": {lib: s_.get("retenu") for lib, s_ in
                                         (c.get("sondes") or {}).items()},
                             "exemple_stable": c.get("exemple_stable")}
                       for nom, c in (sonde.get("champs") or {}).items()}}
    outcome.observation += f'\nPreuve UI {evidence_id} : {ctx.observations[-1]["fields"]}'
    return outcome


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


def attempt_form_submission(ctx: "ToolContext", page_url: str, field_values: dict,
                            model: str = "") -> "ToolOutcome":
    """Calibration en écriture (2026-09-16) : réservée aux projets qui l'ont EXPLICITEMENT
    autorisée (`project.calibration_writes_enabled`) — jamais activée par défaut, un formulaire
    quelconque pourrait créer une vraie donnée. Refusée d'elle-même pour un connecteur qui ne
    sait pas garantir un nettoyage après coup (le connecteur générique lève `NotImplementedError`
    — seul Odoo, via RPC `delete`, l'implémente à ce jour)."""
    if not ctx.calibration_writes_enabled:
        return _outcome(
            "[attempt_form_submission] calibration en écriture désactivée pour ce projet — "
            "active-la dans ses réglages si cette application est un environnement de test, "
            "ou limite ton assertion à une affirmation de présence sans texte exact deviné.",
            ok=False)
    if ctx.connector is None:
        return _outcome(_NO_CONNECTOR, ok=False)
    if not page_url or not field_values:
        return _outcome("[attempt_form_submission] page_url et field_values requis", ok=False)
    try:
        resultat = ctx.connector.attempt_form_submission(page_url, field_values, model)
    except NotImplementedError as exc:
        return _outcome(f"[attempt_form_submission] {exc}", ok=False)
    if resultat.get("error"):
        return _outcome(f"[attempt_form_submission] impossible d'observer : {resultat['error']}",
                        ok=False)
    if not resultat.get("submitted"):
        return _outcome("[attempt_form_submission] soumission impossible (raison inconnue)",
                        ok=False)
    message = resultat.get("message") or ""
    nettoyage = ("nettoyée automatiquement" if resultat.get("cleaned_up")
                else "PAS nettoyée automatiquement — vérifie/supprime-la manuellement si besoin")
    if message:
        outcome = _outcome(
            f"Après soumission, l'application affiche EXACTEMENT : {message!r} (URL résultante : "
            f"{resultat.get('url', '?')}). Donnée de calibration {nettoyage}. Utilise ce texte au "
            "caractère près si ton assertion en dépend, ou une correspondance partielle stable si "
            "une partie est variable.")
        # §F8 (2026-09-23) : ce message est désormais un OBSERVÉ — `smoke_check` (génération)
        # doit pouvoir vérifier qu'un texte affirmé dans le `.feature` en découle vraiment, plutôt
        # que d'être deviné (cas 97, campagne réelle du 23/09).
        from testpilot.generation.smoke_check import MESSAGE_SOURCE_PREFIX
        outcome.verified_fields = {f"{MESSAGE_SOURCE_PREFIX}attempt_form_submission:{page_url}":
                                   [message]}
        return outcome
    return _outcome(
        f"Après soumission, aucun message visible détecté (URL résultante : "
        f"{resultat.get('url', '?')}). Donnée de calibration {nettoyage}. N'affirme pas un texte "
        "que tu n'as pas observé — une affirmation de présence/redirection reste possible.")


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
