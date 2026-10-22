"""Gate de relecture humaine (§4) — logique pure, sans aucune I/O terminal.

Règle : la version courante d'un cas généré par l'IA doit être approuvée en relecture
AVANT sa première exécution. L'approbation porte sur la VERSION : un ré-run de la même
version approuvée ne redemande rien ; une nouvelle version (spec évoluée → re-génération)
repasse par le gate. L'interaction (afficher le Gherkin, demander oui/non) est faite par
la CLI, qui appelle ``submit_review`` puis ``evaluate_gate``.
"""

from __future__ import annotations

from dataclasses import dataclass



@dataclass
class GateDecision:
    allowed: bool
    needs_review: bool
    reason: str


def evaluate_gate(review_repo, version_id: int) -> GateDecision:
    """Décide si la version courante peut être exécutée (lecture seule)."""
    if review_repo.is_version_approved(version_id):
        return GateDecision(allowed=True, needs_review=False, reason="version approuvée en relecture")
    latest = review_repo.latest_for_version(version_id)
    if latest and latest["decision"] == "rejected":
        return GateDecision(allowed=False, needs_review=True,
                            reason="version rejetée en relecture — corriger puis re-générer")
    return GateDecision(allowed=False, needs_review=True,
                        reason="bloqué : la version n'est pas encore approuvée")   # A68 : plus de « relecture »


def bloquer_si_ecart(decision: GateDecision, ecarts: list[str]) -> GateDecision:
    """Décision A42 : un écart entre le cas et son test (le cas cite une donnée que le test n'emploie pas) bloque
    l'exécution, même d'une version approuvée — régénérer le test ou corriger le cas."""
    if not ecarts:
        return decision
    return GateDecision(allowed=False, needs_review=True,
                        reason="écart entre le cas et son test : " + " ; ".join(ecarts)
                        + " — régénérez le test ou corrigez le cas")


def submit_review(review_repo, *, case_id: int, version_id: int, approved: bool,
                  reviewer: str, comment: str = "",
                  repair_budget: int | None = None) -> GateDecision:
    """Enregistre la décision de relecture et renvoie l'état du gate qui en découle.

    `repair_budget` : tentatives de réparation que cette approbation autorise (décision 0014,
    option C). `None` → le défaut de configuration. Réparer exige d'exécuter, et le gate est le
    seul à pouvoir autoriser une exécution (§4.3) : c'est donc lui qui porte cette autorisation.
    """
    review_repo.create(test_case_id=case_id, version_id=version_id,
                       decision="approved" if approved else "rejected",
                       reviewer=reviewer, comment=comment, repair_budget=repair_budget)
    return evaluate_gate(review_repo, version_id)


def auto_approve_metier(review_repo, *, case_id: int, version_id: int,
                        repair_budget: int | None = None) -> GateDecision:
    """Approbation AUTOMATIQUE au titre de la validation métier (amendement §4.3, 2026-07-21).

    Décision du porteur : la validation du **métier** à la création (la pause en 2 passes, ou la
    saisie manuelle) **vaut relecture**. Il n'y a plus de gate humain séparé sur le Gherkin — une
    version produite depuis un métier validé est prête dès qu'elle existe.

    ⚠️ **Ce n'est pas un contournement silencieux du §4.3** : l'approbation est TRACÉE (reviewer
    `validation-metier`, commentaire explicite), exactement comme le projet trace la provenance
    des coûts (`estimated` vs `anthropic_api`). On sait toujours d'où vient l'autorisation.
    Le smoke-check reste affiché comme signal de vigilance — l'amendement retire le geste
    d'approbation, pas la mise en garde technique.
    """
    return submit_review(
        review_repo, case_id=case_id, version_id=version_id, approved=True,
        reviewer="validation-metier",
        comment="Approuvé au titre de la validation métier à la création (amendement §4.3, 2026-07-21).",
        repair_budget=repair_budget)


