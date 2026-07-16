# 0010 — Un step de vérification de la bibliothèque PARTAGÉE ne vérifie rien (`pass`)

Date : 2026-07-16
Statut : **DÉCIDÉ et LIVRÉ**
Famille : **même profil que `0008`** (assertion infalsifiable → faux « conforme »), mais **dans la
bibliothèque partagée**, pas dans du code généré. C'est ce qui change tout.

---

## Le défaut

`behave_runtime/steps_library/_base_steps.py` :

```python
@then("aucun enregistrement inattendu n'est créé dans aucun modèle Odoo "
      "comme effet de bord de cette action")
def step_no_side_effects(context):
    pass
```

Ce step de **vérification** ne vérifie **rien**. Il passe quoi que fasse l'application. Un scénario
qui l'emploie croit contrôler l'absence d'effets de bord et ne contrôle rien : c'est un
`conforme` **déclaratif** (§4.2) et une fabrique à **faux-négatifs**, que §4.4 déclare
**inacceptables**.

## Pourquoi c'est plus grave que `0008`

| | `0008` (écart 2) | `0010` (celui-ci) |
|---|---|---|
| Où | code **généré** pour un cas | **bibliothèque partagée** |
| Portée | le cas concerné | **tout cas qui réutilise le step** |
| Remède | prompt + lint au gate | le step lui-même |

`0008` corrigeait une tautologie écrite **une fois** par l'agent. Ici, le step est **au
catalogue** — donc **montré à l'agent dans le prompt et proposé à la réutilisation** (`0003`). Le
pipeline **invite** à s'appuyer sur une vérification creuse. Pire : `0003` a précisément appris à
l'agent à réutiliser la bibliothèque **plutôt que** d'écrire du custom — un step custom écrit à la
main, lui, aurait été passé au lint du gate.

## Comment il a été trouvé

**Effet de bord de l'audit d'import de `testpilot-agent`** : en passant le lint `0008` sur les
steps de l'ancien projet, 5 avertissements sont sortis. Vérification sur **notre** bibliothèque :
**exactement les mêmes 5, aux mêmes lignes** — l'ancien projet n'y était pour rien, c'est notre
héritage commun (§2.6, la bibliothèque a été reprise telle quelle).

⚠️ **Le lint `0008` le signalait donc depuis toujours. Personne n'avait passé le lint sur la
bibliothèque** : il n'est branché que sur les steps de la **version d'un cas**, au gate. C'est
l'angle mort — le lint garde le code *généré*, jamais le socle *partagé* qu'on lui demande de
réutiliser.

**Portée du dégât, mesurée** : le step est au catalogue, mais **aucun cas ne l'utilise**
aujourd'hui (0 dans `generated/`, 0 en base). Le dégât est donc **nul à ce jour** ; le risque
était **entièrement devant nous** — d'où l'ordre du porteur : corriger **avant** l'import des 4
nouveaux modules, sinon les régénérations auraient pu s'en saisir.

Sur les 5 avertissements, **4 sont des faux positifs** : le step **délègue** à un helper qui
assertit (`no_duplicate` → `assert len(ids) <= 1`, `validation_error_inline` →
`assert has_error.is_visible()`), ou c'est une **attente** portant un double décorateur
`@when`/`@then` (`j'attends la soumission du formulaire`). Le lint ne suit pas les appels : limite
connue et **assumée** (il reste un signal indicatif, non bloquant — invariant `0008`).

## Décision — SUPPRIMER le step, ne pas l'implémenter

**Implémenter est intenable, et c'est le cœur du problème.** Le libellé promet « aucun
enregistrement inattendu dans **aucun modèle Odoo** » : cela demanderait un instantané avant/après
de **tous** les modèles (des centaines), lent et **structurellement faux-positif** — journaux,
séquences, `mail.message` bougent à chaque action. **La promesse du libellé n'est pas tenable** ;
un step qui ne peut pas tenir sa promesse ne doit pas exister. Le `pass` n'était pas un oubli :
c'était la seule façon de faire « passer » une promesse impossible.

**Le besoin réel est déjà couvert**, par des steps **ciblés et honnêtes** (par modèle) qui, eux,
vérifient vraiment :
- `le nombre total d'enregistrements dans le modèle "{model}" n'a pas augmenté`
- `aucun enregistrement partiel avec le champ "{field}" vide n'est persisté dans le modèle "{model}"`
- `aucun enregistrement en double avec le champ "{field}" égal à "{value}" n'existe dans le modèle "{model}"`

**Suppression sans risque** : aucun cas ne l'utilise (mesuré). Supprimer un step utilisé aurait
cassé les cas concernés en `undefined` — ce n'est pas le cas ici.

Même raisonnement que les colonnes mortes de la migration 7 et que la colonne `module` de `0004` :
**on supprime, on ne laisse pas inerte**.

## Ce qu'on ne fait PAS

- **Pas de step « effet de bord » réécrit à la va-vite** sur un modèle unique : ce serait un
  quasi-doublon de `le nombre total … n'a pas augmenté` (volet C de `0003`, écarté).
- **Pas de branchement du lint sur la bibliothèque** dans cette note : l'angle mort est réel
  (§ *Suite*), mais le lint a 4 faux positifs par délégation — le brancher tel quel crierait au
  loup sur du code sain. À traiter séparément si le besoin se confirme.

## Suite à donner (non fait ici)

- **Angle mort du lint** : il ne regarde que le code généré, jamais la bibliothèque partagée. Le
  corriger suppose d'abord de lui apprendre la **délégation** (un `@then` qui appelle un helper
  qui assertit **est** falsifiable), sinon 4 faux positifs. À arbitrer.
