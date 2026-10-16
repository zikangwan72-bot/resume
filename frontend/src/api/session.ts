import { reactive } from 'vue'

// Shared state for the "session expired, log in again" modal. Every request
// that hits a 401 while the modal is open waits on the same promise, so one
// successful re-login retries all of them.
export const reloginState = reactive({ visible: false, email: '' })

let pending: { promise: Promise<void>; resolve: () => void; reject: (reason?: unknown) => void } | null = null

export function requestRelogin(email: string): Promise<void> {
  if (!pending) {
    let resolve!: () => void
    let reject!: (reason?: unknown) => void
    const promise = new Promise<void>((res, rej) => {
      resolve = res
      reject = rej
    })
    pending = { promise, resolve, reject }
    reloginState.email = email
    reloginState.visible = true
  }
  return pending.promise
}

export function finishRelogin(ok: boolean) {
  const current = pending
  pending = null
  reloginState.visible = false
  if (!current) return
  if (ok) current.resolve()
  else current.reject(new Error('relogin cancelled'))
}
