"""Banc de mesure de la fiabilité du verdict (lot 04) — indicateurs I1 à I6 sur l'instance Odoo de RÉFÉRENCE.

    python scripts/banc_mesure.py --version 17.0                 # mode figé (défaut) : coût nul, aucun LLM
    python scripts/banc_mesure.py --version 17.0 --mode génération --plafond-cout 5

Deux modes :

- ``figé`` : rejoue des cas DÉJÀ écrits (``banc/cas_figes/``, écrits à la main, tenant lieu de versions
  approuvées) sur l'instance saine, puis sous chaque défaut injecté et chaque panne d'environnement.
  Mesure le harnais et le verdict : I1 (faux PASSED), I2 (faux FAILED), I5 (blocage bien attribué).
  Aucun appel LLM : coût nul, exécutable en CI.
- ``génération`` : régénère les cas depuis ``specs/banc/*.md`` puis exécute — mesure l'AGENT (I3, I4, I6).
  Appelle un LLM : plafond de coût explicite (``--plafond-cout``, en dollars), arrêt si dépassé.

⚠️ **« Non mesuré » n'est pas « zéro »** (même discipline que ``audit_generation_quality.py``) : un indicateur
sans aucune observation vaut ``None`` et s'affiche « non mesuré », jamais 0 %. Les attendus
(``specs/banc/attendus.yaml``) sont écrits par un humain : ce script ne les déduit jamais d'un run.

Sécurité : le banc n'accepte qu'une instance LOCALE (127.0.0.1 / localhost) — jamais une instance client.
Isolation : une mesure ne modifie jamais les mémoires apprises de production ; elle tourne sur un
``TESTPILOT_DATA_DIR`` jetable dont le chemin figure dans la sortie.

Code de sortie : 0 si I1 = 0 et I5 = 100 % (quand ils sont mesurés) ; 1 si un faux PASSED ou un blocage mal
attribué est constaté ; 2 si l'instance est injoignable ou refusée ; 3 si RIEN n'a pu être mesuré.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

RACINE = Path(__file__).resolve().parents[1]
CAS_FIGES = RACINE / "banc" / "cas_figes"
ATTENDUS = RACINE / "specs" / "banc" / "attendus.yaml"
IMAGES = RACINE / "banc" / "images.env"
SORTIE = RACINE / "docs" / "mesures"

STATUTS = ("passed", "failed", "blocked", "retest", "untested")
HOTES_AUTORISES = {"127.0.0.1", "localhost", "::1"}

# Cibles du plan (§3) — reportées dans le tableau pour lire l'écart d'un coup d'œil.
CIBLES = {
    "I1": "0 faux PASSED", "I2": "≤ 2 %", "I3": "≥ 85 %", "I4": "≥ 75 %", "I5": "100 %", "I6": "< 1 € par cas",
}


# ── Attendus ─────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Attendu:
    config: str      # "sain" | "defaut:<code>" | "panne:<code>"
    cas: str
    statut: str      # statut de LECTURE attendu


def charger_attendus(chemin: Path = ATTENDUS) -> dict:
    import yaml
    return yaml.safe_load(Path(chemin).read_text(encoding="utf-8"))


def liste_des_attendus(attendus: dict) -> list[Attendu]:
    """Toutes les paires (configuration, cas) décrites, avec leur statut attendu."""
    out = [Attendu("sain", cas, statut) for cas, statut in (attendus.get("sain") or {}).items()]
    for code, cas_map in (attendus.get("defauts") or {}).items():
        out += [Attendu(f"defaut:{code}", cas, statut) for cas, statut in cas_map.items()]
    for code, panne in (attendus.get("pannes") or {}).items():
        out += [Attendu(f"panne:{code}", cas, panne["attendu"]) for cas in panne["cas"]]
    return out


def valider_attendus(attendus: dict, cas_disponibles: set[str]) -> list[str]:
    """Erreurs de FORME (cas inconnu, statut inconnu) — jamais un jugement sur les valeurs."""
    erreurs = []
    for a in liste_des_attendus(attendus):
        if a.cas not in cas_disponibles:
            erreurs.append(f"{a.config} : le cas « {a.cas} » n'existe pas dans banc/cas_figes/")
        if a.statut not in STATUTS:
            erreurs.append(f"{a.config}/{a.cas} : statut attendu inconnu « {a.statut} »")
    return erreurs


# ── Indicateurs (purs : testés sur des résultats simulés) ────────────────────────────────────

def _ratio(numerateur: int, denominateur: int):
    return None if denominateur == 0 else numerateur / denominateur


def calculer_indicateurs(observations: list[dict], attendus: dict, generation: dict | None = None) -> dict:
    """I1 à I6 à partir des observations `{config, cas, statut, ...}`.

    `statut` vaut un statut de lecture, ou `None` quand le cas n'a PAS pu être mesuré (harnais tombé, instance
    injoignable) : il sort alors du dénominateur — « non mesuré » n'est jamais compté comme un succès ni comme
    un échec.

    - I1 (faux PASSED) : paires (défaut, cas) dont le cas DOIT échouer et sort `passed` / paires mesurées ;
      détail par défaut (un défaut est « manqué » si TOUTES ses paires mesurées sont `passed`).
    - I2 (faux FAILED) : cas `failed` sur l'instance saine / cas mesurés sur l'instance saine.
    - I5 (blocage attribué) : pannes dont le cas sort `blocked` / paires (panne, cas) mesurées.
    - I3, I4, I6 : mode génération seulement (`generation`) — `None` sinon.
    """
    attendu_de = {(a.config, a.cas): a.statut for a in liste_des_attendus(attendus)}
    mesurees = [o for o in observations if o.get("statut") is not None]

    def paires(prefixe: str):
        return [o for o in mesurees if o["config"].startswith(prefixe)]

    defauts = paires("defaut:")
    faux_passed = [o for o in defauts if o["statut"] == "passed" and attendu_de.get((o["config"], o["cas"])) == "failed"]
    par_defaut: dict[str, dict] = {}
    for o in defauts:
        d = par_defaut.setdefault(o["config"].split(":", 1)[1], {"mesurees": 0, "passed": 0, "cas": []})
        d["mesurees"] += 1
        d["passed"] += o["statut"] == "passed"
        d["cas"].append({"cas": o["cas"], "statut": o["statut"]})
    for d in par_defaut.values():
        d["manque"] = d["passed"] == d["mesurees"]

    sain = paires("sain")
    faux_failed = [o for o in sain if o["statut"] == "failed"]
    pannes = paires("panne:")
    bien_attribuees = [o for o in pannes if o["statut"] == "blocked"]

    gen = generation or {}
    ecarts = [{"config": o["config"], "cas": o["cas"], "attendu": attendu_de[(o["config"], o["cas"])],
               "observe": o["statut"], "cause": o.get("cause", "")}
              for o in mesurees if (o["config"], o["cas"]) in attendu_de
              and attendu_de[(o["config"], o["cas"])] != o["statut"]]
    return {
        "I1": {"valeur": _ratio(len(faux_passed), len(defauts)), "faux_passed": len(faux_passed),
               "paires_mesurees": len(defauts), "par_defaut": par_defaut,
               "defauts_manques": sorted(c for c, d in par_defaut.items() if d["manque"])},
        "I2": {"valeur": _ratio(len(faux_failed), len(sain)), "faux_failed": len(faux_failed),
               "cas_mesures": len(sain)},
        "I3": {"valeur": _ratio(gen.get("sans_erreur_technique", 0), gen.get("generes", 0)) if gen else None,
               "echantillon": gen.get("generes", 0)},
        "I4": {"valeur": _ratio(gen.get("verdict_exploitable", 0), gen.get("generes", 0)) if gen else None,
               "echantillon": gen.get("generes", 0)},
        "I5": {"valeur": _ratio(len(bien_attribuees), len(pannes)), "bloques": len(bien_attribuees),
               "paires_mesurees": len(pannes),
               "mal_attribuees": [{"config": o["config"], "cas": o["cas"], "statut": o["statut"]}
                                  for o in pannes if o["statut"] != "blocked"]},
        "I6": {"valeur": (gen["cout_total"] / gen["nouveaux_cas"]) if gen.get("nouveaux_cas") else None,
               "unite": "$", "echantillon": gen.get("nouveaux_cas", 0)},
        "ecarts_aux_attendus": ecarts,
        "non_mesurees": [{"config": o["config"], "cas": o["cas"], "raison": o.get("raison", "")}
                         for o in observations if o.get("statut") is None],
    }


def code_de_sortie(indicateurs: dict) -> int:
    """0 : rien à signaler ; 1 : un faux PASSED ou un blocage mal attribué ; 3 : RIEN de mesuré."""
    i1, i5 = indicateurs["I1"], indicateurs["I5"]
    rien = (i1["valeur"] is None and indicateurs["I2"]["valeur"] is None and i5["valeur"] is None)
    if i1["faux_passed"] > 0 or (i5["valeur"] is not None and i5["valeur"] < 1.0):
        return 1
    return 3 if rien else 0


# ── Rendu ────────────────────────────────────────────────────────────────────────────────────

def _fmt(valeur, *, pourcent=True, unite=""):
    if valeur is None:
        return "non mesuré"
    return f"{valeur * 100:.1f} %" if pourcent else f"{valeur:.3f}{unite}"


def rendre_markdown(indicateurs: dict, contexte: dict, observations: list[dict]) -> str:
    i = indicateurs
    lignes = [
        f"# Banc de mesure — Odoo {contexte['version']} — {contexte['date']}", "",
        f"Mode : **{contexte['mode']}** · commit `{contexte.get('commit', '?')}` · image `{contexte.get('image', '?')}` · "
        f"données de la mesure : `{contexte.get('data_dir', '?')}`", "",
        "## Indicateurs", "",
        "| Indicateur | Valeur | Échantillon | Cible |", "|---|---|---|---|",
        f"| I1 — Faux PASSED | {_fmt(i['I1']['valeur'])} | {i['I1']['faux_passed']} / {i['I1']['paires_mesurees']} paires (défaut, cas) | {CIBLES['I1']} |",
        f"| I2 — Faux FAILED | {_fmt(i['I2']['valeur'])} | {i['I2']['faux_failed']} / {i['I2']['cas_mesures']} cas sur l'instance saine | {CIBLES['I2']} |",
        f"| I3 — Exécution au 1er passage | {_fmt(i['I3']['valeur'])} | {i['I3']['echantillon'] or 'non mesuré'} cas générés | {CIBLES['I3']} |",
        f"| I4 — Verdict exploitable | {_fmt(i['I4']['valeur'])} | {i['I4']['echantillon'] or 'non mesuré'} cas générés | {CIBLES['I4']} |",
        f"| I5 — Blocage bien attribué | {_fmt(i['I5']['valeur'])} | {i['I5']['bloques']} / {i['I5']['paires_mesurees']} paires (panne, cas) | {CIBLES['I5']} |",
        f"| I6 — Coût par nouveau cas | {_fmt(i['I6']['valeur'], pourcent=False, unite=' $')} | {i['I6']['echantillon'] or 'non mesuré'} nouveaux cas | {CIBLES['I6']} |",
        "", "« non mesuré » signifie qu'aucune observation n'a été faite (mode figé : I3, I4, I6 ne s'appliquent pas) ; "
        "ce n'est PAS zéro.", "",
    ]
    if i["I1"]["defauts_manques"]:
        lignes += ["## ⚠️ Défauts injectés NON détectés (faux PASSED)", ""]
        lignes += [f"- `{d}`" for d in i["I1"]["defauts_manques"]] + [""]
    if i["ecarts_aux_attendus"]:
        lignes += ["## Écarts aux attendus", "", "| Configuration | Cas | Attendu | Observé | Cause |", "|---|---|---|---|---|"]
        lignes += [f"| {e['config']} | {e['cas']} | {e['attendu']} | {e['observe']} | {e['cause'] or '—'} |"
                   for e in i["ecarts_aux_attendus"]] + [""]
    if i["non_mesurees"]:
        lignes += ["## Non mesuré", ""] + [f"- {n['config']} / {n['cas']} : {n['raison'] or 'raison non consignée'}"
                                            for n in i["non_mesurees"]] + [""]
    lignes += ["## Détail par cas", "", "| Configuration | Cas | Statut | Exécution | Fonctionnel | Cause | Durée (s) |",
               "|---|---|---|---|---|---|---|"]
    for o in observations:
        lignes.append(f"| {o['config']} | {o['cas']} | {o.get('statut') or 'non mesuré'} | {o.get('execution', '')} | "
                      f"{o.get('fonctionnel', '')} | {o.get('cause', '')} | {o.get('duree', '')} |")
    return "\n".join(lignes) + "\n"


# ── L'instance du banc ───────────────────────────────────────────────────────────────────────

@dataclass
class InstanceBanc:
    url: str
    base: str = "banc"
    utilisateur: str = "admin"
    mot_de_passe: str = "admin"
    compose: str = "compose.banc.yml"
    _rpc: object = field(default=None, repr=False)

    def __post_init__(self):
        hote = urlparse(self.url).hostname or ""
        if hote not in HOTES_AUTORISES:
            raise SystemExit(f"Refus : le banc n'accepte qu'une instance LOCALE, pas « {hote} » "
                             "(jamais une instance client).")

    def rpc(self):
        import odoorpc
        u = urlparse(self.url)
        connexion = odoorpc.ODOO(u.hostname, protocol="jsonrpc", port=u.port or 8069, timeout=120)
        connexion.login(self.base, self.utilisateur, self.mot_de_passe)
        return connexion

    def attendre(self, delai=180) -> bool:
        debut = time.time()
        while time.time() - debut < delai:
            try:
                urllib.request.urlopen(self.url.rstrip("/") + "/web/login", timeout=5)
                return True
            except Exception:
                time.sleep(3)
        return False

    def fixer_defauts(self, actifs: set[str], codes: list[str]) -> None:
        """Active exactement les défauts `actifs` (tous les autres à 0)."""
        params = self.rpc().env["ir.config_parameter"]
        for code in codes:
            params.set_param("tp_bug." + code, "1" if code in actifs else "0")

    def arreter(self):
        subprocess.run(["docker", "compose", "-f", self.compose, "stop", "odoo"], check=True, cwd=RACINE)

    def demarrer(self):
        subprocess.run(["docker", "compose", "-f", self.compose, "start", "odoo"], check=True, cwd=RACINE)
        if not self.attendre():
            raise RuntimeError("Odoo ne redémarre pas après la panne injectée")

    def desinstaller(self, module: str):
        """Simule « module requis désinstallé » en passant son état à `uninstalled`.

        ⚠️ Volontairement PAS `button_immediate_uninstall` : une désinstallation réelle recharge le registre,
        dépasse le délai RPC, laisse le module en état `to remove` et supprime des données (mesuré : 17.0,
        `crm` + `sale_crm`). Le step « le module Odoo … est installé » lit précisément cet état
        (`ir.module.module.state`) : le signal que le banc veut éprouver est le même. Limite assumée et dite
        dans le rapport — ce n'est pas une désinstallation physique."""
        modele = self.rpc().env["ir.module.module"]
        ids = modele.search([("name", "=", module), ("state", "=", "installed")])
        if ids:
            modele.write(ids, {"state": "uninstalled"})

    def installer(self, module: str):
        """Remet le module à `installed` (inverse de `desinstaller`)."""
        modele = self.rpc().env["ir.module.module"]
        ids = modele.search([("name", "=", module), ("state", "=", "uninstalled")])
        if ids:
            modele.write(ids, {"state": "installed"})


