# Spécification — Création d'un achat de siège social (Portail des Services)

## Contexte technique

Portail Odoo `custom_website` : `http://localhost:10017`. Modèle `helpdesk.ticket`.
Formulaire visé : `/achat_siege/{id}`.

## Besoin

Vérifier qu'un utilisateur connecté peut créer un achat de siège social en renseignant tous les champs
obligatoires, et que l'enregistrement est bien créé après soumission.

## Champs obligatoires (mesurés sur le formulaire réel)

- `partner_email`
- `name`
- `partner_name`
- `denomination`
- `type_investissement` — valeurs : new_aquisition, remplacement
- `justification`
- `amount_ht`
- `supplier_name`
- `quote_file`

## Parcours

1. Se connecter au portail.
2. Ouvrir le formulaire `/achat_siege/{id}`.
3. Renseigner tous les champs obligatoires ci-dessus avec des valeurs plausibles.
4. Soumettre le formulaire.
5. Vérifier qu'un nouvel enregistrement `helpdesk.ticket` a été créé.
