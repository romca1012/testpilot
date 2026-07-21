# Demande de remboursement client

## Contexte

Lorsqu'un client a payé deux fois, ou qu'un avoir doit lui être restitué, la
comptabilité client dépose une **demande de remboursement** sur le Portail des
Services. La demande crée un ticket que la comptabilité traitera.

Le formulaire se trouve à l'adresse `/remboursement/{id}` du portail.

## Ce qu'on veut vérifier

Qu'un utilisateur connecté peut déposer une demande de remboursement complète, avec
les coordonnées bancaires du client, et que la demande est bien enregistrée.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `partner_name` | Le demandeur |
| `code_client1` | Code du client |
| `nom_client` | Nom du client |
| `montant_remboursement` | Montant à rembourser |
| `motif` | Motif du remboursement — l'une de ces valeurs : `avoir`, `double_regl_virement_errone`, `acompte_yes__no_prestation` |
| `nom_banque` | Banque du client |
| `iban_client` | IBAN du client |
| `bic_client` | BIC du client |
| `nom_prenom` | Titulaire du compte |
| `rib_client` | Le RIB — **pièce jointe** |

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de demande de remboursement.
3. Il renseigne toutes les informations demandées ci-dessus.
4. Il joint le RIB.
5. Il envoie la demande.

## Résultat attendu

La demande est enregistrée : un nouveau ticket existe dans le système, et le nombre
total de tickets a augmenté d'une unité.
