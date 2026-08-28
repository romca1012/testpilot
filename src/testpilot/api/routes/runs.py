"""Routes du RUN — une campagne de N cas (décision `0022` n°8, incrément 1).

Un run REGROUPE des cas à jouer ensemble ; le résultat d'un cas dans un run est une exécution
rattachée. Créer un run ne lance RIEN (`0022` 8.c.1) : il naît en brouillon, le lancement est
un geste explicite (incrément 1b). Ici : créer / lister / détailler.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse

from testpilot.api import access, erreurs, schemas
from testpilot.api.deps import get_conn
from testpilot.api.services import attachment_service, campaign_service
from testpilot.store.repositories import CaseRepo, ProjectRepo, ResultRepo, RunRepo
from testpilot.verdict.status import MODE_AUTOMATIQUE, MODE_MANUELLE, MODES_EXECUTION, STATUTS_MANUELS

router = APIRouter(tags=["runs"])

def _summary(run: dict, case_count: int) -> schemas.RunSummary:
    return schemas.RunSummary(
        id=run["id"], project_id=run["project_id"], name=run["name"], status=run["status"],
        selection_mode=run["selection_mode"], mode=run.get("mode", MODE_AUTOMATIQUE),
        case_count=case_count,
        tested_count=run.get("tested_count", 0),
        manuel_count=run.get("manuel_count", 0),
        is_archived=bool(run.get("is_archived")),
        created_at=run.get("created_at", ""))


@router.post("/api/projects/{project_id}/runs", response_model=schemas.RunSummary, status_code=201,
            dependencies=[Depends(access.require_project_access)])
def create_run(project_id: int, body: schemas.RunIn, conn=Depends(get_conn)):
    """Crée une campagne en BROUILLON. Le mode de SÉLECTION `all` est vivant (les cas du projet) ;
    `frozen` fige la sélection fournie. Le filtrage dynamique n'est pas géré (422).

    ⚠️ Le MODE D'EXÉCUTION (`manuelle` / `automatique`) se choisit ICI, à la création, et ne se
    devine pas plus tard : c'est lui qui décide si la campagne se lance ou se saisit.
    """
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="le nom de l'exécution est requis")
    if body.selection_mode not in ("all", "frozen"):
        raise HTTPException(status_code=422,
                            detail="le filtrage dynamique n'est pas encore disponible — "
                                   "choisissez « tous les cas » ou une sélection figée")
    if body.selection_mode == "frozen" and not body.case_ids:
        raise HTTPException(status_code=422,
                            detail="une sélection figée doit contenir au moins un cas")
    if body.mode not in MODES_EXECUTION:
        raise HTTPException(status_code=422,
                            detail=f"mode d'exécution inconnu : « {body.mode} ». Valeurs "
                                   f"possibles : {', '.join(MODES_EXECUTION)}.")
    repo = RunRepo(conn)
    run_id = repo.create(project_id=project_id, name=body.name.strip(),
                         description=body.description, refs=body.refs,
                         selection_mode=body.selection_mode, mode=body.mode,
                         case_ids=body.case_ids)
    return _summary(repo.get(run_id), len(repo.case_ids(run_id)))


@router.get("/api/projects/{project_id}/runs", response_model=list[schemas.RunSummary],
           dependencies=[Depends(access.require_project_access)])
def list_runs(project_id: int, conn=Depends(get_conn)):
    if ProjectRepo(conn).get(project_id) is None:
        raise HTTPException(status_code=404, detail=f"projet {project_id} introuvable")
    repo = RunRepo(conn)
    out = []
    for run in repo.list_for_project(project_id):
        count = run["frozen_count"] if run["selection_mode"] == "frozen" else len(repo.case_ids(run["id"]))
        out.append(_summary(run, count))
    return out


@router.post("/api/runs/{run_id}/launch", response_model=schemas.RunSummary, status_code=202,
            dependencies=[Depends(access.require_project_access_depuis(
                "run_id", access.project_id_depuis_run))])
def launch_run(run_id: int, background: BackgroundTasks, request: Request, conn=Depends(get_conn)):
    """LANCE la campagne : exécute ses cas EN SÉQUENCE (tâche de fond).

    Geste explicite (`0022` 8.c.1) — créer un run ne lance rien. Un run vide est refusé : il
    finirait « terminé » sans avoir rien testé, un succès trompeur.
    """
    # ⚠️ Résolu SYNCHRONE, avant `background.add_task` (migration 32) — une fois en tâche de
    # fond, il n'y a plus de `Request` à lire.
    try:
        params = campaign_service.start_campaign(conn, run_id,
                                                  triggered_by=access.utilisateur_de(request))
    except campaign_service.CampaignError as err:
        raise erreurs.depuis_service(err.code, err.detail)
    background.add_task(campaign_service.run_campaign, **params)
    repo = RunRepo(conn)
    return _summary(repo.get(run_id), len(repo.case_ids(run_id)))


@router.post("/api/runs/{run_id}/archive", response_model=schemas.RunSummary,
            dependencies=[Depends(access.require_project_access_depuis(
                "run_id", access.project_id_depuis_run))])
def archive_run(run_id: int, body: schemas.RunArchiveIn, conn=Depends(get_conn)):
    """Clôt (ou rouvre) une campagne. Archivée = LECTURE SEULE : on ne la relance plus.

    Réversible : une clôture par erreur ne doit pas être irrattrapable. Rien n'est effacé —
    archivage ≠ suppression (§2.10).
    """
    repo = RunRepo(conn)
    if repo.get(run_id) is None:
        raise HTTPException(status_code=404, detail=f"exécution {run_id} introuvable")
    repo.archive(run_id, body.archived)
    return _summary(repo.get(run_id), len(repo.case_ids(run_id)))


@router.get("/api/runs/{run_id}", response_model=schemas.RunDetailOut,
           dependencies=[Depends(access.require_project_access_depuis(
               "run_id", access.project_id_depuis_run))])
def get_run(run_id: int, conn=Depends(get_conn)):
    """Le run + ses cas, chacun avec son résultat DANS ce run (ou None = non testé)."""
    repo = RunRepo(conn)
    run = repo.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"exécution {run_id} introuvable")
    from testpilot.verdict.status import statut_de_test

    cases = []
    for c in repo.cases_with_results(run_id):
        res = c["result"] or {}
        ex, fo = res.get("execution_status"), res.get("functional_status")
        manuel = res.get("statut_manuel", "") or ""
        cases.append(schemas.RunCaseResult(
            id=c["id"], title=c["title"], execution_status=ex, functional_status=fo,
            execution_id=res.get("execution_id"),
            result_mode=res.get("mode", "") or "",
            statut_manuel=manuel,
            comment=res.get("comment", "") or "",
            created_by=res.get("created_by", "") or "",
            result_at=res.get("created_at", "") or "",
            # Un cas SANS résultat dans ce run est « non testé » — même règle que partout
            # ailleurs, calculée au même endroit. Un statut saisi À LA MAIN court-circuite la
            # dérivation : c'est le seul moyen d'intégrer un constat humain sans inventer de mesure.
            statut=statut_de_test(ex, fo, manuel)))
    cibles = repo.cibles_du_run(run_id)
    return schemas.RunDetailOut(
        run=_summary(run, len(cases)), description=run.get("description", ""),
        refs=run.get("refs", ""), cases=cases,
        target_url=cibles[0]["target_url"] if cibles else "",
        target_database=cibles[0]["target_database"] if cibles else "",
        target_mixed=len(cibles) > 1,
        statuts_manuels=list(STATUTS_MANUELS))


# ── Exécution MANUELLE d'un cas : la saisie de son résultat (2026-08-04) ──────────────────────
# Le flux de TestRail : on ouvre une campagne, on choisit un cas, on saisit un statut et un
# commentaire. Ici comme là-bas, **la saisie n'existe que dans une campagne** : un résultat isolé
# ne répondrait à aucune question — « ce cas passe » n'a de sens que dans un contexte de test.

def _cas_de_campagne(conn, run_id: int, case_id: int) -> dict:
    """Vérifie qu'on peut écrire un résultat ICI, et rend le run. Refuse, dans cet ordre :
    campagne inconnue, campagne archivée (lecture seule), cas absent de la campagne.

    ⚠️ L'appartenance se vérifie via `RunRepo.case_ids`, jamais par une requête directe sur
    `test_run_case` : c'est elle qui porte l'invariant de suppression douce. Un cas à la corbeille
    ne fait plus partie d'aucune campagne, et on ne doit pas pouvoir lui écrire un résultat.
    """
    runs = RunRepo(conn)
    run = runs.get(run_id)
    if run is None:
        raise erreurs.ErreurMetier("introuvable", f"campagne {run_id} introuvable")
    if run.get("is_archived"):
        raise erreurs.ErreurMetier(
            "campagne_archivee",
            "cette campagne est clôturée : rouvrez-la pour y saisir un résultat")
    if case_id not in runs.case_ids(run_id):
        raise erreurs.ErreurMetier(
            "cas_hors_campagne",
            f"le cas {case_id} ne fait pas partie de la campagne {run_id}")
    return run


def _result_out(ligne: dict, pieces: list[dict] | None = None) -> schemas.ResultOut:
    from testpilot.verdict.status import statut_de_test

    return schemas.ResultOut(
        attachments=[schemas.AttachmentOut(**{c: p[c] for c in
                                              ("id", "filename", "content_type", "size_bytes")})
                     for p in (pieces or [])],
        id=ligne["id"], mode=ligne["mode"],
        statut=statut_de_test(ligne.get("execution_status"), ligne.get("functional_status"),
                              ligne.get("statut_manuel") or ""),
        statut_manuel=ligne.get("statut_manuel", "") or "",
        comment=ligne.get("comment", "") or "",
        created_by=ligne.get("created_by", "") or "",
        created_at=ligne.get("created_at", "") or "",
        execution_id=ligne.get("execution_id"),
        execution_status=ligne.get("execution_status"),
        functional_status=ligne.get("functional_status"))


@router.get("/api/runs/{run_id}/cases/{case_id}/results",
            response_model=list[schemas.ResultOut],
            dependencies=[Depends(access.require_project_access_depuis(
                "run_id", access.project_id_depuis_run))])
def list_results(run_id: int, case_id: int, conn=Depends(get_conn)):
    """L'HISTORIQUE des résultats d'un cas dans cette campagne, du plus ancien au plus récent.

    Corriger un résultat, c'est en ajouter un autre : cette liste est ce qui rend la correction
    honnête plutôt que silencieuse.
    """
    _cas_de_campagne(conn, run_id, case_id)
    return _avec_pieces(conn, ResultRepo(conn).historique(run_id, case_id))


def _avec_pieces(conn, lignes: list[dict]) -> list[schemas.ResultOut]:
    """Des résultats AVEC leurs pièces jointes, en **une** requête de plus — jamais une par ligne.

    Un historique de dix corrections ferait sinon dix allers-retours pour une liste le plus souvent
    vide : la pièce jointe est optionnelle, et son coût d'affichage doit l'être aussi.
    """
    pieces = ResultRepo(conn).pieces_jointes_de([l["id"] for l in lignes])
    return [_result_out(l, pieces.get(l["id"])) for l in lignes]


@router.post("/api/runs/{run_id}/cases/{case_id}/results",
             response_model=schemas.ResultOut, status_code=201,
             dependencies=[Depends(access.require_project_access_depuis(
                 "run_id", access.project_id_depuis_run))])
def add_result(run_id: int, case_id: int, body: schemas.ResultIn, request: Request,
               conn=Depends(get_conn)):
    """Inscrit le résultat d'un cas JOUÉ À LA MAIN par un humain.

    ⚠️ **Il sera étiqueté « Manuelle » partout, sans exception.** C'est la condition à laquelle
    l'exécution manuelle n'affaiblit pas la promesse du produit : on ne dit jamais « ça marche »
    sans pouvoir dire COMMENT on l'a su — mais un humain qui a réellement suivi les étapes contre
    la vraie application a exécuté le test, et son constat vaut, à condition qu'on voie par quel
    moyen il a été obtenu.

    ⚠️ **Seule une campagne MANUELLE accepte une saisie.** Le mode se choisit à la création ;
    l'écran d'une campagne automatique ne propose donc pas ce geste, et l'API le refuse aussi —
    sinon la règle ne vivrait que dans le navigateur.

    L'auteur est le nom de session (une signature déclarée, pas une identité vérifiée).
    """
    run = _cas_de_campagne(conn, run_id, case_id)
    if run.get("mode", MODE_AUTOMATIQUE) != MODE_MANUELLE:
        raise erreurs.ErreurMetier(
            "campagne_automatique",
            f"la campagne {run_id} est automatique : ses résultats viennent de la machine. "
            "Créez une campagne manuelle pour saisir des résultats à la main.")
    if body.statut not in STATUTS_MANUELS:
        raise erreurs.ErreurMetier(
            "statut_invalide",
            f"« {body.statut} » ne peut pas être saisi. Valeurs possibles : "
            f"{', '.join(STATUTS_MANUELS)}. « untested » n'en fait pas partie : c'est "
            "l'absence de résultat, pas un choix.")

    resultat_id = ResultRepo(conn).saisir(
        run_id=run_id, case_id=case_id, statut=body.statut, comment=body.comment,
        created_by=access.utilisateur_de(request))
    ligne = ResultRepo(conn).dernier(run_id, case_id)
    return _result_out(ligne if ligne and ligne["id"] == resultat_id else {"id": resultat_id,
                       "mode": MODE_MANUELLE, "statut_manuel": body.statut})


# ── Les PIÈCES JOINTES d'un résultat (2026-08-05) ────────────────────────────────────────────
# Un résultat manuel n'a pas de trace machine : la capture d'écran est ce qui atteste qu'il a
# réellement été joué. Elle est **toujours optionnelle** — la saisie d'un résultat n'en dépend
# pas, et c'est pourquoi elle s'envoie APRÈS lui plutôt que dans la même requête : rendre la
# saisie multipart aurait fait dépendre le geste central d'un formulaire de fichier.
#
# ⚠️ Les règles de sécurité (liste blanche, plafonds, nom généré) vivent dans
# `attachment_service` — ici il n'y a que la porte HTTP.

def _resultat_ouvert(conn, result_id: int) -> dict:
    """Le résultat, à condition qu'on ait le droit d'y écrire. Refuse : inconnu, campagne close.

    ⚠️ La campagne ARCHIVÉE est en lecture seule — la même règle que pour la saisie. Sans ce
    refus, on pourrait continuer d'enrichir la preuve d'une campagne clôturée, c'est-à-dire
    modifier après coup ce qu'un rapport signé donne à lire.
    """
    resultat = ResultRepo(conn).get(result_id)
    if resultat is None:
        raise erreurs.ErreurMetier("introuvable", f"résultat {result_id} introuvable")
    run = RunRepo(conn).get(resultat["run_id"])
    if run and run.get("is_archived"):
        raise erreurs.ErreurMetier(
            "campagne_archivee",
            "cette campagne est clôturée : rouvrez-la pour y joindre un fichier")
    return resultat


@router.post("/api/results/{result_id}/attachments",
             response_model=list[schemas.AttachmentOut], status_code=201,
             dependencies=[Depends(access.require_project_access_depuis(
                 "result_id", access.project_id_depuis_result))])
async def add_attachments(result_id: int, files: list[UploadFile] = File(...),
                          conn=Depends(get_conn)):
    """Joint un ou plusieurs fichiers à un résultat déjà inscrit.

    Les fichiers sont traités DANS L'ORDRE et le premier refus arrête tout : mieux vaut un refus
    net qu'un « 3 sur 5 acceptés » que personne ne lit. Les fichiers déjà écrits avant le refus
    restent — ils sont valides, et les redemander à l'utilisateur serait une punition gratuite.
    """
    _resultat_ouvert(conn, result_id)
    return [schemas.AttachmentOut(**await attachment_service.enregistrer(conn, result_id, f))
            for f in files]


@router.delete("/api/results/{result_id}/attachments/{attachment_id}", status_code=204,
               dependencies=[Depends(access.require_project_role_depuis(
                   "result_id", access.project_id_depuis_result, access.ROLE_ADMIN))])
def delete_attachment(result_id: int, attachment_id: int, conn=Depends(get_conn)):
    """Retire une pièce jointe d'un résultat, sans modifier ni supprimer le résultat lui-même."""
    _resultat_ouvert(conn, result_id)
    attachment_service.supprimer(conn, result_id, attachment_id)
    return Response(status_code=204)


