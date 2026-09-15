"""Runner Behave réel — assemble une aire d'exécution isolée puis lance le sous-processus.

C'est l'implémentation concrète du ``DryRunner`` injecté au pilier generation : ``dry_run``
valide le parsing (``--dry-run``, sans navigateur ni Odoo), ``real_run`` exécute pour de vrai.

Chaque run est assemblé dans un dossier temporaire jetable :
    <tmp>/environment.py, <tmp>/steps/<bibliothèque + steps générés>, <tmp>/<module>.feature
ce qui isole les runs et garde ``behave_runtime/generated`` à sa place (sortie de generation).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from testpilot import config
from testpilot.execution.behave_result import (
    FIELD_FALLBACK_FILE_ENV,
    FIELD_FALLBACK_FILENAME,
    REGLES_REFUS_FILE_ENV,
    REGLES_REFUS_FILENAME,
    SELECTOR_TIER_FILE_ENV,
    SELECTOR_TIER_FILENAME,
    BehaveResult,
    parse_behave_json,
    read_field_fallbacks,
    read_refus_mesures,
    read_selector_tiers,
)

logger = logging.getLogger(__name__)

# Formatter maison assemblé dans le run_dir (cf. behave_runtime/tp_json_formatter.py).
_FORMATTER_MODULE = "tp_json_formatter"
_FULL_FORMATTER = f"{_FORMATTER_MODULE}:FullJSONFormatter"


class BehaveRunner:
    def __init__(self, *, runtime_dir: Path | None = None, generated_dir: Path | None = None,
                 steps_library_dir: Path | None = None, dry_timeout: int | None = None,
                 real_timeout: int | None = None, connection: dict[str, str] | None = None,
                 project_id: int | None = None, connector_type: str | None = None):
        self.runtime_dir = runtime_dir or config.BEHAVE_RUNTIME_DIR
        self.generated_dir = generated_dir or config.GENERATED_DIR
        self.steps_library_dir = steps_library_dir or config.STEPS_LIBRARY_DIR
        self.dry_timeout = dry_timeout or config.BEHAVE_DRY_TIMEOUT_SECONDS
        self.real_timeout = real_timeout or config.BEHAVE_REAL_TIMEOUT_SECONDS
        # Connecteur du projet (2026-08-13) : scope QUELS steps partagés sont copiés dans le
        # run_dir — `generic/` + `<connector_type>/` seulement. None (défaut) = tout copier, comme
        # avant la séparation par connecteur (repli sûr, jamais moins de steps qu'aujourd'hui).
        self.connector_type = connector_type
        # Connexion du PROJET (variables d'env) injectée dans le sous-processus behave.
        # Vide → le harnais retombe sur la config globale (.env). Cf. connectors/runtime_env.
        self.connection = connection or {}
        # Projet du run : le résolveur déterministe (§2bis) lit son annuaire au runtime.
        self.project_id = project_id
        # Où CONSERVER la trace brute de ce run (2026-07-24). None → rien n'est gardé, comme avant.
        self.artifacts_dir: Path | None = None
        # L'exécution en cours, pour tracer QUELLE exécution a appris quoi (0023). None → une
        # règle apprise sans ce lien, comme avant ce correctif (les runners de test, `cli.py`).
        self.execution_id: int | None = None

    def cibler_execution(self, execution_id: int | None) -> None:
        """Désigne l'exécution du PROCHAIN run — même motif que `cibler_artefacts` ci-dessous.

        ⚠️ **Pourquoi ça n'existait pas.** `regles_apprises.enregistrer()` accepte `execution_id`
        depuis l'origine (0023), mais rien ne l'appelait jamais avec autre chose que sa valeur par
        défaut (`None`) : chaque règle apprise portait `execution_id: null`, contredisant la
        traçabilité que 0023 promettait (« quel run a appris quoi »). Trouvé en observant de
        vraies règles apprises réelles, toutes `null`, pendant l'audit.

        Le runner est réutilisé d'une tentative de réparation à l'autre, chacune sa propre ligne
        d'exécution (voir `cibler_artefacts`) : la cible se redésigne donc avant chaque run.
        """
        self.execution_id = execution_id

    def cibler_artefacts(self, chemin: Path | None) -> None:
        """Désigne le dossier où archiver la trace brute du PROCHAIN run.

        ⚠️ **Pourquoi ça n'existait pas.** Chaque run est assemblé dans un dossier temporaire
        détruit en sortie (`rmtree` ci-dessous) : la sortie de Behave, son JSON, le `.feature` et
        les steps réellement joués **disparaissaient**. Le rapport était reconstruit depuis la
        base — ce qui suffit pour lire un verdict, jamais pour *instruire* un résultat non
        concluant. Un testeur devant « erreur technique » n'avait rien à ouvrir.

        Le runner est réutilisé d'une tentative de réparation à l'autre, chacune ayant sa propre
        ligne d'exécution : la cible se redésigne donc **avant chaque run**, sinon deux exécutions
        écriraient dans le même dossier et la seconde écraserait la première.
        """
        self.artifacts_dir = chemin

    def _subprocess_env(self, run_dir: Path) -> dict[str, str]:
        """Environnement du sous-processus : celui du parent + la connexion du projet + le sidecar.

        ``environment.py`` appelle ``load_dotenv()`` sans ``override`` : les variables passées
        ici priment donc sur le ``.env``. Connexion vide → le harnais retombe sur la config
        globale, mais l'environnement reste explicite : le sidecar des replis (0007 B+) doit être
        désigné à CHAQUE run, connexion propre au projet ou non.
        """
        env = {**os.environ, **self.connection,
               FIELD_FALLBACK_FILE_ENV: str(run_dir / FIELD_FALLBACK_FILENAME),
               REGLES_REFUS_FILE_ENV: str(run_dir / REGLES_REFUS_FILENAME),
               SELECTOR_TIER_FILE_ENV: str(run_dir / SELECTOR_TIER_FILENAME)}
        # `src` importable dans le sous-processus : le résolveur déterministe (§2bis) importe
        # `testpilot.generation.{valeur_conforme,domain_model}`. Sans ça, `python -m behave`
        # (cwd = run_dir jetable) ne voit pas le paquet `testpilot`. On PRÉPEND pour primer sur
        # un éventuel PYTHONPATH parent.
        src_root = str(config.SRC_DIR.parent)
        ancien = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src_root + (os.pathsep + ancien if ancien else "")
        # L'id du projet, que le résolveur lit pour charger le BON annuaire (0005 : un annuaire
        # par instance). Absent → le résolveur le dira ; les steps fins classiques marchent sans.
        if self.project_id is not None:
            env["TESTPILOT_PROJECT_ID"] = str(self.project_id)
        # Le connecteur (2026-09-08, multi-connecteurs) : `environment.py` en a besoin pour
        # savoir s'il doit ouvrir une session RPC Odoo — un projet sans backend Odoo ferait
        # échouer TOUT scénario dès `before_scenario` si cette session s'ouvrait quand même.
        # Absent → défaut « odoo » côté `environment.py`, comportement inchangé pour un run
        # hors API (CLI sans projet, ex. `.env` de la machine).
        if self.connector_type is not None:
            env["TESTPILOT_CONNECTOR_TYPE"] = self.connector_type
        return env

    def dry_run(self, module_name: str) -> BehaveResult:
        return self._run(module_name, dry_run=True)

    def real_run(self, module_name: str) -> BehaveResult:
        return self._run(module_name, dry_run=False)

    # ── Interne ───────────────────────────────────────────────────────────────
    def _run(self, module_name: str, dry_run: bool) -> BehaveResult:
        feature_src = self.generated_dir / f"{module_name}.feature"
        if not feature_src.exists():
            return BehaveResult(success=False, returncode=-1, dry_run=dry_run,
                                raw_stderr=f".feature introuvable : {feature_src}")

        run_dir = Path(tempfile.mkdtemp(prefix=f"tp_behave_{module_name}_"))
        try:
            self._assemble(run_dir, module_name, feature_src)
            json_path = run_dir / "result.json"
            # Formatter maison : le JSON natif de Behave omet le message des steps « errored »
            # (cf. tp_json_formatter). Repli sur le formatter natif s'il est indisponible.
            fmt = _FULL_FORMATTER if (run_dir / f"{_FORMATTER_MODULE}.py").exists() else "json"
            cmd = [sys.executable, "-m", "behave", "--lang", "fr",
                   "-f", fmt, "-o", str(json_path), f"{module_name}.feature"]
            if dry_run:
                cmd.append("--dry-run")
            timeout = self.dry_timeout if dry_run else self.real_timeout
            try:
                proc = subprocess.run(cmd, cwd=str(run_dir), capture_output=True, text=True,
                                      encoding="utf-8", errors="replace", timeout=timeout,
                                      env=self._subprocess_env(run_dir))
            except subprocess.TimeoutExpired:
                # ⚠️ Un timeout est le cas où la trace est la PLUS utile (« qu'a-t-il fait pendant
                # 15 minutes ? ») — et c'est justement celui où il n'y a pas de `proc`. On archive
                # ce qui existe : le JSON partiel s'il a été écrit, et le contexte du timeout.
                self._archiver(run_dir, module_name, dry_run=dry_run,
                               journal=f"Timeout ({timeout}s) lors du run behave — le "
                                       f"sous-processus a été interrompu, sa sortie est perdue.")
                return BehaveResult(success=False, returncode=-2, dry_run=dry_run,
                                    raw_stderr=f"Timeout ({timeout}s) lors du run behave")
            json_output = json_path.read_text(encoding="utf-8") if json_path.exists() else ""
            self._archiver(run_dir, module_name, dry_run=dry_run,
                           journal=f"{proc.stdout}\n{proc.stderr}")
            result = parse_behave_json(json_output, proc.returncode, dry_run=dry_run,
                                       combined_log=f"{proc.stdout}\n{proc.stderr}")
            # Replis consignés par les helpers UI (0007 B+). Lu ICI, avant le rmtree du `finally`,
            # et depuis le fichier — pas depuis la sortie de Behave, qui n'en porte rien sur un
            # scénario vert (cf. read_field_fallbacks).
            result.field_fallbacks = read_field_fallbacks(run_dir / FIELD_FALLBACK_FILENAME)
            # Refus MESURÉS pendant le run (§5bis n°1). Lus ici, avant le rmtree, puis appris.
            result.refus_mesures = read_refus_mesures(run_dir / REGLES_REFUS_FILENAME)
            self._apprendre(result, dry_run=dry_run)
            # Paliers de résolution de chaque champ (§1.2 du plan de consolidation). Même moment
            # de lecture (avant le rmtree), même sidecar que les deux mécanismes ci-dessus.
            result.selector_tiers = read_selector_tiers(run_dir / SELECTOR_TIER_FILENAME)
            self._detecter_derive(result, module_name, dry_run=dry_run)
            return result
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def _apprendre(self, result: BehaveResult, *, dry_run: bool) -> None:
        """Persiste les refus mesurés en règles apprises pour ce projet (§5bis n°1).

        ⚠️ **Pourquoi ICI et nulle part ailleurs.** `run_service` et `cli.py` clôturent tous deux
        une exécution : y brancher l'apprentissage le dédoublerait, et un jour l'un des deux
        divergerait. Le runner est le seul point que les deux traversent, et il connaît déjà le
        projet.

        Trois bornes, chacune assumée :

        - **jamais sur un dry-run** — il ne touche pas l'application, il ne mesure rien ;
        - **on apprend MÊME SI la version est rejetée** par la boucle de réparation. Un refus
          mesuré est un fait sur l'application ; adopter une version est une décision sur notre
          code. Les confondre perdrait le fait ;
        - **best-effort, jamais fatal** — un disque plein ne doit pas faire tomber une exécution
          qui a créé de vraies données dans l'application testée (même arbitrage que l'archivage).
        """
        if dry_run or self.project_id is None or not result.refus_mesures:
            return
        try:
            from testpilot.generation import regles_apprises
            apprises = regles_apprises.enregistrer(self.project_id, result.refus_mesures,
                                                    execution_id=self.execution_id)
        except Exception:
            logger.warning("[règles apprises] apprentissage impossible — le run reste intact",
                           exc_info=True)
            return
        if apprises:
            logger.info("[règles apprises] projet %s : %d refus mesuré(s) enregistré(s)",
                        self.project_id, apprises)

    def _detecter_derive(self, result: BehaveResult, module_name: str, *, dry_run: bool) -> None:
        """Persiste les paliers de résolution de ce run et journalise toute DÉRIVE (§1.2).

        Mêmes trois bornes qu'`_apprendre`, pour les mêmes raisons :

        - **jamais sur un dry-run** — aucun champ n'y est réellement résolu contre l'application ;
        - **ici et nulle part ailleurs** — le seul point que `run_service` et `cli.py` traversent
          tous les deux ;
        - **best-effort, jamais fatal** — une dérive non enregistrée est un défaut mineur de
          visibilité, jamais une raison de faire tomber une exécution réelle.
        """
        if dry_run or self.project_id is None or not result.selector_tiers:
            return
        try:
            from testpilot.execution import selector_memory
            derives = selector_memory.enregistrer(
                self.project_id, module_name, result.selector_tiers,
                execution_id=self.execution_id)
        except Exception:
            logger.warning("[mémoire sélecteurs] enregistrement impossible — le run reste intact",
                           exc_info=True)
            return
        for derive in derives:
            logger.warning(
                "[dérive de sélecteur] projet %s, module %s, champ '%s' : résolu par « %s » "
                "auparavant, désormais par « %s ». À surveiller — l'application a peut-être "
                "changé sous ce champ.",
                self.project_id, derive.module, derive.ident, derive.ancien_tier,
                derive.nouveau_tier)

    def _archiver(self, run_dir: Path, module_name: str, *, dry_run: bool, journal: str) -> None:
        """Recopie la trace brute du run hors du dossier temporaire, avant sa destruction.

        Ce qu'on garde, et pourquoi chaque pièce :

        - le **journal** (sortie et erreur du sous-processus) : ce que la machine a vu dérouler ;
        - le **JSON de Behave** : le détail par scénario et par step, avec les messages d'erreur ;
        - le **.feature** et les **steps** RÉELLEMENT joués : le cas a pu changer depuis, et un
          résultat qu'on relit six mois plus tard doit être lisible avec le test de son époque ;
        - les **replis de champ** consignés pendant le run, s'il y en a eu ;
        - les **refus mesurés** : ce que l'application a refusé, et qui devient une règle apprise.
          Archivé pour qu'on puisse relire *pourquoi* une valeur est interdite depuis ce run-là ;
        - les **paliers de résolution** de chaque champ (§1.2) : ce qui a permis de détecter une
          dérive éventuelle, à relire même quand la mémoire du projet a depuis été mise à jour.

        ⚠️ **Best-effort, jamais bloquant.** Un disque plein ou un droit manquant ne doit pas
        transformer un run réussi en échec : l'archivage échoue en silence journalisé. L'inverse
        — faire tomber une exécution réelle (qui a créé des données dans l'application testée)
        pour un problème d'archivage — serait une régression bien pire que l'absence de trace.
        """
        if self.artifacts_dir is None:
            return
        prefixe = "dry-run" if dry_run else "execution"
        try:
            self.artifacts_dir.mkdir(parents=True, exist_ok=True)
            (self.artifacts_dir / f"{prefixe}.log").write_text(journal or "", encoding="utf-8")
            for source, cible in (
                (run_dir / "result.json", f"{prefixe}.behave.json"),
                (run_dir / f"{module_name}.feature", f"{module_name}.feature"),
                (run_dir / "steps" / f"{module_name}_steps.py", f"{module_name}_steps.py"),
                (run_dir / FIELD_FALLBACK_FILENAME, f"{prefixe}.replis-de-champ.json"),
                (run_dir / REGLES_REFUS_FILENAME, f"{prefixe}.refus-mesures.jsonl"),
                (run_dir / SELECTOR_TIER_FILENAME, f"{prefixe}.paliers-de-selecteur.jsonl"),
            ):
                if source.exists():
                    shutil.copy2(source, self.artifacts_dir / cible)
            # Captures d'ecran par scenario (dossier "screenshots/" ecrit par environment.py,
            # cf. son docstring) : pas de fichier fixe (un par scenario), donc copie de dossier
            # plutot qu'une entree de plus dans la liste ci-dessus.
            captures = run_dir / "screenshots"
            if captures.is_dir():
                cible_captures = self.artifacts_dir / "screenshots"
                cible_captures.mkdir(exist_ok=True)
                for fichier in captures.glob("*.png"):
                    shutil.copy2(fichier, cible_captures / fichier.name)
        except OSError:
            logger.warning("[artefacts] archivage impossible vers %s — le run, lui, est intact",
                           self.artifacts_dir, exc_info=True)

    def _steps_library_files(self) -> list[Path]:
        """Fichiers `.py` de la bibliothèque partagée à copier, scopés par `self.connector_type`.

        Miroir du scope de `steps_library.catalogue()` (même règle : `generic/` + le connecteur
        actif, jamais un AUTRE connecteur) — mais avec une différence obligatoire : les helpers
        SANS décorateur à la racine (`_base_helpers.py`, `_accent_matcher.py`) sont TOUJOURS
        copiés, scope ou pas, car les steps de `generic/`/`<connector>/` les importent au
        runtime (`from _base_helpers import ...`) — les exclure casserait tout run.
        """
        if self.connector_type is None:
            return list(self.steps_library_dir.rglob("*.py"))
        fichiers = list(self.steps_library_dir.glob("*.py"))  # helpers à la racine, toujours
        for sous_dossier in ("generic", self.connector_type):
            chemin = self.steps_library_dir / sous_dossier
            if chemin.exists():
                fichiers.extend(chemin.rglob("*.py"))
        return fichiers

    def _assemble(self, run_dir: Path, module_name: str, feature_src: Path) -> None:
        """Recopie environment.py, le formatter, la bibliothèque de steps + les steps générés,
        et le .feature."""
        env_src = self.runtime_dir / "environment.py"
        if env_src.exists():
            shutil.copy2(env_src, run_dir / "environment.py")

        # Le formatter vit à la racine du run_dir (= cwd du sous-processus) pour être importable
        # par son nom de module (``python -m behave`` place le cwd en tête de sys.path).
        fmt_src = self.runtime_dir / f"{_FORMATTER_MODULE}.py"
        if fmt_src.exists():
            shutil.copy2(fmt_src, run_dir / fmt_src.name)

        steps_dir = run_dir / "steps"
        steps_dir.mkdir()
        (steps_dir / "__init__.py").write_text("", encoding="utf-8")
        if self.steps_library_dir.exists():
            for lib in self._steps_library_files():
                shutil.copy2(lib, steps_dir / lib.name)
        gen_steps = self.generated_dir / f"{module_name}_steps.py"
        if gen_steps.exists():
            shutil.copy2(gen_steps, steps_dir / gen_steps.name)

        shutil.copy2(feature_src, run_dir / f"{module_name}.feature")
