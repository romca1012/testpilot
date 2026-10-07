"""Descriptions d'outils V2 — le standard Anthropic : quoi, quand, quand NE PAS, paramètres, limites.

⚠️ **Pourquoi V2, et pourquoi derrière un interrupteur.** La doc « Define tools » (relue le
2026-10-07) dit que la description est « de loin » le facteur le plus important de la performance
d'un outil, et demande au moins 3-4 phrases : ce que fait l'outil, quand l'utiliser ET quand ne pas
l'utiliser, le sens de chaque paramètre, les limites. Les descriptions actuelles tiennent souvent en
une phrase. Mais une description, c'est du prompt : la réécrire change le comportement de l'agent, donc
elle se MESURE avant d'être activée (`TESTPILOT_TOOLS_DESCRIPTIONS_V2=1`, désactivé par défaut,
`interrupteurs.py`). Les noms et les schémas ne changent pas ; seules les phrases changent.

⚠️ **Chaque affirmation est liée au code qui l'applique** (principe 6, `docs/PRINCIPES.md`) :
plafonds (`query_data` 1-10, `inspect_schema` 50 champs), refus en mode qualification, calibration en
écriture désactivée par défaut, contrôles de `write_steps_file`. Un test d'accord
(`tests/test_tools_descriptions_v2.py`) garde les promesses déjà testées sur les descriptions V1
(« REMPLACE », « ENTIER », « ASCII », « pas de step partagé redéfini »).

Les descriptions de PARAMÈTRES sont indexées par nom de propriété, outil par outil, et appliquées à
toutes les occurrences de ce nom dans le schéma (y compris imbriquées). Un paramètre sans description,
ou une description sans paramètre, lève une erreur : la dérive est refusée, pas silencieuse.
"""

from __future__ import annotations

import copy

from testpilot.generation.technical_plan import HYPOTHESES_CLE

