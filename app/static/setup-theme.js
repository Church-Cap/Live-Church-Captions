(() => {
  if (document.body?.dataset.factoryReset === 'true') {
    localStorage.clear();
    sessionStorage.clear();
  }
  const button = document.querySelector('#onboardingThemeToggle');
  const label = document.querySelector('#onboardingThemeLabel');
  const glyph = document.querySelector('#onboardingThemeGlyph');
  const formPreference = document.querySelector('#setupThemePreference');
  const media = window.matchMedia?.('(prefers-color-scheme: light)');

  function storedPreference() {
    try {
      const stored = localStorage.getItem('operatorTheme');
      const manual = localStorage.getItem('operatorThemeManual') === '1';
      if (manual && (stored === 'light' || stored === 'dark')) return stored;
    } catch (_) {}
    return 'system';
  }

  function resolvedMode(preference = storedPreference()) {
    if (preference === 'system') return media?.matches ? 'light' : 'dark';
    return preference === 'light' ? 'light' : 'dark';
  }

  function applyTheme(preference, {persist = false} = {}) {
    const mode = resolvedMode(preference);
    document.body.classList.toggle('light-mode', mode === 'light');
    const nextMode = mode === 'light' ? 'dark' : 'light';
    if (label) label.textContent = `${nextMode === 'light' ? 'Light' : 'Dark'} mode`;
    if (glyph) glyph.textContent = nextMode === 'light' ? '☀︎' : '☾';
    if (button) {
      button.setAttribute('aria-label', `Switch to ${nextMode} mode`);
      button.setAttribute('aria-pressed', String(mode === 'light'));
    }
    if (formPreference) formPreference.value = preference === 'system' ? 'system' : mode;
    if (persist) {
      try {
        localStorage.setItem('operatorTheme', mode);
        localStorage.setItem('operatorThemeManual', '1');
      } catch (_) {}
    }
  }

  button?.addEventListener('click', () => {
    const current = resolvedMode();
    applyTheme(current === 'light' ? 'dark' : 'light', {persist: true});
  });

  media?.addEventListener?.('change', () => {
    if (storedPreference() === 'system') applyTheme('system');
  });

  applyTheme(storedPreference());
})();