# ── Exécution d'un cas figé (Behave + Playwright réels) ──────────────────────────────────────

def executer_cas(slug: str, connexion: dict[str, str]) -> dict:
    """Rejoue UN cas figé par le vrai chemin de production : `BehaveRunner` + `Executor` + `derive_verdict`."""
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.execution.executor import Executor
    from testpilot.verdict.status import derive_verdict, statut_de_test

    dossier = Path(tempfile.mkdtemp(prefix="banc_cas_"))
    (dossier / f"{slug}.feature").write_text((CAS_FIGES / f"{slug}.feature").read_text(encoding="utf-8"),
                                             encoding="utf-8")
    (dossier / f"{slug}_steps.py").write_text((CAS_FIGES / f"{slug}_steps.py").read_text(encoding="utf-8"),
                                              encoding="utf-8")
    debut = time.time()
    runner = BehaveRunner(connection=connexion, connector_type="odoo", generated_dir=dossier)
    resultat = Executor(runner, max_retries=0).execute(slug)
    verdict = derive_verdict(resultat, connector_type="odoo")
    causes = sorted({s.cause_category for s in verdict.scenarios if s.cause_category})
    echecs = (resultat.real_run.failures if resultat.real_run else []) or []
    detail = (echecs[0].raw or "").strip()[-400:] if echecs else ""
    if not detail and not resultat.dry_run_passed:
        detail = f"dry-run non passé : {getattr(resultat.dry_run, 'raw_stdout', '')[-300:]}"
    return {"cas": slug, "statut": statut_de_test(verdict.execution_status, verdict.functional_status),
            "execution": verdict.execution_status, "fonctionnel": verdict.functional_status,
            "cause": ", ".join(causes), "duree": round(time.time() - debut, 1), "detail": detail}


