"""Étape 5 du plan unique (A101) — « une erreur de validation est affichée pour le champ X » : l'erreur doit être RATTACHÉE à ce
champ ET APPARUE depuis le début des actions qui précèdent l'« Alors », pas seulement visible quelque part dans la page.

Falsifiabilité, sur un vrai Chromium (deux passes de revue le 2026-10-22, huit faux verts ou faux rouges reproduits puis
fermés) : l'erreur d'un AUTRE champ ne suffit pas ; un bandeau commun est non concluant ; un champ obligatoire vide sans message
(validation native) ne compte pas ; une classe d'ÉTAT de framework (`ng-invalid`) n'est pas une erreur ; une mention rouge fixe
déjà là avant les actions ne prouve rien, même si le formulaire est RENVOYÉ (POST) et réaffiché ; le conteneur racine d'une page
n'est pas l'enveloppe d'un champ ; un formulaire qui disparaît (accepté) est un échec, pas une panne ; une validation à la
sortie du champ, apparue PENDANT les actions, est bien vue.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402

_FORMULAIRE = """<form>
<div class="champ"><label for="nom">Nom</label><input id="nom" name="nom" {nom}>{msg_nom}</div>
<div class="champ"><label for="email">Email</label><input id="email" name="email" {email}>{msg_email}</div>
<span id="aide-nom">Votre nom de famille</span>
<button type="submit">Enregistrer</button>
</form>{bandeau}"""


@pytest.fixture(scope="module")
def navigateur():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch()
        yield nav
        nav.close()


@pytest.fixture(autouse=True)
def _delai_court(monkeypatch):
    monkeypatch.setattr(H, "COUNT_SETTLE_TIMEOUT", 0.5)


def _html(**morceaux):
    valeurs = {"nom": "", "msg_nom": "", "email": "", "msg_email": "", "bandeau": ""}
    valeurs.update(morceaux)
    return _FORMULAIRE.format(**valeurs)


def _page(navigateur, html):
    page = navigateur.new_page()
    page.set_content(html)
    return page


def _contexte(page):
    """Le contexte d'un run, réduit à ce que le relevé lit : l'onglet et ses navigations."""
    return SimpleNamespace(page=page, navigations={})


def _action(ctx):
    """Le début d'une action (`environment.before_step` → `poser_repere_action`) : le relevé des erreurs."""
    H.noter_les_erreurs_avant_action(ctx)


def _constat(ctx, champ="nom"):
    H.validation_error_for_field(ctx.page, champ, H.erreurs_avant_action(ctx))


# ── Rattachement ───────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.conformance
@pytest.mark.parametrize("morceaux", [
    {"msg_nom": '<p class="invalid-feedback" style="display:block">Le nom est obligatoire</p>'},
    {"nom": 'class="is-invalid"'},
    {"nom": 'aria-invalid="true"'},
    {"nom": 'aria-describedby="err" ', "bandeau": '<div id="err" class="error">Nom trop court</div>'},
], ids=["message-dans-l-enveloppe", "classe-invalide", "aria-invalid", "aria-describedby"])
def test_une_erreur_rattachee_au_champ_apparue_apres_l_action_est_reconnue(navigateur, morceaux):
    page = _page(navigateur, _html())
    try:
        ctx = _contexte(page)
        _action(ctx)
        page.set_content(_html(**morceaux))   # le formulaire renvoyé (même adresse), avec son erreur
        _constat(ctx)
    finally:
        page.close()


@pytest.mark.conformance
def test_falsifiable_l_erreur_d_un_autre_champ_ne_prouve_rien_sur_celui_ci(navigateur):
    page = _page(navigateur, _html(email='class="is-invalid"', msg_email='<span class="text-danger">Adresse invalide</span>'))
    try:
        H.validation_error_inline(page)   # l'ancien step, lui, passait
        with pytest.raises(AssertionError, match="aucune pour le champ 'nom'"):
            H.validation_error_for_field(page, "nom")
    finally:
        page.close()


