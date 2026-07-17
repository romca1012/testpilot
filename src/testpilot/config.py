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
COST_LIMIT_PER_RUN_USD = float(os.getenv("TESTPILOT_COST_LIMIT_RUN_USD", "2.00"))

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
# « Moins de 1 € pour un nouveau cas de test » (génération + exécution + rapport, réparations
# cumulées comprises). Depuis l'amendement du 2026-07-17, c'est la SEULE contrainte de coût du
# produit — il n'y en a pas d'autre, et il n'y en a plus de mensuelle.
BUDGET_PER_CASE_EUR = float(os.getenv("TESTPILOT_BUDGET_PER_CASE_EUR", "1.00"))
BUDGET_PER_CASE_USD = BUDGET_PER_CASE_EUR * EUR_USD_RATE

# Plafond de coût des RÉPARATIONS CUMULÉES d'un cas — calibré le 2026-07-17 sur mesures réelles.
#
# ⚠️ Ce plafond est PARTAGÉ par toutes les tentatives d'un cas, et c'est tout l'objet du
# correctif : `propose_fix` instanciait un `CostTracker()` NEUF à chaque tentative, donc chacune
# repartait de zéro avec le plafond entier. Le plafond ne bornait pas ce qu'il prétendait borner
# — un cas pouvait dépenser budget × plafond.
#
# LE CALCUL (mesures réelles du 2026-07-17, cas 1) :
#     §9                          = 1,00 € × 1,08          = $1,0800
#     − génération mesurée                                 = $0,4529   (42 % du §9)
#     ────────────────────────────────────────────────────────────────
#     = marge disponible pour TOUTES les réparations du cas = $0,6271  → arrondi à $0,62
#
# Vérification contre `REPAIR_BUDGET_DEFAULT = 2` : 2 × $0,2895 (réparation mesurée) = $0,5790,
# soit 93 % de ce plafond. Ça tient — avec 7 % de marge, pas plus.
#
# ⚠️ RÉSERVE HONNÊTE, à ne pas taire : **un seul échantillon**, et le coût d'une réparation a
# changé depuis (le dry-run branché rend le chemin heureux à 1 appel LLM au lieu de 2, et le
# chemin malheureux à N — non mesuré). Ce chiffre est un point de départ mesuré, pas une vérité.
# À réviser au prochain rejeu réel.
REPAIR_COST_LIMIT_PER_CASE_USD = float(
    os.getenv("TESTPILOT_REPAIR_COST_LIMIT_PER_CASE_USD", "0.62"))

# ⚠️ TROU CONNU, NON COMBLÉ ICI (arbitrage en attente) : `COST_LIMIT_PER_RUN_USD` = $2,00 ≈ 1,85 €
# borne encore la GÉNÉRATION — soit près du double du §9 à elle seule. Le §9 n'est donc pas encore
# tenu de bout en bout : seul le versant réparation l'est. Le combler suppose de plafonner aussi
# la génération, or la seule génération mesurée ($0,4529) ne laisserait que 10 % de marge sous
# $0,50 — un plafond que le premier cas plus gros ferait sauter, en échouant la création. À
# calibrer sur une 2ᵉ mesure, pas à deviner.
# Source des coûts : "estimated" (tokens × barème, actif) | "anthropic_api" (stub Inc. 0).
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
