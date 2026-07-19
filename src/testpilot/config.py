"""Configuration centralisée — source unique de vérité pour TestPilot (Incrément 0).

Toute valeur ajustable passe par une variable d'environnement (préfixe ``TESTPILOT_``
ou nom natif du connecteur). Aucun secret n'est codé en dur.
"""

import os
from pathlib import Path

# Chargement .env optionnel : le socle reste importable même sans python-dotenv installé.
try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:  # pragma: no cover - dépendance absente en CI minimale
    pass

APP_VERSION = "0.1.0"

# ── Racines de chemins ────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent.parent  # racine du dépôt testpilot/

DATA_DIR = Path(os.getenv("TESTPILOT_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = Path(os.getenv("TESTPILOT_DB_PATH", str(DATA_DIR / "testpilot.db")))
REPORTS_DIR = DATA_DIR / "reports"

BEHAVE_RUNTIME_DIR = BASE_DIR / "behave_runtime"
GENERATED_DIR = BEHAVE_RUNTIME_DIR / "generated"
STEPS_LIBRARY_DIR = BEHAVE_RUNTIME_DIR / "steps_library"

PROMPTS_DIR = SRC_DIR / "generation" / "prompts"
REPORT_TEMPLATES_DIR = SRC_DIR / "reporting" / "templates"

# ── LLM (Anthropic) ───────────────────────────────────────────────────────────
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Clé Admin (optionnelle) — nécessaire uniquement pour les coûts réels (stubés en Inc. 0).
ANTHROPIC_ADMIN_KEY = os.getenv("ANTHROPIC_ADMIN_KEY", "")

MODEL_GENERATION = os.getenv("TESTPILOT_MODEL_GENERATION", "claude-sonnet-4-6")
MODEL_FAST = os.getenv("TESTPILOT_MODEL_FAST", "claude-haiku-4-5-20251001")
MODEL_REPAIR = os.getenv("TESTPILOT_MODEL_REPAIR", "claude-haiku-4-5-20251001")

# ── Garde-fous agent (par run) ────────────────────────────────────────────────
MAX_ITERATIONS = int(os.getenv("TESTPILOT_MAX_ITERATIONS", "25"))
REPAIR_STALL_LIMIT = int(os.getenv("TESTPILOT_REPAIR_STALL_LIMIT", "3"))

# Plafond d'UN run d'agent (génération, analyse) — recalibré le 2026-07-17 sur mesure réelle.
# Il valait $2,00 ≈ 1,85 EUR : presque le DOUBLE du §9 à lui seul, et **16,6× le coût réel**.
#
# LA MESURE (chemin ÉCRAN, la vraie route HTTP, spec `demande_materiel` — la MÊME que la
# référence CLI, sinon on compare deux charges de travail et pas deux chemins) :
#     génération (écran, 2026-07-17) = $0,1050
#     génération (CLI,   2026-07-15) = $0,4529   ← RÉGIME RÉVOLU, voir ci-dessous
#     analyse    (écran, 2026-07-17) = $0,0157   ← n'avait JAMAIS été mesurée
#
# ⚠️ **Le $0,4529 n'est pas « le coût de la génération » : c'est le coût d'AVANT les garde-fous.**
# Sur la même spec, l'agent d'aujourd'hui produit **1 973 car. de steps contre 15 312** (7,8×
# moins) — et **plus** de couverture : 4 scénarios / 44 assertions contre 3 scénarios. Il réutilise
# la bibliothèque au lieu de tout réinventer. C'est le gain **mesuré** du catalogue (`0003`), des
# notes par step (`0012`) et du contrat `{field}` (`0007` A1). Le travail de prompt des deux
# derniers jours a coûté 0 € et divisé la génération par ~4.
#
# $0,50 = **4,8× le coût réel d'aujourd'hui**, et au-dessus du pire jamais observé ($0,4529) :
# ce plafond n'aurait fait échouer **aucune** génération jamais mesurée. Il est là pour couper une
# boucle emballée (25 itérations), pas pour border le travail normal — un plafond qui fait échouer
# une création légitime coûte plus cher qu'il ne rapporte.
COST_LIMIT_PER_RUN_USD = float(os.getenv("TESTPILOT_COST_LIMIT_RUN_USD", "0.50"))

# Tentatives de réparation autorisées PAR DÉFAUT à l'approbation d'une version (décision 0014).
# Le gate reste souverain : le relecteur peut descendre à 0 pour interdire toute réparation.
# Défaut à 2 et non à 0 — arbitrage du porteur : le §6 du brief veut une réparation « invisible
# pour l'utilisateur » ; un défaut à 0 la rendrait opt-in à chaque relecture, ce qui la rendrait
# visible et manuelle (le ping-pong écarté avec l'option B du cadrage).
REPAIR_BUDGET_DEFAULT = int(os.getenv("TESTPILOT_REPAIR_BUDGET_DEFAULT", "2"))

# ── Budget mensuel : NON PERTINENT AU PRODUIT (brief amendé le 2026-07-17) ────
# ⚠️ NE RIEN CONSTRUIRE DESSUS. Le « 50 €/mois » était le budget de DÉVELOPPEMENT du porteur de
# projet, jamais une limite applicative. Le brief a été AMENDÉ en ce sens (§6, §9, §11.2 +
# journal des amendements) : il n'y a **pas** de plafond mensuel produit à faire respecter.
# Ces constantes sont conservées telles quelles et **lues par personne** — c'est voulu, pas un
# oubli. Le seul objectif de coût du produit est `BUDGET_PER_CASE_*` ci-dessous.
MONTHLY_BUDGET_EUR = float(os.getenv("TESTPILOT_MONTHLY_BUDGET_EUR", "50"))
EUR_USD_RATE = float(os.getenv("TESTPILOT_EUR_USD_RATE", "1.08"))
MONTHLY_BUDGET_USD = MONTHLY_BUDGET_EUR * EUR_USD_RATE

# ── Budget UNITAIRE : § 9 du brief — L'UNIQUE CIBLE DE COÛT DU PRODUIT ────────
# « Moins de 1 € pour un nouveau cas de test » (génération + exécution + rapport). Depuis
# l'amendement du 2026-07-17, c'est la SEULE contrainte de coût du produit — il n'y en a pas
# d'autre, et il n'y en a plus de mensuelle.
#
# ⚠️ **CE SEUIL SE COMPARE À UNE CRÉATION, JAMAIS À UN CUMUL** (arbitrage du porteur, 2026-07-17).
#   `CostRepo.creation_cost_usd(case)`   → analyse + génération = CE QUI SE COMPARE À CE SEUIL.
#                                          Mesuré le 2026-07-17 : $0,1207 = 11 % du §9.
#   `CostRepo.total_for_case_usd(case)`  → tout depuis toujours = TÉLÉMÉTRIE DE DEBUG.
#                                          Le cas 1 y affiche $1,1552 = « 107 % » — et ce n'est
#                                          PAS un dépassement : il cumule 5 sessions de débogage
#                                          de l'outil et 7 versions.
# Les confondre fabrique une alarme fausse. C'est arrivé, d'où ces lignes.
BUDGET_PER_CASE_EUR = float(os.getenv("TESTPILOT_BUDGET_PER_CASE_EUR", "1.00"))
BUDGET_PER_CASE_USD = BUDGET_PER_CASE_EUR * EUR_USD_RATE

# ⚠️ SUPERSÉDÉ le 2026-07-19 — plus lu par le garde-fou. La boucle de réparation borne désormais
# le CUMUL du cas (génération + TOUTES les réparations) au **§9** (`BUDGET_PER_CASE_USD`), en
# amorçant son `CostTracker` avec ce que le cas a déjà dépensé (`total_for_case_usd`). Deux
# sous-plafonds indépendants ($0,50 génération + $0,62 réparations) pouvaient s'additionner
# au-dessus du §9 ($1,12 = 104 %) alors que chacun restait sous son seuil : l'enveloppe cumulée
# unique ferme ce trou. Cette constante est conservée pour compat d'env, mais **plus personne ne
# la lit** — même statut que `MONTHLY_BUDGET_*`. Ne rien reconstruire dessus.
#
# --- Historique (calibrage du 2026-07-17, désormais caduc comme garde) ---
# Plafond de coût des RÉPARATIONS CUMULÉES d'un cas — calibré sur mesures réelles.
#
# LE CALCUL — calibré sur le PIRE observé, comme doit l'être un plafond :
#     §9                          = 1,00 € × 1,08          = $1,0800
#     − génération, PIRE jamais mesuré                     = $0,4529   (régime révolu, cf.
#     ────────────────────────────────────────────────────────────────  COST_LIMIT_PER_RUN_USD)
#     = marge disponible pour TOUTES les réparations du cas = $0,6271  → arrondi à $0,62
#
# Vérification contre `REPAIR_BUDGET_DEFAULT = 2` : 2 × $0,2895 (réparation mesurée) = $0,5790
# ≤ $0,62. Ça tient → **le budget par défaut reste à 2** : la mesure ne demande pas de le
# descendre à 1.
#
# ⚠️ RÉSERVES HONNÊTES, à ne pas taire :
#  • **un seul échantillon** de réparation ;
#  • le $0,2895 est **périmé À LA BAISSE** : mesuré avec `dry_runner=None`, donc 2 appels LLM par
#    tentative (l'écriture + un tour perdu). Le fix P0 en supprime un sur le chemin heureux.
#    Non re-mesuré — ce sera fait au rejeu du cas 1.
# Point de départ mesuré, pas une vérité.
REPAIR_COST_LIMIT_PER_CASE_USD = float(
    os.getenv("TESTPILOT_REPAIR_COST_LIMIT_PER_CASE_USD", "0.62"))

# ── Le §9 tenu de bout en bout : où en est-on vraiment (2026-07-17) ───────────
# ✅ Le trou « la génération n'est pas bornée » est COMBLÉ : `COST_LIMIT_PER_RUN_USD` est passé de
# $2,00 (16,6× le réel) à $0,50, sur mesure du chemin ÉCRAN — celui des utilisateurs.
#
# RÉEL MESURÉ (chemin écran, spec `demande_materiel`) :
#     analyse $0,0157 + génération $0,1050        = **$0,1207**  →  **11 % du §9**
#     + 2 réparations au tarif mesuré (+$0,5790)  = **$0,6997**  →  **65 % du §9**
# On est confortablement dessous. Et ce n'est PAS un plafond qui l'obtient : c'est le travail de
# garde-fous (catalogue `0003`, notes `0012`, contrat `0007` A1) qui a divisé la génération par 4.
#
# ⚠️ CE QUE LES PLAFONDS NE GARANTISSENT PAS, et il faut le dire : $0,50 + $0,62 = $1,12, soit
# **104 % du §9** si les DEUX saturaient simultanément. Ce cas exige que la génération coûte 4,8×
# sa valeur mesurée — auquel cas le plafond a déjà coupé et un humain est dans la boucle.
# **Les plafonds sont un filet anti-emballement, pas le mécanisme qui délivre le §9.** Les serrer
# davantage ferait échouer des créations légitimes : on paierait plus cher que ce qu'on économise.
#
# Source des coûts : "estimated" (tokens × barème, actif) | "anthropic_api" (stub Inc. 0).
COST_SOURCE = os.getenv("TESTPILOT_COST_SOURCE", "estimated")

# ── Behave ────────────────────────────────────────────────────────────────────
BEHAVE_DRY_TIMEOUT_SECONDS = int(os.getenv("TESTPILOT_BEHAVE_DRY_TIMEOUT", "120"))
BEHAVE_REAL_TIMEOUT_SECONDS = int(os.getenv("TESTPILOT_BEHAVE_REAL_TIMEOUT", "900"))

# ── Connecteur Odoo (unique cible de l'Incrément 0) ───────────────────────────
ODOO_URL = os.getenv("ODOO_URL", "http://localhost:10017")
ODOO_DB = os.getenv("ODOO_DB", "odoo_test")
ODOO_USER = os.getenv("ODOO_USER", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")

# ── Sécurité : jamais la production ───────────────────────────────────────────
if os.getenv("ODOO_ENV") == "prod":
    raise EnvironmentError(
        "SAFETY: refus d'exécution contre une instance Odoo de production."
    )


def ensure_dirs() -> None:
    """Crée les répertoires runtime (idempotent)."""
    for directory in (DATA_DIR, REPORTS_DIR, GENERATED_DIR):
        directory.mkdir(parents=True, exist_ok=True)
