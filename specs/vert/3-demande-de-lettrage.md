# Demande de lettrage comptable

## Contexte

Sur le Portail des Services, un gestionnaire peut demander le lettrage d'écritures
comptables sur un compte client — le rapprochement entre une facture et son avoir,
ou entre un règlement et les pièces qu'il solde. Sa demande crée un ticket traité
par la comptabilité client.

Le formulaire se trouve à l'adresse `/lettrage/65` du portail.

## Ce qu'on veut vérifier

Qu'un gestionnaire connecté peut déposer une demande de lettrage, et que la demande
est bien enregistrée dans le système.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `partner_name` | Le nom du demandeur |
| `type_lettrage` | La nature du lettrage — `lettrage_fact_avoir`, `lettrage_m3` ou `lettrage_help` |
| `client_number` | Le code client — **exactement 7 chiffres**, le formulaire refuse tout autre format |

Le sujet de la demande et l'adresse e-mail sont **renseignés par le portail** : ils ne
sont pas saisis à l'écran.

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de demande de lettrage.
3. Il indique son nom, la nature du lettrage et le code client.
4. Il envoie la demande.

## Résultat attendu

La demande est enregistrée : un nouveau ticket `helpdesk.ticket` existe dans le
système, et le nombre total de tickets a augmenté d'une unité.

## Point d'attention

Le code client obéit à un format strict (7 chiffres). Une valeur qui ne le respecte pas
est refusée par le navigateur **avant** tout envoi : rien n'est créé, et ce n'est **pas**
un défaut de l'application — c'est la donnée du test qui est irrecevable.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