@router.get("/api/results/{result_id}/attachments/{attachment_id}",
           dependencies=[Depends(access.require_project_access_depuis(
               "result_id", access.project_id_depuis_result))])
def get_attachment(result_id: int, attachment_id: int, conn=Depends(get_conn)):
    """Le CONTENU d'une pièce jointe — par identifiants NUMÉRIQUES, jamais par nom de fichier.

    ⚠️ **Trois gardes, et il en faut trois** (le modèle des artefacts d'exécution, durci) :

    1. **Rien venu du client ne touche un chemin.** Les deux identifiants sont des entiers (FastAPI
       refuse le reste avant d'entrer ici) ; le nom sur disque est LU EN BASE. Un `../../.env` n'a
       aucune porte par où passer — il n'y a pas de nom de fichier dans cette URL.
    2. **L'appartenance est vérifiée** : la pièce jointe doit être CELLE de ce résultat (clause
       SQL, pas convention). Une pièce d'un autre résultat rend 404, jamais son contenu.
    3. **Le dossier est ITÉRÉ et le nom comparé**, comme pour les artefacts : même si une valeur
       aberrante entrait un jour en base, elle ne pourrait pas désigner un fichier hors du dossier.

    Et à la sortie : `nosniff` (le navigateur ne doit pas ré-interpréter le type) et
    `Content-Disposition: attachment` par défaut. Seules les IMAGES de la liste blanche s'affichent
    en ligne — `svg` et `html` n'y sont pas, précisément parce qu'ils exécuteraient du script dans
    l'origine de TestPilot.
    """
    piece = ResultRepo(conn).piece_jointe(result_id, attachment_id)
    if piece is None:
        raise HTTPException(status_code=404, detail="pièce jointe introuvable")
    dossier = Path((piece["attachments_path"] or "").strip() or ".")
    media, est_image = attachment_service.type_servi(piece["stored_name"])
    for f in dossier.iterdir() if dossier.is_dir() else ():
        if f.is_file() and f.name == piece["stored_name"]:
            nom = quote(piece["filename"] or f.name)
            return FileResponse(f, media_type=media, headers={
                "Content-Disposition": f"{'inline' if est_image else 'attachment'};"
                                       f" filename*=UTF-8''{nom}",
                "X-Content-Type-Options": "nosniff",
            })
    raise HTTPException(status_code=404,
                        detail="le fichier de cette pièce jointe est introuvable sur le disque")


