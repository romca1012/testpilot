"""Appariement des steps tolérant aux accents — le 3ᵉ mur de la génération.

LE DÉFAUT MESURÉ (2026-07-19, re-génération du cas 9). Le LLM a écrit tout le `.feature` SANS
accents (« le nombre d'enregistrements dans le modele … est enregistre pour comparaison ») alors
que la bibliothèque partagée a ses accents (« modèle », « enregistré »). Behave apparie à l'exact
→ tous les steps partagés accentués `undefined` → dry-run en boucle → génération `dry_run_stalled`.

Ces tests instancient le matcher DIRECTEMENT (aucun run Behave, aucun LLM). Ils verrouillent le
contrat, dont la garde CRITIQUE : une valeur capturée accentuée n'est jamais dé-accentuée.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from _accent_matcher import AccentTolerantParseMatcher, fold_accents  # noqa: E402


def _noop(context):  # une fonction de step quelconque : le matcher n'appelle rien ici.
    pass


def _match(pattern, texte):
    """Les arguments capturés (liste) si ça matche, `None` sinon."""
    return AccentTolerantParseMatcher(_noop, pattern).check_match(texte)


# 1. Le mur exact du run raté : libellé de bibliothèque ACCENTUÉ, texte généré SANS accents.
def test_libelle_accentue_matche_un_texte_sans_accents():
    pattern = 'le nombre d\'enregistrements dans le modèle "{model}" est enregistré pour comparaison'
    texte = 'le nombre d\'enregistrements dans le modele "helpdesk.ticket" est enregistre pour comparaison'

    args = _match(pattern, texte)

    assert args is not None, "le step accentué doit matcher le texte sans accents"
    assert args[0].value == "helpdesk.ticket"


# 2. Réciproque : libellé SANS accents, texte ACCENTUÉ.
def test_libelle_sans_accents_matche_un_texte_accentue():
    args = _match('je selectionne le modele "{m}"', 'je sélectionne le modèle "sale.order"')

    assert args is not None
    assert args[0].value == "sale.order"


# 3. GARDE ANTI-CORRUPTION (le point critique) : une valeur capturée ACCENTUÉE reste verbatim.
def test_une_valeur_capturee_accentuee_n_est_JAMAIS_de_accentuee():
    args = _match('je renseigne le champ "{f}" avec la valeur "{v}"',
                  'je renseigne le champ "name" avec la valeur "Matériel très spécifique à Évry"')

    assert args is not None
    valeurs = {a.value for a in args}
    assert "Matériel très spécifique à Évry" in valeurs, (
        "la valeur saisie doit être rendue TELLE QUELLE — sinon Odoo reçoit une donnée corrompue")
    assert "Materiel" not in " ".join(str(v) for v in valeurs)


# 4. Les convertisseurs de type `parse` restent intacts.
def test_le_convertisseur_de_type_d_rend_toujours_un_int():
    args = _match('le produit "{name}" avec id {product_id:d} existe',
                  'le produit "PC Portable HP" avec id 78 existe')

    assert args is not None
    valeurs = {a.value for a in args}
    assert 78 in valeurs and "PC Portable HP" in valeurs
    assert any(isinstance(v, int) for v in valeurs), "{id:d} doit rester un entier"


# 5. Pas de sur-appariement : plier les accents ne fait pas matcher n'importe quoi.
def test_deux_steps_reellement_differents_ne_matchent_pas():
    assert _match('je clique sur le bouton "{label}"',
                  'je navigue vers la page "accueil"') is None
    # Même longueur, mots différents : le pliage ne doit rien y changer.
    assert _match('le modèle est vide', 'le modele est plein') is None


# 6. Le branchement est RÉEL : environment.py sélectionne bien le matcher au chargement.
def test_environment_installe_le_matcher_au_chargement(tmp_path, monkeypatch):
    """On rejoue ce que fait le runner : _accent_matcher.py copié dans steps/, puis exec
    d'environment.py → le matcher courant de Behave doit devenir `accent_tolerant`."""
    import shutil
    import importlib.util
    from behave.matchers import get_step_matcher_factory, use_step_matcher

    racine = Path(__file__).resolve().parent.parent / "behave_runtime"
    (tmp_path / "steps").mkdir()
    shutil.copy2(racine / "steps_library" / "_accent_matcher.py", tmp_path / "steps" / "_accent_matcher.py")
    shutil.copy2(racine / "environment.py", tmp_path / "environment.py")

    # État de départ : matcher par défaut.
    use_step_matcher("parse")
    factory = get_step_matcher_factory()

    # Exécute environment.py comme le fait Behave (exec_file : __file__ pointe la copie).
    monkeypatch.setenv("ODOO_ENV", "")  # ne pas déclencher la garde prod
    ns = {"__file__": str(tmp_path / "environment.py"), "__name__": "builtins"}
    exec(compile((tmp_path / "environment.py").read_text(encoding="utf-8"),
                 str(tmp_path / "environment.py"), "exec"), ns)

    assert factory.current_matcher.__name__ == "AccentTolerantParseMatcher", (
        "après le chargement d'environment.py, Behave doit apparier avec le matcher tolérant")
    use_step_matcher("parse")  # on restaure pour ne pas polluer les autres tests


# Le pliage lui-même : préservation de la LONGUEUR (indispensable à l'alignement des spans).
def test_le_pliage_preserve_la_longueur():
    for s in ["modèle", "enregistré", "Matériel très spécifique à Évry", "çàâäéèêëîïôöùûü"]:
        assert len(fold_accents(s)) == len(s), f"le pliage doit préserver la longueur : {s!r}"
