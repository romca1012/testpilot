# Lot 07a — la connexion à l'exécution, mesurée sur des applications réelles (2026-09-24)

**Protocole.** Six cas écrits comme le ferait l'agent (Gherkin + un step d'assertion « je suis connecté »),
**sans aucun step de connexion**, exécutés de bout en bout par `BehaveRunner` + `Executor` (Behave et
Playwright réels, sous-processus, connecteur `web`, aucun appel LLM) contre SauceDemo et the-internet.
Les mêmes six cas sont rejoués sur `master` (avant le lot) pour référence. Script : `l07a_e2e.py`
(hors dépôt, dans le répertoire de travail de la session).

| Cas | Avant (master) | Après (lot 07a) |
|---|---|---|
| SauceDemo — identifiants valides, le cas doit être connecté | `failed` (`assertion_mismatch`) : le cas tournait **anonyme** | **`passed`** |
| SauceDemo — mot de passe du projet faux | `failed` : anonyme, puis assertion en échec | **`blocked`** (`precondition_non_remplie`), message : « la connexion n'a pas abouti… message affiché : « Epic sadface: Username and password do not match… » » |
| SauceDemo — cas qui teste la connexion (« … sans me connecter », mauvais mot de passe saisi) | `retest` (`technical_error` : step inexistant) | **`passed`** |
| the-internet — identifiants valides | `failed` : anonyme | **`passed`** |
| the-internet — mot de passe du projet faux | `failed` | **`blocked`**, message : « … message affiché : « Your password is invalid! × » » |
| the-internet — cas qui teste la connexion | `retest` (step inexistant) | **`passed`** |

Lecture : avant le lot, un cas « connecté » échouait pour la mauvaise raison (application testée en
anonyme) ; un mauvais mot de passe du projet n'était même pas signalé. Après, le premier passe, le second
est **bloqué** (jamais `failed`, jamais `technical_error`) avec l'URL, le schéma tenté et le message que
l'application a affiché, et le cas qui teste la connexion ne se retrouve pas connecté d'office.

## Le critère par défaut suffit seul (demande du porteur)

Critère : l'URL a quitté la page de connexion **et** aucun champ mot de passe n'est plus visible. Aucun
sélecteur « connecté » n'est lu (il n'existe d'ailleurs aucun réglage de projet pour cela). Vérifié en
navigateur réel (`pytest -m conformance tests/test_conformite_connexion_execution.py`, **12 passés**) sur
trois applications :

| Application | Connexion valide | Mauvais mot de passe |
|---|---|---|
| SauceDemo (React, un écran) | `/` → `/inventory.html`, plus de mot de passe → réussie | même URL, mot de passe encore là → refusée |
| the-internet (Sinatra, un écran) | `/login` → `/secure` → réussie | redirigée vers la même `/login` → refusée |
| fixture « torture » (deux écrans, `tests/fixtures/torture_app/`) | `login1.html` → `dashboard.html` → réussie | `login2.html?u=…` : l'URL a bougé mais le mot de passe reste → refusée (**les deux conditions sont nécessaires**) |

## Limite constatée en passant

the-internet met 25 à 29 s à atteindre `domcontentloaded` depuis ce poste (mesuré : 29,0 / 26,9 / 24,6 s,
alors que `curl` répond en 1,3 s — une ressource tierce bloquante). Les tests de conformité utilisent donc un
délai de page de 60 s ; ce n'est pas un défaut du lot.