DESCRIPTIONS_V2: dict[str, str] = {
    "inspect_schema": (
        "Retourne les champs d'un modèle de données (nom technique, type, requis ou optionnel) lus "
        "via le connecteur, avec un identifiant de preuve `observation-N` à citer dans "
        "`evidence_ids`. "
        "Quand l'utiliser : une seule fois par modèle, avant d'écrire un nom de champ dans un "
        "scénario, dès que la spécification cite une entité. "
        "Ne pas l'utiliser pour lire des valeurs (c'est `query_data`), ni pour une page web sans "
        "modèle de données interrogeable (c'est `inspect_page_snapshot`). "
        "Limites : 50 champs au plus sont rendus ; c'est une lecture RPC, elle prouve qu'un champ "
        "existe côté serveur mais pas qu'il est visible dans la page courante ; un modèle inconnu "
        "rend une erreur, jamais un schéma deviné."),
    "query_data": (
        "Lit quelques enregistrements réels d'un modèle (les champs demandés, ou `id` et `name` par "
        "défaut) pour observer des valeurs concrètes au lieu d'en inventer. "
        "Quand l'utiliser : après `inspect_schema`, pour voir un exemple de valeur réelle (format "
        "d'une référence, valeur d'une liste) avant de l'écrire dans un scénario. "
        "Ne pas l'utiliser pour compter des enregistrements ni pour fixer un état attendu : un "
        "comptage ou un état se vérifie dans le test, avec les steps du catalogue, jamais par une "
        "lecture faite pendant la génération. "
        "Limites : entre 1 et 10 enregistrements (3 par défaut) ; refusé en mode qualification, où "
        "l'on utilise les prérequis de test déclarés ; réservé aux connecteurs qui exposent un "
        "modèle de données."),
    "inspect_page_form": (
        "Observe un formulaire réel de l'application : ses champs, les champs requis, le mécanisme "
        "de soumission (clic, requête, route), les formats de saisie observés et les éléments "
        "cliquables visibles, avec un identifiant de preuve `observation-N`. "
        "Quand l'utiliser : une seule fois par page, avant d'écrire un scénario qui remplit ou "
        "soumet un formulaire, et avant de choisir la valeur d'un champ. "
        "Ne pas l'utiliser pour une page sans formulaire (préfère `inspect_page_snapshot`), ni pour "
        "déduire le texte d'un message d'erreur : seuls `attempt_login` et `attempt_form_submission` "
        "observent un message affiché. "
        "Limites : la page est ouverte par simple navigation, donc l'outil ne rejoue pas un clic de "
        "menu préalable ; les éléments cliquables rendus sont un extrait, pas un catalogue "
        "exhaustif."),
    "inspect_odoo_view": (
        "Observe une VRAIE vue Odoo par RPC : boutons (nom technique, libellé, condition de "
        "visibilité), barre d'état du workflow, champs x2many et leurs sous-champs éditables, "
        "champs requis. "
        "Quand l'utiliser : avant de cliquer un bouton de workflow (« Confirmer », « Valider »…) ou "
        "de citer une ligne de commande — jamais deviner un nom de bouton ou un état. "
        "Ne pas l'utiliser avec un connecteur autre qu'Odoo (il répond que ce connecteur n'expose "
        "pas de vues Odoo), ni pour lire des données (c'est `query_data`). "
        "Limites : la visibilité d'un bouton est une condition, souvent liée à un état, pas un "
        "simple visible ou caché ; seuls les champs réels observés sont retenus comme champs "
        "vérifiés, jamais un bouton."),
    "inspect_page_snapshot": (
        "Rend l'instantané des éléments interactifs réellement visibles d'une page web : rôle, nom "
        "accessible et type de chacun. "
        "Quand l'utiliser : avant de citer un lien, un menu ou un bouton qu'aucun formulaire déjà "
        "inspecté n'a montré, pour reprendre son libellé exact au lieu de le deviner. "
        "Ne pas l'utiliser pour connaître les champs requis ou le mécanisme de soumission d'un "
        "formulaire (c'est `inspect_page_form`), ni pour lire un message affiché. "
        "Limites : la liste est plafonnée et ne montre que ce qui est visible à l'instant de "
        "l'observation (un contenu chargé plus tard peut manquer) ; une page sans élément rend "
        "« aucun élément », jamais une liste inventée."),
    "discover_route": (
        "Sonde une route de l'application par une requête HTTP légère (HEAD, puis GET en repli) "
        "pour en découvrir l'URL réelle, le statut et la méthode. "
        "Quand l'utiliser : quand le scénario doit naviguer vers une route dont tu ne connais que le "
        "motif, avec un identifiant variable, et qu'aucune URL réelle mesurée n'est fournie. "
        "Ne pas l'utiliser pour inventer un identifiant, ni pour juger le comportement d'une page : "
        "cela relève du scénario, pas de la génération. "
        "Limites : le résultat décrit une seule sonde (statut, méthode, URL), jamais le contenu de "
        "la page."),
    "attempt_login": (
        "Soumet CES identifiants au formulaire de connexion et rend le message réellement affiché "
        "après coup, avec l'URL résultante. "
        "Quand l'utiliser : avant d'écrire une assertion sur un message lié à une tentative de "
        "connexion (identifiants valides, mot de passe erroné, compte verrouillé…) : le texte rendu "
        "se reprend au caractère près, il ne se devine jamais de mémoire. "
        "Ne pas l'utiliser pour te connecter afin d'entrer dans l'application (la connexion "
        "automatique du projet s'en charge), ni pour un message affiché après la création d'un "
        "enregistrement (c'est `attempt_form_submission`). "
        "Limites : n'utilise que les identifiants du scénario ; refusé en mode qualification ; "
        "l'absence de message détecté ne prouve pas que la connexion a réussi."),
    "attempt_form_submission": (
        "Remplit les champs donnés (par nom technique) sur le vrai formulaire et le soumet, puis "
        "rend le message réellement affiché et dit si la donnée créée a été nettoyée. "
        "Quand l'utiliser : seulement pour observer le texte affiché après la création d'un "
        "enregistrement, sur un projet qui a explicitement autorisé la calibration en écriture, "
        "avant d'écrire une assertion sur ce texte. "
        "Ne pas l'utiliser pour la connexion (c'est `attempt_login`), ni sur un projet qui ne l'a "
        "pas autorisée (l'outil refuse), ni avec un connecteur incapable de nettoyer derrière lui "
        "(le connecteur générique refuse). "
        "Limites : il crée potentiellement une vraie donnée ; fournis `model` (le nom technique du "
        "modèle Odoo) pour qu'elle soit supprimée après lecture du message ; refusé en mode "
        "qualification."),
    "write_feature_file": (
        "REMPLACE le fichier .feature (Gherkin français) du module par le contenu fourni, après "
        "avoir vérifié la syntaxe Gherkin, la présence d'au moins un scénario avec des étapes et "
        "l'absence de référence prouvée inexistante. Rends le fichier ENTIER : ce que tu n'écris "
        "pas est perdu. "
        "Quand l'utiliser : seulement pour un parcours que le catalogue de steps partagés ne couvre "
        "pas ; sinon utilise `write_test_plan`, qui compile le Gherkin lui-même. "
        "Ne pas l'utiliser pour corriger une seule ligne en n'envoyant qu'un extrait : tout le reste "
        "du fichier serait effacé. "
        "Limites : refuse un contenu vide, un Gherkin invalide, un scénario sans étape, une valeur "
        "de liste ou une référence relationnelle prouvée inexistante ; ne vérifie pas qu'un `Alors` "
        "est présent ni que chaque exigence est couverte (le dry-run contrôlera seulement que "
        "chaque step trouve un décorateur)."),
    "write_steps_file": (
        "REMPLACE le fichier _steps.py du module par le contenu fourni. Rends le fichier ENTIER — "
        "tous les steps, y compris ceux que tu ne modifies pas : ce que tu n'écris pas est PERDU et "
        "son step deviendra `undefined`. Validé : ASCII, pas de step partagé redéfini. "
        "Quand l'utiliser : dans le même tour que l'écriture du .feature ; un fichier minimal sans "
        "step personnalisé (juste les imports) est valide quand tout vient du catalogue. "
        "Ne pas l'utiliser pour redéfinir un step du catalogue, ouvrir tes propres connexions HTTP, "
        "recompter des enregistrements toi-même ni écrire une assertion ailleurs que dans un "
        "`@then`. "
        "Limites : refuse les guillemets typographiques, une erreur de syntaxe Python, un transport "
        "réinventé, un comptage recalculé, un `source=` forgé, toute référence au mécanisme réservé "
        "au socle et toute assertion mal placée."),
    "write_test_plan": (
        "Compile un plan technique ENTIER en Gherkin à partir des étapes du catalogue partagé et "
        "écrit le fichier .feature ; c'est l'outil par défaut. Il relie chaque scénario aux "
        "identifiants métier fournis dans le message initial (`requirement_ids`) et aux preuves "
        "observées (`evidence_ids`), puis refuse le plan si une exigence n'est couverte par aucun "
        "scénario, si un step n'est pas dans le catalogue, si une preuve est inconnue ou si un "
        "scénario n'a aucune assertion. "
        "Quand l'utiliser : dès que le parcours est couvert par le catalogue ; écris ensuite le "
        "fichier de steps (vide si tout vient du catalogue). "
        "Ne pas l'utiliser pour un parcours qui exige un step hors catalogue (utilise alors "
        "`write_feature_file` puis `write_steps_file`), ni compter comme assertion une attente telle "
        "que « j'attends la soumission du formulaire » : seul un `Alors` qui constate un résultat "
        "compte. "
        "Limites : chaque libellé tient sur une seule ligne ; les `evidence_ids` viennent des "
        "inspections (une liste vide signifie « aucune preuve », pas « validé »)."),
}