# ⚠️ `validation_status_after_run` a été SUPPRIMÉE (2026-08-04). Elle calculait un statut de
# validation DÉRIVÉ de l'exécution, recopié sur le cas par cinq appelants. Ce statut est parti
# avec la migration 25 : il se présentait comme un cycle de vie sans en être un (aucun humain ne
# pouvait le poser), et il faisait doublon avec ce que les exécutions disent déjà. `test_case.etat`
# le remplace — écrit par un humain, et par personne d'autre.


# Auteur des versions écrites par l'agent de RÉPARATION — lu par `run_service` (le run d'une telle version non relue n'est jamais
# le résultat du cas) et par l'édition du métier (elle n'approuve pas d'office un code réparé non relu). Constante PARTAGÉE :
# trois copies littérales existaient, un renommage en aurait désactivé une sans bruit (revue du lot VH-03).
AUTEUR_REPARATION = "repair-agent"


def attente_metier_changee(avant: dict | None, apres: dict | None) -> bool:
    """D31 (validée par le porteur le 2026-10-09) : `apres` garde le TEST de `avant` mais change ce qu'il doit vérifier.

    Vrai si `avant` porte un test (Gherkin non vide) et que le résultat attendu ou les étapes métier diffèrent. Le titre et
    les préconditions ne comptent pas : ils ne changent pas ce que le test doit prouver (l'amendement §4.3 s'y applique
    toujours). Comparaison de textes HUMAINS (le métier validé), jamais du texte de l'agent.
    """
    if not avant or not apres or not (avant.get("feature_content") or "").strip():
        return False
    return any((avant.get(champ) or "") != (apres.get(champ) or "") for champ in ("expected_result", "test_steps"))


def test_non_relu(review_repo, version: dict | None) -> bool:
    """Une version qui porte un test (Gherkin non vide) et n'est pas approuvée — quel que soit son auteur.

    Revue D30-D32 (B1) : l'édition du métier recopie ce test ; l'approuver d'office le « blanchirait » (une correction
    laissée à relire par D30, une attente changée par D31 en attente de décision)."""
    return (bool(version) and bool((version.get("feature_content") or "").strip())
            and not evaluate_gate(review_repo, version["id"]).allowed)


def version_reparee_non_relue(review_repo, version: dict | None) -> bool:
    """Une version écrite par l'agent de réparation et pas (encore) approuvée par un humain."""
    return bool(version) and version.get("created_by") == AUTEUR_REPARATION and not evaluate_gate(
        review_repo, version["id"]).allowed


# ── Étape 2 du plan unique (A63, A67, A68 — porteur, 2026-10-20) : « bloqué », avec sa raison ──────────────────────────────
#
# Un test que l'IA n'a pas réussi à rendre propre est LIVRÉ BLOQUÉ, la raison sur la fiche ; jamais « à relire » (A63).
# L'état n'est PAS enregistré (A67) : il se déduit de ce qui décide déjà du lancement — l'approbation de la version et les
# écarts cas/test (A42) — et les raisons viennent des points de vigilance. Les raisons ne font que DIRE pourquoi : elles ne
# peuvent jamais autoriser un lancement (`bloque` vaut toujours `not decision.allowed`). Un test ne se débloque jamais seul :
# seule une approbation le débloque.

