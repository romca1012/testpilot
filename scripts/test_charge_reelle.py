"""Preuve RÉELLE du plafond de tâches de fond (§6 addendum charge machine).

`tests/test_concurrency.py` prouve `guardrails/concurrency.py` avec des threads Python DANS le
même process pytest — jamais avec un vrai serveur et de vraies requêtes HTTP concurrentes. Ce
script ferme cet écart : il démarre un VRAI `uvicorn`, dans un VRAI sous-processus, et l'attaque
avec de vrais clients HTTP en parallèle.

    ./.venv/Scripts/python.exe scripts/test_charge_reelle.py
    ./.venv/Scripts/python.exe scripts/test_charge_reelle.py --n 12 --max-concurrent 3

────────────────────────────────────────────────────────────────────────────────
CHOIX DU POINT D'ENTRÉE — documenté, pas improvisé
────────────────────────────────────────────────────────────────────────────────

Les 6 points gatés par `concurrency.py` sont `automate_case`/`start_run` (cases.py), `launch_run`
(runs.py), `add_case`/`validate_metier` (modules.py) et `start_exploration` (projects.py). Les
5 premiers exigent soit un cas de test déjà généré (Gherkin réel), soit un appel à l'API Anthropic
réelle (clé, coût, non déterministe) — trop lourd à monter pour CE test-ci, qui ne veut mesurer que
l'admission-control, pas rejouer tout le produit.

`start_exploration` (`POST /api/projects/{id}/exploration`) ne demande qu'un PROJET avec une
connexion « complète » (`verifier_connexion` ne vérifie que la PRÉSENCE des champs, jamais leur
JOIGNABILITÉ) — aucun cas, aucun Gherkin, aucun appel LLM (`exploration_service` : « Aucun LLM
ici »). C'est le plus léger des 6 à déclencher : on crée N projets minimaux et on explore chacun.

`already_running` (un seul crawl actif par PROJET, `exploration_service.job_en_cours`) veut dire
qu'explorer N fois le MÊME projet ne prouverait rien — la 2ᵉ requête serait rejetée avant même
d'atteindre la file. D'où N PROJETS distincts, un par requête.

**Pointer chaque projet vers une adresse qui n'existe pas** fait échouer le crawl réel APRÈS
l'admission dans la file — acceptable ici, seule l'admission est mesurée. Le choix précis de
l'adresse a un effet DIRECT sur la fiabilité de la preuve :

- un port LOCAL fermé (connexion refusée) échoue en quelques millisecondes → la fenêtre pendant
  laquelle une tâche occupe sa place est trop courte pour être fiablement observée par un polling
  externe (flaky selon la charge de la machine) ;
- une adresse **non routable** (`192.0.2.1`, bloc TEST-NET-1, RFC 5737 — réservé à la documentation
  et aux tests, jamais assigné sur l'internet réel) fait que le navigateur attend une réponse qui
  ne viendra jamais, jusqu'à son propre timeout de navigation (`behave_runtime/steps_library/
  _base_helpers.py:playwright_login`, `page.goto(..., wait_until="domcontentloaded")` sans
  `timeout` explicite → 30 s, la valeur par défaut de Playwright). Fenêtre large et DÉTERMINISTE,
  au prix d'un temps d'exécution plus long (~30 s par lot de `max_concurrent` tâches). Choix
  assumé : la fiabilité de la preuve prime sur la vitesse d'un script qui ne tourne pas en CI.

────────────────────────────────────────────────────────────────────────────────
CE QUE LE SCRIPT FAIT, DANS L'ORDRE
────────────────────────────────────────────────────────────────────────────────

1. Choisit un port TCP libre (bind éphémère, jamais un port codé en dur — évite tout conflit avec
   les conteneurs Docker déjà en service sur ce poste, vérifiés manuellement avant d'écrire ce
   script : 5431/5433/10017 Postgres/Odoo, aucun rapport avec ce test).
2. Démarre `uvicorn testpilot.api.app:app` en sous-processus, avec `TESTPILOT_DATA_DIR` sous un
   dossier temporaire dédié (jamais le vrai `data/` du poste — `TESTPILOT_DB_URL` reste VIDE :
   SQLite isolé, pas de dépendance PostgreSQL pour cette preuve) et `TESTPILOT_MAX_CONCURRENT_JOBS`
   fixé à `--max-concurrent`.
3. Attend `/api/health`, se connecte avec un compte Admin créé pour l'occasion
   (`TESTPILOT_ADMIN_USERNAME`/`TESTPILOT_ADMIN_PASSWORD`, amorcé par `_amorcer_premier_admin`),
   crée `--n` projets minimaux pointant chacun vers l'adresse non routable.
4. Démarre un thread de polling qui interroge `GET /api/modules/jobs/queue/status` en continu,
   PENDANT que les N requêtes d'exploration partent — toutes en même temps (`threading.Barrier`),
   pas en boucle séquentielle.
5. Attend que la file se vide (`running == 0 and waiting == 0`), affiche et enregistre le rapport,
   puis arrête le serveur — **dans un `finally`**, y compris si la preuve échoue.

Si le plafond n'est PAS respecté en conditions réelles (pic de `running` > `max_concurrent`), le
script le rapporte tel quel et sort en échec (code 1) — jamais masqué.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent

# TEST-NET-1 (RFC 5737) : jamais routé sur l'internet réel, jamais une machine de quelqu'un —
# le navigateur attend une réponse qui ne viendra jamais, jusqu'à son propre timeout (30 s).
ADRESSE_NON_ROUTABLE = "http://192.0.2.1"


# ── Petits utilitaires ────────────────────────────────────────────────────────────────────

def _port_libre() -> int:
    """Un port TCP local libre À L'INSTANT T (bind éphémère puis relâché) — jamais un port codé
    en dur, qui finirait par entrer en conflit avec un service déjà démarré sur ce poste."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _attendre(predicat, timeout: float, pas: float = 0.1, message: str = "délai dépassé") -> None:
    fin = time.monotonic() + timeout
    while time.monotonic() < fin:
        if predicat():
            return
        time.sleep(pas)
    if not predicat():
        raise TimeoutError(message)


