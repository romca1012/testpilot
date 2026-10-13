// Lot PT-00 (2026-10-13) — la nouvelle organisation « Paramètres de test » est-elle allumée sur cette installation ?
//
// Un seul endroit pour le savoir : chaque écran concerné pose la même question, et un interrupteur lu de deux façons
// finirait par montrer la nouveauté à moitié. Éteint (défaut), l'interface est strictement celle d'avant.
import { computed } from 'vue'
import { useSettings } from './useSettings'

export const CLE_PARAMETRES_DE_TEST = 'parametres_de_test_enabled'

export function estAllume(valeur: string | undefined | null): boolean {
  return ['1', 'true', 'oui', 'on', 'yes'].includes(String(valeur ?? '').trim().toLowerCase())
}

export function useParametresDeTest() {
  const { get, loaded } = useSettings()
  // `connu` : les réglages sont arrivés. Avant, « éteint » voudrait seulement dire « pas encore chargé ».
  return { actifs: computed(() => estAllume(get(CLE_PARAMETRES_DE_TEST))), connu: loaded }
}
