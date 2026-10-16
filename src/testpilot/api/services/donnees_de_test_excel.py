"""Le tableau des données de test en Excel (lot PT-02a) : l'exporter, et l'importer en le COMPLÉTANT.

Le format est celui de l'écran (A54, 2026-10-16, comme le « Data Table » de QTP/UFT) : case A1 « Ligne », puis une VARIABLE
par colonne ; une ligne par jeu de données (« Par défaut » d'abord), une valeur par case. L'export sert de modèle à remplir.
Un fichier à l'ancien format (A1 « Variable », une variable par ligne, un jeu par colonne) est toujours accepté à l'import.

Décision du porteur (2026-10-14, A37) : l'import COMPLÈTE le tableau — il ajoute les variables et les jeux qui manquent et
met à jour les cases qu'il remplit ; une case vide du fichier ne vide rien, rien n'est supprimé. L'écran montre ce qui va
changer avant d'enregistrer (`comparer`), et `appliquer` refait la même comparaison : rien n'est écrit si le fichier a une
erreur, nommée par sa case.

Les noms et les valeurs passent par `parametres/resolution.py` — les règles mêmes du remplacement : un fichier ne peut pas
faire entrer une valeur qu'un test ne saurait recevoir. Une case calculée par une formule vaut la valeur que le classeur a
enregistrée (jamais recalculée ici) ; sans valeur enregistrée, elle compte comme vide.
"""
from __future__ import annotations

import datetime as dt
import io
import unicodedata
import zipfile
from dataclasses import dataclass, field

from testpilot.api.services.excel_import import FichierExcelInvalide, lire_classeur
from testpilot.parametres import resolution
from testpilot.store.repositories import (
    _JEUX_MAX, _NOM_DE_JEU_MAX, _VARIABLES_MAX, NOM_DU_JEU_PAR_DEFAUT, DonneeDeTestInvalide, TestDataRepo, _key,
)

ENTETE = "Ligne"            # A54 : une ligne par jeu de données, une variable par colonne
ENTETE_ANCIEN = "Variable"  # avant A54 : une variable par ligne, un jeu par colonne — toujours lu
TAILLE_MAX = 2 * 1024 * 1024   # un tableau de 200 variables × 50 jeux tient très largement
DECOMPRESSE_MAX = 50 * 1024 * 1024
LIGNES_PARCOURUES = 5000   # au-delà, même vides, les lignes ne sont pas lues


@dataclass
class Lecture:
    variables: list[str] = field(default_factory=list)
    jeux: list[str] = field(default_factory=list)
    valeurs: dict[tuple[str, str], str] = field(default_factory=dict)   # (variable, jeu) → valeur ; cases vides absentes
    erreurs: list[str] = field(default_factory=list)


def _colonne(index: int) -> str:
    """0 → A, 25 → Z, 26 → AA — pour nommer une case comme Excel la nomme."""
    lettres = ""
    index += 1
    while index:
        index, reste = divmod(index - 1, 26)
        lettres = chr(65 + reste) + lettres
    return lettres


class _CaseInvalide(ValueError):
    """Une case que l'import refuse en la nommant (erreur Excel, nombre trop long)."""


def _texte(case) -> str:
    """Le texte d'une case. Un nombre entier s'écrit sans « .0 » ; une date sans heure, en AAAA-MM-JJ. Une case en ERREUR
    (#N/A, #DIV/0!…) est refusée : un test saisirait sinon « #N/A » dans l'application. Un nombre de 15 chiffres ou plus
    aussi : Excel l'a déjà arrondi, la valeur lue ne serait pas celle tapée — il s'écrit alors comme du texte."""
    valeur = getattr(case, "value", case)
    if getattr(case, "data_type", None) == "e":
        raise _CaseInvalide(f"la case est en erreur dans le classeur ({valeur})")
    if valeur is None:
        return ""
    if isinstance(valeur, bool):
        return "VRAI" if valeur else "FAUX"
    if isinstance(valeur, (int, float)) and abs(valeur) >= 1e15:
        raise _CaseInvalide("nombre trop long : écrivez-le comme du texte (précédé d'une apostrophe)")
    if isinstance(valeur, float) and valeur.is_integer():
        return str(int(valeur))
    if isinstance(valeur, dt.datetime):
        return valeur.date().isoformat() if valeur.time() == dt.time() else valeur.isoformat(sep=" ")
    if isinstance(valeur, (dt.date, dt.time)):
        return valeur.isoformat()
    return str(valeur)