# ── Résultat d'une requête d'exploration individuelle ─────────────────────────────────────

@dataclass
class ResultatRequete:
    project_id: int
    ok: bool
    status_code: int | None = None
    job_id: str = ""
    erreur: str = ""
    duree_s: float = 0.0


@dataclass
class RapportCharge:
    n_requetes: int
    max_concurrent: int
    pic_running: int = 0
    pic_waiting: int = 0
    echantillons: int = 0
    requetes_reussies: int = 0
    requetes_echouees: int = 0
    file_videe: bool = False
    duree_totale_s: float = 0.0
    details_requetes: list = field(default_factory=list)
    releve_running_waiting: list = field(default_factory=list)  # (t_relatif_s, running, waiting)
    erreurs_polling: list = field(default_factory=list)  # diagnostic si échantillons == 0

    def conforme(self) -> bool:
        """La preuve centrale : jamais dépassé, la file a bien servi (waiting > 0 observé un
        instant), toutes les requêtes ont reçu une réponse, et rien n'est resté bloqué."""
        return (
            self.pic_running <= self.max_concurrent
            and self.pic_waiting > 0
            and self.requetes_echouees == 0
            and self.file_videe
        )


# ── Serveur réel, en sous-processus ────────────────────────────────────────────────────────

@contextlib.contextmanager
def serveur_reel(*, port: int, data_dir: Path, max_concurrent: int, admin_user: str,
                 admin_password: str, log_path: Path):
    """Démarre `uvicorn testpilot.api.app:app` en sous-processus réel, l'arrête TOUJOURS à la
    sortie (y compris si le corps du `with` lève) — jamais de process orphelin.

    `PYTHONPATH` est préfixé avec CE dépôt (`REPO_ROOT/src`) : l'environnement virtuel partagé
    (`.venv`) peut être installé en mode éditable vers un AUTRE checkout (courant avec les
    worktrees git) — sans ce préfixe, le sous-processus testerait le mauvais code source.
    """
    env = dict(os.environ)
    env["TESTPILOT_DATA_DIR"] = str(data_dir)
    env["TESTPILOT_MAX_CONCURRENT_JOBS"] = str(max_concurrent)
    env["TESTPILOT_ADMIN_USERNAME"] = admin_user
    env["TESTPILOT_ADMIN_PASSWORD"] = admin_password
    env["TESTPILOT_DB_URL"] = ""  # jamais PostgreSQL pour cette preuve — SQLite isolé, simple
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [sys.executable, "-m", "uvicorn", "testpilot.api.app:app",
          "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]

    with open(log_path, "w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT), env=env, stdout=log_file,
                                stderr=subprocess.STDOUT)
        try:
            yield proc
        finally:
            # Arrêt propre puis, seulement si nécessaire, forcé — jamais de process qui traîne.
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)


