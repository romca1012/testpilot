"""Le filtre de chemins de `banc.yml` couvre les répertoires que le banc Odoo exerce (2026-09-25).

Le filtre listait des FICHIERS ; le lot 07c a modifié `behave_runtime/environment.py`, `connectors/odoo.py` et `connectors/runtime_env.py`
— exercés par la mesure du banc — sans déclencher le banc. Ce test tient la liste des répertoires et échoue si l'un d'eux disparaît
du filtre ; il vérifie aussi que le coût de CI reste borné (aucun répertoire de documentation ou de frontend).
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
WORKFLOW = (RACINE / ".github" / "workflows" / "banc.yml").read_text(encoding="utf-8")


def _chemins_surveilles() -> list[str]:
    bloc = re.search(r"pull_request:\s*\n\s*paths:\n(.*?)\n\npermissions:", WORKFLOW, re.S).group(1)
    return re.findall(r'^\s*-\s*"([^"]+)"', bloc, re.M)


REPERTOIRES_EXERCES = ("behave_runtime/**", "src/testpilot/connectors/**", "src/testpilot/execution/**",
                       "src/testpilot/verdict/**")


def test_les_repertoires_exerces_par_le_banc_declenchent_le_banc():
    chemins = _chemins_surveilles()

    manquants = [r for r in REPERTOIRES_EXERCES if r not in chemins]
    assert not manquants, f"banc.yml ne surveille plus : {manquants}"


def test_les_artefacts_generes_sont_exclus():
    chemins = _chemins_surveilles()

    assert "!behave_runtime/generated/**" in chemins
    assert chemins.index("behave_runtime/**") < chemins.index("!behave_runtime/generated/**"), (
        "une exclusion doit suivre le motif qu'elle retire")


def test_falsifiable_les_fichiers_du_lot_07c_seraient_maintenant_couverts():
    """Les trois fichiers que le filtre d'avant a laissé passer sont sous un répertoire surveillé."""
    chemins = _chemins_surveilles()
    for fichier in ("behave_runtime/environment.py", "src/testpilot/connectors/odoo.py",
                    "src/testpilot/connectors/runtime_env.py"):
        assert any(fichier.startswith(c.rstrip("*")) for c in chemins if not c.startswith("!")), fichier


def test_aucun_repertoire_surveille_ne_contient_de_documentation_ni_de_frontend():
    """Coût de CI borné : un répertoire de code, pas un dossier que la documentation ou le frontend feraient déclencher pour rien."""
    # Les quatre répertoires de CODE ajoutés au filtre — pas `banc/**` (le dossier du banc lui-même, dont le README déclenche déjà le banc
    # depuis le lot 04 : une documentation du banc EST une modification du banc).
    for chemin in REPERTOIRES_EXERCES:
        base = chemin.split("*")[0].rstrip("/")
        cible = RACINE / base
        if not cible.is_dir():
            continue
        parasites = [p for p in cible.rglob("*")
                     if p.is_file() and p.suffix in {".md", ".vue", ".ts", ".css", ".html"}
                     and "generated" not in p.parts and "__pycache__" not in p.parts]
        assert not parasites, f"{chemin} déclencherait le banc pour {parasites[:3]}"