@pytest.mark.conformance
def test_un_bandeau_commun_est_non_concluant(navigateur):
    page = _page(navigateur, _html(bandeau='<div role="alert">Le formulaire contient des erreurs</div>'))
    try:
        with pytest.raises(H.ConstatNonConcluantError, match="bandeau commun"):
            H.validation_error_for_field(page, "nom")
    finally:
        page.close()


@pytest.mark.conformance
@pytest.mark.parametrize("morceaux", [
    {},
    {"nom": "required"},   # invalide pour le navigateur, mais rien n'est affiché dans la page
    {"nom": 'aria-describedby="aide-nom"'},   # une aide, pas une erreur
], ids=["rien", "validation-native-seule", "aide-designee"])
def test_falsifiable_sans_erreur_affichee_pour_le_champ_le_constat_echoue(navigateur, morceaux):
    page = _page(navigateur, _html(**morceaux))
    try:
        with pytest.raises(AssertionError, match="Aucune erreur de validation visible pour le champ 'nom'"):
            H.validation_error_for_field(page, "nom")
    finally:
        page.close()


@pytest.mark.conformance
def test_odoo_champ_marque_o_field_invalid_sur_son_enveloppe(navigateur):
    page = _page(navigateur, '<div class="o_form_view"><div class="o_field_widget o_field_char o_field_invalid" name="name">'
                             '<input id="name_0" name="name"></div><div class="o_field_widget"><input id="ref" name="ref"></div>'
                             '</div>')
    try:
        H.validation_error_for_field(page, "name")
        with pytest.raises(AssertionError):
            H.validation_error_for_field(page, "ref")
    finally:
        page.close()


@pytest.mark.conformance
@pytest.mark.parametrize("html", [
    # Angular au repos : `ng-invalid` posé dès l'affichage d'un champ obligatoire vide — un ÉTAT, pas une erreur affichée.
    '<form><div class="champ"><label for="nom">Nom</label>'
    '<input id="nom" name="nom" class="ng-untouched ng-pristine ng-invalid" required></div></form>',
    # Angular Material : l'enveloppe porte `ng-invalid` et contient le libellé — elle contient le champ, ce n'est pas un message.
    '<form><mat-form-field class="mat-form-field ng-invalid"><span>Nom</span><input id="nom" name="nom"></mat-form-field>'
    '</form>',
], ids=["angular-au-repos", "angular-material"])
def test_falsifiable_une_classe_d_etat_de_framework_n_est_pas_une_erreur(navigateur, html):
    page = _page(navigateur, html)
    try:
        with pytest.raises(AssertionError, match="Aucune erreur de validation visible pour le champ 'nom'"):
            H.validation_error_for_field(page, "nom")
    finally:
        page.close()


@pytest.mark.conformance
def test_falsifiable_le_conteneur_racine_d_une_page_a_un_seul_champ_n_est_pas_son_enveloppe(navigateur):
    page = _page(navigateur, '<div id="app"><div class="champ"><label for="nom">Nom</label><input id="nom" name="nom">'
                             '</div><div role="alert">Erreur serveur</div></div>')
    try:
        with pytest.raises(H.ConstatNonConcluantError):
            H.validation_error_for_field(page, "nom")
    finally:
        page.close()


# ── Apparue depuis le début des actions ────────────────────────────────────────────────────────────────────────────────

_MENTION_FIXE = '<small class="text-danger">Champ obligatoire</small>'


