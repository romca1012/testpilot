"""GARDE bout-en-bout — le repli adaptatif de `navigate_menu` doit remonter jusqu'au VRAI
`BehaveResult`, exactement comme `test_field_resolution.py::test_GARDE_...` le fait déjà pour
`resolve_field_name`.

⚠️ **Le VRAI bug que ce test aurait dû détecter, et n'a détecté qu'à sa deuxième version.** Un run
RÉEL contre l'instance Sapian (2026-09-22) a montré le palier adaptatif totalement muet —
`field_fallbacks` restait vide en base après plusieurs rejeux, malgré `test_resolution_adaptative.py`
tout vert. Cause RACINE, confirmée dans le code source de Behave installé
(`.venv-v1/Lib/site-packages/behave/runner_util.py::load_step_modules`) : Behave charge chaque
fichier de `steps/` avec `exec_file()` (pas un `import`) sous un `PathManager(step_paths)` **local,
scopé à cette seule boucle** — `steps/` est retiré de `sys.path` dès que le chargement se termine,
BIEN AVANT l'exécution des scénarios. Un import DIFFÉRÉ (déclenché depuis l'intérieur d'une fonction,
exécuté PENDANT un scénario — le premier jet de `_repli_adaptatif`) lève alors
`ModuleNotFoundError: No module named '_adaptive_resolution'`, silencieusement avalé par un
`except Exception: return None` sans trace. Le correctif : `_base_helpers.py` importe
`_adaptive_resolution` **au niveau module** — cet import s'exécute PENDANT le chargement des steps
(déclenché par `_odoo_steps.py::from _base_helpers import ...`, dans la même fenêtre favorable),
exactement comme `_base_helpers` lui-même est chargé à ce moment-là.

La PREMIÈRE version de ce test de garde avait accidentellement MASQUÉ ce bug : son step généré
faisait lui-même `import _adaptive_resolution` au niveau module pour le monkeypatcher, ce qui
mettait le module en cache AVANT que le code réel ne tente son propre import — donc le test passait
même sur l'implémentation cassée. Cette version ne monkeypatche QUE l'attribut déjà chargé par
`_base_helpers` (`_base_helpers._adaptive_resolution.resoudre_champ_adaptatif`), jamais un import
séparé dans le step de test — la seule façon de faire courir ce test sur le VRAI chemin de code.
"""

from __future__ import annotations

from pathlib import Path

from testpilot.execution.behave_runner import BehaveRunner

_STEPS_LIBRARY_REELLE = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"