# Descriptions des paramètres, par outil puis par NOM de propriété (appliquées partout où le nom
# apparaît dans le schéma, imbriqué compris).
PARAMETRES_V2: dict[str, dict[str, str]] = {
    "inspect_schema": {
        "model": "Nom technique du modèle de données à inspecter, par exemple `res.partner`.",
    },
    "query_data": {
        "model": "Nom technique du modèle dont lire des enregistrements.",
        "fields": ("Noms techniques des champs à lire, pris dans `inspect_schema` ; `id` et `name` "
                   "si absent."),
        "limit": "Nombre d'enregistrements à lire, borné d'office entre 1 et 10 ; 3 si absent.",
    },
    "inspect_page_form": {
        "page_url": "URL réelle de la page qui porte le formulaire, jamais une URL inventée.",
    },
    "inspect_odoo_view": {
        "model": "Nom technique du modèle Odoo dont observer la vue, par exemple `sale.order`.",
        "view_type": "Type de vue à observer ; `form` si absent.",
    },
    "inspect_page_snapshot": {
        "page_url": "URL réelle de la page web dont relever les éléments interactifs visibles.",
    },
    "discover_route": {
        "path_pattern": "Motif de chemin de la route à sonder, relatif à l'URL de l'application.",
        "sample_id": "Identifiant d'exemple qui remplace la partie variable du motif ; facultatif.",
    },
    "attempt_login": {
        "username": "Identifiant EXACT du scénario à tester, valide ou non selon le cas visé.",
        "password": "Mot de passe EXACT du scénario à tester, valide ou non selon le cas visé.",
    },
    "attempt_form_submission": {
        "page_url": "URL réelle de la page qui porte le formulaire de création.",
        "field_values": "Valeurs à saisir, sous la forme {nom technique du champ: valeur}.",
        "model": "Nom technique du modèle Odoo de l'enregistrement créé, pour le supprimer ensuite.",
    },
    "write_feature_file": {
        "content": "Contenu ENTIER du fichier .feature, en Gherkin français (`# language: fr`).",
    },
    "write_steps_file": {
        "content": "Contenu ENTIER du fichier _steps.py, en Python ASCII, tous les steps compris.",
    },
    "write_test_plan": {
        "title": "Titre de la fonctionnalité Gherkin, sur une seule ligne.",
        "scenarios": ("Scénarios du plan (au moins un) ; chaque exigence métier fournie doit être "
                      "couverte par au moins l'un d'eux."),
        "name": ("Nom du scénario, sur une seule ligne, par convention préfixé par son type : "
                 "[Nominal], [Erreur] ou [Limite]."),
        "requirement_ids": ("Identifiants métier couverts par ce scénario (au moins un), repris tels "
                            "quels du message initial, par exemple `expected_result` ou `step:1`."),
        "steps": ("Étapes du scénario dans l'ordre ; la première est de type Soit, Quand ou Alors, "
                  "et au moins un `Alors` doit constater un résultat."),
        "keyword": ("Mot-clé Gherkin : Soit (contexte), Quand (action), Alors (résultat attendu) ; "
                    "Et ou Mais reprennent le type de l'étape précédente."),
        "text": ("Libellé du step, mot pour mot celui du catalogue partagé, valeurs entre guillemets "
                 "comprises, sur une seule ligne."),
        "evidence_ids": ("Identifiants `observation-N` des inspections qui prouvent cette étape ; "
                         "une liste vide signifie « aucune preuve », pas « validé »."),
        HYPOTHESES_CLE: ("Ce dont tu n'es pas sûr (une hypothèse non vérifiée, un champ deviné faute "
                         "de mieux), en phrases courtes, 5 au plus ; liste vide s'il n'y a aucun "
                         "doute. Lu par l'humain qui relit, jamais utilisé pour décider d'un verdict."),
    },
}


