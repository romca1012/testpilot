# Rapport de continuité — la connexion automatique via formulaire enregistré n'aboutit pas

Pour reprendre le débogage dans une nouvelle session, en local, sans repasser par le cycle
push → PR → CI → déploiement à chaque essai (trop lent, cause de ce rapport).

⚠️ **Ce n'est pas un problème propre à un seul projet.** Le mécanisme en cause
(`remplir_et_soumettre_formulaire_connexion` / le crawl du connecteur `web` générique) est
générique, partagé par tous les projets qui l'utilisent. `yros` est simplement le cas où on l'a
observé et mesuré en premier — ne pas restreindre l'investigation à ses spécificités (son URL,
son wording) tant que la cause réelle n'est pas isolée. Le même test devrait être refait sur au
moins un second projet une fois une hypothèse confirmée sur `yros`, pour vérifier qu'elle
généralise.

## Le problème, en une phrase

Sur un projet `web` où le formulaire de connexion a été enregistré (3 clics guidés : champ
identifiant, champ mot de passe, bouton), le formulaire se remplit et se soumet **sans lever
d'erreur**, mais l'exploration qui suit ne débloque aucun contenu authentifié — sur le cas mesuré
(`yros`), elle ne trouve toujours que **3 routes** (`/`, `/login`, `/mot-de-passe-oublie`),
exactement comme AVANT que la connexion n'existe. La connexion **manuelle**, elle, fonctionne
(confirmé par le porteur avec les vrais identifiants du projet `yros`).

## Ce qui est CONFIRMÉ (par mesure, pas par supposition)

1. **La capture a réussi** : les 3 champs (identifiant = « Adresse email », mot de passe = « Mot
   de passe », bouton = « Se connecter ») ont été identifiés et confirmés — visible dans l'écran
   « Enregistrer la connexion », capture d'écran à l'appui.
2. **Le rejeu ne lève AUCUNE exception** (mesuré sur `yros`) : aucun `FormulaireConnexionObsoleteError`
   dans les logs serveur — donc `page.get_by_role(role, name=..., exact=True)` retrouve bien les 3
   éléments de façon unique, les remplit, et clique le bouton, sans timeout ni ambiguïté.
3. **La connexion manuelle marche** (testée par le porteur avec les vrais identifiants sur
   `https://yros-portail.agilicis.com/login`) — donc ce ne sont ni de mauvais identifiants, ni un
   refus de l'application.
4. **Hypothèse « divergence placeholder vs `get_by_role` » écartée empiriquement** : un test isolé
   (page HTML minimale, un seul champ `<input placeholder="Email">` sans `<label>`) montre que
   `get_by_role("textbox", name="Email", exact=True)` retrouve bien ce champ — Playwright compte
   donc le `placeholder` dans le nom accessible, au moins dans ce cas simple. Ne pas re-explorer
   cette piste sans nouvelle preuve contraire sur la VRAIE page `yros`.
