"""Q3-a — surcoût, en tokens et en dollars, des définitions d'outils durcies. LOCAL, ne dépense rien.

    PYTHONUTF8=1 python scripts/mesure_cout_outils_q3a.py

⚠️ **C'est une ESTIMATION, pas une mesure.** Aucun appel à l'API : les tokens sont estimés à
`caractères / 4` (règle empirique de l'anglais). Le français et le JSON se découpent en général en
plus de tokens (≈ 3 caractères par token) : le script donne donc AUSSI une borne haute à
`caractères / 3`. Le chiffre qui fait foi se lit sur `usage.input_tokens` d'un appel réel (ou
`count_tokens`, `scripts/mesure_cout_tokenizer.py`) — à faire avec l'accord du porteur.

Modèle de coût (`guardrails/cost_tracker.PRICING`, claude-sonnet-4-6 = modèle de génération par
défaut) : les outils précèdent le prompt système dans le préfixe, et `cache_control` est posé sur le
bloc système (`llm/adapter.py::call_with_tools`) : outils et système sont donc mis en cache ENSEMBLE.
Un octet de plus dans une définition d'outil se paie une fois en écriture de cache (tour 1, 1,25x),
puis `tours - 1` fois en lecture de cache (0,1x). Sans cache, il se paierait `tours` fois plein tarif.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot import config  # noqa: E402
from testpilot.generation import prompt as pm  # noqa: E402
from testpilot.generation.interrupteurs import (  # noqa: E402
    ENV_PROMPT_HYPOTHESES,
    ENV_TOOLS_DESCRIPTIONS_V2,
    ENV_TOOLS_STRICT,
)
from testpilot.generation.technical_plan import HYPOTHESE_MAX_CARACTERES, HYPOTHESES_MAX  # noqa: E402
from testpilot.generation.tools.api_definitions import tools_for_api  # noqa: E402
from testpilot.guardrails.cost_tracker import PRICING  # noqa: E402

MODELE = "claude-sonnet-4-6"
TOURS = 25                      # plafond dur de la boucle (`config.MAX_ITERATIONS`)
CONFIGURATIONS: dict[str, dict[str, str]] = {
    "actuel (tout éteint)": {},
    "descriptions V2": {ENV_TOOLS_DESCRIPTIONS_V2: "1"},
    "strict + input_examples": {ENV_TOOLS_STRICT: "1"},
    "strict + exemples + hypothèses": {ENV_TOOLS_STRICT: "1", ENV_PROMPT_HYPOTHESES: "1"},
    "tout allumé": {ENV_TOOLS_STRICT: "1", ENV_PROMPT_HYPOTHESES: "1",
                    ENV_TOOLS_DESCRIPTIONS_V2: "1"},
}


def estimer_tokens(texte: str, caracteres_par_token: float = 4.0) -> int:
    """Estimation locale : `ceil(caractères / ratio)`. Jamais un décompte exact."""
    return math.ceil(len(texte) / caracteres_par_token)


def tokens_outils(env: dict[str, str], caracteres_par_token: float = 4.0) -> int:
    """Tokens estimés de la liste d'outils envoyée sous cette configuration."""
    return estimer_tokens(json.dumps(tools_for_api(env), ensure_ascii=False), caracteres_par_token)


def surcout_usd(tokens_en_plus: int, tours: int = TOURS, modele: str = MODELE) -> dict[str, float]:
    """Ce que coûtent `tokens_en_plus` tokens d'ENTRÉE ajoutés au préfixe d'un run de `tours` tours.

    `avec_cache` : 1 écriture de cache + (tours - 1) lectures — le cas nominal. `sans_cache` : plein
    tarif à chaque tour — le pire cas (cache invalide, ou expiré entre deux tours > 5 min).
    """
    p = PRICING[modele]
    avec_cache = tokens_en_plus * (p["cache_write"] + (tours - 1) * p["cache_read"]) / 1_000_000
    sans_cache = tokens_en_plus * tours * p["input"] / 1_000_000
    return {"avec_cache": avec_cache, "sans_cache": sans_cache}


def surcout_sortie_hypotheses_usd(tours_restants: int = TOURS - 1, modele: str = MODELE,
                                  caracteres_par_token: float = 4.0) -> float:
    """Borne HAUTE du coût d'un champ `hypotheses_non_verifiees` plein (5 x 200 caractères).

    Écrit UNE fois en sortie (tarif sortie), puis relu à chaque tour suivant dans l'historique mis en
    cache (tarif lecture de cache). C'est un plafond : un champ réel est bien plus court.
    """
    p = PRICING[modele]
    tokens = estimer_tokens("x" * (HYPOTHESES_MAX * HYPOTHESE_MAX_CARACTERES), caracteres_par_token)
    return tokens * (p["output"] + tours_restants * p["cache_read"]) / 1_000_000


def main() -> None:
    base = tokens_outils({})
    systeme = estimer_tokens(pm.build_system_prompt(None, None))
    phrase = estimer_tokens(pm._PHRASE_HYPOTHESES)
    budget = config.BUDGET_PER_CASE_USD
    print("=" * 96)
    print("Q3-a — SURCOÛT DES DÉFINITIONS D'OUTILS (ESTIMATION LOCALE : caractères/4 ; borne haute /3)")
    print(f"Modèle {MODELE} · {TOURS} tours · budget §9 = {config.BUDGET_PER_CASE_EUR:.2f} EUR "
          f"= ${budget:.4f} par cas · plafond par run = ${config.COST_LIMIT_PER_RUN_USD:.2f}")
    print(f"Référence : outils actuels ≈ {base} tokens ; prompt système SANS catalogue ≈ {systeme}.")
    print("=" * 96)
    print(f"{'configuration':<34}{'outils':>8}{'Δ/appel':>9}{'Δ/appel(/3)':>13}"
          f"{'Δ$ (/3) cache':>14}{'Δ$ (/3) sans':>14}{'% du §9':>9}")
    for nom, env in CONFIGURATIONS.items():
        total = tokens_outils(env)
        delta = total - base
        delta_haut = tokens_outils(env, 3.0) - tokens_outils({}, 3.0)
        if ENV_PROMPT_HYPOTHESES in env:       # la phrase de prompt s'ajoute au préfixe système
            delta += phrase
            delta_haut += estimer_tokens(pm._PHRASE_HYPOTHESES, 3.0)
        cout = surcout_usd(delta_haut)         # on chiffre la borne HAUTE : le §9 se protège large
        print(f"{nom:<34}{total:>8}{delta:>9}{delta_haut:>13}"
              f"{cout['avec_cache']:>14.5f}{cout['sans_cache']:>14.5f}"
              f"{100 * cout['avec_cache'] / budget:>8.2f}%")
    sortie = surcout_sortie_hypotheses_usd()
    print(f"\nChamp d'hypothèses PLEIN (5 x {HYPOTHESE_MAX_CARACTERES} car.), écrit en sortie puis relu "
          f"en cache : ≤ ${sortie:.5f} par `write_test_plan` ({100 * sortie / budget:.2f} % du §9).")
    print("\nLimites : (1) estimation, pas décompte ; (2) l'API ajoute elle-même un prompt système "
          "d'outils et, en strict, un\nsurcoût d'entrée « légèrement plus élevé » (doc, montant non "
          "publié) ; (3) la 1re requête strict paie une\ncompilation de grammaire — LATENCE, pas "
          "tokens (cache 24 h) ; (4) un cache invalidé → colonne « sans cache ».")


if __name__ == "__main__":
    main()