def _connexion(instance: InstanceBanc, mot_de_passe: str | None = None) -> dict[str, str]:
    return {"ODOO_URL": instance.url, "ODOO_DB": instance.base, "ODOO_USER": instance.utilisateur,
            "ODOO_PASSWORD": mot_de_passe if mot_de_passe is not None else instance.mot_de_passe}


def mesurer_fige(instance: InstanceBanc, attendus: dict, executer=executer_cas, journal=print,
                 configs: set[str] | None = None) -> list[dict]:
    """Instance saine, puis chaque défaut, puis chaque panne — uniquement les paires DÉCRITES par les attendus.

    `configs` restreint la mesure (mise au point : `sain`, `defaut:total_faux`, `panne:odoo_arrete`) ; une mesure
    PUBLIÉE ne le passe jamais — les indicateurs d'une mesure partielle ne sont pas ceux du banc.
    """
    def voulu(config: str) -> bool:
        return configs is None or config in configs

    codes = list((attendus.get("defauts") or {}).keys())
    observations: list[dict] = []

    def lancer(config: str, cas: str, connexion: dict[str, str]):
        try:
            observation = executer(cas, connexion)
        except Exception as exc:  # le harnais lui-même est tombé : NON MESURÉ, jamais un succès
            observation = {"cas": cas, "statut": None, "raison": f"{type(exc).__name__}: {exc}"}
        observation["config"] = config
        observations.append(observation)
        journal(f"  {config:<34} {cas:<26} {observation.get('statut') or 'NON MESURÉ'}")

    journal("== Instance saine")
    instance.fixer_defauts(set(), codes)
    for cas in (attendus.get("sain") or {}) if voulu("sain") else ():
        lancer("sain", cas, _connexion(instance))

    for code, cas_map in (attendus.get("defauts") or {}).items():
        if not voulu(f"defaut:{code}"):
            continue
        journal(f"== Défaut {code}")
        instance.fixer_defauts({code}, codes)
        try:
            for cas in cas_map:
                lancer(f"defaut:{code}", cas, _connexion(instance))
        finally:
            instance.fixer_defauts(set(), codes)

    for code, panne in (attendus.get("pannes") or {}).items():
        config = f"panne:{code}"
        if not voulu(config):
            continue
        journal(f"== Panne {code}")
        if code == "odoo_arrete":
            instance.arreter()
            try:
                for cas in panne["cas"]:
                    lancer(config, cas, _connexion(instance))
            finally:
                instance.demarrer()
        elif code == "mauvais_mot_de_passe":
            for cas in panne["cas"]:
                lancer(config, cas, _connexion(instance, mot_de_passe="mot-de-passe-errone-du-banc"))
        elif code == "module_desinstalle":
            try:
                instance.desinstaller(panne["module"])
            except Exception as exc:  # la panne n'a pas pu être posée : NON MESURÉ, pas un succès
                for cas in panne["cas"]:
                    observations.append({"config": config, "cas": cas, "statut": None,
                                         "raison": f"panne non posée : {type(exc).__name__}: {exc}"})
                continue
            try:
                for cas in panne["cas"]:
                    lancer(config, cas, _connexion(instance))
            finally:
                instance.installer(panne["module"])
        else:
            for cas in panne["cas"]:
                observations.append({"config": config, "cas": cas, "statut": None,
                                     "raison": f"panne inconnue « {code} »"})
    return observations


