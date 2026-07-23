"""Le VERROU de coût de la migration Sonnet 5 (Vague 2, B1) — QUASI GRATUIT.

    PYTHONUTF8=1 python scripts/mesure_cout_tokenizer.py

⚠️ **Ce qu'il mesure, et ce qu'il ne mesure pas.** Le prix par token de Sonnet 5 est le MÊME que
Sonnet 4.6 (3/15 $ le million). Ce qui change, c'est le NOMBRE de tokens : Sonnet 5 a un nouveau
tokenizer (≈ +30 % documenté). Ce script compte les tokens d'un prompt de génération RÉEL sur les
DEUX modèles (`count_tokens`, sans aucune génération → ~0 €) et projette l'impact sur le §9.

C'est le chiffre que le porteur lit pour décider le FLIP (`TESTPILOT_MODEL_GENERATION=claude-sonnet-5`).
Pas une extrapolation : le delta est mesuré sur NOTRE prompt système + un plan réel.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot import config  # noqa: E402
from testpilot.analysis.spec_analyzer import SpecAnalyzer  # noqa: E402
from testpilot.generation import domain_model, prompt as pm, steps_library  # noqa: E402
from testpilot.store.db import get_initialized_db  # noqa: E402
from testpilot.store.repositories import ProjectRepo  # noqa: E402

ANCIEN = "claude-sonnet-4-6"
NOUVEAU = "claude-sonnet-5"
# Cible du §9 : moins de 1 € (~1,08 $) par cas, génération incluse.
CIBLE_9 = 1.08


def _prompt_representatif() -> tuple[str, str]:
    """Le prompt système + le message initial d'une génération réelle (annuaire du projet 1)."""
    conn = get_initialized_db(config.DB_PATH)
    projet = ProjectRepo(conn).get(1)
    conn.close()
    modele = domain_model.charger_modele(projet) if projet else None

    spec = Path("specs/mesure/achat_siege.md").read_text(encoding="utf-8")
    # Analyse SANS LLM : on ne veut qu'un TestPlan plausible pour dimensionner le prompt. On
    # construit un plan minimal à la main plutôt que de payer une analyse.
    from testpilot.analysis.plan import TestPlan
    plan = TestPlan(module_name="achat_siege", models=["helpdesk.ticket"], scenarios=[],
                    personas=["utilisateur"], portal_routes=["/achat_siege/{id}"], risks=[],
                    connector_type="odoo", cost_usd=0.0, raw_spec=spec,
                    entry_url="/achat_siege/{id}")

    systeme = pm.build_system_prompt(connector=None, shared_steps=steps_library.catalogue())
    initial = pm.build_initial_message(plan, modele)
    return systeme, initial


def _compter(client, model: str, systeme: str, initial: str) -> int:
    resp = client.messages.count_tokens(
        model=model,
        system=[{"type": "text", "text": systeme}],
        messages=[{"role": "user", "content": initial}],
    )
    return resp.input_tokens


def _cout_entree(tokens: int, model: str) -> float:
    from testpilot.guardrails.cost_tracker import PRICING, _PRICING_FALLBACK
    prix = PRICING.get(model, PRICING[_PRICING_FALLBACK])["input"]
    return tokens * prix / 1_000_000


def main() -> int:
    import anthropic
    if not config.ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY manquante — impossible d'appeler count_tokens.")
        return 1
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    systeme, initial = _prompt_representatif()
    print("=" * 70)
    print("MESURE TOKENIZER — Sonnet 4.6 vs Sonnet 5 (count_tokens, ~0 €)")
    print("=" * 70)
    print(f"Prompt système : {len(systeme)} caractères · message initial : {len(initial)} caractères")

    t_ancien = _compter(client, ANCIEN, systeme, initial)
    t_nouveau = _compter(client, NOUVEAU, systeme, initial)
    delta = (t_nouveau / t_ancien - 1) * 100 if t_ancien else 0.0

    print(f"\n  {ANCIEN:20} : {t_ancien:>7} tokens d'entrée")
    print(f"  {NOUVEAU:20} : {t_nouveau:>7} tokens d'entrée")
    print(f"  → écart tokenizer : {delta:+.1f} %")

    # Projection §9 : l'ENTRÉE du prompt est le poste dominant (répété à chaque tour ReAct). On
    # projette le coût d'entrée d'UN appel aux deux modèles — l'ordre de grandeur qui décide.
    c_ancien = _cout_entree(t_ancien, ANCIEN)
    c_nouveau = _cout_entree(t_nouveau, NOUVEAU)
    print(f"\n  Coût d'ENTRÉE d'un appel (tarif plein) :")
    print(f"    {ANCIEN:20} : ${c_ancien:.5f}")
    print(f"    {NOUVEAU:20} : ${c_nouveau:.5f}  ({(c_nouveau/c_ancien-1)*100:+.1f} %)")
    print(f"\n  Cible §9 : < ${CIBLE_9:.2f} / cas. L'écart ci-dessus s'applique à TOUS les tokens")
    print("  d'entrée du run (× nombre de tours ReAct). ⚠️ Le cache de prompt amortit la majeure")
    print("  partie : seul le premier tour paie plein tarif, les suivants ~0,1× (cache_read).")
    print("\n  → Décision du FLIP au porteur : basculer TESTPILOT_MODEL_GENERATION=claude-sonnet-5")
    print("    si l'écart projeté laisse le §9 tenu. Sinon, rester sur Sonnet 4.6.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
