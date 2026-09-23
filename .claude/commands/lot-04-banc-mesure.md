---
description: Lot 04 — Instance Odoo de référence, bugs et pannes injectés, indicateurs I1-I6 (C8)
argument-hint: "[version Odoo : 16.0 | 17.0 | 18.0 — défaut 17.0]"
---

# Lot 04 — Banc de mesure de la fiabilité du verdict

Lis `CLAUDE.md`, §3 (indicateurs) et C8 du plan. Décision requise : **D9**.
Version ciblée en premier : `$ARGUMENTS` (défaut `17.0`). Branche : `lot-04-banc-mesure`.

## Pourquoi

On ne peut pas affirmer qu'un statut est vrai sans une application dont on **connaît** les
défauts. Aujourd'hui la fiabilité Odoo ne se mesure que sur une recette client partagée et
mouvante. Ce banc rend I1 (faux PASSED) mesurable, donc chaque lot suivant prouvable.

## À lire d'abord

- `compose.production.yml`, `Dockerfile`, `.github/workflows/conformance.yml`, `ci.yml`.
- `scripts/audit_generation_quality.py` (méthode de mesure existante, à réutiliser).
- `scripts/crawl_domaine.py`, `src/testpilot/generation/domain_model.py`.
- `specs/mesure/` et `specs/vert/` (format des specs).
- `src/testpilot/api/services/run_service.py`, `campaign_service.py` (comment lancer un cas).

## Travail

1. **`compose.banc.yml`** : `postgres:16` + `odoo:<version>` (images figées **par digest**), port
   dédié, volume de données jetable. Script `scripts/banc_init.sh` (et `.ps1` pour le poste
   Windows) : crée la base `banc` avec données de démo, installe les modules de D9 et
   `tp_bugs_injectes`, exécute `odoo neutralize` (≥ 16), crée deux comptes de test
   (`banc_commercial` : Ventes/Utilisateur, `banc_manager` : Ventes/Administrateur + Stock +
   Facturation), fixe la langue `fr_FR` pour les deux.
2. **Module `banc/odoo_addons/tp_bugs_injectes/`** : défauts activables un par un par
   `ir.config_parameter` `tp_bug.<code>` = `1`, inactifs par défaut. Au minimum :
   - `vente_sans_livraison` : confirmer un devis ne crée pas de bon de livraison ;
   - `total_faux` : `amount_total` d'une commande de vente décalé de 1 % ;
   - `client_non_requis` : `partner_id` optionnel sur la commande de vente ;
   - `etat_bloque` : `action_confirm` laisse l'état `draft` sans erreur ;
   - `facture_non_postee` : la validation de facture ne passe pas en `posted` ;
   - `droit_trop_large` : `banc_commercial` peut supprimer une commande confirmée ;
   - `message_absent` : pas de message d'erreur visible sur un champ requis vide.
   Chaque défaut est écrit pour être compatible 16/17/18 (sinon, marqué non applicable).
3. **Pannes d'environnement injectables** (pour I5), pilotées par `scripts/banc_mesure.py` :
   Odoo arrêté, mauvais mot de passe du compte, module requis désinstallé.
4. **Corpus `specs/banc/`** : 12 à 15 specs couvrant vente, achat, stock, facturation, CRM,
   droits d'accès, champ requis, portail. Fichier `specs/banc/attendus.yaml` :
   pour chaque spec, le statut attendu instance saine et le statut attendu sous chaque défaut
   qui la concerne. Les attendus sont écrits **par un humain** (toi, puis relus par le porteur),
   jamais déduits d'un run.
5. **`scripts/banc_mesure.py`** : deux modes.
   - `--mode figé` : rejoue des versions **déjà approuvées** (aucun appel LLM, coût nul) sur
     l'instance saine puis sous chaque défaut et chaque panne → mesure le harnais et le verdict.
   - `--mode génération` : régénère les cas depuis les specs puis exécute → mesure l'agent
     (I3, I4, I6). Plafond de coût explicite en argument, arrêt si dépassé.
   Sortie : tableau I1-I6 + détail par spec, en Markdown dans
   `docs/mesures/banc-<version>-<date>.md` et en JSON à côté. Même discipline que
   `audit_generation_quality.py` : distingue « non mesuré » de « zéro ».
6. **Projet TestPilot du banc** : script qui crée (idempotent) le projet `Banc Odoo <version>`
   pointant sur l'instance, lance l'exploration et versionne `data/domain/projet-<id>.json`.
7. **CI** : `.github/workflows/banc.yml`, nocturne + manuel, matrice 16.0/17.0/18.0, mode
   `figé` uniquement (pas de coût LLM en CI). Échec du job si I1 > 0 ou I5 < 100 %.

## Tests exigés

- Tests unitaires de `banc_mesure.py` sur des résultats simulés : calcul de chaque indicateur,
  « non mesuré » ≠ 0, un faux PASSED fait échouer le code de sortie.
- Test Odoo du module (`odoo --test-tags tp_bugs_injectes`) : chaque défaut activé produit bien
  l'effet décrit, désactivé ne change rien.

## Critères d'acceptation

- [ ] `docker compose -f compose.banc.yml up -d` + `banc_init` aboutissent sur 17.0 en < 10 min.
- [ ] Mesure initiale publiée (mode figé et mode génération) **avant** tout autre lot de
      couverture : c'est la ligne de base. Si les lots 01-03 sont déjà faits, mesure aussi sur le
      commit qui les précède pour montrer leur effet.
- [ ] Workflow `banc.yml` vert sur au moins une version, les autres documentées si en échec.

## Interdits

- Pointer le banc sur une instance client.
- Écrire un attendu en regardant le résultat du run.

Rapport au format `CLAUDE.md` §10 ; lance `verdict-reviewer`.
