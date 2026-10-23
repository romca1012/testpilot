"""Orchestrateur mince du pilier generation.

``generate(plan)`` : assemble prompt + contexte, lance la boucle ReAct, construit le
GenerationResult, et (si des repos sont fournis) persiste la version + pose le statut de
validation « en attente de relecture ». N'exécute jamais le test et n'appelle jamais le
gate de relecture — il ne fait qu'exposer l'information pour que ``verdict`` s'y branche.
"""

from __future__ import annotations

import logging

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.analysis.spec_analyzer import spec_hash
from testpilot.generation import domain_model
from testpilot.generation import prompt as prompt_mod
from testpilot.generation import steps_library
from testpilot.generation.interfaces import Connector, DryRunner
from testpilot.generation.react_loop import run_loop
from testpilot.generation.state import AgentState, GenerationResult
from testpilot.store.repositories import ensure_default_module
from testpilot.generation.tools import ToolContext
from testpilot.parametres.ia_peut_agir import ia_peut_ecrire
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)



class GenerationAgent:
    def __init__(self, *, llm: LLMAdapter | None = None, connector: Connector | None = None,
                 dry_runner: DryRunner | None = None, cost_tracker: CostTracker | None = None,
                 case_repo=None, version_repo=None, max_iterations: int | None = None,
                 stall_limit: int | None = None):
        self.llm = llm or LLMAdapter()
        self.connector = connector
        self.dry_runner = dry_runner
        self.cost_tracker = cost_tracker or CostTracker()
        self.case_repo = case_repo
        self.version_repo = version_repo
        self.max_iterations = max_iterations if max_iterations is not None else config.MAX_ITERATIONS
        self.stall_limit = stall_limit if stall_limit is not None else config.REPAIR_STALL_LIMIT

    @staticmethod
    def _formes_oracle(modele: dict | None, projet: dict | None) -> dict | None:
        """Lot VH-08 (A51) : les formes relevées à l'exploration, seulement pour les requêtes ENCORE déclarées et si
        l'interrupteur est allumé. Éteint : None, le message est celui d'avant, octet pour octet."""
        from testpilot.generation import interrupteurs
        if not interrupteurs.forme_oracle_actif():
            return None
        declarees = set((projet or {}).get("oracle_requetes_disponibles") or ())
        formes = (modele or {}).get("formes_oracle") or {}
        return {nom: f for nom, f in formes.items() if nom in declarees} or None

    def generate(self, plan: TestPlan, *, case_id: int | None = None,
                 title: str = "", author: str = "", module_id: int | None = None,
                 metier: dict | None = None, group_id: int | None = None,
                 projet: dict | None = None, refs: str = "",
                 failure_context: list[dict] | None = None,
                 qualification: bool = False, regeneration: bool = False,
                 valeurs_d_essai: dict | None = None,
                 regeneration_apres_defaut: dict | None = None,
                 variables_des_lignes=None, intention: str | None = None,
                 modele_du_cas=None, ecrit_pour: dict | None = None) -> GenerationResult:
        """`metier` — le document métier VALIDÉ (passe 4b de `0022`). Présent, il fixe le périmètre
        du Gherkin et se fige DANS la version, avec lui (décision n°10 : une version = le cas
        entier). Absent, le comportement est celui d'avant (chemin CLI et cas legacy).

        `projet` — le projet testé, qui porte SA cartographie du domaine. Sans lui, aucun annuaire
        n'est chargé : l'agent explore comme avant, sans contrainte inventée.

        `refs` — nom de la user story dont ce cas est issu (§9, génération multi-cas). Écrit tel
        quel sur le CAS (champ `refs`, texte libre comme TestRail), jamais versionné.

        `regeneration` — voir `prompt.build_initial_message` (F26) : coupe le rappel de la
        spécification brute d'origine quand le métier transmis peut porter une correction propre
        à ce cas.

        `regeneration_apres_defaut` (revue A62, 2026-10-20) — `{execution_id, version_id}` quand on régénère un test dont la
        dernière exécution a trouvé un défaut FONCTIONNEL : fait consigné dans la provenance, lu par les points de
        vigilance (`generation_service._verification_changee_apres_defaut`) — jamais montré à l'agent.

        `variables_des_lignes`, `intention` (étape 2, A61) — pour le contrôle de fin d'écriture : les variables que les
        lignes du cas font varier, et ce que le cas DÉCLARE tester (`generation_service._intention_declaree`). Absents :
        aucune variable, et l'intention lue dans `metier`.

        `valeurs_d_essai` (IT-3b) — la première ligne propre au cas, posée par-dessus le jeu « Par défaut » pour l'essai sur
        le bac à sable (comme l'exécution la jouerait). Jamais montrée : masquée dans tout ce qui revient à l'agent."""
        state = AgentState(module_name=plan.module_name)
        # L'annuaire du domaine alimente la CONTRAINTE de complétude (champs requis + obligation
        # de soumettre). Jusqu'ici seul le GATE le lisait : la génération devait deviner les
        # champs requis « par observation », d'où sa variabilité (2 champs sur 8 au tirage du
        # 2026-07-19). Best-effort : absent ⇒ message d'avant, aucune contrainte inventée.
        # ⚠️ Il est propre au PROJET (son instance), plus au type de connecteur : deux projets
        # Odoo distincts n'ont ni les mêmes routes ni les mêmes champs.
        # Étape 4, morceau 7 : `modele_du_cas` (interrupteur allumé, cas joué avec un autre compte) — les écrans de ce compte.
        # Absent : exactement le modèle d'avant.
        modele = modele_du_cas.modele if modele_du_cas is not None else domain_model.charger_modele(projet)
        compte_du_test = ({**modele_du_cas.compte, "vue": modele_du_cas.vue}
                          if modele_du_cas is not None and modele_du_cas.compte else None)
        # Revue finale : des lignes à compte — UNE consigne (celle des lignes, qui dit déjà le compte des lignes vides), jamais
        # deux contradictoires ; elle dit de qui sont les écrans fournis.
        lignes_a_compte = modele_du_cas.comptes_des_lignes if modele_du_cas is not None else []
        ecrans_de = ((modele_du_cas.compte or {}).get("libelle") if modele_du_cas is not None and modele_du_cas.vue == "compte"
                     else "principal")
        if lignes_a_compte:
            compte_du_test = None
        # Lot PT-02d : les noms des variables de test (interrupteur éteint : liste vide, message d'avant).
        from testpilot.generation import variables_de_test
        variables, valeurs_par_defaut = variables_de_test.pour_l_agent(projet)
        # Lot PT-02f (A39) : le cas fait foi — l'agent ne voit que les variables que le cas cite (plus celles que le test
        # actuel emploie déjà, A41) et doit toutes les employer. Interrupteur éteint : `variables` inchangées.
        variables, variables_requises, controle_du_cas = variables_de_test.du_cas(
            variables, metier,
            (metier or {}).get("variables_deja_dans_le_test") or (),
            (projet or {}).get("variables_de_test_a_la_corbeille") or ())
        informee = _informee(plan, projet, metier)
        state.messages.append({"role": "user",
                               "content": prompt_mod.build_initial_message(
                                   plan, modele, metier, comptes=(projet or {}).get("comptes_libelles"),
                                   oracle=(projet or {}).get("oracle_requetes_disponibles"),
                                   regeneration=regeneration, variables=variables,
                                   formes_oracle=self._formes_oracle(modele, projet),
                                   **({"compte_du_test": compte_du_test} if compte_du_test else {}),
                                   **({"comptes_des_lignes": lignes_a_compte, "ecrans_de": ecrans_de}
                                      if lignes_a_compte else {}),
                                   **({"informee": informee} if informee else {}))})
        if failure_context:
            state.messages[0]["content"] = [
                {"type": "text", "text": state.messages[0]["content"]}, *failure_context]
        # Un seul catalogue pour les deux usages : ce qu'on MONTRE à l'agent (prompt) et ce
        # qu'on lui REFUSE à l'écriture (redéfinition). Cf. décision 0003.
        # Scopé au connecteur DU PROJET (Phase 1c) : sans ça, un futur 2e connecteur verrait
        # (et se ferait bloquer par) les steps spécifiques à un autre — faux positif AmbiguousStep.
        connector_type = (projet or {}).get("connector_type")
        # Version DÉCLARÉE de l'instance (migration 38) — simple contexte informatif transmis au
        # prompt, jamais une contrainte : vide (indéterminée) ⇒ aucune mention.
        connector_version = (projet or {}).get("connector_version", "")
        shared_steps = steps_library.catalogue(
            connector_type=connector_type, profil_instance=(projet or {}).get("profil_instance"))
        ctx = ToolContext(
            module_name=plan.module_name,
            generated_dir=config.GENERATED_DIR,
            connector=self.connector,
            reserved_steps=frozenset(s.label for s in shared_steps),
            # Migration 45 (2026-09-16) : décision du PROJET, jamais un défaut du connecteur ; pour Odoo, il doit AUSSI se
            # déclarer instance de test (A45).
            calibration_writes_enabled=ia_peut_ecrire(projet),
            qualification=qualification,
            project_id=(projet or {}).get("id"),
            # F26(b), migration 58 : signal déterministe pour `write_feature_file` — JAMAIS montré
            # à l'agent dans le prompt (une consigne textuelle a déjà échoué trois fois, cf.
            # registre F26). Vérifié au moment de l'écriture, pas espéré par instruction.
            depend_dun_autre_cas_du_groupe=bool((metier or {}).get("depend_dun_autre_cas_du_groupe")),
            etat_a_creer_par_ce_cas=str((metier or {}).get("etat_a_creer_par_ce_cas") or ""),
        )
        # Lot VH-05 (D24) : contrôle BLOQUANT des littéraux à l'écriture — connecteur web seulement pour l'instant (l'annuaire
        # d'un projet Odoo ne relève pas les vues du back-office : il refuserait à tort des champs techniques réels).
        from testpilot.generation import litteraux_observes
        litteraux_observes.brancher_controles(ctx, connector_type, modele, config.BEHAVE_RUNTIME_DIR)
        # Lot VH-07 (D26) : « exécuter puis écrire » — seulement si le PROJET se déclare bac à sable (calibration en écriture
        # autorisée + adresse de remise à zéro). Sinon `None` : l'outil n'est pas proposé, la génération est celle d'avant.
        from testpilot.generation.tools import essai as essai_tools
        from testpilot.generation.tools import outils_optionnels
        ctx.essai = essai_tools.construire(projet, self.dry_runner, self.connector)
        # Lot VH-08 (A51, interrupteur) : les requêtes d'oracle DÉCLARÉES — un test qui en cite une autre est refusé à
        # l'écriture. Éteint : `None`, aucun contrôle (l'exécution le bloque, comme avant).
        from testpilot.generation import interrupteurs as _interrupteurs
        ctx.requetes_oracle = (frozenset((projet or {}).get("oracle_requetes_disponibles") or ())
                               if _interrupteurs.forme_oracle_actif() and projet is not None else None)
        ctx.formes_oracle = self._formes_oracle(modele, projet)
        if _interrupteurs.garde_connexion_actif():
            # Étape 5 (AV-6) : l'intention DÉCLARÉE du cas (jamais le texte de l'agent) ; sans métier (banc, outil isolé),
            # inconnue — seule la règle des comptes s'applique, et seulement si le projet est connu.
            import json as _json_garde

            from testpilot.generation import garde_connexion
            m = metier or {}
            declaree = intention if intention is not None else "\n".join(str(x) for x in (
                m.get("title"), m.get("preconditions"), _json_garde.dumps(m["steps"], ensure_ascii=False) if m.get("steps") else "",
                m.get("expected_result")) if x)
            ctx.garde_connexion = {
                "porte": garde_connexion.porte_sur_la_connexion(declaree) if declaree.strip() else None,
                "comptes": ([str(c.get("label") or "") for c in projet.get("comptes_libelles") or []]
                            if projet is not None else None)}
        if _interrupteurs.ia_informee_actif():
            declarees = set((projet or {}).get("oracle_requetes_disponibles") or ())
            # AV-9 : sur une application web, les outils de données disent ce que l'IA peut relever à la place.
            ctx.outils_web_informes = projet is not None and (connector_type or "") == "web"
            ctx.requetes_oracle_declarees = frozenset(declarees)
            ctx.formes_oracle_relevees = {nom: f for nom, f in ((modele or {}).get("formes_oracle") or {}).items()
                                          if nom in declarees} or None
        ctx.variables_de_test = frozenset(v["nom"] for v in variables)
        # IT-3b : l'essai sur le bac à sable joue la PREMIÈRE ligne du cas, posée par-dessus le jeu « Par défaut » — comme
        # l'exécution la jouerait. Masquées dans tout ce qui revient à l'agent (PT-02d).
        ctx.valeurs_de_test = {**valeurs_par_defaut, **{str(n): str(v) for n, v in (valeurs_d_essai or {}).items()}}
        ctx.controle_du_cas = controle_du_cas
        ctx.variables_du_cas = variables_requises
        ctx.variables_de_preparation = frozenset(v["nom"] for v in variables if v.get("preparation"))
        # Étape 7 (A110) : les calculs retenus. Leurs entrées sont des données de test que le test DOIT saisir — permises même
        # si le texte du cas ne les cite pas (« le total » ne nomme pas la quantité).
        ctx.calculs = tuple({"nom": c.get("nom", ""), "entrees": tuple(c.get("entrees") or ())}
                            for c in (metier or {}).get("calculs") or [])
        ctx.parcours = dict((metier or {}).get("parcours") or {})   # étape 7b (A109)
        entrees = frozenset(e for c in ctx.calculs for e in c["entrees"])
        if entrees and (ctx.variables_de_test or ctx.controle_du_cas):
            ctx.variables_de_test = ctx.variables_de_test | entrees
        from testpilot.generation.provenance import fingerprint, target_fingerprint
        ctx.target_sha256 = target_fingerprint(
            projet, compte=compte_du_test["empreinte"] if compte_du_test and compte_du_test["vue"] == "compte" else None)
        ctx.shared_steps = shared_steps
        ctx.requirements = {'expected_result': (metier or {}).get('expected_result') or plan.raw_spec}
        ctx.requirements.update({f'step:{i}': str(step)
                                 for i, step in enumerate((metier or {}).get('steps') or [], 1)})
        import json
        requirements_message = ('\nIdentifiants métier pour write_test_plan : '
                                + json.dumps(ctx.requirements, ensure_ascii=False))
        if isinstance(state.messages[0]['content'], str):
            state.messages[0]['content'] += requirements_message
        else:
            state.messages[0]['content'][0]['text'] += requirements_message
        system_prompt = prompt_mod.build_system_prompt(self.connector, shared_steps, connector_version)
        # Q3-a : l'empreinte porte sur ce que l'API REÇOIT (interrupteurs compris), pas sur le schéma
        # local complet — sinon deux runs aux outils différents auraient la même provenance. Les
        # interrupteurs éteints, c'est l'empreinte d'avant (même contenu).
        from testpilot.generation.tools.api_definitions import tools_for_api
        outils_envoyes = tools_for_api(avec=outils_optionnels(ctx))
        input_sha256 = fingerprint(state.messages[0])
        # Étape 2 (A61, interrupteur éteint jusqu'à sa mesure) : quand le test passe la vérification à blanc, ses points de
        # vigilance — le MÊME calcul que sur la version enregistrée (`avis_du_test`) — sont renvoyés à l'IA avant de clore.
        controle = None
        if _interrupteurs.controle_fin_ecriture_actif():
            from testpilot.generation.avis_du_test import avis_du_test
            m = metier or {}
            intention_du_cas = intention if intention is not None else "\n".join(str(x) for x in (
                m.get("title") or title, m.get("preconditions"),
                json.dumps(m["steps"], ensure_ascii=False) if m.get("steps") else "", m.get("expected_result")) if x)

            from testpilot.generation.variables_de_test import ALORS_IDENTIQUE

            def controle(etat):
                # Revue de l'étape 2 (C4) : « même résultat pour toutes les lignes » peut être légitime (classe
                # d'équivalence) — une personne en juge ; le renvoyer à l'IA la pousserait à déformer le test.
                return [a for a in _avis_du_test(etat) if a.get("kind") != ALORS_IDENTIQUE]

            def _avis_du_test(etat):
                return avis_du_test(
                    feature=etat.feature_content, steps=etat.steps_content, observations=ctx.observations,
                    target_sha256=ctx.target_sha256, base_url=(projet or {}).get("base_url", ""), reference_time=None,
                    variables_des_lignes=variables_des_lignes or (),
                    connecteur_web=projet is not None and (connector_type or "") == "web",
                    # Le registre est TOUJOURS contrôlé : la version enregistrée l'est aussi (un cas a toujours un projet,
                    # au pire celui par défaut) — mesuré par `test_controle_fin_ecriture` (même calcul).
                    intention=intention_du_cas, modele=modele, verified_fields=etat.verified_fields)
        run_loop(
            llm=self.llm,
            system_prompt=system_prompt,
            state=state,
            ctx=ctx,
            dry_runner=self.dry_runner,
            cost_tracker=self.cost_tracker,
            max_iterations=self.max_iterations,
            stall_limit=self.stall_limit,
            controle_fin=controle,
        )
        result = self._build_result(plan, state)
        result.observation_evidence = ctx.observations
        result.technical_plan = ctx.technical_plan
        result.generation_provenance = {
            'model': config.MODEL_GENERATION, 'system_prompt_sha256': fingerprint(system_prompt),
            'input_sha256': input_sha256, 'tools_sha256': fingerprint(outils_envoyes),
            'requirements_sha256': fingerprint(ctx.requirements),
            'domain_sha256': fingerprint(modele), 'target_sha256': ctx.target_sha256,
            'calibration_attempts': ctx.calibration_attempts, 'qualification': qualification,
            'artifact_sha256': fingerprint([result.feature_content, result.steps_content]),
            'cost_usd': result.cost_usd, 'iterations': result.iterations,
        }
        # Étape 4, morceau 7 (A86) : pour quel compte ce test a été écrit, et avec quels écrans — relu par l'écart de compte (un
        # test joué ensuite avec un autre compte est bloqué) et par la relecture (`modele_du_cas`). Sans précision (un cas
        # neuf) : le principal, avec ses écrans.
        result.generation_provenance['ecrit_pour'] = dict(ecrit_pour or {
            'compte_id': None, 'libelle': 'principal', 'empreinte': '', 'vue': 'principal'})
        if regeneration_apres_defaut:
            result.generation_provenance['regeneration_apres_defaut'] = dict(regeneration_apres_defaut)
        if controle is not None:
            # Étape 2 : fait consigné pour la mesure (étape 3) et pour la correction d'après-coup, qui ne repasse pas sur
            # des points que l'IA a déjà vus (`generation_service._finaliser_version_generee`).
            result.generation_provenance['controle_fin_ecriture'] = {
                'tours': state.tours_de_controle, 'avis_envoyes': sorted(set(state.avis_envoyes)),
                'avis_restants': sorted({a.get('kind') or '' for a in controle(state)}) if state.dry_run_passed else []}
        if ctx.essai is not None:
            # Lot VH-07 : ce test a été écrit après des essais sur le bac à sable — fait consigné, jamais un verdict.
            result.generation_provenance['essais'] = {
                'joues': len(ctx.essai.journal), 'reussis': sum(1 for e in ctx.essai.journal if e.get('reussi')),
                'non_remis_a_zero': bool(ctx.essai.etat_laisse),
                # Les données (jetons à chiffres) que les essais ont montrées : la relecture signale tout « Alors » qui en cite.
                'donnees_vues': sorted(ctx.essai.vus)}
        if result.success and self.case_repo is not None and self.version_repo is not None:
            self._persist(plan, result, case_id=case_id, title=title, author=author,
                          module_id=module_id, metier=metier, group_id=group_id, refs=refs)
        return result

    def _build_result(self, plan: TestPlan, state: AgentState) -> GenerationResult:
        success = state.dry_run_passed and state.stopped_reason == "done"
        return GenerationResult(
            success=success,
            module_name=plan.module_name,
            stopped_reason=state.stopped_reason or "incomplete",
            dry_run_passed=state.dry_run_passed,
            iterations=state.iterations,
            cost_usd=round(self.cost_tracker.total_cost, 6),
            feature_path=(config.GENERATED_DIR / f"{plan.module_name}.feature") if state.feature_written else None,
            steps_path=(config.GENERATED_DIR / f"{plan.module_name}_steps.py") if state.steps_written else None,
            feature_content=state.feature_content,
            steps_content=state.steps_content,
            spec_hash=spec_hash(plan.raw_spec),
            awaiting_review=success,
            verified_fields=state.verified_fields,
            diagnostic_arret={} if success else {
                "arret": state.stopped_reason or "incomplete", "tours": state.iterations,
                "feature_ecrite": state.feature_written, "steps_ecrits": state.steps_written,
                "refus_recents": list(state.refus_recents), "dernier_dry_run": state.dernier_dry_run},
        )

    def _persist(self, plan: TestPlan, result: GenerationResult, *,
                 case_id: int | None, title: str, author: str,
                 module_id: int | None = None, metier: dict | None = None,
                 group_id: int | None = None, refs: str = "") -> None:
        """Crée/repère le cas, écrit la nouvelle version, pose le statut « à relire »."""
        import json as _json

        metier = metier or {}
        # Le titre du CAS vient du document métier quand il existe : c'est lui que l'humain a
        # validé. L'argument `title` reste le repli (chemin CLI, cas sans passe métier).
        libelle = (metier.get("title") or "").strip() or title or plan.module_name

        if case_id is None:
            # Rattachement métier (§7) : module imposé par l'appelant (ajout depuis un module),
            # sinon projet/module par défaut déduit du slug technique (CLI).
            if module_id is None:
                module_id = ensure_default_module(self.case_repo.conn, plan.module_name)
            case_id = self.case_repo.create(
                title=libelle, module_id=module_id, group_id=group_id,
                feature_slug=plan.module_name,
                author=author, description=plan.raw_spec[:500], refs=refs,
            )
        # ⚠️ Générer une nouvelle version ne touche PLUS à l'état du cas (migration 25). Ce qui
        # rouvre la relecture, c'est la version elle-même : le gate porte sur la VERSION, et une
        # version neuve n'est pas approuvée. Le statut recopié sur le cas ne faisait que redire
        # ça, moins fidèlement — et il empêchait l'État d'être ce qu'il doit être : un champ que
        # l'humain pose, et que la machine ne lui reprend pas (arbitré le 2026-08-04).

        # ⚠️ Le texte de la spec change de propriétaire (§9c, 2026-08-05) : avec une Section
        # explicite (`group_id`), c'est ELLE qui le porte (`case_group.spec_content`, écrit à sa
        # création par `generation_service`) — pas la version. Sans Section (chemin CLI, ou
        # automatisation d'un cas manuel qui n'a ni `group_id` ni Section), rien d'autre ne le
        # porte : on garde le comportement d'avant pour ne rien perdre sur ces chemins-là.
        version_spec_content = plan.raw_spec if group_id is None else ""

        version_id = self.version_repo.create(
            test_case_id=case_id,
            spec_content=version_spec_content,
            spec_hash=result.spec_hash,
            feature_content=result.feature_content,
            steps_content=result.steps_content,
            feature_path=str(result.feature_path or ""),
            steps_path=str(result.steps_path or ""),
            change_summary="Génération IA",
            created_by=author,
            verified_fields=_json.dumps(result.verified_fields, ensure_ascii=False),
            observation_evidence=_json.dumps(result.observation_evidence, ensure_ascii=False),
            generation_provenance=_json.dumps(result.generation_provenance, ensure_ascii=False),
            technical_plan=_json.dumps(result.technical_plan, ensure_ascii=False),
            # ── Le MÉTIER se fige DANS la version, avec le technique (décision `0022` n°10) ──
            # Sans ça, les champs de la migration 14 restaient vides sur tout cas généré et
            # l'écran en dérivait un aperçu depuis le Gherkin : un texte qui avait l'air rédigé
            # sans l'être. C'est ce couple figé ensemble qui rend l'historique diffable et permet
            # au gate d'approuver « le cas entier » d'un seul geste.
            title=libelle,
            preconditions=metier.get("preconditions", ""),
            # `""` et non `"[]"` quand il n'y a pas de métier : « jamais rédigé » et « rédigé
            # vide » ne sont pas le même fait, et c'est ce champ qui décide si l'écran affiche le
            # document ou son repli dérivé.
            test_steps=(_json.dumps(metier["steps"], ensure_ascii=False)
                        if metier.get("steps") else ""),
            expected_result=metier.get("expected_result", ""),
            depend_dun_autre_cas_du_groupe=bool(metier.get("depend_dun_autre_cas_du_groupe", False)),
            etat_a_creer_par_ce_cas=metier.get("etat_a_creer_par_ce_cas", ""),
        )
        self.case_repo.set_current_version(case_id, version_id)
        result.case_id = case_id
        result.version_id = version_id
        result.awaiting_review = True