# ── Le corps de la preuve ──────────────────────────────────────────────────────────────────

def _login(client: httpx.Client, username: str, password: str) -> None:
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    if not r.json().get("authenticated"):
        raise RuntimeError(f"connexion refusée pour {username!r} : {r.text}")


def _creer_projets(client: httpx.Client, n: int) -> list[int]:
    """N projets minimaux, chacun avec une connexion « complète » mais qui ne mène nulle part —
    `already_running` (un crawl actif par PROJET) impose des projets DISTINCTS : explorer N fois
    le même projet ne testerait pas la file, juste le refus de doublon."""
    identifiants: list[int] = []
    suffixe = uuid.uuid4().hex[:8]
    for i in range(n):
        body = {
            "name": f"charge-reelle-{suffixe}-{i}",
            "connector_type": "odoo",
            "base_url": ADRESSE_NON_ROUTABLE,
            "database": "base-inexistante",
            "username": "utilisateur-factice",
            "password": "mot-de-passe-factice",
        }
        r = client.post("/api/projects", json=body)
        r.raise_for_status()
        identifiants.append(r.json()["id"])
    return identifiants


def _poller_file(client: httpx.Client, arret: threading.Event, releve: list,
                 t0: float, intervalle: float, erreurs: list) -> None:
    """Tourne dans un thread séparé : interroge `/api/modules/jobs/queue/status` en continu
    pendant que les requêtes d'exploration partent et tournent — c'est cette boucle qui capture
    l'INSTANTANÉ réel (`running`/`waiting`), pas une lecture isolée après coup.

    Un raté ISOLÉ de polling ne doit pas interrompre la mesure — mais s'il rate SYSTÉMATIQUEMENT
    (mauvaise URL, cookie manquant...), `erreurs` en garde une trace pour le rapport final plutôt
    que de laisser `échantillons: 0` sans explication."""
    while not arret.is_set():
        try:
            r = client.get("/api/modules/jobs/queue/status", timeout=5.0)
            r.raise_for_status()
            corps = r.json()
            releve.append((time.monotonic() - t0, corps["running"], corps["waiting"]))
        except httpx.HTTPError as exc:
            if len(erreurs) < 3:
                erreurs.append(str(exc))
        time.sleep(intervalle)


def _explorer_un_projet(base_url: str, project_id: int, cookies: httpx.Cookies,
                        barriere: threading.Barrier, resultats: list,
                        verrou: threading.Lock) -> None:
    """Exécuté dans son propre thread avec son propre client HTTP (un `httpx.Client` n'est pas
    forcément sûr à partager entre threads pour des requêtes concurrentes) ; la `Barrier`
    synchronise le DÉPART de tous les threads — c'est elle qui rend les N requêtes réellement
    SIMULTANÉES plutôt qu'une rafale étalée dans le temps. `cookies` porte le jeton de session déjà
    obtenu par `_login` — chaque client est neuf, mais doit rester authentifié comme l'Admin qui
    a créé les projets, sinon le verrou d'accès (`api/app.py:verrou_acces`) répond 401 avant même
    d'atteindre la file d'admission."""
    with httpx.Client(base_url=base_url, timeout=15.0, cookies=cookies) as client:
        barriere.wait()
        debut = time.monotonic()
        try:
            r = client.post(f"/api/projects/{project_id}/exploration")
            duree = time.monotonic() - debut
            if r.status_code == 202:
                resultat = ResultatRequete(project_id, True, r.status_code,
                                          r.json().get("job_id", ""), duree_s=duree)
            else:
                resultat = ResultatRequete(project_id, False, r.status_code,
                                          erreur=r.text[:300], duree_s=duree)
        except httpx.HTTPError as exc:
            resultat = ResultatRequete(project_id, False, erreur=str(exc),
                                      duree_s=time.monotonic() - debut)
    with verrou:
        resultats.append(resultat)


