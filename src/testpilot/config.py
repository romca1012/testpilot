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

# ── Budget mensuel cumulé (§6/§9) ─────────────────────────────────────────────
# Le brief fixe 50 €/mois ; les coûts LLM arrivent en USD. On tracke tout en USD et
# on convertit le plafond via un taux configurable (décision de cadrage validée).
MONTHLY_BUDGET_EUR = float(os.getenv("TESTPILOT_MONTHLY_BUDGET_EUR", "50"))
EUR_USD_RATE = float(os.getenv("TESTPILOT_EUR_USD_RATE", "1.08"))
MONTHLY_BUDGET_USD = MONTHLY_BUDGET_EUR * EUR_USD_RATE
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
