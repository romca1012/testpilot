# Mutation d'un client

## Contexte

Quand un client change de dénomination ou d'entité juridique, le service commercial
déclare une **mutation** sur le Portail des Services. Cette déclaration crée un ticket
qui sera traité par la gestion clients.

Le formulaire se trouve à l'adresse `/mutation/{id}` du portail.

## Ce qu'on veut vérifier

Qu'un utilisateur connecté peut déclarer la mutation d'un client de bout en bout, et
que la déclaration est bien enregistrée.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `partner_name` | Le déclarant |
| `code_client1` | Code du client actuel |
| `nom_client` | Nom du client actuel |
| `mutation_code_client` | Nouveau code client |
| `nouveau_nom_client` | Nouveau nom du client |
| `date_mutation_client` | Date d'effet de la mutation (format `AAAA-MM-JJ`) |
| `justificatifs_mutation` | Le justificatif — **pièce jointe** |

## Parcours attendu

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de mutation client.
3. Il renseigne toutes les informations demandées ci-dessus.
4. Il joint le justificatif.
5. Il envoie la déclaration.

## Résultat attendu

La mutation est enregistrée : un nouveau ticket existe dans le système, et le nombre
total de tickets a augmenté d'une unité.
