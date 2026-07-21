# Demande d'achat pour le siège

## Contexte

Sur le Portail des Services, un collaborateur du siège peut demander l'achat d'un
équipement ou d'un investissement. Sa demande crée un ticket que le service Achats
traitera ensuite.

Le formulaire se trouve à l'adresse `/achat_siege/{id}` du portail.

## Ce qu'on veut vérifier

Qu'un collaborateur connecté peut déposer une demande d'achat complète, et que la
demande est bien enregistrée dans le système.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `partner_name` | Le demandeur |
| `denomination` | L'intitulé de la demande |
| `type_investissement` | Nature de l'investissement — soit `new_aquisition`, soit `remplacement` |
| `justification` | Pourquoi cet achat est nécessaire |
| `amount_ht` | Montant hors taxes |
| `supplier_name` | Le fournisseur pressenti |
| `quote_file` | Le devis — **pièce jointe** |

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de demande d'achat pour le siège.
3. Il renseigne toutes les informations demandées ci-dessus.
4. Il joint le devis.
5. Il envoie la demande.

## Résultat attendu

La demande est enregistrée : un nouveau ticket existe dans le système, et le
nombre total de tickets a augmenté d'une unité.
