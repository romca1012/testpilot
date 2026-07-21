# Spécification — La déclaration d'un sinistre client (Portail des Services)

## Contexte technique

Portail Odoo `custom_website` : `http://localhost:10017`. Modèle `helpdesk.ticket`.
Formulaire visé : `/sinistre_client/{id}`.

## Besoin

Vérifier qu'un utilisateur connecté peut enregistrer la déclaration d'un sinistre client en renseignant tous les
champs obligatoires du formulaire, et que l'enregistrement est bien créé après soumission.

## Champs obligatoires saisissables (mesurés sur le formulaire réel)

- `agence` — valeurs : 
- `partner_name`
- `code_client1`
- `nom_client`
- `info_sinistre_ids`
- `info_sinistre_ids`
- `info_sinistre_ids`
- `info_sinistre_ids`
- `justificatifs_mutation` — pièce jointe
- `amount_sinistre`
- `nom_cheque`
- `destinataire_name`
- `adresse_id`
- `cp_id`
- `city`

## Parcours

1. Se connecter au portail.
2. Ouvrir le formulaire `/sinistre_client/{id}`.
3. Renseigner tous les champs obligatoires ci-dessus avec des valeurs plausibles.
4. Soumettre le formulaire.
5. Vérifier qu'un nouvel enregistrement `helpdesk.ticket` a été créé.
