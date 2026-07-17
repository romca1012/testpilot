"""Preuve reproductible de la décision 0015 — AVANT/APRÈS, bout en bout.

Compare la taxonomie **réellement** en vigueur avant 0015 (extraite de git, taxonomie ET
`defect_origin` d'origine — les deux, sinon l'« avant » est infidèle : c'est l'erreur que la
première version de cette mesure a commise) à celle d'aujourd'hui.

    python scripts/prove_0015_signal_vs_texte.py [--ref <git-ref>]

Ce qu'elle établit :

1. Le **même** `TypeError` recevait **quatre** classements selon le seul nom du step — désormais
   un seul, décidé par le TYPE d'exception (que l'agent ne produit pas).
2. Le **faux négatif** (§4.4, inacceptable) est fermé : un vrai bug applicatif sur un step nommé
   `…"team_id"…` passait `test_a_reparer` — la boucle `0014` aurait réparé un test CORRECT contre
   une application cassée. Il reste `vrai_bug` quoi qu'écrive l'agent.
3. Le **coût assumé**, montré et non caché : une assertion « sémantique » qui tombait en
   `test_a_reparer` par mots-clés devient `vrai_bug` → le circuit s'arrête. On sur-arrête **plus**
   sur cette voie ; c'est la direction sûre (§4.4 tolère le faux positif, `0013` permet de
   l'infirmer), mais ce n'est pas gratuit.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

# Formats RÉELS, tels que Behave 1.3.3 les émet — vérifiés en base (`scenario_result`) :
#  - une exception → traceback complet, donc le nom de la classe est là ;
#  - une AssertionError → « ASSERT FAILED: {message} », le nom de la classe DISPARAÎT
#    (`model.py:1888`), et pas de traceback hors mode verbose.
# Ne PAS écrire « AssertionError: … » ici : cette forme n'existe dans aucun de nos runs. Le premier
# jet de 0015 la testait, et validait donc un monde imaginaire — pendant que les assertions réelles
# étaient classées par mots-clés, c.-à-d. par le texte de l'agent.
TYPE_ERROR = "TypeError: 'int' object is not subscriptable"
ASSERTION_BUG = "ASSERT FAILED: le ticket devrait être en état 'validé', obtenu 'brouillon'"


@dataclass
class Failure:
    """Miroir de `behave_result.StepFailure` — les champs lus par la taxonomie."""
    scenario_name: str = "Scénario"
    step_text: str = ""
    failure_type: str = "unknown"
    traceback_summary: str = ""
    raw: str = ""


def _charger(nom: str, chemin: Path):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def _extraire(ref: str, relatif: str, dest: Path) -> Path:
    contenu = subprocess.run(["git", "show", f"{ref}:{relatif}"], cwd=RACINE,
                             capture_output=True, text=True, encoding="utf-8", check=True).stdout
    dest.write_text(contenu, encoding="utf-8")
    return dest


def charger_avant(ref: str, tmp: Path):
    """Taxonomie + origin d'AVANT, cohérentes entre elles.

    `defect_origin` fait `from testpilot.verdict import defect_taxonomy` : on le fait résoudre
    vers l'ANCIENNE taxonomie le temps de son chargement, puis on rétablit. Le code courant est
    importé AVANT le shim — sinon `sys.modules.get` rend `None` et le shim n'est jamais retiré.
    """
    import testpilot.verdict as pkg
    from testpilot.verdict import defect_taxonomy as taxo_courante

    taxo = _charger("taxo_avant", _extraire(ref, "src/testpilot/verdict/defect_taxonomy.py",
                                            tmp / "taxo_avant.py"))
    sys.modules["testpilot.verdict.defect_taxonomy"] = taxo
    pkg.defect_taxonomy = taxo
    try:
        origin = _charger("origin_avant", _extraire(ref, "src/testpilot/verdict/defect_origin.py",
                                                    tmp / "origin_avant.py"))
    finally:
        sys.modules["testpilot.verdict.defect_taxonomy"] = taxo_courante
        pkg.defect_taxonomy = taxo_courante

    # Garde : si l'« avant » ressemble à l'« après », la comparaison ne prouve rien.
    assert not hasattr(taxo, "BROKEN_TEST_CODE"), f"{ref} contient déjà 0015 — « avant » infidèle"
    assert origin._ORIGIN_BY_CAUSE[taxo.MISSING_SERVER_CONTEXT] == "test_a_reparer", \
        f"{ref} contient déjà l'arbitrage Q4 — « avant » infidèle"
    return taxo, origin


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="", help="ref git d'avant 0015 (défaut : le commit du code d'avant)")
    args = parser.parse_args()

    from testpilot.verdict import defect_origin as origin_ap
    from testpilot.verdict import defect_taxonomy as taxo_ap

    ref = args.ref or subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "src/testpilot/verdict/defect_taxonomy.py"],
        cwd=RACINE, capture_output=True, text=True, check=True).stdout.strip()

    with tempfile.TemporaryDirectory() as d:
        taxo_av, origin_av = charger_avant(ref, Path(d))

        def avant(f):
            return origin_av.classify_defect_origin(taxo_av.classify_failure(f))

        def apres(f):
            return origin_ap.classify_defect_origin(taxo_ap.classify_failure(f))

        print(f"AVANT = {ref[:10]} | APRÈS = arbre de travail\n")

        print("1. LE MÊME TypeError (l'échec réel du cas 2), quatre noms de step")
        causes_av, causes_ap = set(), set()
        for step in ('Alors le dernier ticket créé a le champ "team_id" pointant vers "Matériel"',
                     "Alors le ticket est créé",
                     'Alors la route "/tickets" répond',
                     "Alors le timeout est respecté"):
            f = Failure(step_text=step, raw=TYPE_ERROR)
            causes_av.add(taxo_av.classify_failure(f))
            causes_ap.add(taxo_ap.classify_failure(f))
            print(f"   {step[:44]:46} AVANT={avant(f):15} APRÈS={apres(f)}")
        print(f"\n   AVANT : {len(causes_av)} causes pour UN échec → {sorted(causes_av)}")
        print(f"   APRÈS : {len(causes_ap)} cause  → {sorted(causes_ap)}")
        assert len(causes_av) > 1 and len(causes_ap) == 1

        print("\n2. LE FAUX NÉGATIF (§4.4 : inacceptable) — vrai bug + step piégeux")
        for step in ("Alors le ticket est validé",
                     'Alors le champ "team_id" du ticket est correct'):
            f = Failure(step_text=step, raw=ASSERTION_BUG, failure_type="assertion")
            a, b = avant(f), apres(f)
            marque = "   ← RÉPARÉ À TORT" if a == "test_a_reparer" else ""
            print(f"   {step[:44]:46} AVANT={a:15} APRÈS={b}{marque}")
            assert b == "vrai_bug"

        print("\n3. LE COÛT ASSUMÉ — assertion « sémantique » : on sur-arrête PLUS")
        f = Failure(step_text="Alors le ticket est créé", failure_type="assertion",
                    raw="ASSERT FAILED: le champ caché est resté vide")
        print(f"   {'ASSERT FAILED: champ caché resté vide':46} AVANT={avant(f):15} APRÈS={apres(f)}")

        print("\n4. LA PORTE QUE LE PREMIER JET DE 0015 LAISSAIT OUVERTE")
        print("   Behave n'écrit jamais « AssertionError » (model.py:1888 → « ASSERT FAILED: »).")
        print("   Sans reconnaître SON rendu, ces assertions retombaient sur les mots-clés —")
        print("   c.-à-d. sur le message de l'agent, que 0015 prétendait avoir écarté :")
        for message in ("ASSERT FAILED: permission denied pour cet utilisateur",
                        "ASSERT FAILED: le sélecteur est introuvable"):
            f = Failure(raw=message, failure_type="unknown")
            print(f"   {message[:46]:46} AVANT={avant(f):15} APRÈS={apres(f)}")
            assert apres(f) == "vrai_bug"

    print("\nOK — le classement ne dépend plus d'un texte écrit par l'agent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
