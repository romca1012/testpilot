"""Refus à l'ÉCRITURE d'un test qui contient le masque d'un secret (`[secret]`).

Cas réel (banc web, essai 1, 2026-10-06) : le harnais de qualification remplace les secrets du projet par
`[secret]` dans ce que voit l'IA. Elle a recopié ce masque comme mot de passe ; SauceDemo a refusé la connexion à
juste titre ; le verdict a conclu « non conforme » sur une application saine (faux « échoué »). Un refus
déterministe à l'écriture laisse l'IA se corriger tout de suite, avant un run entier.
"""

from __future__ import annotations

from testpilot.generation.placeholders import SECRET_MASQUE
from testpilot.generation.qualification_budget import QualificationLLM
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools.write import write_feature_file, write_steps_file

_FEATURE_AVEC_MASQUE = """# language: fr
Fonctionnalité: Une connexion valide ouvre le catalogue
  Scénario: Connexion valide
    Soit j'accède à la page de connexion sans me connecter
    Quand je renseigne le champ "user-name" avec la valeur "standard_user"
    Et je renseigne le champ "password" avec la valeur "[secret]"
    Et je clique sur le bouton "Login"
    Alors l'URL courante contient "/inventory.html"
"""

_FEATURE_SANS_MASQUE = _FEATURE_AVEC_MASQUE.replace('Soit j\'accède à la page de connexion sans me connecter',
                                                    "Soit j'accède à la page d'accueil de l'application") \
    .replace('    Quand je renseigne le champ "user-name" avec la valeur "standard_user"\n', "") \
    .replace('    Et je renseigne le champ "password" avec la valeur "[secret]"\n', "") \
    .replace('    Et je clique sur le bouton "Login"\n', "")

_STEPS_AVEC_MASQUE = '''from behave import when


@when('je saisis le mot de passe')
def step(context):
    context.page.fill("#password", "[secret]")
'''


def test_le_masque_est_une_constante_partagee_avec_le_harnais():
    """Une seule définition : le harnais masque, l'outil d'écriture refuse la MÊME valeur."""
    llm = QualificationLLM(budget=None, trial="t", secrets=("motdepasse",))

    assert llm._redact("le mot de passe est motdepasse") == f"le mot de passe est {SECRET_MASQUE}"


def test_une_feature_qui_contient_le_masque_est_refusee_avec_une_consigne_actionnable(tmp_path):
    resultat = write_feature_file(ToolContext("demo", tmp_path), _FEATURE_AVEC_MASQUE)

    assert resultat.ok is False
    assert "SECRET_NON_RESOLU" in resultat.observation
    assert "j'accède à la page d'accueil de l'application" in resultat.observation  # dit quoi faire à la place
    assert not (tmp_path / "demo.feature").exists()  # rien n'est écrit sur le disque


def test_un_fichier_de_steps_qui_contient_le_masque_est_refuse(tmp_path):
    resultat = write_steps_file(ToolContext("demo", tmp_path), _STEPS_AVEC_MASQUE)

    assert resultat.ok is False
    assert "SECRET_NON_RESOLU" in resultat.observation


def test_falsifiable_une_feature_sans_masque_n_est_pas_refusee_pour_cette_raison(tmp_path):
    """La garde ne refuse que le masque : le même test, sans lui, passe cette garde."""
    resultat = write_feature_file(ToolContext("demo", tmp_path), _FEATURE_SANS_MASQUE)

    assert "SECRET_NON_RESOLU" not in resultat.observation
    assert resultat.ok is True
