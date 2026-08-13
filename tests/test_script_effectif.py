"""Script effectif consultable (Phase 2, audit DA 2026-08-13) — decision liée à 0003.

`match_referenced` et `load_step_source` sont les deux briques PURES qui permettent de montrer,
pour un cas donné, le script COMPLET qu'il exécute réellement — pas seulement son
`steps_content` propre, qui laisse la bibliothèque partagée invisible.
"""

from testpilot.generation.steps_library import SharedStep, load_step_source, match_referenced

_CATALOGUE = [
    SharedStep(keyword="given", label="je me connecte avec mes identifiants utilisateur",
              source="generic/_generic_steps.py"),
    SharedStep(keyword="when", label='je renseigne le champ "{field}" avec la valeur "{value}"',
              source="generic/_generic_steps.py"),
    SharedStep(keyword="then",
              label='le nombre total d\'enregistrements dans le modèle "{model}" augmente de {n}',
              source="odoo/_odoo_steps.py", note="Compare au compteur enregistré avant le scénario."),
]

_FEATURE = """# language: fr
Fonctionnalité: Achat de siège
  Contexte:
    Soit l'instance Odoo accessible

  Scénario: Nominal
    Soit je me connecte avec mes identifiants utilisateur
    Quand je renseigne le champ "name" avec la valeur "TEST"
    Alors le nombre total d'enregistrements dans le modèle "helpdesk.ticket" augmente de 1
"""


def test_match_referenced_trouve_les_steps_reellement_utilises():
    trouves = match_referenced(_FEATURE, _CATALOGUE)
    assert {s.label for s in trouves} == {
        "je me connecte avec mes identifiants utilisateur",
        'je renseigne le champ "{field}" avec la valeur "{value}"',
        'le nombre total d\'enregistrements dans le modèle "{model}" augmente de {n}',
    }


def test_match_referenced_ignore_les_steps_non_references():
    """Un step du catalogue absent du .feature n'apparaît pas — la plupart du catalogue n'est
    jamais utilisée par un cas donné, ce n'est pas une anomalie."""
    catalogue = _CATALOGUE + [
        SharedStep(keyword="when", label='je clique sur le bouton "{label}"', source="generic/x.py"),
    ]
    trouves = match_referenced(_FEATURE, catalogue)
    assert 'je clique sur le bouton "{label}"' not in {s.label for s in trouves}


def test_match_referenced_feature_vide_rend_liste_vide():
    assert match_referenced("", _CATALOGUE) == []
    assert match_referenced(_FEATURE, []) == []


def test_match_referenced_ignore_les_lignes_hors_steps():
    """Les lignes de titre (Fonctionnalité/Scénario/Contexte) ne sont jamais des steps — les
    confondre ferait chercher un match sur du texte qui n'en est pas un."""
    feature = 'Fonctionnalité: Et voilà un titre qui commence comme un step\n'
    assert match_referenced(feature, _CATALOGUE) == []


def test_load_step_source_relit_decorateur_et_corps(tmp_path):
    fichier = tmp_path / "_generic_steps.py"
    fichier.write_text(
        '"""Module."""\n'
        "from behave import given, when\n\n\n"
        "@given('je me connecte avec mes identifiants utilisateur')\n"
        "def step_connexion(context):\n"
        '    """Authentifie la session."""\n'
        "    context.odoo = connect()\n",
        encoding="utf-8",
    )
    steps = [SharedStep(keyword="given",
                        label="je me connecte avec mes identifiants utilisateur",
                        source=fichier.name)]
    code = load_step_source(steps, directory=tmp_path)
    assert set(code) == {"je me connecte avec mes identifiants utilisateur"}
    texte = code["je me connecte avec mes identifiants utilisateur"]
    assert texte.startswith("@given(")
    assert "def step_connexion(context):" in texte
    assert "context.odoo = connect()" in texte


def test_load_step_source_step_introuvable_absent_du_resultat(tmp_path):
    fichier = tmp_path / "_generic_steps.py"
    fichier.write_text("from behave import given\n", encoding="utf-8")
    steps = [SharedStep(keyword="given", label="un step qui n'existe pas dans ce fichier",
                        source=fichier.name)]
    assert load_step_source(steps, directory=tmp_path) == {}


def test_load_step_source_fichier_source_disparu_ne_plante_pas(tmp_path):
    steps = [SharedStep(keyword="given", label="peu importe", source="fichier_absent.py")]
    assert load_step_source(steps, directory=tmp_path) == {}
