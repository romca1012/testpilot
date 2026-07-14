# 0001 — Traitement des confirmations `pending_human` reporté à l'Incrément 1

Date : 2026-07-14
Statut : acté

## Contexte

L'asymétrie §5 (pilier verdict) produit des tentatives de réparation classées
`confirmation_status = 'pending_human'` : un « test à réparer » ou un défaut d'origine
indéterminée ne peut être classé définitivement sans validation humaine. La table
`repair_attempt` porte déjà cette colonne, et `RepairRepo.list_pending()` sait lister
les tentatives en attente.

Une sous-commande CLI (`testpilot review`) permettant à un humain de traiter cette file
d'attente — afficher les tentatives `pending_human`, confirmer/rejeter, appeler
`RepairRepo.confirm(...)` — a été envisagée pour le pilier reporting.

## Décision

**Hors périmètre de la preuve de concept (Incrément 0).** Le pilier reporting se limite
à `testpilot run <spec>` (+ `--yes`, `--author`). Le traitement interactif des
confirmations `pending_human` en attente relève de l'**Incrément 1**.

## Justification

- La PoC vise à démontrer le pipeline bout-en-bout `spec → rapport à deux axes`, pas la
  gestion d'une file de revue humaine dans la durée.
- L'infrastructure de données est **déjà en place** (colonne `confirmation_status`,
  `list_pending()`, `confirm()`) : rien n'est perdu, l'ajout Inc. 1 sera additif.
- Le besoin est réel et reconnu — cette note existe pour ne pas le perdre de vue.

## Conséquences

- En Inc. 0, une tentative `pending_human` est **persistée et signalée dans le rapport**
  (drapeau « confirmation humaine requise »), mais **non traitée** interactivement.
- À faire en Inc. 1 : sous-commande `testpilot review` (liste → décision → `confirm`).