def _nom(texte: str) -> str:
    """Un nom tel qu'on le compare : espaces réduits, forme Unicode composée (un « é » venu d'un Mac ou d'un copier-coller
    peut être écrit en deux caractères — sans cela, « Par défaut » créerait un second jeu qui s'affiche à l'identique)."""
    return unicodedata.normalize("NFC", " ".join(texte.split()))


def _verifier_l_archive(data: bytes) -> None:
    """Un .xlsx est une archive : ses fichiers DÉCOMPRESSÉS sont bornés avant qu'openpyxl ne les lise (2 Mo compressés
    peuvent sinon en faire des gigaoctets)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            total = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile as exc:
        raise FichierExcelInvalide("ce fichier n'est pas un classeur Excel (.xlsx)") from exc
    if total > DECOMPRESSE_MAX:
        raise FichierExcelInvalide("classeur trop volumineux une fois ouvert pour un tableau de données de test")


def _lignes(data: bytes) -> list[list]:
    """Les lignes NON VIDES de la première feuille ([numéro, cases]), au plus `LIGNES_PARCOURUES` lignes parcourues : une
    ligne vide mise en forme (fréquent dans un classeur) ne compte pas comme une variable."""
    _verifier_l_archive(data)
    classeur = lire_classeur(data)
    try:
        lignes = []
        feuille = classeur.worksheets[0]
        colonnes_max = max(_JEUX_MAX, _VARIABLES_MAX) + 2   # les deux sens du tableau (A54 et l'ancien)
        for numero, ligne in enumerate(feuille.iter_rows(max_row=LIGNES_PARCOURUES, max_col=colonnes_max), start=1):
            if any(getattr(c, "value", None) not in (None, "") for c in ligne):
                lignes.append([numero, list(ligne)])
        return lignes
    except Exception as exc:   # en lecture seule, la feuille n'est analysée qu'ici : une case corrompue lève à ce moment
        raise FichierExcelInvalide(f"classeur Excel illisible : {exc}") from exc
    finally:
        classeur.close()


def lire(data: bytes) -> Lecture:
    """Le fichier lu et vérifié. Lève `FichierExcelInvalide` pour un fichier illisible ; toute autre faute est rangée dans
    `erreurs`, une par case, pour que l'écran les montre toutes d'un coup."""
    if len(data) > TAILLE_MAX:
        raise FichierExcelInvalide(f"tableau de données trop volumineux ({TAILLE_MAX // (1024 * 1024)} Mo au plus)")
    lignes = _lignes(data)
    lecture = Lecture()
    if not lignes or lignes[0][0] != 1:
        lecture.erreurs.append(f"case A1 : « {ENTETE} » attendu (le modèle s'obtient avec « Exporter »)")
        return lecture
    entete = []
    for i, case in enumerate(lignes[0][1]):
        try:
            entete.append(_texte(case))
        except _CaseInvalide as exc:
            lecture.erreurs.append(f"case {_colonne(i)}1 : {exc}")
            entete.append("")
    while entete and not entete[-1].strip():
        entete.pop()
    sens = entete[0].strip().casefold() if entete else ""
    if sens == ENTETE.casefold():
        return _lire_par_lignes(lignes, entete, lecture)
    if sens != ENTETE_ANCIEN.casefold():
        lecture.erreurs.append(f"case A1 : « {ENTETE} » attendu (le modèle s'obtient avec « Exporter »)")
        return lecture
    if len(lignes) - 1 > _VARIABLES_MAX:
        lecture.erreurs.append(f"{_VARIABLES_MAX} variables au plus")
    if len(entete) - 1 > _JEUX_MAX:
        lecture.erreurs.append(f"{_JEUX_MAX} jeux de données au plus")
    colonnes: dict[int, str] = {}
    for i, brut in enumerate(entete[1:], start=1):
        nom = _nom(brut)
        if not nom:
            lecture.erreurs.append(f"case {_colonne(i)}1 : nom du jeu de données manquant")
        elif len(nom) > _NOM_DE_JEU_MAX:
            lecture.erreurs.append(f"case {_colonne(i)}1 : {_NOM_DE_JEU_MAX} caractères au plus")
        elif any(_key(nom) == _key(deja) for deja in lecture.jeux):
            lecture.erreurs.append(f"case {_colonne(i)}1 : le jeu « {nom} » est déjà une autre colonne")
        else:
            colonnes[i] = nom
            lecture.jeux.append(nom)
    for numero, ligne in lignes[1:]:
        cases: list[str] = []
        for i, case in enumerate(ligne):
            try:
                cases.append(_texte(case))
            except _CaseInvalide as exc:
                lecture.erreurs.append(f"case {_colonne(i)}{numero} : {exc}")
                cases.append("")
        try:
            variable = resolution.valider_nom(_nom(cases[0]) if cases else "")
        except resolution.NomInvalide as exc:
            lecture.erreurs.append(f"case A{numero} : {exc}")
            continue
        if variable in lecture.variables:
            lecture.erreurs.append(f"case A{numero} : la variable « {variable} » est déjà une autre ligne")
            continue
        lecture.variables.append(variable)
        for i, jeu in colonnes.items():
            valeur = cases[i] if i < len(cases) else ""
            if not valeur.strip():
                continue   # case vide (ou d'espaces seulement) : ne vide rien (A37)
            try:
                lecture.valeurs[(variable, jeu)] = resolution.valider_valeur(valeur)
            except resolution.ValeurInvalide as exc:
                lecture.erreurs.append(f"case {_colonne(i)}{numero} : {exc}")
        for i in range(len(entete), len(cases)):
            if cases[i].strip():
                lecture.erreurs.append(f"case {_colonne(i)}{numero} : colonne sans nom de jeu de données")
                break
    return lecture


def _lire_par_lignes(lignes: list[list], entete: list[str], lecture: Lecture) -> Lecture:
    """A54 : une VARIABLE par colonne (en-tête), une ligne par JEU de données (colonne A). Mêmes règles que l'ancien sens,
    chaque faute nommée par sa case."""
    if len(entete) - 1 > _VARIABLES_MAX:
        lecture.erreurs.append(f"{_VARIABLES_MAX} variables au plus")
    if len(lignes) - 1 > _JEUX_MAX:
        lecture.erreurs.append(f"{_JEUX_MAX} jeux de données au plus")
    colonnes: dict[int, str] = {}
    for i, brut in enumerate(entete[1:], start=1):
        try:
            variable = resolution.valider_nom(_nom(brut))
        except resolution.NomInvalide as exc:
            lecture.erreurs.append(f"case {_colonne(i)}1 : {exc}")
            continue
        if variable in lecture.variables:
            lecture.erreurs.append(f"case {_colonne(i)}1 : la variable « {variable} » est déjà une autre colonne")
            continue
        colonnes[i] = variable
        lecture.variables.append(variable)
    for numero, ligne in lignes[1:]:
        cases: list[str] = []
        for i, case in enumerate(ligne):
            try:
                cases.append(_texte(case))
            except _CaseInvalide as exc:
                lecture.erreurs.append(f"case {_colonne(i)}{numero} : {exc}")
                cases.append("")
        nom = _nom(cases[0]) if cases else ""
        if not nom:
            lecture.erreurs.append(f"case A{numero} : nom du jeu de données manquant")
            continue
        if len(nom) > _NOM_DE_JEU_MAX:
            lecture.erreurs.append(f"case A{numero} : {_NOM_DE_JEU_MAX} caractères au plus")
            continue
        if any(_key(nom) == _key(deja) for deja in lecture.jeux):
            lecture.erreurs.append(f"case A{numero} : le jeu « {nom} » est déjà une autre ligne")
            continue
        lecture.jeux.append(nom)
        for i, variable in colonnes.items():
            valeur = cases[i] if i < len(cases) else ""
            if not valeur.strip():
                continue   # case vide (ou d'espaces seulement) : ne vide rien (A37)
            try:
                lecture.valeurs[(variable, nom)] = resolution.valider_valeur(valeur)
            except resolution.ValeurInvalide as exc:
                lecture.erreurs.append(f"case {_colonne(i)}{numero} : {exc}")
        for i in range(len(entete), len(cases)):
            if cases[i].strip():
                lecture.erreurs.append(f"case {_colonne(i)}{numero} : colonne sans nom de variable")
                break
    return lecture


def comparer(conn, project_id: int, lecture: Lecture) -> dict:
    """Ce que l'import changerait : variables et jeux ajoutés, cases modifiées (avant → après) ; et les erreurs, celles du
    fichier puis celles des plafonds du projet. Une case déjà à cette valeur n'est pas un changement."""
    depot = TestDataRepo(conn)
    tableau = depot.tableau(project_id)
    variables = {v["nom"]: v["id"] for v in tableau["variables"]}
    jeux = {_key(j["nom"]): j for j in tableau["jeux"]}
    nouvelles_variables = [n for n in lecture.variables if n not in variables]
    nouveaux_jeux = [n for n in lecture.jeux if _key(n) not in jeux
                     and not (not jeux and _key(n) == _key(NOM_DU_JEU_PAR_DEFAUT))]   # « Par défaut » naît seul
    erreurs = list(lecture.erreurs)
    if len(variables) + len(nouvelles_variables) > _VARIABLES_MAX:
        erreurs.append(f"le projet aurait plus de {_VARIABLES_MAX} variables")
    if max(len(jeux), 1) + len(nouveaux_jeux) > _JEUX_MAX:
        erreurs.append(f"le projet aurait plus de {_JEUX_MAX} jeux de données")
    cases = []
    for (variable, nom_du_jeu), apres in lecture.valeurs.items():
        jeu = jeux.get(_key(nom_du_jeu))
        avant = ""
        if jeu is not None and variable in variables:
            avant = tableau["valeurs"][jeu["id"]].get(variables[variable], "")
        if apres and avant != apres:   # une valeur vide ne vide jamais une case (A37)
            cases.append({"variable": variable, "jeu": jeu["nom"] if jeu else nom_du_jeu, "avant": avant, "apres": apres})
    return {"nouvelles_variables": nouvelles_variables, "nouveaux_jeux": nouveaux_jeux, "cases": cases, "erreurs": erreurs}