# ── UN CAS DANS UNE CAMPAGNE : l'objet « test » (2026-08-05) ──────────────────────────────────
# Ce que TestRail nomme `T…`, par opposition au cas `C…`. La notion existait déjà en base (le
# couple campagne × cas du registre) ; il lui manquait une adresse. Sans elle, cliquer un cas dans
# une campagne menait au rapport technique d'UNE exécution ou à la fiche du cas — deux écrans qui
# ne répondent pas à la question posée : « où en est CE cas, ICI ? ».

def _test_de_campagne(conn, run_id: int, case_id: int) -> tuple[dict, list[int]]:
    """Le run + l'ordre de ses cas, après avoir vérifié que le cas y figure.

    ⚠️ Distinct de `_cas_de_campagne` : une campagne ARCHIVÉE se lit très bien. Refuser la lecture
    d'un test clôturé rendrait inconsultable exactement ce qu'on archive pour garder.
    """
    runs = RunRepo(conn)
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"exécution {run_id} introuvable")
    ids = runs.case_ids(run_id)
    if case_id not in ids:
        raise HTTPException(
            status_code=404,
            detail=f"le cas {case_id} ne fait pas partie de l'exécution {run_id}")
    return run, ids


def _ailleurs(ligne: dict) -> schemas.ResultAilleurs:
    from testpilot.verdict.status import statut_de_test

    return schemas.ResultAilleurs(
        run_id=ligne["run_id"], run_name=ligne.get("run_name", "") or "",
        statut=statut_de_test(ligne.get("execution_status"), ligne.get("functional_status"),
                              ligne.get("statut_manuel") or ""),
        mode=ligne["mode"], created_by=ligne.get("created_by", "") or "",
        created_at=ligne.get("created_at", "") or "")


