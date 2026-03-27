import { onMounted, onUnmounted, type Ref } from 'vue'

export function useClickOutside(
  target: Ref<HTMLElement | null>,
  handler: () => void
) {
  const listener = (e: MouseEvent) => {
    if (!target.value?.contains(e.target as Node)) handler()
  }
  onMounted(() => document.addEventListener('mousedown', listener))
  onUnmounted(() => document.removeEventListener('mousedown', listener))
}
