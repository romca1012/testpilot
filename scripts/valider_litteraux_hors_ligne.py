"""Valide HORS LIGNE le contrôle « littéraux observés » (lot VH-05) sur des tests déjà générés : aucun LLM, aucun navigateur.

Pour chaque test généré d'une campagne du banc d'agents (`.local-preview/qualification/banc-agents-<cas>-t<essai>/campagne.json`),
applique `testpilot.generation.litteraux_observes` avec l'annuaire de l'application, puis confronte le résultat à ce que le rejeu
réel a donné sur l'application SAINE (rapport JSON de la campagne). Ce qu'on attend du contrôle :
- les tests sortis en erreur technique pour un littéral faux sont signalés (détection) ;
- les tests qui s'exécutaient correctement ne sont PAS signalés (aucun refus à tort) — chaque signalement d'un test « vert »
  est imprimé pour être examiné à la main : un vert peut venir du repli LLM à l'exécution (banc sans mode strict avant VH-01).

Usage : python scripts/valider_litteraux_hors_ligne.py --rapport docs/mesures/banc-agents-2026-10-08-base-3.json \
            --annuaire <chemin de projet-<id>.json> [--qualification .local-preview/qualification]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from testpilot.generation import litteraux_observes as lo  # noqa: E402


def charger_test(dossier: Path) -> tuple[str, str] | None:
    chemin = dossier / "campagne.json"
    if not chemin.exists():
        return None
    rapports = json.loads(chemin.read_text(encoding="utf-8"))
    gen = (rapports[0] if rapports else {}).get("generation") or {}
    if not gen.get("feature_content"):
        return None
    return gen["feature_content"], gen.get("steps_content") or ""


def main(argv=None) -> int:
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parseur = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parseur.add_argument("--rapport", type=Path, required=True)
    parseur.add_argument("--annuaire", type=Path, required=True)
    parseur.add_argument("--qualification", type=Path, default=RACINE / ".local-preview" / "qualification")
    args = parseur.parse_args(argv)

    annuaire = lo.annuaire_depuis_modele(json.loads(args.annuaire.read_text(encoding="utf-8")))
    autorises = lo.attributs_du_harnais(RACINE / "behave_runtime")
    rapport = json.loads(args.rapport.read_text(encoding="utf-8"))
    saines = {(o["cas"], o["essai"]): o for o in rapport["observations"] if o["variante"] == "saine"}

    bilan = Counter()
    for (cas, essai), obs in sorted(saines.items()):
        test = charger_test(args.qualification / f"banc-agents-{cas}-t{essai}")
        if test is None:
            bilan["sans test généré"] += 1
            continue
        feature, steps = test
        ecarts = lo.controler_feature(feature, annuaire) + lo.controler_steps(steps, annuaire, autorises)
        technique = obs["obtenu"] == "technical_error"
        cle = ("erreur technique " if technique else "exécuté ") + ("signalé" if ecarts else "non signalé")
        bilan[cle] += 1
        marque = {"erreur technique signalé": "DÉTECTÉ", "erreur technique non signalé": "MANQUÉ",
                  "exécuté signalé": "À EXAMINER", "exécuté non signalé": "ok"}[cle]
        print(f"[{marque:10}] {cas} essai {essai} — rejeu saine : {obs['obtenu']} ({obs.get('cause') or '-'})")
        if technique:
            print(f"             échec réel : {str(obs.get('detail') or '')[:150]}")
        for e in ecarts:
            print(f"             · {e.regle} {e.ou} : « {e.cite} » — {e.raison}" + (f" (observé : « {e.observe} »)" if e.observe else ""))
    print("\nBilan :", dict(bilan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