def appliquer(conn, project_id: int, lecture: Lecture) -> dict:
    """Écrit ce que `comparer` annonce, et seulement si le fichier n'a aucune erreur (`DonneeDeTestInvalide` sinon : rien
    n'est écrit). Les variables d'abord (la première crée le jeu « Par défaut »), puis les jeux, puis les cases.

    Chaque écriture du dépôt est validée à son tour : tout est vérifié AVANT la première, si bien qu'un arrêt en cours de
    route ne peut venir que d'une écriture concurrente — l'import est alors simplement à refaire."""
    changements = comparer(conn, project_id, lecture)
    if changements["erreurs"]:
        raise DonneeDeTestInvalide(changements["erreurs"][0])
    depot = TestDataRepo(conn)
    for nom in changements["nouvelles_variables"]:
        depot.creer_variable(project_id, nom=nom)
    for nom in changements["nouveaux_jeux"]:
        depot.creer_jeu(project_id, nom=nom)
    variables = {v["nom"]: v["id"] for v in depot.variables(project_id)}
    jeux = {_key(j["nom"]): j["id"] for j in depot.jeux(project_id)}
    par_jeu: dict[int, dict[int, str]] = {}
    for case in changements["cases"]:
        par_jeu.setdefault(jeux[_key(case["jeu"])], {})[variables[case["variable"]]] = case["apres"]
    for dataset_id, valeurs in par_jeu.items():
        depot.poser_valeurs(project_id, dataset_id, valeurs)
    return changements


def exporter(conn, project_id: int) -> bytes:
    """Le tableau du projet en .xlsx, au format que `lire` relit. Chaque case est écrite comme du TEXTE : une valeur qui
    commence par « = » ne doit jamais devenir une formule dans le classeur de celui qui l'ouvre."""
    import openpyxl

    tableau = TestDataRepo(conn).tableau(project_id)
    classeur = openpyxl.Workbook()
    feuille = classeur.active
    feuille.title = "Données de test"
    # A54 : une ligne par jeu de données (« Par défaut » d'abord), une variable par colonne.
    lignes = [[ENTETE, *[v["nom"] for v in tableau["variables"]]]]
    for j in tableau["jeux"]:
        lignes.append([j["nom"], *[tableau["valeurs"][j["id"]].get(v["id"], "") for v in tableau["variables"]]])
    for r, ligne in enumerate(lignes, start=1):
        for c, valeur in enumerate(ligne, start=1):
            feuille.cell(row=r, column=c).number_format = "@"   # ce qu'on tape dans le modèle reste du texte
            if valeur != "":
                case = feuille.cell(row=r, column=c)
                case.value = valeur
                case.data_type = "s"
    tampon = io.BytesIO()
    classeur.save(tampon)
    return tampon.getvalue()
