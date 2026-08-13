// Piège de focus partagé (lot D, 2026-07-24 — extrait en composable le 2026-08-13).
//
// Avant, cette logique vivait UNIQUEMENT dans Modal.vue : ConfirmDialog.vue et
// PaletteCommandes.vue rouvraient chacune leur propre superposition sans elle — deux fenêtres
// modales sur trois laissaient `Tab` s'échapper vers la page masquée derrière, le défaut
// d'accessibilité le plus courant et le plus désorientant des fenêtres modales. Un seul piège,
// posé une fois, plutôt qu'une troisième copie qui aurait fini par diverger.
//
// Trois gestes, indissociables : donner le focus à l'ouverture (au premier CHAMP, pas au premier
// élément focusable — ouvrir sur la croix de fermeture suggère qu'on propose d'abord de
// renoncer), l'enfermer tant que le panneau vit, et le RENDRE à l'élément qui l'avait à la
// fermeture — sinon le focus repart au début de la page, ce qui oblige à tout re-parcourir.
import { nextTick, onMounted, onUnmounted, ref, watch, type Ref } from 'vue'

const FOCUSABLES = 'a[href], button:not([disabled]), input:not([disabled]), '
  + 'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function elementsFocusables(racine: HTMLElement | null): HTMLElement[] {
  // ⚠️ Pas de filtre sur `offsetParent` : il vaut TOUJOURS null hors d'un vrai navigateur, et
  // le piège se retrouverait alors sans aucune cible — un filtre qui supprime tout ne protège
  // rien. On s'en tient aux critères portables et vérifiables.
  return Array.from(racine?.querySelectorAll<HTMLElement>(FOCUSABLES) || [])
    .filter((el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true')
}

export function useFocusTrap(ouvert: Ref<boolean>, fermer: () => void) {
  const panneau = ref<HTMLElement | null>(null)
  let avant: HTMLElement | null = null

  function onKey(e: KeyboardEvent) {
    if (!ouvert.value) return
    if (e.key === 'Escape') { fermer(); return }
    if (e.key !== 'Tab') return

    const cibles = elementsFocusables(panneau.value)
    if (!cibles.length) return
    const premier = cibles[0]
    const dernier = cibles[cibles.length - 1]
    const actif = document.activeElement as HTMLElement | null

    // Le focus BOUCLE dans le panneau : après le dernier élément on revient au premier, et
    // inversement avec Maj+Tab. C'est ce qui empêche d'en sortir sans le vouloir.
    if (!e.shiftKey && (actif === dernier || !panneau.value?.contains(actif))) {
      e.preventDefault()
      premier.focus()
    } else if (e.shiftKey && (actif === premier || !panneau.value?.contains(actif))) {
      e.preventDefault()
      dernier.focus()
    }
  }

  watch(ouvert, async (v) => {
    if (v) {
      avant = document.activeElement as HTMLElement | null
      await nextTick()
      const cibles = elementsFocusables(panneau.value)
      const champ = cibles.find((el) => ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))
      ;(champ || cibles[0])?.focus()
    } else {
      avant?.focus()   // rendre le focus à celui qui a ouvert
      avant = null
    }
  })

  onMounted(() => window.addEventListener('keydown', onKey))
  onUnmounted(() => window.removeEventListener('keydown', onKey))

  return { panneau }
}
