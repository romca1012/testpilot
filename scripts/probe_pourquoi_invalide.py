"""D'OÙ vient le refus du navigateur ? — la sonde qui décide de la stratégie.

    PYTHONUTF8=1 python scripts/probe_pourquoi_invalide.py

⚠️ Aucun LLM, aucune écriture en base. Ouvre les formulaires fautifs, remplit les champs comme le
test généré l'a fait, et demande au navigateur **pourquoi** il refuse.

La question décisive : le refus vient-il d'un `pattern` LISIBLE (même posé par JavaScript), ou
d'un `setCustomValidity()` dont la règle n'existe que dans du code ?

- `patternMismatch` + `el.pattern` non vide → **on peut fabriquer une valeur conforme**
  automatiquement, donc supprimer l'erreur au lieu de la constater.
- `customError` seul → la règle est invisible ; il faudra une autre voie (essai-correction guidé
  par le message, ou saisie assistée).

C'est cette réponse qui dit si l'objectif « zéro erreur de données » est atteignable de façon
déterministe ou seulement approchable.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

import types  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

from testpilot import config  # noqa: E402

# Les champs qui ont produit un faux verdict, avec la valeur exacte que le test avait écrite.
CIBLES = [
    ("/fournisseur/creation/66", {"tva_intracommunautaire": "FR12345678901",
                                  "siret_fournisseur": "123456789 12345"}),
    ("/retenue_garantie/86", {"numero_facture1": "FAC-2024-001"}),
    ("/client_contentieux/78", {"numero_facture1": "FAC-2024-001"}),
]

_SONDE = """(noms) => {
    const out = [];
    for (const nom of noms) {
        const el = document.querySelector(`[name="${nom}"]`);
        if (!el) { out.push({nom, absent: true}); continue; }
        const v = el.validity;
        out.push({
            nom,
            valeur: el.value,
            valide: el.checkValidity(),
            message: el.validationMessage || '',
            // L'attribut est lisible MÊME s'il a été posé par du JavaScript — c'est tout l'enjeu.
            pattern: el.getAttribute('pattern') || '',
            title: el.getAttribute('title') || '',
            maxlength: el.getAttribute('maxlength') || '',
            drapeaux: Object.keys(ValidityState.prototype)
                .filter(k => k !== 'valid' && v[k] === true),
        });
    }
    return out;
}"""


def main() -> int:
    import _base_helpers as H

    with sync_playwright() as p:
        nav = p.chromium.launch()
        page = nav.new_page()
        ctx = types.SimpleNamespace(page=page, odoo_url=config.ODOO_URL, odoo_db=config.ODOO_DB,
                                    odoo_user=config.ODOO_USER, odoo_password=config.ODOO_PASSWORD)
        H.playwright_login(ctx)

        for route, valeurs in CIBLES:
            print(f"\n{'=' * 72}\n{route}\n{'=' * 72}", flush=True)
            try:
                page.goto(config.ODOO_URL.rstrip("/") + route, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
                for nom, valeur in valeurs.items():
                    try:
                        champ = page.locator(f'[name="{nom}"]').first
                        champ.fill(valeur)
                        # Les règles JS se déclenchent sur input/change/blur : on les provoque.
                        champ.dispatch_event("input")
                        champ.dispatch_event("change")
                        champ.dispatch_event("blur")
                    except Exception as exc:
                        print(f"  {nom} : remplissage impossible ({type(exc).__name__})")
                page.wait_for_timeout(500)
                print("  -- AVANT toute soumission --", flush=True)
                for info in page.evaluate(_SONDE, list(valeurs)):
                    print("   ", json.dumps(info, ensure_ascii=False), flush=True)

                # ⚠️ LA question. Si une règle est posée par `setCustomValidity()` dans le
                # gestionnaire de soumission, elle N'EXISTE PAS avant le clic — et une
                # vérification « avant envoi » ne la verrait jamais. On clique donc, puis on
                # relit. C'est ce qui départage « prévenir » et « constater ».
                try:
                    page.get_by_role("button", name="Envoyer").first.click(timeout=5000)
                    page.wait_for_timeout(1500)
                except Exception as exc:
                    print(f"    (clic Envoyer impossible : {type(exc).__name__})", flush=True)
                print("  -- APRÈS le clic sur Envoyer --", flush=True)
                tous = page.evaluate("""() => {
                    const out = [];
                    for (const el of document.querySelectorAll('input, select, textarea')) {
                        if (el.willValidate && !el.checkValidity()) {
                            out.push({nom: el.name || el.id, valeur: el.value,
                                      message: el.validationMessage,
                                      pattern: el.getAttribute('pattern') || '',
                                      title: el.getAttribute('title') || '',
                                      custom: el.validity.customError});
                        }
                    }
                    return out;
                }""")
                print("   ", json.dumps(tous, ensure_ascii=False, indent=4)[:1500], flush=True)
            except Exception as exc:
                print(f"  page inaccessible : {type(exc).__name__} {exc}"[:200], flush=True)

        nav.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