# ── Contexte de la mesure ────────────────────────────────────────────────────────────────────

def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=RACINE, check=True).stdout.strip()
    except Exception:
        return "?"


def _image(version: str) -> str:
    cle = "ODOO_IMAGE_" + version.replace(".", "_")
    for ligne in IMAGES.read_text(encoding="utf-8").splitlines():
        if ligne.startswith(cle + "="):
            return ligne.split("=", 1)[1].strip()
    return "?"


def ecrire_sortie(version: str, mode: str, indicateurs: dict, observations: list[dict], contexte: dict,
                  dossier: Path = SORTIE) -> tuple[Path, Path]:
    dossier.mkdir(parents=True, exist_ok=True)
    base = dossier / f"banc-{version}-{contexte['date']}" if mode == "figé" else \
        dossier / f"banc-{version}-{contexte['date']}-{mode}"
    # ⚠️ `Path.with_suffix` prendrait « .0-2026-09-24 » (de « 17.0-2026-09-24 ») pour une extension et l'écraserait.
    md, js = Path(f"{base}.md"), Path(f"{base}.json")
    md.write_text(rendre_markdown(indicateurs, contexte, observations), encoding="utf-8")
    js.write_text(json.dumps({"contexte": contexte, "indicateurs": indicateurs, "observations": observations},
                             ensure_ascii=False, indent=2), encoding="utf-8")
    return md, js


