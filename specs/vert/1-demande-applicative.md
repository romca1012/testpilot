# Demande d'assistance applicative

## Contexte

Sur le Portail des Services, un collaborateur peut ouvrir une demande d'assistance
sur une application métier. Sa demande crée un ticket que le service concerné
prendra en charge.

Le formulaire se trouve à l'adresse `/formulaire-applicatif/22` du portail.

## Ce qu'on veut vérifier

Qu'un collaborateur connecté peut déposer une demande d'assistance, et que cette
demande est bien enregistrée dans le système.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `name` | La raison de la demande — **seule information que l'utilisateur doit saisir** |

Le demandeur et son adresse e-mail sont **pré-remplis par le portail** à partir de la
session : l'utilisateur n'a pas à les renseigner, et le test non plus.

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de demande applicative.
3. Il renseigne la raison de sa demande.
4. Il envoie la demande.

## Résultat attendu

La demande est enregistrée : un nouveau ticket `helpdesk.ticket` existe dans le
système, et le nombre total de tickets a augmenté d'une unité.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
