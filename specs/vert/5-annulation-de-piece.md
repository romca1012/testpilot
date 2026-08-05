# Demande d'annulation de pièce

## Contexte

Sur le Portail des Services, un collaborateur peut demander l'annulation d'une pièce comptable
(facture ou avoir) déjà émise auprès d'un fournisseur. Sa demande crée un ticket traité par le
service comptable, accompagné d'une copie de la pièce concernée.

Le formulaire se trouve à l'adresse `/annulation_piece/{id}` du portail.

## Ce qu'on veut vérifier

Qu'un collaborateur connecté peut déposer une demande d'annulation de pièce complète, pièce
jointe comprise, et que la demande est bien enregistrée dans le système.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `partner_name` | Le nom du demandeur |
| `numero_fournisseur` | Le numéro du fournisseur — **exactement 6 chiffres** |
| `nom_fournisseur` | Le nom du fournisseur |
| `numero_facture_annulation` | Le numéro de la facture à annuler — **entre 1 et 10 caractères alphanumériques** |
| `montant_ttc` | Le montant TTC de la pièce |
| `piece_jointe_facture` | Une copie de la facture ou de l'avoir (fichier) |

Le sujet de la demande et l'adresse e-mail du demandeur sont **renseignés par le portail** : ils
ne sont pas saisis à l'écran.

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de demande d'annulation de pièce.
3. Il indique le fournisseur, la facture concernée et le montant.
4. Il joint une copie de la pièce.
5. Il envoie la demande.

## Résultat attendu

La demande est enregistrée : un nouveau ticket `helpdesk.ticket` existe dans le système, et le
nombre total de tickets a augmenté d'une unité.

## Point d'attention

Le numéro de fournisseur et le numéro de facture obéissent chacun à un format strict. Une valeur
qui ne le respecte pas est refusée par le navigateur avant tout envoi — ce n'est pas un défaut de
l'application, c'est la donnée du test qui est irrecevable.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
