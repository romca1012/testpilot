# Formulaire de désistement

## Contexte

Sur le Portail des Services, un client peut se désister d'un chèque déjà remis — par exemple un
chèque égaré ou remplacé par un autre moyen de paiement. Sa demande crée un ticket traité par la
comptabilité client.

Le formulaire se trouve à l'adresse `/desistement/{id}` du portail.

## Ce qu'on veut vérifier

Qu'un gestionnaire connecté peut déposer une demande de désistement complète, avec les
coordonnées du chèque concerné, et que la demande est bien enregistrée dans le système.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `partner_name` | Le nom du demandeur |
| `email_client` | L'adresse e-mail du client concerné |
| `code_client1` | Le code client — **exactement 7 chiffres** |
| `nom_client` | Le nom du client |
| `numero_facture1` | Le numéro de la facture — **exactement 7 chiffres** |
| `numero_cheque` | Le numéro du chèque — **exactement 7 chiffres** |
| `nom_banque` | Le nom de la banque |
| `date_emission_cheque` | La date d'émission du chèque — **doit être postérieure à aujourd'hui** |
| `montant_cheque` | Le montant du chèque |

Le sujet de la demande et l'adresse e-mail du demandeur sont **renseignés par le portail** : ils
ne sont pas saisis à l'écran.

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de désistement.
3. Il indique le client, la facture, le chèque et la banque concernés.
4. Il envoie la demande.

## Résultat attendu

La demande est enregistrée : un nouveau ticket `helpdesk.ticket` existe dans le système, et le
nombre total de tickets a augmenté d'une unité.

## Point d'attention

Trois champs obéissent au même format strict (7 chiffres) : le code client, le numéro de facture
et le numéro de chèque. Une valeur qui ne le respecte pas est refusée par le navigateur **avant**
tout envoi — ce n'est pas un défaut de l'application, c'est la donnée du test qui est irrecevable.
La date d'émission du chèque doit, elle, être dans le futur : une date passée est également
refusée par le formulaire.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