@pytest.mark.conformance
def test_falsifiable_une_mention_fixe_reste_non_concluante_meme_formulaire_renvoye(navigateur):
    """Revue, seconde passe : le serveur ACCEPTE la saisie vide et réaffiche le même formulaire (POST, même adresse) — les
    éléments sont neufs, la mention fixe aussi ; sa SIGNATURE était déjà là."""
    page = _page(navigateur, _html(msg_nom=_MENTION_FIXE))
    try:
        ctx = _contexte(page)
        _action(ctx)
        page.set_content(_html(msg_nom=_MENTION_FIXE))   # réponse au POST : même page, même adresse
        with pytest.raises(H.ConstatNonConcluantError, match="rien ne prouve"):
            _constat(ctx)
        # L'application refuse vraiment : un message NOUVEAU apparaît dans l'enveloppe du champ.
        page.set_content(_html(msg_nom=_MENTION_FIXE + '<p class="invalid-feedback">Le nom est obligatoire</p>'))
        _constat(ctx)
    finally:
        page.close()


@pytest.mark.conformance
def test_falsifiable_une_autre_adresse_apres_une_creation_acceptee_garde_la_mention_fixe_non_concluante(navigateur):
    """Revue, 3e passe : POST accepté, 303, GET vers la fiche en modification — même formulaire, même mention fixe, autre
    adresse. Pas la règle d'A97 : une nouvelle adresse dit plutôt que la saisie a été acceptée."""
    page = _page(navigateur, _html(msg_nom=_MENTION_FIXE))
    try:
        ctx = _contexte(page)
        _action(ctx)
        page.set_content(_html(msg_nom=_MENTION_FIXE))   # la fiche créée : nouveau document, demandé en GET (303)
        ctx.navigations[page] = {"methode": "GET"}
        with pytest.raises(H.ConstatNonConcluantError):
            _constat(ctx)
        page.set_content(_html(msg_nom=_MENTION_FIXE + '<p class="invalid-feedback">Le nom est obligatoire</p>'))
        _constat(ctx)   # une erreur NOUVELLE, elle, se voit sur n'importe quelle page
    finally:
        page.close()


@pytest.mark.conformance
def test_falsifiable_un_champ_sans_nom_est_compare_par_sa_position(navigateur):
    """Revue, 3e passe : un contrôle sans name, id ni aria-label n'était jamais comparé — un clic sans effet passait."""
    html = ('<form><div class="champ"><label>Nom <input></label><small class="text-danger">Champ obligatoire</small></div>'
            '</form>')
    page = _page(navigateur, html)
    try:
        ctx = _contexte(page)
        _action(ctx)
        with pytest.raises(H.ConstatNonConcluantError):
            _constat(ctx, champ="Nom")
    finally:
        page.close()


@pytest.mark.conformance
def test_un_champ_encore_affiche_mais_introuvable_par_le_test_n_accuse_pas_l_application(navigateur, monkeypatch):
    """Revue, 3e passe : désigné par un nom que `locate_field` ne résout pas (son `id`), le champ est encore là — erreur du
    test, jamais « n'est plus affiché »."""
    page = _page(navigateur, '<form><input placeholder="Code postal"></form>')
    monkeypatch.setattr(H, "locate_field", lambda page, field, timeout=0: page.locator("#absent"))
    try:
        with pytest.raises(H.ElementIntrouvableError):
            H.validation_error_for_field(page, "Code postal", None, True)
    finally:
        page.close()


@pytest.mark.conformance
def test_une_validation_a_la_sortie_du_champ_apparue_pendant_les_actions_est_vue(navigateur):
    """Revue, seconde passe : l'erreur apparaît pendant « je laisse le champ vide » (sortie du champ), AVANT le clic. Le constat
    compare au relevé du DÉBUT du bloc, pas à celui du clic."""
    page = _page(navigateur, _html())
    try:
        ctx = _contexte(page)
        _action(ctx)   # « je laisse le champ "Nom" vide »
        page.evaluate("""() => { const p = document.createElement('p'); p.className = 'invalid-feedback';
                                 p.textContent = 'Le nom est obligatoire'; document.querySelector('.champ').appendChild(p); }""")
        _action(ctx)   # « je clique sur le bouton "Enregistrer" »
        _constat(ctx)
        # Un « Alors » clôt le bloc : au bloc suivant, cette même erreur est déjà là.
        H.fermer_le_bloc_d_actions(ctx)
        _action(ctx)
        with pytest.raises(H.ConstatNonConcluantError):
            _constat(ctx)
    finally:
        page.close()


