# Remboursement client

## Contexte

Sur le Portail des Services, un utilisateur peut demander le remboursement d'un client, par
virement bancaire. Sa demande crée un ticket que le service comptable concerné prendra en
charge.

Le formulaire se trouve à l'adresse `/remboursement/64` du portail, sous Services Métiers →
Finance → Compta Client → Remboursement.

⚠️ Le formulaire affiche lui-même une règle de refus explicite : *« Les demandes de
remboursement pour lesquelles cette mention n'est pas cochée ne seront pas acceptées »*, à
propos de la case de certification du RIB.

## Ce qu'on veut vérifier

Qu'un utilisateur peut déposer une demande de remboursement client complète et valide, que
sa demande est bien enregistrée dans le système, et que le formulaire refuse une demande dont
l'IBAN ou le BIC ne respectent pas le format attendu, ou dont la case de certification du RIB
n'est pas cochée.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `agence` | L'agence concernée — liste déroulante, **facultative** |
| `nom_demandeur` | Nom du demandeur — **obligatoire**, pré-rempli par le portail |
| `code_client` | Code client — **obligatoire**, un nombre à **exactement 7 chiffres** |
| `nom_client` | Nom du client — **obligatoire** |
| `montant_remboursement` | Montant du remboursement — **obligatoire** |
| `motif` | Motif du remboursement — **obligatoire**, un choix parmi : *Avoir*, *Double règlement ou virement erroné*, *Acompte versé et prestation non réalisée* |
| `nom_banque` | Nom de la banque du client — **obligatoire** |
| `iban` | IBAN du client — **obligatoire**, format `FRXX XXXX XXXX XXXX XXXX XXXX XXX` |
| `bic` | BIC du client — **obligatoire**, 8 à 11 caractères alphanumériques (ex. `BNPAFRPPXXX`) |
| `rib` | RIB original du client — pièce jointe **obligatoire** |
| `certification_rib` | Case à cocher certifiant que les vérifications de validité du RIB ont été faites — **obligatoire**, sans quoi la demande est explicitement refusée par le formulaire lui-même |

## Parcours attendu (cas nominal)

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de remboursement client.
3. Il renseigne le code et le nom du client.
4. Il renseigne le montant et choisit un motif de remboursement.
5. Il renseigne le nom de la banque, l'IBAN et le BIC, au format attendu.
6. Il joint le RIB original et coche la case de certification.
7. Il envoie la demande.

## Résultat attendu (cas nominal)

La demande est enregistrée : un nouveau ticket existe dans le système, avec le service
« Compta Client », et le nombre total de tickets a augmenté d'une unité.

## Cas d'erreur à couvrir

- **IBAN mal formé** : un IBAN qui ne respecte pas le format `FRXX XXXX XXXX XXXX XXXX
  XXXX XXX` est refusé — aucun ticket ne doit être créé.
- **BIC mal formé** : un BIC qui ne contient pas entre 8 et 11 caractères alphanumériques
  est refusé — aucun ticket ne doit être créé.
- **Certification du RIB non cochée** : une demande envoyée sans que la case de
  certification soit cochée est refusée — aucun ticket ne doit être créé. C'est une règle que
  le formulaire annonce lui-même explicitement.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
