# Spécification — Le passage d'un client en contentieux (Portail des Services)

## Contexte technique

Portail Odoo `custom_website` : `http://localhost:10017`. Modèle `helpdesk.ticket`.
Formulaire visé : `/client_contentieux/{id}`.

## Besoin

Vérifier qu'un utilisateur connecté peut enregistrer le passage d'un client en contentieux en renseignant tous les
champs obligatoires du formulaire, et que l'enregistrement est bien créé après soumission.

## Champs obligatoires saisissables (mesurés sur le formulaire réel)

- `partner_name`
- `code_client1`
- `name_customer`
- `siren`
- `amount_creance`
- `ref_doc`
- `copy_doc` — pièce jointe
- `numero_facture1`
- `copy_invoice_part` — pièce jointe

## Parcours

1. Se connecter au portail.
2. Ouvrir le formulaire `/client_contentieux/{id}`.
3. Renseigner tous les champs obligatoires ci-dessus avec des valeurs plausibles.
4. Soumettre le formulaire.
5. Vérifier qu'un nouvel enregistrement `helpdesk.ticket` a été créé.