def _noms_de_proprietes(schema: dict) -> set[str]:
    """Tous les noms de propriétés d'un schéma, imbriqués compris."""
    noms: set[str] = set()
    for nom, sous in (schema.get("properties") or {}).items():
        noms.add(nom)
        noms |= _noms_de_proprietes(sous)
    if isinstance(schema.get("items"), dict):
        noms |= _noms_de_proprietes(schema["items"])
    return noms


def _decrire(schema: dict, descriptions: dict[str, str]) -> None:
    for nom, sous in (schema.get("properties") or {}).items():
        sous["description"] = descriptions[nom]
        _decrire(sous, descriptions)
    if isinstance(schema.get("items"), dict):
        _decrire(schema["items"], descriptions)


def appliquer_v2(definition: dict) -> dict:
    """Copie de `definition` avec la description V2 de l'outil et celle de chacun de ses paramètres.

    Lève `KeyError` si l'outil n'a pas de description V2, si un paramètre du schéma n'a pas de
    description, ou si une description vise un paramètre qui n'existe plus : un outil ajouté ou un
    schéma modifié sans mise à jour d'ici est REFUSÉ, jamais servi à moitié décrit.
    """
    nom = definition["name"]
    copie = copy.deepcopy(definition)
    copie["description"] = DESCRIPTIONS_V2[nom]
    descriptions = PARAMETRES_V2[nom]
    presents = _noms_de_proprietes(copie["input_schema"])
    manquants = presents - set(descriptions)
    if manquants:
        raise KeyError(f"{nom} : paramètre(s) sans description V2 {sorted(manquants)}")
    # Une description de paramètre absent du schéma COURANT n'est pas une erreur pour
    # `HYPOTHESES_CLE` seul : le champ est retiré du schéma tant que son interrupteur est éteint.
    orphelins = set(descriptions) - presents - {HYPOTHESES_CLE}
    if orphelins:
        raise KeyError(f"{nom} : description V2 d'un paramètre inexistant {sorted(orphelins)}")
    _decrire(copie["input_schema"], descriptions)
    return copie
