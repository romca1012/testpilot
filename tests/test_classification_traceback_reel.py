"""Correctif A (rejeu 2026-07-23) — la CLASSIFICATION doit voir le nom de classe en QUEUE.

⚠️ **Le bug latent, trouvé par le réel.** `parse_behave_json` stockait `raw=err[:500]` = la TÊTE
du traceback (frames Behave/Playwright). Or le nom de la classe d'exception est à la FIN. La
taxonomie, qui lit `raw`, ne voyait donc JAMAIS `DonneeRefuseeError` ni `InvalidOptionValueError`
en run réel → le 4ᵉ verdict ne se déclenchait pas (verdict `technical_error` au lieu de
`donnee_invalide`). Mes tests unitaires passaient car ils mettaient le nom de classe DIRECTEMENT
dans `raw` — l'angle mort §8.8 : vert ≠ prouvé en réel.

Ces tests rejouent un traceback RÉALISTE et LONG (frames > 500 caractères, classe en queue). Ils
ÉCHOUERAIENT sur l'implémentation `err[:500]`. C'est ce qui en fait une garde, pas une description.
"""

from __future__ import annotations

import json

from testpilot.execution.behave_result import parse_behave_json
from testpilot.verdict import defect_taxonomy as dt


def _traceback_long(ligne_exception: str) -> str:
    """Un traceback plausible : beaucoup de frames (largement > 500 car.) PUIS la classe en fin."""
    frames = ["Traceback (most recent call last):"]
    for i in range(25):  # ~ largement plus de 500 caractères de frames
        frames.append(f'  File ".../site-packages/behave/model.py", line {1000 + i}, in run')
        frames.append(f"    self.func(context, *args, **kwargs)  # frame de remplissage n°{i}")
    frames.append(ligne_exception)
    return "\n".join(frames)


def _json_avec(traceback: str) -> str:
    return json.dumps([{
        "elements": [{
            "type": "scenario", "name": "[Nominal] créer", "status": "error",
            "steps": [{"keyword": "Alors", "name": "un enregistrement existe",
                       "result": {"status": "error",
                                  "error_message": traceback.splitlines()}}],
        }],
    }])


def _cause_reelle(ligne_exception: str) -> str:
    """Le chemin RÉEL : behave JSON → parse → classify (ce que fait `run_service`)."""
    result = parse_behave_json(_json_avec(_traceback_long(ligne_exception)), returncode=1)
    return dt.classify_failure(result.failures[0])


def test_donnee_refusee_est_classee_meme_avec_un_traceback_LONG():
    """Le cas exact du rejeu : la classe est à > 500 car. du début. Sur `err[:500]` → `unknown`."""
    ligne = ("_base_helpers.DonneeRefuseeError: LE NAVIGATEUR A REFUSÉ D'ENVOYER le formulaire : "
             "1 champ(s) invalide(s) — tva_intracommunautaire : uniquement des chiffres.")
    assert _cause_reelle(ligne) == dt.DONNEE_REFUSEE


def test_invalid_option_value_est_classee_avec_un_traceback_LONG():
    """Réparé AU PASSAGE : 0019 dépendait du même signal et souffrait du même angle mort."""
    ligne = ("_base_helpers.InvalidOptionValueError: select 'agence' : la valeur 'X' n'existe pas. "
             "Options réelles : (aucune option).")
    assert _cause_reelle(ligne) == dt.BROKEN_TEST_CODE


def test_une_vraie_assertion_metier_reste_non_conforme_avec_traceback_long():
    """Garde négative : le changement ne doit pas requalifier une vraie assertion métier."""
    # Behave rend « ASSERT FAILED: » pour une AssertionError (pas de nom de classe) — le préfixe
    # reste en queue et doit être reconnu.
    assert _cause_reelle("ASSERT FAILED: total attendu 0, obtenu 5") == dt.ASSERTION_MISMATCH