@pytest.mark.conformance
def test_falsifiable_un_formulaire_qui_disparait_est_un_echec_pas_une_panne(navigateur):
    """Revue, seconde passe : l'application ACCEPTE le nom vide et passe à la liste — le constat échoue (vite), il ne devient
    jamais une erreur technique (une réparation payée sur un test juste)."""
    page = _page(navigateur, _html())
    try:
        ctx = _contexte(page)
        _action(ctx)
        page.evaluate("() => setTimeout(() => { document.body.innerHTML = '<h1>Clients</h1>'; }, 150)")
        with pytest.raises(AssertionError, match="n'est plus affiché"):
            _constat(ctx)
    finally:
        page.close()


def test_une_page_illisible_pendant_tout_le_delai_est_une_panne_pas_un_echec(monkeypatch):
    class _Element:
        def evaluate(self, _js, timeout=None):
            raise RuntimeError("Target page, context or browser has been closed")

    class _Champ:
        first = _Element()

        def __init__(self):
            self.lectures = 0

        def count(self):
            self.lectures += 1
            if self.lectures > 1:
                raise RuntimeError("Target page, context or browser has been closed")
            return 1

    monkeypatch.setattr(H, "locate_field", lambda page, field, timeout=0: _Champ())
    monkeypatch.setattr(H, "COUNT_SETTLE_TIMEOUT", 0.05)
    page = SimpleNamespace(url="http://app.test/x")
    with pytest.raises(RuntimeError, match="n'a pas pu être relu"):
        H.validation_error_for_field(page, "nom")


@pytest.mark.conformance
def test_un_champ_jamais_vu_pendant_les_actions_reste_introuvable_pas_un_defaut(navigateur, monkeypatch):
    """Un nom que le test a inventé n'accuse jamais l'application : seul un champ VU pendant les actions puis disparu est un
    échec (formulaire accepté)."""
    monkeypatch.setattr(H, "locate_field", lambda page, field, timeout=0: page.locator("#absent"))
    page = _page(navigateur, "<h1>Clients</h1>")
    try:
        with pytest.raises(H.ElementIntrouvableError):
            H.validation_error_for_field(page, "nom", None, False)
        with pytest.raises(AssertionError, match="n'est plus affiché"):
            H.validation_error_for_field(page, "nom", None, True)
    finally:
        page.close()


# ── Revue, 4e passe : le champ cité par une PARTIE de son libellé (« Nom » pour « Nom * ») ───────────────────────────────

_ETOILE = ('<form><div class="champ"><label for="x1">Nom *</label><input id="x1" {nom}>'
           '<small class="text-danger">Champ obligatoire</small>{erreur}</div><button>Enregistrer</button></form>')


@pytest.mark.conformance
@pytest.mark.parametrize("nom", ["", 'name="nom_client"'], ids=["sans-name", "name-different-du-texte-cite"])
@pytest.mark.parametrize("ailleurs", [False, True], ids=["meme-page", "fiche-creee-ailleurs"])
def test_falsifiable_libelle_plus_long_que_le_texte_cite_la_mention_fixe_ne_passe_pas(navigateur, nom, ailleurs):
    page = _page(navigateur, _ETOILE.format(nom=nom, erreur=""))
    try:
        ctx = _contexte(page)
        _action(ctx)
        if ailleurs:   # accepté, puis la fiche créée (nouveau document, demandé en GET)
            page.set_content(_ETOILE.format(nom=nom, erreur=""))
            ctx.navigations[page] = {"methode": "GET"}
        with pytest.raises(H.ConstatNonConcluantError):
            _constat(ctx, champ="Nom")
        page.set_content(_ETOILE.format(nom=nom, erreur='<p class="invalid-feedback">Le nom est obligatoire</p>'))
        _constat(ctx, champ="Nom")   # une erreur NOUVELLE passe
    finally:
        page.close()


