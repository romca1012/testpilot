"""Règle 8 des prompts (lot 07d) : une boîte de dialogue native se décide AVANT l'action qui l'ouvre.

Playwright refuse une boîte `alert`/`confirm`/`prompt` d'office dès qu'elle s'ouvre : un « j'accepte la boîte de dialogue » placé APRÈS le clic
arrive trop tard. L'agent ne peut pas le deviner de la seule liste des steps — la règle vit dans les trois prompts (génération, correction,
réparation) avec un exemple correct et un exemple refusé. Ces tests gardent qu'elle y reste, que les steps qu'elle cite EXISTENT, et que son
exemple « refusé » est bien celui que le test de bout en bout rejoue et refuse (`tests/test_vocabulaire_universel.py`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from testpilot import config
from testpilot.generation import steps_library

_PROMPTS = config.PROMPTS_DIR
_RACINE = Path(__file__).resolve().parent.parent
_TITRE = "AVANT l'action qui l'ouvre"


@pytest.mark.parametrize("prompt", ["system_prompt.md", "correction_prompt.md", "repair_prompt.md"])
def test_chaque_prompt_porte_la_regle_d_ordre(prompt):
    texte = (_PROMPTS / prompt).read_text(encoding="utf-8")

    assert _TITRE in texte, f"{prompt} n'enseigne plus l'ordre « décision AVANT le clic »"
    assert "j'accepte la boîte de dialogue" in texte and "je refuse la boîte de dialogue" in texte
    assert "refusée d'office" in texte


def test_le_prompt_de_generation_donne_un_exemple_correct_et_un_exemple_refuse():
    texte = (_PROMPTS / "system_prompt.md").read_text(encoding="utf-8")
    regle = texte[texte.index("### Règle 8"):texte.index("## PILIER 1")]

    assert "# CORRECT" in regle and "# REFUSÉ" in regle
    correct = regle[regle.index("# CORRECT"):regle.index("# REFUSÉ")]
    refuse = regle[regle.index("# REFUSÉ"):]
    # Le bon exemple décide AVANT de cliquer ; le mauvais clique d'abord.
    assert correct.index("j'accepte la boîte de dialogue") < correct.index("je clique sur")
    assert refuse.index("je clique sur") < refuse.index("j'accepte la boîte de dialogue")


def test_les_steps_cites_existent_dans_la_bibliotheque_partagee():
    """Un prompt qui cite un step absent est un « affiché ≠ réel » (§4.6) au niveau du prompt."""
    libelles = {s.label for s in steps_library.catalogue(connector_type="web")}
    texte = (_PROMPTS / "system_prompt.md").read_text(encoding="utf-8")

    assert "j'accepte la boîte de dialogue" in libelles and "je refuse la boîte de dialogue" in libelles
    assert 'je clique sur "{libelle}" dans la ligne contenant "{texte}"' in libelles
    assert 'la page affiche le texte "{texte}"' in libelles
    assert 'je clique sur "Supprimer" dans la ligne contenant "CMD-1"' in texte


def test_l_exemple_refuse_est_celui_que_le_test_de_bout_en_bout_rejoue_et_refuse():
    """Le REFUSÉ du prompt n'est pas une supposition : ces deux steps, dans cet ordre, donnent une erreur technique (jamais un vert)."""
    prompt = (_PROMPTS / "system_prompt.md").read_text(encoding="utf-8")
    rejoue = (_RACINE / "tests" / "test_vocabulaire_universel.py").read_text(encoding="utf-8")
    bloc = rejoue[rejoue.index('"boîte native décidée APRÈS le clic"'):]
    bloc = bloc[:bloc.index('"technique")')]

    assert 'je clique sur "Supprimer" dans la ligne contenant "CMD-1"' in bloc and "accepte la boîte de dialogue" in bloc
    assert bloc.index("je clique sur") < bloc.index("accepte la boîte de dialogue")
    assert 'Quand je clique sur "Supprimer" dans la ligne contenant "CMD-1"\nEt j\'accepte la boîte de dialogue' in prompt
