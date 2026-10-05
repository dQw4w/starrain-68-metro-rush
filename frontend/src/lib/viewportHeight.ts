/**
 * Publishes the *actually visible* viewport height as `--app-vh`.
 *
 * iOS sizes `100vh` (and `height:100%` on html) to the LARGE viewport — the
 * page as it would be with the browser toolbars hidden. With Chrome's
 * toolbars on screen the app is therefore taller than what you can see, the
 * document becomes scrollable, and scrolling takes the player page's header
 * (team name / chips / clock) up underneath the URL bar, where it's awkward
 * to get back. Safari hides its toolbar as you scroll so it masks the same
 * bug.
 *
 * `100dvh` fixes this on iOS 15.4+, and the CSS uses it when available — but
 * this measurement is the belt-and-braces version: `window.innerHeight` on
 * iOS always reports the currently visible height, including on older
 * versions, and updates as the toolbars come and go.
 */
export function installViewportHeightVar(): () => void {
  const apply = () => {
    document.documentElement.style.setProperty('--app-vh', `${window.innerHeight}px`)
  }
  apply()
  window.addEventListener('resize', apply)
  window.addEventListener('orientationchange', apply)
  // Toolbar show/hide doesn't always fire a window resize on iOS, but it
  // does move the visual viewport.
  window.visualViewport?.addEventListener('resize', apply)
  return () => {
    window.removeEventListener('resize', apply)
    window.removeEventListener('orientationchange', apply)
    window.visualViewport?.removeEventListener('resize', apply)
  }
}