@pytest.mark.conformance
def test_un_champ_cite_par_une_partie_de_son_libelle_et_disparu_est_un_echec(navigateur):
    page = _page(navigateur, _ETOILE.format(nom="", erreur=""))
    try:
        ctx = _contexte(page)
        _action(ctx)
        assert H.champ_vu_pendant_les_actions(ctx, "Nom")
        page.set_content("<h1>Clients</h1>")
        with pytest.raises(AssertionError, match="n'est plus affiché"):
            H.validation_error_for_field(page, "Nom", H.erreurs_avant_action(ctx), H.champ_vu_pendant_les_actions(ctx, "Nom"))
    finally:
        page.close()


@pytest.mark.conformance
def test_des_releves_sans_ce_champ_ne_rendent_jamais_tout_nouveau(navigateur):
    """La clé du champ a changé depuis les relevés (ou il n'y figurait pas) : rien à quoi comparer — non concluant."""
    page = _page(navigateur, '<form><div class="champ"><label for="a">Ville</label><input id="a" name="ville"></div></form>')
    try:
        ctx = _contexte(page)
        _action(ctx)
        page.set_content(_html(msg_nom=_MENTION_FIXE))
        with pytest.raises(H.ConstatNonConcluantError):
            _constat(ctx)
    finally:
        page.close()


# ── Revue, 5e passe : un champ de même clé sur une AUTRE page du même bloc ────────────────────────────────────────────────

_RECHERCHE = '<form><div class="champ"><label for="f">Nom</label><input id="f" name="nom"></div></form>'


@pytest.mark.conformance
@pytest.mark.parametrize("spa", [False, True], ids=["page-rechargee", "application-monopage"])
def test_falsifiable_le_releve_d_une_autre_page_de_meme_cle_ne_sert_pas_de_reference(navigateur, spa):
    page = _page(navigateur, _RECHERCHE)
    try:
        ctx = _contexte(page)
        _action(ctx)   # « Soit j'ouvre la page "/recherche" » : relevé pris avant (page vide) — sans importance
        _action(ctx)   # « Quand j'ouvre la page "/clients/nouveau" » : relevé encore sur /recherche (champ « nom », sans signe)
        if spa:
            page.evaluate("(html) => { document.body.innerHTML = html; }", _html(msg_nom=_MENTION_FIXE))
        else:
            page.set_content(_html(msg_nom=_MENTION_FIXE))
        _action(ctx)   # « Et je clique sur le bouton "Enregistrer" » : sur /clients/nouveau, la mention fixe est là
        with pytest.raises(H.ConstatNonConcluantError):
            _constat(ctx)
    finally:
        page.close()


@pytest.mark.conformance
def test_un_champ_encore_affiche_par_inclusion_n_accuse_pas_l_application(navigateur, monkeypatch):
    """Revue, 5e passe : « nom » est contenu dans « nom_client » — le champ est encore là, `locate_field` ne l'a pas résolu."""
    page = _page(navigateur, '<form><input name="nom_client"></form>')
    monkeypatch.setattr(H, "locate_field", lambda page, field, timeout=0: page.locator("#absent"))
    try:
        with pytest.raises(H.ElementIntrouvableError):
            H.validation_error_for_field(page, "nom", None, True)
    finally:
        page.close()


@pytest.mark.conformance
def test_des_releves_seulement_dans_un_autre_onglet_ne_rendent_jamais_tout_nouveau(navigateur):
    """Revue, 6e passe : l'onglet affiché n'a aucun relevé, un autre en a — non concluant, jamais « tout est nouveau »."""
    autre = _page(navigateur, _html())
    page = _page(navigateur, _html(msg_nom=_MENTION_FIXE))
    try:
        ctx = _contexte(autre)
        _action(ctx)
        ctx.page = page   # un nouvel onglet devient l'onglet du test après la dernière action
        with pytest.raises(H.ConstatNonConcluantError):
            _constat(ctx)
    finally:
        page.close()
        autre.close()