@router.get("/api/runs/{run_id}/tests/{case_id}", response_model=schemas.TestDansRunOut,
           dependencies=[Depends(access.require_project_access_depuis(
               "run_id", access.project_id_depuis_run))])
def get_test(run_id: int, case_id: int, conn=Depends(get_conn)):
    """« Ce cas, dans cette campagne » : ses métadonnées, tous ses résultats ici, ses voisins de
    campagne, et son parcours dans les AUTRES campagnes.

    Une seule réponse pour tout l'écran : ses trois onglets se lisent sans second aller-retour, et
    les flèches précédent/suivant n'obligent pas à charger les 500 cas de la campagne.
    """
    from testpilot.verdict.status import STATUT_UNTESTED

    run, ids = _test_de_campagne(conn, run_id, case_id)
    cas = CaseRepo(conn).get(case_id)
    if cas is None:
        raise HTTPException(status_code=404, detail=f"cas {case_id} introuvable")

    resultats = _avec_pieces(conn, ResultRepo(conn).historique(run_id, case_id))
    i = ids.index(case_id)
    return schemas.TestDansRunOut(
        run_id=run_id, run_name=run["name"], run_archived=bool(run.get("is_archived")),
        run_mode=run.get("mode", MODE_AUTOMATIQUE),
        case_id=case_id, title=cas["title"],
        type=cas.get("type", "fonctionnel"), etat=cas.get("etat", "new"),
        priority=cas.get("priority", "medium"), estimate=cas.get("estimate", "") or "",
        refs=cas.get("refs", "") or "",
        # Le dernier inscrit FAIT FOI — même règle que partout, et déjà calculée par `_result_out`.
        statut=resultats[-1].statut if resultats else STATUT_UNTESTED,
        results=resultats,
        prev_case_id=ids[i - 1] if i > 0 else None,
        next_case_id=ids[i + 1] if i < len(ids) - 1 else None,
        historique_du_cas=[_ailleurs(r) for r in ResultRepo(conn).historique_du_cas(case_id)])


@router.get("/api/runs/{run_id}/activite", response_model=schemas.RunActiviteOut,
           dependencies=[Depends(access.require_project_access_depuis(
               "run_id", access.project_id_depuis_run))])
def get_activite(run_id: int, conn=Depends(get_conn)):
    """Le fil chronologique d'une campagne — et, par la même occasion, sa progression.

    Les deux écrans (Activité, Progression) lisent CETTE réponse : la progression n'est que
    l'activité comptée autrement. Deux routes recompteraient la même chose de deux façons.
    """
    from testpilot.verdict.status import statut_de_test

    repo = RunRepo(conn)
    run = repo.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"exécution {run_id} introuvable")
    events = [
        schemas.ActiviteOut(
            case_id=l["case_id"], case_title=l.get("case_title", "") or "",
            statut=statut_de_test(l.get("execution_status"), l.get("functional_status"),
                                  l.get("statut_manuel") or ""),
            mode=l["mode"], created_by=l.get("created_by", "") or "",
            created_at=l.get("created_at", "") or "")
        for l in ResultRepo(conn).activite_du_run(run_id)]
    return schemas.RunActiviteOut(run_id=run_id, run_name=run["name"],
                                  case_count=len(repo.case_ids(run_id)), events=events)
