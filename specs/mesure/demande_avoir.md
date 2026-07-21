# Spécification — Création d'une demande d'avoir (Portail des Services)

## Contexte technique

Portail Odoo `custom_website` : `http://localhost:10017`. Modèle `helpdesk.ticket`.
Formulaire visé : `/demande_avoir/{id}`.

## Besoin

Vérifier qu'un utilisateur connecté peut créer une demande d'avoir en renseignant tous les champs
obligatoires, et que l'enregistrement est bien créé après soumission.

## Champs obligatoires (mesurés sur le formulaire réel)

- `partner_email`
- `name`
- `partner_name`
- `compte_client`
- `customer_name`
- `justification_demande_avoir`
- `motif_anulation_avoir`

## Parcours

1. Se connecter au portail.
2. Ouvrir le formulaire `/demande_avoir/{id}`.
3. Renseigner tous les champs obligatoires ci-dessus avec des valeurs plausibles.
4. Soumettre le formulaire.
5. Vérifier qu'un nouvel enregistrement `helpdesk.ticket` a été créé.
