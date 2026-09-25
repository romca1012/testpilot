"""Mode « génération » du banc de mesure (lot 04) — mesure l'AGENT (I3, I4, I6). ⚠️ APPELLE UN LLM (coût réel).

Appelé par ``banc_mesure.py --mode génération --plafond-cout <dollars>`` ; jamais par la CI (le workflow du banc
n'utilise que le mode figé, coût nul).

Méthode — réutiliser l'outillage de campagne déjà éprouvé plutôt qu'en écrire un second :

1. un dossier de DONNÉES JETABLE reçoit le projet « Banc Odoo <version> » (``banc_projet``), son annuaire
   (exploration déterministe, sans LLM) et UN cas par spec de ``specs/banc/*.md`` — le document métier
   (titre, étapes, résultat attendu) est lu DÉTERMINISTEMENT dans la spec, sans appel LLM ;
2. ``scripts/qualify_campaign_pilot.py`` est lancé en sous-processus sur ce dossier
   (``TESTPILOT_CAMPAIGN_SOURCE_DATA``) : génération indépendante par cas, exécution physique UNIQUE (aucun rejeu,
   aucune réparation), plafond de coût réel (arrêt AVANT le premier essai qui le dépasserait, code de sortie 3) ;
3. ``campagne.json`` est relu et réduit à ``{generes, sans_erreur_technique, verdict_exploitable, cout_total,
   nouveaux_cas}``.

L'instance mesurée est l'instance SAINE (aucun défaut actif) : un cas généré qui n'y sort pas ``passed`` est un
défaut de l'agent ou du verdict, pas de l'application.

⚠️ Ce mode n'a été validé que sur des résultats simulés dans le lot 04 : il n'a PAS été exécuté pour de vrai (coût
LLM, à autoriser explicitement par le porteur — voir le rapport).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SPECS = RACINE / "specs" / "banc"
CAMPAGNE = RACINE / "scripts" / "qualify_campaign_pilot.py"
MODULE_DU_BANC = "Banc de mesure"


# ── Le document métier d'une spec (déterministe : aucun LLM) ─────────────────────────────────

def metier_depuis_spec(texte: str) -> dict:
    """`{title, preconditions, steps, expected_result}` lus dans une spec `specs/banc/*.md`."""
    titre = re.search(r"^#\s+Spécification\s+—\s+(.+?)(?:\s+\(banc de mesure Odoo\))?\s*$", texte, re.M)
    if not titre:
        raise ValueError("spec sans titre « # Spécification — … »")

    def section(nom: str) -> str:
        m = re.search(rf"^##\s+{re.escape(nom)}\s*\n(.*?)(?=^##\s|\Z)", texte, re.M | re.S)
        return m.group(1).strip() if m else ""

    etapes = [re.sub(r"^\d+\.\s*", "", ligne).strip()
              for ligne in section("Parcours").splitlines() if re.match(r"^\d+\.\s", ligne)]
    critere = section("Critère de réussite")
    if not etapes or not critere:
        raise ValueError(f"spec « {titre.group(1)} » : parcours ou critère de réussite manquant")
    return {"title": titre.group(1).strip(), "preconditions": section("Contexte technique"),
            "steps": etapes, "expected_result": critere}


# ── Réduction de campagne.json aux indicateurs de génération ─────────────────────────────────

def statistiques_depuis_campagne(rapports: list[dict], arret: dict | None = None) -> dict:
    """Réduit les essais d'une campagne à ce dont I3, I4 et I6 ont besoin.

    - `generes` : essais LANCÉS (un cas dont la génération échoue compte contre l'agent, pas hors échantillon) ;
    - `sans_erreur_technique` : essais dont l'exécution physique a eu lieu ET n'est pas `technical_error` ;
    - `verdict_exploitable` : essais `conforme` ou `non_conforme` (statut de lecture `passed`/`failed`) ;
    - `cout_total` : somme des `generation.cost_usd` (dollars) ; `nouveaux_cas` : un cas par essai.
    """
    generes = len(rapports)
    sans_erreur = exploitable = 0
    cout = 0.0
    for r in rapports:
        gen = r.get("generation") or {}
        exe = r.get("execution") or {}
        cout += float(gen.get("cost_usd") or 0.0)
        if exe and exe.get("execution_status") not in (None, "technical_error", "not_executed"):
            sans_erreur += 1
        if exe and exe.get("functional_status") in ("conforme", "non_conforme"):
            exploitable += 1
    return {"generes": generes, "sans_erreur_technique": sans_erreur, "verdict_exploitable": exploitable,
            "cout_total": round(cout, 6), "nouveaux_cas": generes,
            # Campagne INCOMPLÈTE (plafond de coût, crédits épuisés) : les indicateurs portent sur les essais lancés
            # seulement et ne sont jamais présentés comme ceux du corpus entier.
            "interrompue": (arret or {}).get("raison", "")}


def observations_depuis_campagne(rapports: list[dict], slug_de_cas: dict[int, str]) -> list[dict]:
    """Une observation par essai (configuration `generation`) : statut de lecture de l'exécution unique."""
    from testpilot.verdict.status import statut_de_test

    out = []
    for r in rapports:
        slug = slug_de_cas.get(r.get("case_id"), str(r.get("case_id")))
        exe = r.get("execution")
        if not exe:
            out.append({"config": "generation", "cas": slug, "statut": None,
                        "raison": r.get("generation_error") or "cas non généré ou dry-run non passé"})
            continue
        out.append({"config": "generation", "cas": slug,
                    "statut": statut_de_test(exe["execution_status"], exe["functional_status"]),
                    "execution": exe["execution_status"], "fonctionnel": exe["functional_status"]})
    return out


# ── Préparation des données et lancement ─────────────────────────────────────────────────────

def preparer_donnees(version: str, url: str, data_dir: Path, secret_key: str) -> tuple[int, dict[int, str]]:
    """Projet du banc + annuaire + un cas par spec dans `data_dir`. Rend (id du projet, {id de cas: slug})."""
    os.environ["TESTPILOT_DATA_DIR"] = str(data_dir)
    os.environ["TESTPILOT_SECRET_KEY"] = secret_key
    sys.path.insert(0, str(RACINE / "src"))
    import banc_projet
    from testpilot import config
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ModuleRepo

    conn = get_initialized_db(Path(config.DB_PATH))
    project_id = banc_projet.assurer_le_projet(conn, version, url)
    banc_projet.explorer(conn, project_id)
    modules = ModuleRepo(conn)
    module = next((m for m in modules.list_for_project(project_id) if m["name"] == MODULE_DU_BANC), None)
    module_id = module["id"] if module else modules.create(project_id=project_id, name=MODULE_DU_BANC)
    cas = CaseRepo(conn)
    slug_de_cas: dict[int, str] = {}
    for chemin in sorted(SPECS.glob("*.md")):
        metier = metier_depuis_spec(chemin.read_text(encoding="utf-8"))
        cid = cas.create_manual(
            module_id=module_id, title=metier["title"], preconditions=metier["preconditions"],
            test_steps=json.dumps(metier["steps"], ensure_ascii=False),
            expected_result=metier["expected_result"], author="banc")
        slug_de_cas[cid] = chemin.stem
    return project_id, slug_de_cas


def mesurer_generation(instance, attendus: dict, version: str, plafond_cout: float):
    """Génère puis exécute un cas par spec ; rend `(observations, statistiques)`.

    Lève `SystemExit(3)` (campagne INCOMPLÈTE) si le plafond de coût a arrêté la campagne : jamais confondue avec
    une campagne terminée — les statistiques partielles sont tout de même publiées par l'appelant.
    """
    import tempfile
    from cryptography.fernet import Fernet

    data_dir = Path(os.environ.get("BANC_DATA_DIR") or tempfile.mkdtemp(prefix="banc_gen_data_"))
    cle = os.environ.get("TESTPILOT_SECRET_KEY") or Fernet.generate_key().decode()
    project_id, slug_de_cas = preparer_donnees(version, instance.url, data_dir, cle)
    sortie = f"banc-{version}-generation"
    commande = [sys.executable, str(CAMPAGNE), "--out", sortie, "--project-id", str(project_id),
                "--cases", ",".join(str(c) for c in slug_de_cas), "--iterations", "1",
                "--expected-base-url", instance.url, "--max-cost-usd", str(plafond_cout)]
    env = {**os.environ, "TESTPILOT_CAMPAIGN_SOURCE_DATA": str(data_dir), "TESTPILOT_SECRET_KEY": cle}
    env.pop("TESTPILOT_DATA_DIR", None)
    fichier = RACINE / ".local-preview" / "qualification" / sortie / "campagne.json"
    # Un run précédent laisse ses résultats dans ce dossier (réutilisé) : un `arret_plafond.json` périmé ferait afficher
    # « INCOMPLÈTE » à tort, un `campagne.json` périmé ferait passer un plantage pour un run complet.
    for reste in (fichier, fichier.parent / "arret_plafond.json"):
        reste.unlink(missing_ok=True)
    proc = subprocess.run(commande, cwd=RACINE, env=env)
    rapports = json.loads(fichier.read_text(encoding="utf-8")) if fichier.exists() else []
    arret_fichier = fichier.parent / "arret_plafond.json"
    arret = json.loads(arret_fichier.read_text(encoding="utf-8")) if arret_fichier.exists() else None
    if proc.returncode not in (0, 3):
        raise RuntimeError(f"la campagne de génération a échoué (code {proc.returncode})")
    stats = statistiques_depuis_campagne(rapports, arret)
    if plafond_cout and stats["cout_total"] > plafond_cout:  # dépassement d'UN essai au plus : dit, jamais tu
        stats["plafond_depasse_de"] = round(stats["cout_total"] - plafond_cout, 6)
    return observations_depuis_campagne(rapports, slug_de_cas), stats