def _ecrire_aire_de_run_menu(tmp_path, *, echoue_sur: str, resolution) -> BehaveRunner:
    """Aire de run de FORME RÉELLE (comme `test_field_resolution.py::_ecrire_aire_de_run`), avec
    `steps_library_dir` pointant vers le VRAI dossier partagé — pour que `_adaptive_resolution.py`
    soit copié exactement comme en production.

    `resolution` : soit un `Locator` factice (succès), soit `None` (échec) — jamais un import
    séparé de `_adaptive_resolution` dans le step généré, voir la docstring du module.
    """
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "environment.py").write_text(
        "# environment.py minimal : sa PRÉSENCE suffit à activer la capture de Behave.\n"
        "def before_all(context):\n    pass\n", encoding="utf-8")

    gen = tmp_path / "gen"; gen.mkdir()
    locator_src = (
        "class _LocatorAdaptatif:\n"
        "    def __init__(self, page): self._page = page\n"
        "    def click(self, timeout=None): self._page.url += '&navigue=1'\n"
    ) if resolution == "succes" else ""
    fake_resoudre = (
        "lambda page, ident, intention, **kw: (\n"
        "    setattr(page, '_tp_dernier_diagnostic_adaptatif',\n"
        "            'résolu — élément #0 choisi parmi 24 candidat(s)') or _LocatorAdaptatif(page)\n"
        "    if ident == %r else None\n"
        ")" % echoue_sur
    ) if resolution == "succes" else (
        "lambda page, ident, intention, **kw: (\n"
        "    setattr(page, '_tp_dernier_diagnostic_adaptatif',\n"
        "            'aucune correspondance parmi 24 éléments') or None\n"
        ")"
    )
    (gen / "garde_menu_steps.py").write_text(
        "from behave import given\n"
        "from playwright.sync_api import TimeoutError as PWTimeout\n"
        "import _base_helpers\n"
        "from _base_helpers import navigate_menu\n"
        "\n"
        f"{locator_src}\n"
        "\n"
        "class _LocatorTimeout:\n"
        "    @property\n"
        "    def first(self): return self\n"
        "    def click(self, timeout=None): raise PWTimeout('rien trouvé')\n"
        "\n"
        "class _LocatorOk:\n"
        "    def __init__(self, journal, texte): self._journal, self._texte = journal, texte\n"
        "    @property\n"
        "    def first(self): return self\n"
        "    def click(self, timeout=None): self._journal.append(self._texte)\n"
        "\n"
        "class _P:\n"
        "    def __init__(self):\n"
        "        self.urls_visitees, self.clics = [], []\n"
        "        self.url = 'https://sapian.example.com/web#action=menu'\n"
        "    def goto(self, url, **_k):\n"
        "        self.urls_visitees.append(url)\n"
        "        self.url = url\n"
        "    def wait_for_selector(self, *a, **kw): pass\n"
        f"    def get_by_text(self, texte, exact=True):\n"
        f"        if texte == {echoue_sur!r}: return _LocatorTimeout()\n"
        "        return _LocatorOk(self.clics, texte)\n"
        "\n"
        "class _Ctx:\n"
        "    odoo_url = 'https://sapian.example.com'\n"
        "    def __init__(self): self.page = _P()\n"
        "\n"
        "# ⚠️ Monkeypatch de l'ATTRIBUT déjà chargé par `_base_helpers` lui-même — jamais un\n"
        "# `import _adaptive_resolution` séparé ici, qui masquerait le bug de timing réel.\n"
        f"_base_helpers._adaptive_resolution.resoudre_champ_adaptatif = {fake_resoudre}\n"
        "\n"
        "@given('un menu est resolu par repli adaptatif')\n"
        "def step_impl(context):\n"
        "    ctx = _Ctx()\n"
        "    try:\n"
        f"        navigate_menu(ctx, {echoue_sur!r})\n"
        + ("    except PWTimeout:\n"
           "        pass\n" if resolution != "succes" else "    except PWTimeout:\n"
           "        raise AssertionError('le repli adaptatif aurait dû résoudre')\n"),
        encoding="utf-8")
    (gen / "garde_menu.feature").write_text(
        "# language: fr\n"
        "Fonctionnalité: garde du repli adaptatif de navigate_menu\n"
        "  Scénario: un scenario VERT qui exerce le repli adaptatif\n"
        "    Soit un menu est resolu par repli adaptatif\n", encoding="utf-8")
    return BehaveRunner(runtime_dir=runtime, generated_dir=gen,
                        steps_library_dir=_STEPS_LIBRARY_REELLE, real_timeout=60)


def test_GARDE_le_repli_adaptatif_de_navigate_menu_remonte_dun_run_reel(tmp_path):
    """Reproduit EXACTEMENT le layout de production, SANS importer `_adaptive_resolution` dans le
    step de test — la seule façon de vraiment exercer le chemin d'import réel de `_base_helpers`."""
    runner = _ecrire_aire_de_run_menu(tmp_path, echoue_sur="Surveys", resolution="succes")
    result = runner.real_run("garde_menu")

    assert result.passed == 1, f"le scénario de garde doit être VERT : {result.raw_stdout}"
    assert result.field_fallbacks, (
        "le repli adaptatif d'un scénario VERT doit remonter jusqu'à BehaveResult — s'il ne "
        "remonte plus, le signal est perdu en silence (le symptôme exact mesuré le 2026-09-22).")
    assert "Surveys" in result.field_fallbacks[0]
    assert "ADAPTATIVE" in result.field_fallbacks[0]


def test_GARDE_un_echec_de_repli_adaptatif_reste_trace_dans_field_fallbacks(tmp_path):
    """Le VRAI cas mesuré sur Sapian (2026-09-22) : `resoudre_champ_adaptatif` ne trouve rien,
    `navigate_menu` échoue quand même (comportement attendu) — mais le DIAGNOSTIC de cet échec
    doit survivre jusqu'au rapport, sinon impossible à distinguer d'un mécanisme jamais appelé."""
    runner = _ecrire_aire_de_run_menu(tmp_path, echoue_sur="Surveys", resolution="echec")
    result = runner.real_run("garde_menu")

    assert result.passed == 1, f"le scénario avale son propre TimeoutError : {result.raw_stdout}"
    assert result.field_fallbacks, (
        "un échec de résolution adaptative doit rester visible dans field_fallbacks — sinon "
        "aucun moyen de distinguer 'le palier n'a jamais tourné' de 'il a tourné et échoué'.")
    assert "aucune correspondance parmi 24 éléments" in result.field_fallbacks[0]