def _attendre_file_vide(client: httpx.Client, timeout: float) -> bool:
    def videe() -> bool:
        corps = client.get("/api/modules/jobs/queue/status", timeout=5.0).json()
        return corps["running"] == 0 and corps["waiting"] == 0

    try:
        _attendre(videe, timeout=timeout, pas=0.5, message="la file ne s'est jamais vidée")
        return True
    except TimeoutError:
        return False


def executer_charge(*, n: int, max_concurrent: int, port: int, data_dir: Path,
                    timeout_demarrage: float, timeout_drain: float,
                    intervalle_poll: float, log_path: Path) -> RapportCharge:
    admin_user = "admin-charge-reelle"
    admin_password = uuid.uuid4().hex  # jetable — n'a de sens que pour la durée du sous-processus
    base_url = f"http://127.0.0.1:{port}"

    with (
        serveur_reel(port=port, data_dir=data_dir, max_concurrent=max_concurrent,
                    admin_user=admin_user, admin_password=admin_password,
                    log_path=log_path) as proc,
        httpx.Client(base_url=base_url, timeout=15.0) as client,
    ):
            # 1. Le serveur doit répondre avant qu'on lui parle de quoi que ce soit d'autre.
            def sain() -> bool:
                if proc.poll() is not None:
                    raise RuntimeError(
                        f"le serveur s'est arrêté prématurément (code {proc.returncode}) — "
                        f"voir {log_path}")
                try:
                    return client.get("/api/health", timeout=2.0).status_code == 200
                except httpx.HTTPError:
                    return False
            _attendre(sain, timeout=timeout_demarrage,
                     message=f"le serveur n'a jamais répondu sur {base_url}/api/health "
                             f"— voir {log_path}")

            _login(client, admin_user, admin_password)
            project_ids = _creer_projets(client, n)

            # 2. Polling continu, démarré AVANT les requêtes concurrentes, arrêté APRÈS le drain.
            releve: list = []
            erreurs_poll: list = []
            arret_poll = threading.Event()
            t0 = time.monotonic()
            with httpx.Client(base_url=base_url, timeout=10.0, cookies=client.cookies) as client_poll:
                thread_poll = threading.Thread(
                    target=_poller_file,
                    args=(client_poll, arret_poll, releve, t0, intervalle_poll, erreurs_poll),
                    daemon=True)
                thread_poll.start()

                # 3. N requêtes RÉELLEMENT concurrentes — départ synchronisé par la barrière.
                barriere = threading.Barrier(n)
                resultats: list[ResultatRequete] = []
                verrou = threading.Lock()
                threads = [
                    threading.Thread(target=_explorer_un_projet,
                                    args=(base_url, pid, client.cookies, barriere, resultats,
                                         verrou))
                    for pid in project_ids
                ]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=30.0)
                    if t.is_alive():
                        # Ne doit normalement jamais arriver : le 202 part avant la tâche de fond.
                        resultats.append(ResultatRequete(-1, False,
                                                         erreur="thread requête jamais terminé"))

                # 4. Laisse la file se vider réellement (jusqu'à 30 s par lot admis, cf. docstring).
                file_videe = _attendre_file_vide(client, timeout=timeout_drain)

                arret_poll.set()
                thread_poll.join(timeout=5.0)

            duree_totale = time.monotonic() - t0

    pics_running = [r for _, r, _ in releve] or [0]
    pics_waiting = [w for _, _, w in releve] or [0]
    rapport = RapportCharge(
        n_requetes=n, max_concurrent=max_concurrent,
        pic_running=max(pics_running), pic_waiting=max(pics_waiting),
        echantillons=len(releve),
        requetes_reussies=sum(1 for r in resultats if r.ok),
        requetes_echouees=sum(1 for r in resultats if not r.ok),
        file_videe=file_videe, duree_totale_s=duree_totale,
        details_requetes=[r.__dict__ for r in sorted(resultats, key=lambda r: r.project_id)],
        releve_running_waiting=releve,
        erreurs_polling=erreurs_poll,
    )
    return rapport