# Une phrase courte par sorte de point de vigilance, en français (CONTINUITE §4.7 : aucune valeur brute à l'écran).
RAISONS_DES_AVIS: dict[str, str] = {
    "always_true_constant": "Une vérification ne peut jamais échouer.",
    "tautology_negation_in_else": "Une vérification ne peut jamais échouer.",
    "then_without_assertion": "Une vérification ne vérifie rien.",
    "assertion_dans_contexte": "Une vérification est placée dans le Contexte.",
    "step_modifie": "La réparation a modifié ce que le test vérifie.",
    "step_supprime": "La réparation a modifié ce que le test vérifie.",
    "assertion_code_modifiee": "La réparation a modifié ce que le test vérifie.",
    "scenario_supprime": "La réparation a modifié ce que le test vérifie.",
    "assertion_modifiee": "La réparation a modifié ce que le test vérifie.",
    "exemple_modifie": "La réparation a modifié ce que le test vérifie.",
    "verification_affaiblie_par_correction": "La correction automatique a modifié une vérification.",
    "attente_metier_changee": "Le cas a changé depuis l'écriture du test : régénérez-le.",
    "alors_identique_pour_toutes_les_lignes": "Le test vérifie la même chose pour toutes les lignes de données.",
    "verification_changee_apres_defaut": "Régénéré après un défaut de l'application : il ne vérifie plus la même chose.",
    "valeur_vue_a_l_essai": "Une valeur attendue a été lue sur l'application pendant un essai.",
    "valeur_option_inexistante": "Une option choisie n'existe pas dans l'application.",
    "champ_inconnu": "Un champ du test n'existe pas dans l'application.",
    "champ_ui_non_verifie": "Un champ n'a pas été vu à l'écran pendant la génération.",
    "champs_requis_manquants": "Des champs obligatoires du formulaire ne sont pas remplis.",
    "soumission_absente": "Le formulaire n'est jamais envoyé.",
    "message_non_observe": "Un message attendu n'a jamais été vu sur l'application.",
    "produit_non_observe": "Un élément choisi n'a jamais été vu sur l'application.",
    "menu_non_observe": "Un menu du test n'a jamais été vu sur l'application.",
    "connexion_non_testee": "Ce test de connexion s'ouvrirait déjà connecté.",
    "enregistrement_non_cree_par_le_scenario": "Le test agit sur un enregistrement qu'il n'a pas créé.",
    "controles_ecriture_contournes": "Modifié à la main, le test ne passe pas les contrôles d'écriture.",
}
RAISON_AVIS_INCONNU = "Un point de vigilance reste à vérifier."
# Revue de l'étape 2 : la liste « Cas bloqués » n'affiche que la PREMIÈRE raison — la plus grave d'abord (ce qui touche à
# la vérité du verdict avant ce qui touche à la preuve).
_GRAVITE = ("verification_changee_apres_defaut", "verification_affaiblie_par_correction", "attente_metier_changee",
            "valeur_vue_a_l_essai", "enregistrement_non_cree_par_le_scenario", "always_true_constant",
            "tautology_negation_in_else", "then_without_assertion")
RAISON_NON_APPROUVE = "Pas encore approuvé."
RAISON_REJETE = "Rejeté en relecture."


def raisons_du_blocage(decision: GateDecision, *, approuvee: bool, rejetee: bool, ecarts: list[str],
                       avis: list[dict]) -> list[str]:
    """Pourquoi la version ne sera pas lancée — vide si elle peut l'être. Pur.

    `decision` : celle de `bloquer_si_ecart(evaluate_gate(…), ecarts)`, seule source de `allowed`. Une version approuvée mais
    en écart (A42) donne la raison de l'écart seulement (ses points de vigilance ont été jugés par l'approbation) ; une
    version non approuvée, ses points de vigilance (dédoublonnés, dans l'ordre), à défaut « pas encore approuvé ». Jamais de
    liste vide pour une version bloquée."""
    if decision.allowed:
        return []
    raisons: list[str] = []
    if ecarts:
        raisons.append("Écart entre le cas et son test : " + " ; ".join(ecarts) + ".")
    if rejetee:
        raisons.append(RAISON_REJETE)
    rang = {k: i for i, k in enumerate(_GRAVITE)}
    for avis_ in sorted([] if approuvee else avis, key=lambda a: rang.get(a.get("kind") or "", len(rang))):
        raison = RAISONS_DES_AVIS.get(avis_.get("kind") or "", RAISON_AVIS_INCONNU)
        if raison not in raisons:
            raisons.append(raison)
    return raisons or [RAISON_NON_APPROUVE]
