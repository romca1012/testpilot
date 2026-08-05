# Client en contentieux (créance douteuse)

## Contexte

Sur le Portail des Services, un gestionnaire peut signaler un client dont la créance devient
douteuse — par exemple à l'ouverture d'une procédure collective. Sa demande crée un ticket traité
par le service contentieux, accompagné d'une copie de la facture concernée.

Le formulaire se trouve à l'adresse `/creance_douteux/{id}` du portail.

## Ce qu'on veut vérifier

Qu'un gestionnaire connecté peut déposer une déclaration de créance douteuse complète, pièce
jointe comprise, et que la demande est bien enregistrée dans le système.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `partner_name` | Le nom du demandeur |
| `code_client1` | Le code client — **exactement 7 chiffres** |
| `name_customer` | Le nom du client |
| `siren` | Le numéro SIREN du client — **exactement 9 chiffres** |
| `date_proc` | La date de la procédure collective |
| `amount_creance` | Le montant total de la créance TTC |
| `copy_invoice_part` | Une copie de la facture concernée (fichier) |

Le sujet de la demande et l'adresse e-mail du demandeur sont **renseignés par le portail** : ils
ne sont pas saisis à l'écran.

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de créance douteuse.
3. Il indique le client, le SIREN, la date de procédure et le montant de la créance.
4. Il joint une copie de la facture.
5. Il envoie la demande.

## Résultat attendu

La demande est enregistrée : un nouveau ticket `helpdesk.ticket` existe dans le système, et le
nombre total de tickets a augmenté d'une unité.

## Point d'attention

Le code client et le SIREN obéissent chacun à un format strict (7 puis 9 chiffres) : une valeur
qui ne le respecte pas est refusée par le navigateur avant tout envoi. La date de procédure
affiche par ailleurs une borne technique (« pas après aujourd'hui ») portée par un gabarit du
portail plutôt que par une vraie règle métier — connu et sans incidence sur ce test, une date du
jour la respecte toujours.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
