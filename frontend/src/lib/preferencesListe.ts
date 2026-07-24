// Les PRÉFÉRENCES DE LECTURE de la liste des cas (lot C, 2026-07-24).
//
// Densité, colonnes visibles, tri : ce sont des préférences d'AFFICHAGE, pas de l'état serveur.
// Elles n'ont donc rien à faire dans la couche de données (`lib/donnees.ts`) — un utilisateur
// qui règle sa densité ne modifie rien pour les autres.
//
// ⚠️ **Conservées par projet, et réinitialisables.** Une liste qui oublie ses réglages à chaque
// visite oblige à les refaire ; une liste qui les garde sans permettre de revenir en arrière
// piège l'utilisateur dans une vue qu'il ne sait plus défaire. Les deux sont des défauts connus
// des tables denses — d'où le bouton « réinitialiser », qui n'est pas un détail.

import { ref, watch } from 'vue'

export type Densite = 'compacte' | 'normale' | 'aeree'
export type Colonne = 'id' | 'titre' | 'module' | 'type' | 'priorite' | 'statut'

/** Les colonnes qu'on peut masquer. `titre` et `statut` n'en font pas partie : une liste de cas
 *  sans titre ni verdict ne montre plus rien — laisser les masquer serait offrir de casser
 *  l'écran. */
export const COLONNES_MASQUABLES: { cle: Colonne; label: string }[] = [
  { cle: 'id', label: 'ID' },
  { cle: 'module', label: 'Module' },
  { cle: 'type', label: 'Type' },
  { cle: 'priorite', label: 'Priorité' },
]

export const HAUTEUR_LIGNE: Record<Densite, string> = {
  compacte: 'py-1.5',
  normale: 'py-2.5',
  aeree: 'py-4',
}

interface Preferences {
  densite: Densite
  colonnes: Colonne[]
  tri: 'id' | 'title' | 'status'
}

const DEFAUTS: Preferences = {
  densite: 'normale',
  colonnes: ['id', 'module', 'type', 'priorite'],
  tri: 'id',
}

const cle = (pid: string) => `tp.liste.${pid}`

export function usePreferencesListe(pid: () => string) {
  const prefs = ref<Preferences>({ ...DEFAUTS })

  function charger() {
    try {
      const brut = localStorage.getItem(cle(pid()))
      // Fusion avec les défauts : une préférence enregistrée AVANT l'ajout d'un réglage n'a pas
      // sa clé — sans fusion, ce réglage vaudrait `undefined` et l'écran se casserait sur une
      // préférence pourtant valide au moment où elle a été écrite.
      prefs.value = brut ? { ...DEFAUTS, ...JSON.parse(brut) } : { ...DEFAUTS }
    } catch {
      prefs.value = { ...DEFAUTS }   // stockage illisible : la liste marche quand même
    }
  }

  watch(prefs, (v) => {
    try {
      localStorage.setItem(cle(pid()), JSON.stringify(v))
    } catch { /* jamais bloquer la lecture pour une préférence d'affichage */ }
  }, { deep: true })

  function reinitialiser() {
    prefs.value = { ...DEFAUTS }
  }

  /** Vrai si l'utilisateur a modifié quelque chose — c'est ce qui décide d'AFFICHER le bouton
   *  « réinitialiser » : le proposer en permanence encombrerait la barre pour rien. */
  function estModifie() {
    return JSON.stringify(prefs.value) !== JSON.stringify(DEFAUTS)
  }

  charger()
  return { prefs, reinitialiser, estModifie, charger }
}
