---
description: Lot 06 — Teardown générique et profils d'instance ; sortie du code Sapian du socle (F6)
---

# Lot 06 — Nettoyage des données de test et profils d'instance

Lis `CLAUDE.md`, F6 du plan. Décision requise : **D6**. Dépend du lot 01.
Branche : `lot-06-nettoyage-profils`.

## Pourquoi

`environment.py` ne supprime que `helpdesk.ticket` (`_TEST_OUTPUT_MODELS`, ~l.118) : une commande,
un partenaire ou une facture créés par un test restent, ce qui provoque des collisions d'unicité au
rejeu et fausse les données des tests suivants. Le même `after_scenario` restaure
`employee_front_role_ids`, un champ propre à l'instance Sapian, dans le harnais commun à tous les
projets. Et `generic/_generic_steps.py` contient des steps propres à une application
(« je force le nom du ticket », « … avec accessoires »).

## À lire d'abord

- `behave_runtime/environment.py` (en entier), `register_created`.
- `behave_runtime/steps_library/generic/_generic_steps.py`, `odoo/_odoo_steps.py`,
  `_base_helpers.py` (tous les appels à `register_created`, `_roles_to_restore`).
- `src/testpilot/execution/behave_runner.py` (assemblage `generic/` + `<connecteur>/`),
  `src/testpilot/generation/steps_library.py` (`catalogue`).
- `tests/test_garde_generique_sans_marqueur_odoo.py` (garde existante à étendre).
- Schéma du projet (réglages de connexion) et écran de réglages du projet.

## Travail

1. **Registre complet** : tout id créé par le scénario et identifié (lot 01, `register_created`,
   captures RPC) est enregistré avec son modèle, dans l'ordre de création.
   **Ajout du 2026-09-24 — une création sans step de comptage n'est pas nettoyée** (ticket 30298,
   campagne réelle : les steps de comptage personnalisés n'enregistraient rien ; F9 ferme cette
   cause, pas le cas général). Un scénario qui crée sans aucun step de comptage laisse un résidu :
   relever le `max_id` des modèles touchés même sans comptage demandé (par exemple à partir des
   modèles apparaissant dans les réponses RPC/formulaire capturées), pour pouvoir nettoyer
   `id > max_id` sur ces modèles.
2. **Teardown générique Odoo** (ordre inverse de création), par enregistrement :
   `unlink` ; en cas de refus, tentative d'annulation si le modèle expose `action_cancel` /
   `button_cancel` puis `unlink` ; sinon `write({"active": False})` si le champ existe ; sinon
   consignation. Jamais d'exception qui remonte (le verdict est déjà rendu). Les restes non
   supprimés sont écrits dans un sidecar `TP_RESIDUS_FILE` et affichés dans le détail du run.
   Ne supprime **jamais** un enregistrement dont l'id est ≤ au `max_id` relevé (prérequis).
3. **Profils d'instance** (D6) : dossier `behave_runtime/steps_library/<connecteur>/profils/`,
   un module par profil exposant des steps et des hooks optionnels (`apres_scenario(context)`).
   Réglage de projet `profil_instance` (vide par défaut). Le runner copie le profil choisi à côté
   de `generic/` et `<connecteur>/` ; `catalogue()` l'inclut pour ce projet seulement.
4. Déplace vers `odoo/profils/sapian.py` : la restauration `employee_front_role_ids` et tout step
   propre à Sapian. Déplace vers `generic/profils/demo_saucedemo.py` (ou supprime s'ils ne servent
   qu'aux tests de conformité, et adapte ceux-ci) les steps « ticket » et « accessoires ».
   Migration de données : les projets existants qui utilisaient ces steps reçoivent le bon profil.
5. Étends la garde de `test_garde_generique_sans_marqueur_odoo.py` : ni `generic/` ni
   `environment.py` ne contiennent de nom de champ ou de libellé propre à une instance (liste
   noire : `employee_front`, `sapian`, `ticket`, `accessoires`, à compléter).

## Tests exigés

- Teardown : supprime dans l'ordre inverse ; commande confirmée → annulée puis supprimée (doublure) ;
  modèle sans `unlink` possible ni `active` → résidu consigné, aucune exception.
- Un prérequis (id ≤ max_id) n'est jamais supprimé.
- Profil : un projet sans profil ne voit pas les steps Sapian ; un projet `sapian` les voit ;
  le dry-run d'un `.feature` Sapian existant reste vert avec le profil.
- Garde générique étendue.

## Critères d'acceptation

- [ ] Rejouer deux fois de suite le même cas du banc (lot 04) ne produit aucun `donnee_invalide`
      dû à une collision d'unicité.
- [ ] Plus aucune référence à une instance client dans le socle (grep dans le rapport).

Rapport au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
