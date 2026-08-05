# Retenue de garantie

## Contexte

Sur le Portail des Services, un utilisateur peut demander la libération d'une retenue de
garantie sur un marché. Sa demande crée un ticket que le service comptable concerné prendra
en charge.

Le formulaire se trouve à l'adresse `/retenue_garantie/86` du portail, sous Services Métiers
→ Finance → Recouvrement → Retenue de Garantie.

## Ce qu'on veut vérifier

Qu'un utilisateur peut déposer une demande de retenue de garantie complète, que sa demande
est bien enregistrée dans le système, et que le formulaire refuse une demande dont le code
client, le SIREN ou le numéro de facture ne respectent pas le format attendu, ou à qui il
manque une pièce jointe obligatoire.

## Informations demandées par le formulaire

| Champ | Description |
|---|---|
| `agence` | L'agence concernée — liste déroulante, **facultative** |
| `nom_demandeur` | Nom du demandeur — **obligatoire**, pré-rempli par le portail |
| `code_client` | Code client — **obligatoire**, un nombre à **exactement 7 chiffres** |
| `nom_client` | Nom du client — **obligatoire** |
| `siren` | Numéro SIREN du client — **obligatoire**, un nombre à **exactement 9 chiffres** |
| `montant_ttc` | Montant TTC de la pièce — **obligatoire** |
| `date_debut_marche` | Date de début du marché — **obligatoire** |
| `date_fin_marche` | Date de fin du marché — **obligatoire** |
| `contrat_signe` | Copie du document contractuel signé par les deux parties — pièce jointe **obligatoire** |
| `pv_reception` | Copie du PV de réception de travaux sans réserve — pièce jointe **obligatoire** |
| `numero_facture` | Numéro de facture — **obligatoire**, format « groupes de 7 chiffres » (ex. `1234567/7654321`) |
| `copie_facture` | Copie de la facture — pièce jointe **obligatoire** |
| `commentaires` | Contexte libre de la demande — facultatif |

## Parcours attendu (cas nominal)

1. L'utilisateur est connecté au portail.
2. Il ouvre le formulaire de demande de retenue de garantie.
3. Il renseigne le code client et le nom du client, au format attendu.
4. Il renseigne le SIREN, au format attendu.
5. Il renseigne le montant TTC et les dates de début et de fin du marché.
6. Il joint le document contractuel signé, le PV de réception, le numéro et la copie de la
   facture, au format attendu.
7. Il envoie la demande.

## Résultat attendu (cas nominal)

La demande est enregistrée : un nouveau ticket existe dans le système, avec le service
« Recouvrement », et le nombre total de tickets a augmenté d'une unité.

## Cas d'erreur à couvrir

- **Code client ou SIREN mal formé** : un code client qui ne contient pas exactement 7
  chiffres, ou un SIREN qui n'en contient pas exactement 9, est refusé — aucun ticket ne doit
  être créé.
- **Numéro de facture mal formé** : un numéro qui ne respecte pas le format « groupes de 7
  chiffres » est refusé — aucun ticket ne doit être créé.
- **Pièce jointe obligatoire manquante** : l'envoi sans le document contractuel, le PV de
  réception ou la copie de facture est refusé — aucun ticket ne doit être créé.

## Nettoyage

Le ticket créé par le test doit être supprimé en fin de scénario.