# ── Point d'entrée ───────────────────────────────────────────────────────────────────────────

def _isoler_donnees() -> Path:
    """Une mesure ne modifie JAMAIS `data/` : dossier de données JETABLE, posé avant tout import de `testpilot`."""
    dossier = Path(os.environ.get("BANC_DATA_DIR") or tempfile.mkdtemp(prefix="banc_data_"))
    os.environ["TESTPILOT_DATA_DIR"] = str(dossier)
    os.environ.pop("ODOO_ENV", None)
    sys.path.insert(0, str(RACINE / "src"))
    sys.path.insert(0, str(RACINE))
    return dossier


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="17.0", choices=["16.0", "17.0", "18.0"])
    parser.add_argument("--mode", default="figé", choices=["figé", "fige", "génération", "generation"])
    parser.add_argument("--url", default=os.environ.get("BANC_URL", "http://127.0.0.1:18069"))
    parser.add_argument("--base", default="banc")
    parser.add_argument("--utilisateur", default="admin")
    parser.add_argument("--mot-de-passe", default="admin")
    parser.add_argument("--compose", default="compose.banc.yml")
    parser.add_argument("--plafond-cout", type=float, default=None,
                        help="mode génération : plafond de coût en dollars (obligatoire)")
    parser.add_argument("--sortie", type=Path, default=SORTIE)
    parser.add_argument("--configs", default=None,
                        help="MISE AU POINT seulement : configurations séparées par des virgules (sain, defaut:<code>, "
                             "panne:<code>) — une mesure publiée ne s'en sert jamais")
    args = parser.parse_args(argv)
    mode = "figé" if args.mode in ("figé", "fige") else "génération"

    if mode == "génération" and args.plafond_cout is None:
        parser.error("--plafond-cout est obligatoire en mode génération (coût LLM réel)")

    data_dir = _isoler_donnees()
    instance = InstanceBanc(args.url, args.base, args.utilisateur, args.mot_de_passe, args.compose)
    attendus = charger_attendus()
    erreurs = valider_attendus(attendus, {p.stem for p in CAS_FIGES.glob("*.feature")})
    if erreurs:
        print("Attendus invalides :\n  " + "\n  ".join(erreurs), file=sys.stderr)
        return 2
    if not instance.attendre(delai=60):
        print(f"Instance injoignable sur {args.url} — lance `scripts/banc_init.sh {args.version}`.", file=sys.stderr)
        return 2

    generation = None
    if mode == "figé":
        observations = mesurer_fige(instance, attendus,
                                    configs=set(args.configs.split(",")) if args.configs else None)
    else:
        from banc_generation import mesurer_generation  # noqa: E402  (importé au besoin : LLM)
        observations, generation = mesurer_generation(instance, attendus, args.version, args.plafond_cout)

    indicateurs = calculer_indicateurs(observations, attendus, generation)
    contexte = {"version": args.version, "mode": mode, "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "commit": _commit(), "image": _image(args.version), "data_dir": str(data_dir),
                "echantillon": {"cas_figes": len(list(CAS_FIGES.glob("*.feature"))),
                                "observations": len(observations)}}
    md, js = ecrire_sortie(args.version, mode, indicateurs, observations, contexte, args.sortie)
    print(f"\nRapport : {md}\nJSON    : {js}")
    code = code_de_sortie(indicateurs)
    print(f"I1 {_fmt(indicateurs['I1']['valeur'])} · I2 {_fmt(indicateurs['I2']['valeur'])} · "
          f"I5 {_fmt(indicateurs['I5']['valeur'])} → code de sortie {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
