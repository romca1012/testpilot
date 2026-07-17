"""`0019` option D — corrige « new » → « nouvel_entrant » dans le `.feature` du cas 1.

    PYTHONUTF8=1 python scripts/fix_0019_types_demandes.py [--dry-run]

**Correction MANUELLE, ratifiée au gate — décision explicite du porteur (2026-07-17).**
Aucun appel LLM : le diagnostic est fait (`0019`), payer l'agent pour redécouvrir ce qu'on sait
déjà serait le gaspillage qu'on dénonce (*« ne pas dépenser de budget pour deviner une deuxième
fois »*).

**Pourquoi ce n'est pas un contournement du processus, mais son usage prévu :**
- le gate humain existe **précisément** pour ratifier ce genre de correction (§4.3) ;
- la règle « validé = jamais régénéré » (§5 du brief) **ne s'applique pas** : ce cas n'a jamais
  été validé sur cette version — il est `validated` d'un run antérieur, mais sa version courante
  `v1` n'a jamais produit de run vert.

**Ce qui est corrigé, et c'est tout** : la valeur d'une option de `<select>`, sondée sur la vraie
application (`scripts/probe_select_options.py`) :

    types_demandes : 'nouvel_entrant' | 'remplacement_materiel'   ← les SEULES valeurs réelles
    le .feature demandait : "new"                                  ← n'existe pas

Une **nouvelle version** est créée (jamais d'écrasement : l'historique est la preuve, §2.10) et
elle repasse **`to_review`** — le gate reste souverain, personne n'auto-approuve.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from testpilot import config  # noqa: E402
from testpilot.store.db import get_initialized_db  # noqa: E402
from testpilot.store.repositories import CaseRepo, VersionRepo  # noqa: E402

CASE_ID = 1
FAUX = '"types_demandes" est rempli avec "new"'
VRAI = '"types_demandes" est rempli avec "nouvel_entrant"'


def main() -> None:
    dry = "--dry-run" in sys.argv
    conn = get_initialized_db(config.DB_PATH)
    cases, versions = CaseRepo(conn), VersionRepo(conn)

    case = cases.get(CASE_ID)
    courante = versions.get(case["current_version_id"])
    feature = courante["feature_content"] or ""

    print("=" * 74)
    print("0019 / D — correction manuelle de la valeur d'option" + ("  [DRY-RUN]" if dry else ""))
    print("=" * 74)
    print(f"  cas {CASE_ID} « {case['title']} », version courante v{courante['version_number']}")

    occurrences = feature.count(FAUX)
    print(f"  occurrences de la valeur inventée « new » : {occurrences}")
    if not occurrences:
        print("  → rien à corriger (déjà fait ?). Abandon.")
        conn.close()
        return

    nouveau = feature.replace(FAUX, VRAI)
    for i, (avant, apres) in enumerate(zip(feature.split("\n"), nouveau.split("\n")), 1):
        if avant != apres:
            print(f"\n  ligne {i}")
            print(f"    -  {avant.strip()}")
            print(f"    +  {apres.strip()}")

    if dry:
        print("\n  → [dry-run] rien n'est écrit")
        conn.close()
        return

    # ⚠️ Une NOUVELLE version, jamais un écrasement : l'historique est la preuve (§2.10). Les
    # steps sont repris tels quels — seule la valeur d'option change.
    new_id = versions.create(
        test_case_id=CASE_ID,
        spec_content=courante["spec_content"], spec_hash=courante["spec_hash"],
        feature_content=nouveau, steps_content=courante["steps_content"],
        change_summary=("0019 : « new » → « nouvel_entrant » (valeur d'option sondée sur "
                        "l'application ; « new » n'existe pas). Correction manuelle, à ratifier."),
        created_by="fix-manuel-0019",
    )
    cases.set_current_version(CASE_ID, new_id)
    # Le gate reste souverain : la version n'est PAS approuvée d'office (§4.3).
    cases.set_validation_status(CASE_ID, "to_review")

    # ⚠️ LE DISQUE, et ce n'est pas un détail — j'ai failli l'oublier en croyant que le runner
    # lisait la base. VÉRIFIÉ : `BehaveRunner._assemble` recopie les fichiers depuis
    # `GENERATED_DIR` (le DISQUE), jamais depuis la base. Sans cette écriture, le rejeu
    # exécuterait l'ANCIEN `.feature` avec « new » tout en prétendant jouer la nouvelle version :
    # « affiché ≠ réel » (§4.6), et le pire genre — le verdict porterait sur un autre code.
    # C'est exactement ce que `repair_service._sync_disque` fait après une réparation.
    feature_path = config.GENERATED_DIR / f"{case['feature_slug']}.feature"
    config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    feature_path.write_text(nouveau, encoding="utf-8")

    apres = cases.get(CASE_ID)
    v = versions.get(new_id)
    print(f"\n  → v{v['version_number']} créée (id {new_id}), version courante du cas")
    print(f"  → validation_status : {apres['validation_status']}  "
          f"(le gate doit RATIFIER — aucune auto-approbation)")
    print(f"  → disque resynchronisé : {feature_path}")
    relu = feature_path.read_text(encoding="utf-8")
    print(f"  → vérification disque : « new » restant = {relu.count(FAUX)}, "
          f"« nouvel_entrant » = {relu.count(VRAI)}")
    conn.close()


if __name__ == "__main__":
    main()