def _informee(plan: TestPlan, projet: dict | None, metier: dict | None) -> dict:
    """Étape 5 (interrupteur `TESTPILOT_IA_INFORMEE`, éteint) : le vrai type d'application, la langue de l'interface et le TEXTE
    DU CAS validé (pour choisir les pages à détailler quand le plan n'en vise aucune). Éteint : {} — message d'avant."""
    from testpilot.generation import interrupteurs

    if not interrupteurs.ia_informee_actif():
        return {}
    from testpilot.connectors.contexte_navigateur import DEFAUT_LOCALE

    projet = projet or {}
    m = metier or {}
    texte = " ".join([str(m.get("title") or ""), " ".join(str(e) for e in m.get("steps") or []),
                      str(m.get("expected_result") or ""), str(m.get("preconditions") or "")])
    connector_type = projet.get("connector_type") or plan.connector_type
    # Revue : la langue n'est annoncée que là où elle est CELLE de l'écran — une application web suit la langue du navigateur
    # du harnais (`browser_locale`, défaut fr-FR) ; sur Odoo, l'écran suit la langue de l'utilisateur Odoo, que rien ne mesure
    # encore : ne rien dire plutôt qu'une langue fausse (l'inverse de G7).
    langue = ""
    if str(connector_type or "").lower() == "web":
        from testpilot.connectors.contexte_navigateur import _LOCALE_RE
        candidate = str(projet.get("browser_locale") or "").strip() or DEFAUT_LOCALE
        langue = candidate if _LOCALE_RE.match(candidate) else ""
    return {"connector_type": connector_type, "langue": langue, "texte_du_cas": texte.strip()}
