"""Preuve DOM réelle, locale, sans compte distant ni appel LLM."""
import pytest
from playwright.sync_api import sync_playwright

from testpilot.connectors._web_helpers import extract_form
from testpilot.generation.evidence import record_observation, contextual_warnings
from testpilot.generation.tools import ToolContext

pytestmark = pytest.mark.conformance


def test_observation_navigateur_et_mutation_champ_masque(tmp_path):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content('''<html lang="fr"><form action="/submit">
                <label for="category">Catégorie</label>
                <select id="category" name="category" required>
                <option value="bug">Anomalie</option></select>
                <button class="btn-primary" type="button">Enregistrer</button>
                </form></html>''')
            info = extract_form(page)
            field = info['fields'][0]
            assert field['label'] == 'Catégorie' and field['visible']
            assert field['options'] == [['bug', 'Anomalie']] and info['language'] == 'fr'
            assert info['submission']['trigger_selector'] == ''  # aucun submit inventé
            ctx = ToolContext('fixture', tmp_path, target_sha256='local')
            feature = 'Quand je navigue vers "/form"\nEt je renseigne le champ "category" avec "bug"'
            record_observation(ctx, source='ui', resource='/form', fields=info['fields'])
            assert contextual_warnings(feature, ctx.observations, target_sha256='local') == []
            page.locator('#category').evaluate("el => el.style.display = 'none'")
            hidden = extract_form(page)
            ctx.observations.clear()
            record_observation(ctx, source='ui', resource='/form', fields=hidden['fields'])
            assert contextual_warnings(feature, ctx.observations, target_sha256='local')
        finally:
            browser.close()
