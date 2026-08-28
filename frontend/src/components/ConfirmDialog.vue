<script setup lang="ts">
// Dialogue de confirmation pour actions destructives (ex. suppression de projet).
// Rien n'est supprimé sans confirmation explicite — standard produit.
//
// Piège de focus et verrouillage du scroll : composables partagés avec Modal.vue (lib/
// useFocusTrap, lib/scrollLock) — absents ici jusqu'au 2026-08-13, ce dialogue laissait `Tab`
// s'échapper vers la page masquée derrière, et la page défilait encore sous l'overlay.
import { toRef, watch } from 'vue'
import Button from './ui/Button.vue'
import { useFocusTrap } from '../lib/useFocusTrap'
import { verrouillerScroll, deverrouillerScroll } from '../lib/scrollLock'

const props = defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  busy?: boolean
  confirmDisabled?: boolean
}>()
const emit = defineEmits<{ (e: 'confirm'): void; (e: 'cancel'): void }>()

const { panneau } = useFocusTrap(toRef(props, 'open'), () => emit('cancel'))

watch(toRef(props, 'open'), (v) => (v ? verrouillerScroll() : deverrouillerScroll()))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 grid place-items-center bg-background/70 backdrop-blur-sm p-4"
         @click.self="emit('cancel')">
      <div ref="panneau" class="w-full max-w-md rounded-xl border border-border bg-surface-overlay p-5 shadow-2xl"
           role="dialog" aria-modal="true" :aria-label="title">
        <h3 class="text-base font-semibold">{{ title }}</h3>
        <p class="mt-2 text-sm text-muted-foreground whitespace-pre-line">{{ message }}</p>
        <div class="mt-5 flex justify-end gap-2">
          <Button variant="ghost" :disabled="busy" @click="emit('cancel')">Annuler</Button>
          <Button variant="danger" :loading="busy" :disabled="confirmDisabled" @click="emit('confirm')">{{ confirmLabel || 'Supprimer' }}</Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
