# Spécification — Création d'une mutation de client (Portail des Services)

## Contexte technique

Portail Odoo `custom_website` : `http://localhost:10017`. Modèle `helpdesk.ticket`.
Formulaire visé : `/mutation/{id}`.

## Besoin

Vérifier qu'un utilisateur connecté peut créer une mutation de client en renseignant tous les champs
obligatoires, et que l'enregistrement est bien créé après soumission.

## Champs obligatoires (mesurés sur le formulaire réel)

- `partner_name`
- `partner_email`
- `name`
- `code_client1`
- `nom_client`
- `mutation_code_client`
- `nouveau_nom_client`
- `date_mutation_client`
- `justificatifs_mutation`

## Parcours

1. Se connecter au portail.
2. Ouvrir le formulaire `/mutation/{id}`.
3. Renseigner tous les champs obligatoires ci-dessus avec des valeurs plausibles.
4. Soumettre le formulaire.
5. Vérifier qu'un nouvel enregistrement `helpdesk.ticket` a été créé.