# ── Rapport lisible ─────────────────────────────────────────────────────────────────────

def afficher_rapport(rapport: RapportCharge) -> None:
    print()
    print("=" * 78)
    print("PREUVE DE CHARGE RÉELLE — plafond de tâches de fond (guardrails/concurrency.py)")
    print("=" * 78)
    print(f"Requêtes envoyées (réellement concurrentes) : {rapport.n_requetes}")
    print(f"Plafond configuré (TESTPILOT_MAX_CONCURRENT_JOBS) : {rapport.max_concurrent}")
    print(f"Échantillons de /api/modules/jobs/queue/status collectés : {rapport.echantillons}")
    print(f"Pic de `running` observé : {rapport.pic_running}")
    print(f"Pic de `waiting` observé : {rapport.pic_waiting}")
    print(f"Requêtes ayant reçu une réponse : "
          f"{rapport.requetes_reussies}/{rapport.n_requetes} "
          f"({rapport.requetes_echouees} échouée(s))")
    print(f"File revenue à 0/0 avant la fin du script : {'oui' if rapport.file_videe else 'NON'}")
    print(f"Durée totale de la charge : {rapport.duree_totale_s:.1f} s")
    print()

    if rapport.pic_running > rapport.max_concurrent:
        print(f"** ÉCART DÉTECTÉ ** : `running` a dépassé le plafond configuré "
              f"({rapport.pic_running} > {rapport.max_concurrent}) — le plafond N'EST PAS "
              f"respecté en conditions réelles. Ne pas corriger ici sans en discuter d'abord.")
    if rapport.pic_waiting == 0:
        print("** SUSPECT ** : `waiting` n'est jamais monté au-dessus de 0 — soit le plafond n'a "
              "jamais été saturé (N pas assez grand par rapport à max_concurrent), soit le "
              "polling a manqué la fenêtre. La preuve n'est pas concluante telle quelle.")
    if rapport.echantillons == 0 and rapport.erreurs_polling:
        print("** LE POLLING A ÉCHOUÉ SYSTÉMATIQUEMENT ** — 0 échantillon collecté. Premières "
              "erreurs observées :")
        for e in rapport.erreurs_polling:
            print(f"    {e}")
    if rapport.requetes_echouees:
        print(f"** {rapport.requetes_echouees} requête(s) HTTP n'ont jamais reçu de réponse "
              f"utilisable ** — voir détails ci-dessous.")
        for d in rapport.details_requetes:
            if not d["ok"]:
                print(f"    projet {d['project_id']} : {d['erreur']}")
    if not rapport.file_videe:
        print("** LA FILE NE S'EST JAMAIS VIDÉE ** dans le délai imparti — au moins une tâche "
              "semble bloquée.")

    print()
    verdict = "CONFORME" if rapport.conforme() else "NON CONFORME"
    print(f"Verdict : {verdict} — le plafond {'a bien' if rapport.conforme() else 'n a PAS'} "
          f"été respecté ET démontré sous charge réelle concurrente.")
    print("=" * 78)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preuve réelle (vrai serveur, vraies requêtes HTTP concurrentes) du plafond "
                    "de tâches de fond de TestPilot.")
    parser.add_argument("--n", type=int, default=8,
                        help="nombre de requêtes d'exploration réellement concurrentes (défaut 8)")
    parser.add_argument("--max-concurrent", type=int, default=2,
                        help="TESTPILOT_MAX_CONCURRENT_JOBS pour le serveur de la preuve (défaut 2)")
    parser.add_argument("--port", type=int, default=0,
                        help="port du serveur (défaut : un port libre choisi automatiquement)")
    parser.add_argument("--timeout-demarrage", type=float, default=20.0,
                        help="secondes d'attente que le serveur réponde à /api/health")
    parser.add_argument("--timeout-drain", type=float, default=240.0,
                        help="secondes d'attente que la file revienne à 0/0 après la charge "
                             "(chaque lot admis peut prendre jusqu'à ~30 s, cf. docstring)")
    parser.add_argument("--intervalle-poll", type=float, default=0.1,
                        help="secondes entre deux lectures de /api/modules/jobs/queue/status")
    parser.add_argument("--json", type=Path, default=None,
                        help="chemin où écrire le rapport en JSON (défaut : dans le dossier "
                             "temporaire de la preuve)")
    parser.add_argument("--conserver-tmp", action="store_true",
                        help="ne pas supprimer le dossier temporaire (base + logs serveur) à la "
                             "fin — utile pour diagnostiquer un échec")
    args = parser.parse_args()

    if args.n <= args.max_concurrent:
        print(f"⚠ --n ({args.n}) <= --max-concurrent ({args.max_concurrent}) : la file ne sera "
              f"jamais saturée, `waiting` restera à 0 — la preuve ne serait pas concluante. "
              f"Augmentez --n.", file=sys.stderr)
        return 2

    data_dir_racine = Path(tempfile.mkdtemp(prefix="testpilot_charge_reelle_"))
    data_dir = data_dir_racine / "data"
    log_path = data_dir_racine / "serveur.log"
    port = args.port or _port_libre()

    print(f"[préparation] dossier temporaire isolé : {data_dir_racine}")
    print(f"[préparation] port choisi : {port}")
    print(f"[préparation] plafond configuré pour ce serveur : {args.max_concurrent}")
    print(f"[préparation] requêtes concurrentes prévues : {args.n}")

    echec_infra = None
    rapport = None
    try:
        rapport = executer_charge(
            n=args.n, max_concurrent=args.max_concurrent, port=port, data_dir=data_dir,
            timeout_demarrage=args.timeout_demarrage, timeout_drain=args.timeout_drain,
            intervalle_poll=args.intervalle_poll, log_path=log_path)
    except Exception as exc:  # rapporter honnêtement même un échec d'infrastructure
        echec_infra = exc
    finally:
        json_path = args.json or (data_dir_racine / "rapport.json")
        if rapport is not None:
            afficher_rapport(rapport)
            json_path.write_text(json.dumps({
                "n_requetes": rapport.n_requetes,
                "max_concurrent": rapport.max_concurrent,
                "pic_running": rapport.pic_running,
                "pic_waiting": rapport.pic_waiting,
                "echantillons": rapport.echantillons,
                "requetes_reussies": rapport.requetes_reussies,
                "requetes_echouees": rapport.requetes_echouees,
                "file_videe": rapport.file_videe,
                "duree_totale_s": rapport.duree_totale_s,
                "conforme": rapport.conforme(),
                "details_requetes": rapport.details_requetes,
                "releve_running_waiting": rapport.releve_running_waiting,
                "erreurs_polling": rapport.erreurs_polling,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[rapport] JSON écrit : {json_path}")
        if echec_infra is not None:
            print(f"[ÉCHEC INFRASTRUCTURE] la preuve n'a pas pu tourner jusqu'au bout : "
                  f"{echec_infra}", file=sys.stderr)
            print(f"[ÉCHEC INFRASTRUCTURE] voir le journal du serveur : {log_path}", file=sys.stderr)

        if args.conserver_tmp or echec_infra is not None or (rapport and not rapport.conforme()):
            print(f"[nettoyage] dossier temporaire CONSERVÉ pour diagnostic : {data_dir_racine}")
        else:
            shutil.rmtree(data_dir_racine, ignore_errors=True)
            print("[nettoyage] dossier temporaire supprimé (succès, --conserver-tmp non demandé).")

    if echec_infra is not None:
        return 1
    return 0 if rapport.conforme() else 1


if __name__ == "__main__":
    raise SystemExit(main())