5. **Le job Sapian (« Portail Sapian - Intégration », projet id 2, Odoo) qui a échoué avec
   `FormulaireConnexionObsoleteError` (« champ_identifiant introuvable ou ambigu ») n'est PAS
   l'urgence actuelle** : `SELECT login_form_json FROM project_login_recording WHERE
   project_id=2` sur la base de staging rend une valeur VIDE — soit ce job date d'avant, soit le
   porteur a depuis recommencé sans les 3 clics guidés. À revérifier si Sapian re-échoue, mais ne
   pas supposer que c'est encore actif.

## Ce qui reste à découvrir (hypothèses NON vérifiées, dans l'ordre le plus probable)

1. **SPA sans navigation détectable** (hypothèse générique, pas spécifique à `yros`) : le crawl
   (`scripts/crawl_domaine.py`, appelé depuis `exploration_service._crawl`) découvre les pages via
   `document.querySelectorAll('a[href]')` (fonction `_liens_visibles` dans `_web_helpers.py`). Toute
   application React/Vue qui change de route côté client SANS vrais `<a href>` (navigation par
   bouton + JS) échapperait de la même façon au crawl, connectée ou non — ce n'est pas un trait de
   `yros` en particulier, plutôt une limite structurelle du crawler qui toucherait n'importe quel
   projet construit ainsi. **Test décisif** : après connexion manuelle (sur `yros`, ou un autre
   projet touché), ouvrir l'inspecteur du navigateur sur la page qui suit et vérifier si les
   éléments de navigation sont des `<a href="...">` ou des `<button>`/`<div onClick>`.
2. **Timing / connexion asynchrone** : `remplir_et_soumettre_formulaire_connexion` (dans
   `src/testpilot/connectors/_web_helpers.py`) clique le bouton puis appelle
   `page.wait_for_load_state("networkidle")` et rend la main. Si l'authentification réelle se fait
   par un appel réseau (fetch/XHR) suivi d'une redirection CÔTÉ CLIENT (History API, sans nouvelle
   requête réseau), `networkidle` peut se résoudre AVANT que la redirection n'ait eu lieu — le
   crawl démarrerait alors depuis la page de login, pas depuis la page post-connexion.
3. **Le point d'entrée du crawl (`crawl_roots`)** ne re-vérifie peut-être pas où la page a
   atterri après la tentative de connexion — à relire dans `connectors/base.py`
   (`Connector.crawl_roots`, défaut générique) et `scripts/crawl_domaine.py::crawler`.

## Instrumentation déjà en place (pas encore mergée)

PR #48 (`fix-yros-diagnostic-connexion`, branche poussée sur `origin`) ajoute UNE ligne de log,
sans changement de comportement, dans `src/testpilot/connectors/generic_web.py::crawl_relogin_hook` :

```python
logger.info("[web-générique] après tentative de connexion : url=%s", getattr(ctx.page, "url", "?"))
```

Elle répond à la question : **sur quelle URL la page est-elle exactement, juste après le clic sur
« Se connecter » ?** Si c'est encore une URL de login → la connexion échoue réellement (hypothèse
2, ou une raison encore non identifiée). Si c'est une URL post-connexion → c'est le crawl qui ne
voit rien de nouveau (hypothèse 1).

CI de cette PR a flaké sur un test SANS RAPPORT avec ce changement (`Page.screenshot: Protocol
error`, dans `test_live_session_ws.py`, un test de session live, alors que le diff ne touche que
`generic_web.py`) — relancé, résultat pas encore connu au moment d'écrire ce rapport.

## Reproduire en LOCAL (ce que la prochaine session doit faire directement, sans CI)

1. `git fetch origin fix-yros-diagnostic-connexion && git checkout fix-yros-diagnostic-connexion`
   (contient déjà la ligne de log ci-dessus, en plus de tout ce qui est déjà sur `master`).
2. Lancer l'API en local (`uvicorn testpilot.api.app:app --reload --port 8010` — le port 8000 est
   occupé par un processus fantôme connu sur la machine Windows du porteur, voir
   `frontend/src/lib/api.ts:5-8`) et le frontend (`npm run dev` dans `frontend/`).
3. Créer/retrouver le projet `yros` en local (même URL réelle `https://yros-portail.agilicis.com`,
   mêmes identifiants réels) — l'app cible est un vrai site externe, accessible depuis n'importe
   quelle machine avec accès réseau sortant, pas seulement depuis le serveur de staging. Une fois
   une piste confirmée sur `yros`, la reproduire sur un second projet `web` avec formulaire
   enregistré pour vérifier qu'elle généralise (voir l'avertissement en tête de rapport).
4. Relancer une exploration et regarder directement les logs de `uvicorn` dans le terminal (plus
   besoin de SSH/`docker logs` : c'est un simple `print`/log en local) — chercher la ligne
   `[web-générique] après tentative de connexion : url=...`.
5. Si besoin d'aller plus loin, ajouter un `page.screenshot(path=...)` temporaire juste après la
   tentative de connexion, dans `crawl_relogin_hook` (`generic_web.py`) — en local, aucun coût de
   cycle CI pour itérer sur ce genre d'instrumentation.

## Fichiers clés pour cette investigation

- `src/testpilot/connectors/generic_web.py` — `crawl_relogin_hook`, `_tenter_connexion_generique`
  (point d'entrée de la tentative de connexion pendant l'exploration).
- `src/testpilot/connectors/_web_helpers.py` — `remplir_et_soumettre_formulaire_connexion`,
  `rejouer_sequence_connexion` (le mécanisme de rejeu lui-même).
- `src/testpilot/api/services/exploration_service.py` — `_crawl` (démarre le BFS après
  `crawl_relogin_hook`).
- `scripts/crawl_domaine.py` — `_liens_visibles`, `crawler` (la découverte de pages elle-même,
  candidate n°1 si l'hypothèse SPA se confirme).

## État Git au moment de ce rapport

- `master` (`c630434`) : capture guidée du formulaire + essai Odoo, mergé et déployé sur `/dev` et
  `/staging`.
- PR #48 (`fix-yros-diagnostic-connexion`) : la ligne de log diagnostic ci-dessus, ouverte, CI en
  cours de relance après un flake sans rapport.
- Ce rapport est sur la même branche que la PR #48 s'il a été poussé (à vérifier), ou disponible
  en pièce jointe directe si la session s'est arrêtée avant de pousser.
