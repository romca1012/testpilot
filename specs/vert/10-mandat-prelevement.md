# Mandat de prélèvement

## Contexte

Sur le Portail des Services, un utilisateur peut déposer un mandat de prélèvement pour un
client, accompagné des pièces justificatives signées. Sa demande crée un ticket que le
service comptable concerné prendra en charge.

Le formulaire se trouve à l'adresse `/prelevements/85` du portail, sous Services Métiers →
Finance → Compta Client → Prélèvement.

## Ce qu'on veut vérifier

Qu'un utilisateur peut déposer un mandat de prélèvement complet, que sa demande est bien
enregistrée dans le système, et que le formulaire refuse une demande à qui il manque l'une
des deux pièces justificatives obligatoires.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `agence` | L'agence concernée — liste déroulante, **facultative** |
| `date_demande` | Date de la demande — facultative, pré-remplie par le portail |
| `nom_demandeur` | Nom du demandeur — **obligatoire**, pré-rempli par le portail |
| `code_client` | Code client — **obligatoire** |
| `nom_client` | Nom du client — **obligatoire** |
| `formulaire_signe` | Formulaire de prélèvement signé et tamponné par le client — pièce jointe **obligatoire** |
| `rib_original` | RIB original du client — pièce jointe **obligatoire** |
| `commentaires` | Contexte libre de la demande — facultatif |

## Parcours attendu (cas nominal)

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de mandat de prélèvement.
3. Il renseigne le code et le nom du client.
4. Il joint le formulaire de prélèvement signé et tamponné.
5. Il joint le RIB original du client.
6. Il envoie la demande.

## Résultat attendu (cas nominal)

La demande est enregistrée : un nouveau ticket existe dans le système, avec le service
« Compta Client », et le nombre total de tickets a augmenté d'une unité.

## Cas d'erreur à couvrir

- **Formulaire signé manquant** : l'envoi sans le formulaire de prélèvement signé et
  tamponné est refusé — aucun ticket ne doit être créé.
- **RIB original manquant** : l'envoi sans le RIB original du client est refusé — aucun
  ticket ne doit être créé.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
