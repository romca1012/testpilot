"""Pilier 1 — analyse d'une spécification fonctionnelle en TestPlan.

L'analyse n'appelle que le LLM (aucune dépendance à la cible vivante). Elle extrait
l'intention métier (modèles, actions, scénarios, assertions) et, si la spec les décrit
explicitement, le parcours technique. Elle n'invente JAMAIS un détail absent : les champs
techniques vides seront découverts par l'agent à l'exécution (boîte noire).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from testpilot import config
from testpilot.analysis.plan import NavStep, ScenarioIntent, SubmissionSpec, TestPlan
from testpilot.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

_SYSTEM = "Tu es un analyste de tests fonctionnels BDD. Réponds uniquement en JSON valide."


def spec_hash(content: str) -> str:
    """Empreinte stable d'une spec (détection d'évolution → cas « à réviser »)."""
    return hashlib.sha1((content or "").encode("utf-8")).hexdigest()[:12]


def _parse_nav_steps(raw: list | None) -> list[NavStep]:
    out: list[NavStep] = []
    for n in raw or []:
        if not isinstance(n, dict):
            continue
        kind = n.get("kind", "goto")
        if kind not in ("goto", "click_tab", "click_item", "js_trigger"):
            kind = "goto"
        out.append(NavStep(
            kind=kind,
            target=str(n.get("target", "")),
            selector=str(n.get("selector", "")),
            method=str(n.get("method", "GET") or "GET").upper(),
        ))
    return out


def _parse_submission(raw: dict | None) -> SubmissionSpec | None:
    if not isinstance(raw, dict):
        return None
    mech = raw.get("mechanism", "")
    if mech not in ("button_click", "fetch_post", "js_post"):
        return None
    return SubmissionSpec(
        mechanism=mech,
        endpoint=str(raw.get("endpoint", "")),
        trigger_selector=str(raw.get("trigger_selector", "")),
    )


def _citer_ou_retirer(entries: list, content: str, module_name: str) -> list[str]:
    """Ne garde un modèle proposé que s'il est accompagné d'une citation VÉRIFIABLE — une
    sous-chaîne réelle de la spec source. Technique documentée par Anthropic (guide « reduce
    hallucinations ») : ancrer sur des citations exactes, retirer une affirmation qu'aucune
    citation ne soutient.

    ⚠️ **Ce que ça bouche.** Ce pilier est un site « texte pur » (`call_simple`, aucun outil
    d'observation) — jusqu'ici, un modèle inventé (plausible pour le domaine mais absent de la
    spec) traversait cette étape sans aucun contrôle : le seul garde-fou existant
    (`generation/smoke_check.py`) n'intervient que bien plus tard, sur un Gherkin déjà écrit.

    Repli rétrocompatible : le LLM peut encore répondre par une liste de chaînes nues (ancien
    format, ou modèle qui n'a pas suivi la consigne) — accepté seulement si le nom lui-même
    apparaît tel quel dans la spec, jamais accepté à l'aveugle.
    """
    retenues: list[str] = []
    contenu_lower = content.lower()
    for entree in entries or []:
        if isinstance(entree, str):
            nom = entree.strip()
            if not nom:
                continue
            if nom.lower() in contenu_lower:
                retenues.append(nom)
            else:
                logger.warning(
                    "[analyzer] %s : modèle '%s' proposé sans citation vérifiable — écarté",
                    module_name, nom)
            continue
        if not isinstance(entree, dict):
            continue
        nom = str(entree.get("name", "")).strip()
        citation = str(entree.get("citation", "")).strip()
        if not nom:
            continue
        if citation and citation.lower() in contenu_lower:
            retenues.append(nom)
        else:
            logger.warning(
                "[analyzer] %s : modèle '%s' écarté — citation absente ou introuvable dans la "
                "spec (%r)", module_name, nom, citation[:80])
    return retenues


class SpecAnalyzer:
    def __init__(self, llm: LLMAdapter | None = None, cost_tracker=None,
                 connector_type: str = "odoo", model: str = ""):
        self.llm = llm or LLMAdapter()
        self.cost_tracker = cost_tracker
        self.connector_type = connector_type
        self.model = model or config.MODEL_FAST

    # ── Entrées publiques ────────────────────────────────────────────────────
    def analyze_spec_file(self, spec_path: str | Path) -> TestPlan:
        path = Path(spec_path)
        content = self._read_spec(path)
        logger.info("[analyzer] analyse spec : %s", path.stem)
        return self.analyze_spec_content(path.stem, content)

    def analyze_spec_content(self, module_name: str, content: str) -> TestPlan:
        logger.info("[analyzer] analyse spec content : %s (%d chars)", module_name, len(content))
        prompt = self._build_prompt(content)

        extracted = self._extract_plan_json(prompt, max_tokens=8000)
        if not extracted.get("scenarios"):
            logger.warning("[analyzer] plan vide — retry JSON compact (max_tokens=12000)")
            extracted = self._extract_plan_json(
                prompt + "\n\nIMPORTANT : réponds en JSON MINIFIÉ (aucun espace superflu).",
                max_tokens=12000,
            )
        if not extracted.get("scenarios"):
            logger.warning("[analyzer] 0 scénario extrait pour '%s'", module_name)

        modeles_verifies = _citer_ou_retirer(extracted.get("models", []), content, module_name)

        scenarios = [
            ScenarioIntent(
                name=s.get("name", "Scénario"),
                type=s.get("type", "nominal"),
                action=s.get("action", ""),
                persona=s.get("persona", "utilisateur"),
                preconditions=s.get("preconditions", []),
                expected_outcome=s.get("expected_outcome", ""),
                models_involved=s.get("models_involved", []),
                navigation=_parse_nav_steps(s.get("navigation")),
                assertions=[a for a in s.get("assertions", []) if isinstance(a, dict)],
            )
            for s in extracted.get("scenarios", [])
        ]

        return TestPlan(
            module_name=module_name,
            models=modeles_verifies,
            scenarios=scenarios,
            personas=extracted.get("personas", ["utilisateur"]),
            portal_routes=extracted.get("portal_routes", []),
            risks=extracted.get("ambiguities", []),
            connector_type=self.connector_type,
            cost_usd=self.cost_tracker.total_cost if self.cost_tracker else 0.0,
            raw_spec=content,
            entry_url=str(extracted.get("entry_url", "") or ""),
            server_injected_fields=[str(f) for f in extracted.get("server_injected_fields", []) if f],
            submission=_parse_submission(extracted.get("submission")),
            required_role=str(extracted.get("required_role", "") or ""),
        )

    # ── Construction du prompt ───────────────────────────────────────────────
    def _build_prompt(self, content: str) -> str:
        model_hint = "modèle.odoo" if self.connector_type == "odoo" else "modèle/ressource"
        return f"""Analyse cette spécification fonctionnelle pour un système de type « {self.connector_type} ».
Extrais en JSON :
{{
  "models": [{{"name": "sale.order", "citation": "phrase EXACTE de la spec qui nomme ce modèle"}}, ...],
  "personas": ["acheteur", "manager"],
  "portal_routes": ["/my/orders", ...],
  "ambiguities": ["..."],
  "entry_url": "URL d'entrée du parcours si la spec en décrit un, sinon \\"\\"",
  "server_injected_fields": ["champs peuplés CÔTÉ SERVEUR par le parcours"],
  "submission": {{"mechanism": "button_click|fetch_post|js_post", "endpoint": "", "trigger_selector": ""}},
  "required_role": "rôle requis ou \\"\\"",
  "scenarios": [
    {{
      "name": "Nom du scénario",
      "type": "nominal|erreur|limite",
      "action": "décrire l'action",
      "persona": "qui effectue l'action",
      "preconditions": ["..."],
      "expected_outcome": "résultat attendu",
      "models_involved": ["{model_hint}"],
      "navigation": [{{"kind": "goto|click_tab|click_item|js_trigger", "target": "texte ou URL", "selector": "CSS éventuel", "method": "GET|POST"}}],
      "assertions": [{{"model": "{model_hint}", "field": "nom_du_champ", "expected": "valeur attendue"}}]
    }}
  ]
}}

RÈGLES D'EXTRACTION (n'invente JAMAIS — champ absent ⇒ valeur vide) :
- PRIORITÉ À L'INTENTION : actions, expected_outcome et scenarios doivent TOUJOURS être extraits.
- LES CHAMPS TECHNIQUES SONT OPTIONNELS (entry_url, server_injected_fields, submission,
  selector) : ne les remplis QUE si la spec les fournit. Sinon vides — l'agent les
  DÉCOUVRIRA en explorant l'application (boîte noire). Ne devine jamais une URL/sélecteur.
- assertions[] : pour chaque champ vérifié après soumission, utilise le NOM EXACT du champ
  tel qu'écrit dans la spec.
- models[].citation : copie MOT POUR MOT un extrait de la spec ci-dessous qui nomme ce modèle —
  jamais une reformulation. Un modèle dont la citation ne se retrouve pas telle quelle dans le
  texte source sera écarté avant même d'atteindre la génération.

Réponds UNIQUEMENT en JSON valide. Génère au minimum 3 scénarios (1 nominal, 1 erreur, 1 limite).

Spécification :
{content}"""

    # ── Appel LLM + parsing robuste ──────────────────────────────────────────
    def _extract_plan_json(self, prompt: str, max_tokens: int) -> dict:
        raw = self.llm.call_simple(
            system_prompt=_SYSTEM,
            user_content=prompt,
            model=self.model,
            max_tokens=max_tokens,
            cost_tracker=self.cost_tracker,
            label="analysis",
        )
        logger.debug("[analyzer] raw LLM (%d chars)", len(raw))
        return self._parse_json_response(raw)

    def _parse_json_response(self, text: str) -> dict:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        candidate = match.group(0) if match else text
        try:
            return json.loads(candidate)
        except Exception as exc:
            repaired = self._repair_truncated_json(candidate)
            if repaired is not None:
                logger.warning("[analyzer] JSON tronqué réparé (%s) — %d scénario(s)",
                               exc, len(repaired.get("scenarios", [])))
                return repaired
            logger.warning("[analyzer] JSON invalide (%s)", exc)
            return {}

    @staticmethod
    def _repair_truncated_json(text: str) -> dict | None:
        """Ferme un JSON coupé par la limite de tokens en rééquilibrant les délimiteurs."""
        cut = max(text.rfind("}"), text.rfind("]"))
        if cut == -1:
            return None
        head = text[: cut + 1]
        stack: list[str] = []
        in_str = esc = False
        for ch in head:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch in "{[":
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()
        closing = "".join("}" if c == "{" else "]" for c in reversed(stack))
        try:
            return json.loads(head + closing)
        except Exception:
            return None

    @staticmethod
    def _read_spec(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                import pdfplumber
            except ImportError as exc:
                raise ImportError("pdfplumber requis pour lire un PDF : pip install pdfplumber") from exc
            with pdfplumber.open(path) as pdf:
                return "\n\n".join(p.extract_text() or "" for p in pdf.pages).strip()
        if suffix in (".md", ".txt"):
            return path.read_text(encoding="utf-8").strip()
        raise ValueError(f"Format de spec non supporté : {suffix}")
