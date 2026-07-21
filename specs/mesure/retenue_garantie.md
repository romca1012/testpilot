# Spécification — Une demande de retenue de garantie (Portail des Services)

## Contexte technique

Portail Odoo `custom_website` : `http://localhost:10017`. Modèle `helpdesk.ticket`.
Formulaire visé : `/retenue_garantie/{id}`.

## Besoin

Vérifier qu'un utilisateur connecté peut enregistrer une demande de retenue de garantie en renseignant tous les
champs obligatoires du formulaire, et que l'enregistrement est bien créé après soumission.

## Champs obligatoires saisissables (mesurés sur le formulaire réel)

- `partner_name`
- `code_client1`
- `nom_client`
- `numero_siren`
- `montant_ttc_marche`
- `date_debut`
- `date_fin`
- `piece_jointe_facture` — pièce jointe
- `rib_original` — pièce jointe
- `numero_facture1`
- `copy_invoice_part` — pièce jointe

## Parcours

1. Se connecter au portail.
2. Ouvrir le formulaire `/retenue_garantie/{id}`.
3. Renseigner tous les champs obligatoires ci-dessus avec des valeurs plausibles.
4. Soumettre le formulaire.
5. Vérifier qu'un nouvel enregistrement `helpdesk.ticket` a été créé.
