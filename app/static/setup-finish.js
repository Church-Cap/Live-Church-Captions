(() => {
  const translationCard = document.querySelector('#onboardingInstallCard');
  const spokenCard = document.querySelector('#onboardingSpokenInstallCard');
  if (!translationCard && !spokenCard) return;

  let timer = null;

  function boundedPercent(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, Math.min(100, Math.round(number))) : fallback;
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (!Number.isFinite(bytes) || bytes <= 0) return '0 MB';
    if (bytes >= 1000 ** 3) return `${(bytes / (1000 ** 3)).toFixed(1)} GB`;
    return `${Math.ceil(bytes / (1000 ** 2))} MB`;
  }

  function progressMeta(progress = {}) {
    const parts = [];
    if (Number(progress.total_bytes || 0) > 0) parts.push(`${formatBytes(progress.downloaded_bytes)} of ${formatBytes(progress.total_bytes)}`);
    if (Number(progress.item_count || 0) > 0) parts.push(`Package ${Math.min(Number(progress.item_index || 1), Number(progress.item_count))} of ${Number(progress.item_count)}`);
    return parts.join(' · ');
  }

  function renderCard(card, install, kind) {
    if (!card) return 'absent';
    const state = String(install?.status || 'idle');
    const progress = install?.progress || {};
    const percent = state === 'complete' ? 100 : boundedPercent(progress.percent);
    const prefix = kind === 'spoken' ? 'onboardingSpokenInstall' : 'onboardingInstall';
    const title = document.querySelector(`#${prefix}Title`);
    const percentLabel = document.querySelector(`#${prefix}Percent`);
    const bar = document.querySelector(`#${prefix}ProgressBar`);
    const detail = document.querySelector(`#${prefix}Detail`);
    const meta = document.querySelector(`#${prefix}Meta`);
    const spinner = document.querySelector(`#${prefix}Spinner`);
    card.dataset.state = state;
    bar?.style.setProperty('--install-progress', `${percent}%`);
    if (percentLabel) percentLabel.textContent = state === 'error' && progress.percent == null ? '—' : `${percent}%`;
    if (spinner) spinner.hidden = !['waiting', 'installing'].includes(state);

    if (kind === 'spoken') {
      if (state === 'complete') {
        if (title) title.textContent = 'Spoken translated audio is installed';
        if (detail) detail.textContent = install.message || progress.detail || 'The selected voice packs are ready.';
      } else if (state === 'error') {
        if (title) title.textContent = 'Spoken audio needs attention';
        if (detail) detail.textContent = install.error || progress.detail || 'Open Spoken Translated Audio from Languages to retry.';
      } else if (state === 'waiting') {
        if (title) title.textContent = 'Spoken audio is queued';
        if (detail) detail.textContent = progress.detail || 'Waiting for caption language installation to finish.';
      } else {
        if (title) title.textContent = 'Installing spoken translated audio';
        if (detail) detail.textContent = progress.detail || 'Preparing the selected local voices.';
      }
    } else if (state === 'complete') {
      if (title) title.textContent = 'Translated captions are installed';
      if (detail) detail.textContent = install.message || progress.detail || 'The selected language pack is ready.';
    } else if (state === 'error') {
      if (title) title.textContent = 'The language download needs attention';
      if (detail) detail.textContent = install.error || install.message || 'Open Languages from the Operator page to retry.';
    } else {
      if (title) title.textContent = 'Installing translated captions';
      if (detail) detail.textContent = progress.detail || 'Preparing the selected local language pack.';
    }

    const metaText = progressMeta(progress);
    if (meta) {
      meta.textContent = metaText;
      meta.hidden = !metaText;
    }
    return state;
  }

  function parseInitial(id) {
    try { return JSON.parse(document.querySelector(id)?.textContent || '{}'); }
    catch (_error) { return {}; }
  }

  function allFinished(translationState, spokenState) {
    const terminal = (state) => ['complete', 'error', 'absent'].includes(state);
    return terminal(translationState) && terminal(spokenState);
  }

  async function poll() {
    try {
      const response = await fetch('/api/setup/install-status', {headers: {'Accept': 'application/json'}, cache: 'no-store'});
      if (response.status === 401) {
        window.location.href = '/login';
        return;
      }
      const data = await response.json();
      const translationState = renderCard(translationCard, data.translation || {}, 'translation');
      const spokenState = renderCard(spokenCard, data.spoken_audio || {}, 'spoken');
      if (!allFinished(translationState, spokenState)) timer = setTimeout(poll, 1200);
    } catch (_error) {
      const detail = document.querySelector('#onboardingInstallDetail') || document.querySelector('#onboardingSpokenInstallDetail');
      if (detail) detail.textContent = 'Waiting for Church Cap to report installation progress…';
      timer = setTimeout(poll, 2000);
    }
  }

  const translationState = renderCard(translationCard, parseInitial('#onboardingInstallInitialState'), 'translation');
  const spokenState = renderCard(spokenCard, parseInitial('#onboardingSpokenInstallInitialState'), 'spoken');
  if (!allFinished(translationState, spokenState)) poll();
})();
