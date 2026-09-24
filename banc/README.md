# Banc de mesure de la fiabilité du verdict (lot 04)

Une instance Odoo de RÉFÉRENCE jetable, dont on CONNAÎT les défauts : on peut alors affirmer qu'un statut est vrai (ou
faux) au lieu de le croire. Le banc rend **I1 (faux PASSED)** et **I5 (blocage bien attribué)** mesurables, donc chaque
lot suivant prouvable.

⚠️ **Jamais sur une instance client.** Les défauts du module `tp_bugs_injectes` sont faits pour se tromper ; le script
de mesure refuse tout hôte qui n'est pas local.

## Démarrer

```bash
scripts/banc_init.sh 17.0              # ou .\scripts\banc_init.ps1 -Version 17.0 sous Windows ; ≈ 7 min la première fois
python scripts/banc_mesure.py --version 17.0     # mode figé : coût nul, aucun LLM (≈ 12 min)
docker compose -f compose.banc.yml down -v       # effacer le banc
```

Versions : `16.0`, `17.0`, `18.0` (Community, données de démo, images figées **par digest** dans `banc/images.env`).
Port dédié : `18069` (`BANC_PORT`), lié à `127.0.0.1` seulement. Comptes : `admin / admin`, `banc_commercial`
(Ventes / Utilisateur), `banc_manager` (Ventes / Administrateur + Stock + Facturation) — mots de passe jetables.

## Ce que contient le banc

| Chemin | Rôle |
|---|---|
| `compose.banc.yml`, `banc/images.env` | PostgreSQL + Odoo, images par digest, volume jetable |
| `scripts/banc_init.sh` / `.ps1` | crée la base `banc`, installe les modules de D9 et `tp_bugs_injectes`, `odoo neutralize`, comptes, `fr_FR` |
| `banc/odoo_addons/tp_bugs_injectes/` | 7 défauts activables un par un (`ir.config_parameter` `tp_bug.<code>` = `1`), inactifs par défaut, avec leurs tests Odoo |
| `banc/cas_figes/` | 15 cas écrits à la main (feature + steps), tenant lieu de versions approuvées — mode `figé` |
| `specs/banc/*.md` | les 15 specs correspondantes — mode `génération` |
| `specs/banc/attendus.yaml` | le statut attendu de chaque cas, instance saine / sous chaque défaut / sous chaque panne — **écrit par un humain** |
| `scripts/banc_mesure.py` | rejoue les cas et calcule I1–I6 ; sortie Markdown + JSON dans `docs/mesures/` |
| `scripts/banc_projet.py` | crée (idempotent) le projet TestPilot « Banc Odoo <version> » et l'explore |
| `scripts/banc_generation.py` | mode `génération` (LLM, plafond de coût obligatoire) |
| `.github/workflows/banc.yml` | nocturne + manuel + PR touchant le banc ; matrice 16.0 / 17.0 / 18.0 ; mode figé seulement |

## Les défauts et les pannes

| Défaut (`tp_bug.<code>`) | Effet |
|---|---|
| `vente_sans_livraison` | confirmer un devis ne crée pas de bon de livraison |
| `total_faux` | `amount_total` d'une commande de vente décalé de 1 % |
| `client_non_requis` | `partner_id` optionnel sur la commande de vente |
| `etat_bloque` | `action_confirm` laisse l'état `draft` sans erreur |
| `facture_non_postee` | la validation de facture ne passe pas en `posted` |
| `droit_trop_large` | `banc_commercial` peut supprimer une commande confirmée |
| `message_absent` | aucun message d'erreur visible sur un champ requis vide (masqué côté interface) |

| Panne | Mise en place | Attendu |
|---|---|---|
| `odoo_arrete` | `docker compose stop odoo` | `blocked` |
| `mauvais_mot_de_passe` | mot de passe erroné pour le compte du projet | `blocked` |
| `module_desinstalle` | état du module `crm` passé à `uninstalled` (le step de Contexte lit cet état ; pas de désinstallation physique — voir le rapport) | `blocked` |

## Règles de mesure

- **« Non mesuré » n'est pas « zéro »** : un indicateur sans observation vaut `non mesuré`.
- **Les attendus ne se déduisent jamais d'un run.** Si un run contredit un attendu, c'est un constat à instruire.
- **Une mesure ne modifie jamais `data/`** : elle tourne sur un dossier de données jetable (chemin dans la sortie).
- **Ne pas lancer la suite pytest et une mesure en même temps** sur le même poste.
- Ne jamais publier les indicateurs d'une mesure partielle (`--configs` est réservé à la mise au point).

## Constats du banc sur la bibliothèque de steps (Odoo 17.0 Community)

Le banc a déjà trouvé des limites de la bibliothèque, consignées dans le rapport du lot 04 : `je navigue vers le menu
Odoo` ouvre `/web#action=menu`, qui n'existe pas sur 17.0 Community ; les steps de lecture `le champ … est égal à`
échouent sur une facture (`browse().read()` d'odoorpc et sérialisation de la réponse Odoo 17).
