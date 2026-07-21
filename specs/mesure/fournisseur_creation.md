# Spécification — La création d'un fournisseur (Portail des Services)

## Contexte technique

Portail Odoo `custom_website` : `http://localhost:10017`. Modèle `helpdesk.ticket`.
Formulaire visé : `/fournisseur/creation/{id}`.

## Besoin

Vérifier qu'un utilisateur connecté peut enregistrer la création d'un fournisseur en renseignant tous les
champs obligatoires du formulaire, et que l'enregistrement est bien créé après soumission.

## Champs obligatoires saisissables (mesurés sur le formulaire réel)

- `partner_name`
- `nom_fournisseur`
- `raison_sociale`
- `adresse_id`
- `cp_id`
- `city`
- `siret_fournisseur`
- `tva_intracommunautaire`
- `categorie_achats` — valeurs : , biens_et_services, immobilisations, sous_traitance
- `piece_jointe_rib` — pièce jointe
- `piece_jointe_kbis` — pièce jointe
- `email_envoi_avis`
- `piece_jointe` — pièce jointe
- `phone_contact_comptable`

## Parcours

1. Se connecter au portail.
2. Ouvrir le formulaire `/fournisseur/creation/{id}`.
3. Renseigner tous les champs obligatoires ci-dessus avec des valeurs plausibles.
4. Soumettre le formulaire.
5. Vérifier qu'un nouvel enregistrement `helpdesk.ticket` a été créé.
