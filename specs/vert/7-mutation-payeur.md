# Mutation payeur

## Contexte

Sur le Portail des Services, un utilisateur peut demander le transfert d'un compte d'un
payeur vers un autre (« mutation payeur »). Sa demande crée un ticket que le service
comptable concerné prendra en charge.

Le formulaire se trouve à l'adresse `/mutation/67` du portail, sous Services Métiers →
Finance → Compta Client → Demande de mutation.

## Ce qu'on veut vérifier

Qu'un utilisateur peut déposer une demande de mutation payeur complète, que sa demande est
bien enregistrée dans le système, et que le formulaire refuse une demande incomplète ou
dont les codes payeur ne respectent pas le format attendu.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `agence` | L'agence concernée — liste déroulante, **facultative** |
| `name` | Nom du demandeur — **obligatoire**, pré-rempli par le portail à partir de la session |
| `code_payeur_actuel` | Code du payeur actuel — **obligatoire**, un nombre à **exactement 7 chiffres** |
| `nom_payeur_actuel` | Nom du payeur actuel — **obligatoire** |
| `code_payeur_cible` | Code du payeur cible (destination de la mutation) — **obligatoire**, un nombre à **exactement 7 chiffres** |
| `nom_payeur_cible` | Nom du payeur cible — **obligatoire** |
| `date_effective` | Date effective de mutation demandée par le client — **obligatoire** |
| `description` | Contexte libre de la demande — facultatif, accepte une pièce jointe |

Le formulaire affiche lui-même la règle de format des codes payeur : « Veuillez saisir un
numéro à 7 chiffres ».

## Parcours attendu (cas nominal)

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de demande de mutation payeur.
3. Il renseigne le code et le nom du payeur actuel.
4. Il renseigne le code et le nom du payeur cible.
5. Il renseigne la date effective souhaitée de la mutation.
6. Il envoie la demande.

## Résultat attendu (cas nominal)

La demande est enregistrée : un nouveau ticket existe dans le système, avec le service
« Compta Client », et le nombre total de tickets a augmenté d'une unité.

## Cas d'erreur à couvrir

- **Code payeur mal formé** : un code payeur (actuel ou cible) qui ne contient pas
  exactement 7 chiffres est refusé — aucun ticket ne doit être créé, et le message de
  format doit rester visible.
- **Champ obligatoire manquant** : l'envoi sans l'un des champs obligatoires (nom du
  demandeur, l'un des couples code/nom payeur, date effective) est refusé — aucun ticket ne
  doit être créé.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
