# Lot 12 — mesure avant / après (2026-09-24)

Protocole : projet 1 (Portail Sapian, base locale `localhost:10017`, copie de dev), cas 99, 101, 126 et 13,
3 tirages par cas, données isolées par campagne (`TESTPILOT_DATA_DIR`), clé API passée par l'environnement,
aucun rejeu (mode qualification). Plafond de coût de la campagne « après » : 1,7 $.

| | Avant | Après |
|---|---|---|
| Code | `master` non modifié (prompts en CRLF au checkout) | `27cc47c` (worktree `testpilot-lot12`, LF) |
| Essais valides | 12 (12 essais avortés à coût nul exclus : clé API absente) | 12 |
| Coût total | 1,500 $ (0,125 $ / essai) | 1,255 $ (0,105 $ / essai) |
| Itérations de l'agent (moyenne) | 5,33 | 4,08 |
| `conforme` au premier passage | 2 / 12 | 9 / 12 |
| `donnee_invalide` | 5 | 0 |
| `non_conforme` | 4 | 3 (tous cas 99) |
| `technical_error` | 1 | 0 |

## Essai par essai

| Cas | Tirage | Avant | Après | Coût après | Sonde (statut) |
|---|---|---|---|---|---|
| 99 | 1 | non_conforme | non_conforme | 0,161 | ok |
| 99 | 2 | non_conforme | non_conforme | 0,104 | **interrompue** |
| 99 | 3 | non_conforme | non_conforme | 0,097 | ok |
| 101 | 1 | non_conforme | conforme | 0,085 | **interrompue** |
| 101 | 2 | donnee_invalide | conforme | 0,095 | ok |
| 101 | 3 | donnee_invalide | conforme | 0,131 | ok |
| 126 | 1 | donnee_invalide | conforme | 0,098 | ok |
| 126 | 2 | donnee_invalide | conforme | 0,103 | ok |
| 126 | 3 | donnee_invalide | conforme | 0,100 | ok |
| 13 | 1 | technical_error | conforme | 0,093 | ok |
| 13 | 2 | conforme | conforme | 0,093 | ok |
| 13 | 3 | conforme | conforme | 0,095 | ok |

## « Sauvegarde automatique détectée » (statut `interrompue`), essai par essai

2 essais sur 12 (les 12 essais portent une trace de sonde) : **cas 99 tirage 2**
et **cas 101 tirage 1**. Raison relevée dans les deux : `POST http://localhost:10017/web/dataset/call_kw/res.users/read`.
Aucun autre essai n'est interrompu. La réexploration dédiée (4 formulaires du projet 1, 2 pages `/web` du projet 12)
n'a marqué aucun formulaire.

**Cette détection est un faux positif** : `res.users/read` est un appel RPC de LECTURE émis en `POST` par le client
Odoo, pas un brouillon. Les préfixes ignorés (`_ARRIERE_PLAN`) couvrent `/web/webclient/`, `/web/session/` mais pas
`/web/dataset/call_kw/<modèle>/read`. Le comportement est sûr (l'appel est abandonné, la sonde s'arrête, aucune écriture
n'atteint le serveur) mais l'information de format est perdue pour ces deux essais.

## Ce que la mesure prouve, et ce qu'elle ne prouve pas

- Les trois familles d'échecs « avant » qui relèvent du lot (valeur écrite sans avoir été observée : `FAC-2026-001`
  devenu `2026001`, produit inventé du cas 13) ont disparu sur les 12 essais.
- **Attribution non séparée** : « après » cumule la sonde (D10 bis), le bloc de formats observés, le refus des références
  inexistantes (D11), les règles 3/6/7 du prompt système et le passage en LF. Les deux essais où la sonde est
  interrompue (aucun format transmis) sont pourtant `conforme` dans un cas sur deux : une part de l'amélioration ne vient
  pas de la sonde. 3 tirages par cas restent un petit échantillon.
- Cas 99 inchangé (3 / 3 `non_conforme`) : refus silencieux non instruit, constat F10, hors périmètre du lot (lot 02).
- Les `conforme` des cas 101 et 126 sont des chemins négatifs (« une erreur de validation est affichée » +
  « le nombre de tickets n'a pas augmenté », vérification indépendante : 0 nouveau enregistrement). L'assertion prouve
  qu'une erreur s'affiche ; elle ne prouve pas que c'est le champ visé (SIREN, dates) qui la cause. Dans le cas 101
  « après » `numero_facture1` n'est pas renseigné, contrairement à « avant ».

## Masques jamais vus pendant la conception (fixture `tests/fixtures/torture_app/masques.html`, Chromium réel)

| Champ | Résultat |
|---|---|
| Téléphone par paires (10 chiffres) | exemple stable trouvé : `12 34 56 78 90` |
| Carte par groupes de 4 | exemple stable trouvé : `1234` |
| IBAN à préfixe de lettres | aucun exemple (limite assumée : la sonde tape des chiffres) |
| Champ sans masque | aucune observation |

## Réexploration (sonde active, données isolées)

- Premier passage sur `8339179` : `retenue_garantie/1` en statut `erreur` (Playwright refuse les lettres dans un
  `type=number`, le formulaire entier échouait). Corrigé par `27cc47c`, test réel `ebc8d46`.
- Deuxième passage sur `27cc47c` : `retenue_garantie/1` sondé sur 6 champs, `formulaire/1`, `/71`, `/72` sondés (1 champ),
  aucune sauvegarde automatique détectée. Projet 12 : pages `/web#action=179` et `#action=907`, aucune sonde tentée
  (attendu : back-office Odoo).
- Vérification RPC après réexploration : 420 modèles contrôlés, aucune création métier sur la fenêtre (5 lignes
  `res.users.log`, connexions).
