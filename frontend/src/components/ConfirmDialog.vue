<script setup lang="ts">
// Dialogue de confirmation pour actions destructives (ex. suppression de projet).
// Rien n'est supprimé sans confirmation explicite — standard produit.
import Button from './ui/Button.vue'

defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  busy?: boolean
}>()
const emit = defineEmits<{ (e: 'confirm'): void; (e: 'cancel'): void }>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 grid place-items-center bg-background/70 backdrop-blur-sm p-4"
         @click.self="emit('cancel')">
      <div class="w-full max-w-md rounded-xl border border-border bg-surface-overlay p-5 shadow-2xl">
        <h3 class="text-base font-semibold">{{ title }}</h3>
        <p class="mt-2 text-sm text-muted-foreground whitespace-pre-line">{{ message }}</p>
        <div class="mt-5 flex justify-end gap-2">
          <Button variant="ghost" :disabled="busy" @click="emit('cancel')">Annuler</Button>
          <Button variant="danger" :loading="busy" @click="emit('confirm')">{{ confirmLabel || 'Supprimer' }}</Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
