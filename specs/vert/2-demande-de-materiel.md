# Demande de matériel pour un nouvel entrant

## Contexte

Sur le Portail des Services, un collaborateur peut demander du matériel informatique,
soit pour l'arrivée d'un nouvel entrant, soit pour remplacer un équipement existant.
Sa demande crée un ticket traité par le service Matériel.

Le formulaire se trouve à l'adresse `/formulaire/71` du portail.

## Ce qu'on veut vérifier

Qu'un collaborateur connecté peut déposer une demande de matériel complète, et que
la demande est bien enregistrée dans le système.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `partner_name` | Le demandeur |
| `name` | La raison de la demande |
| `types_demandes` | Le type de demande — soit `nouvel_entrant`, soit `remplacement_materiel` |

L'adresse de livraison (destinataire, rue, ville, code postal) et l'adresse e-mail sont
**renseignées par le portail** à partir de la fiche de l'utilisateur : elles ne sont pas
saisies à l'écran, et le test ne doit pas chercher à les remplir.

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de demande de matériel.
3. Il indique son nom, la raison de sa demande et le type de demande.
4. Il envoie la demande.

## Résultat attendu

La demande est enregistrée : un nouveau ticket `helpdesk.ticket` existe dans le
système, et le nombre total de tickets a augmenté d'une unité.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
