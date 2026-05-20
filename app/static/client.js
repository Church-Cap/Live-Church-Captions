(() => {
  const current = document.getElementById('currentCaption');
  const history = document.getElementById('history');
  const connection = document.getElementById('connection');
  const languageSelect = document.getElementById('languageSelect');
  const languageFlag = document.getElementById('languageFlag');
  const translationNotice = document.getElementById('translationNotice');
  const translationWarning = document.getElementById('translationWarning');

  const MAX_HISTORY_ITEMS = 120;
  const SOURCE_LANGUAGE = 'en';
  const UI_STRINGS = window.CC_UI_STRINGS || {};
  const LANGUAGES = window.CC_LANGUAGES || [{code: 'en', native: 'English', flag: '🇬🇧', dir: 'ltr'}];
  let translationState = window.CC_TRANSLATION_STATE || {enabled: false};

  let paused = false;
  let fontScale = Number(localStorage.getItem('captionFontScale') || '1');
  let comfortMode = localStorage.getItem('captionComfortMode') === '1';
  let viewerTheme = localStorage.getItem('captionTheme') || 'dark';
  let viewerLanguage = localStorage.getItem('captionLanguage') || navigator.language?.split('-')[0] || SOURCE_LANGUAGE;
  if (!LANGUAGES.find(l => l.code === viewerLanguage)) viewerLanguage = SOURCE_LANGUAGE;
  let pendingCurrentText = null;
  let rafScheduled = false;
  const seenIds = new Set();
  let socket = null;
  let reconnectTimer = null;
  let manualReconnect = false;

  function t(key) {
    return (UI_STRINGS[viewerLanguage] && UI_STRINGS[viewerLanguage][key]) ||
           (UI_STRINGS.en && UI_STRINGS.en[key]) || key;
  }

  function setConnection(text, ok) {
    if (!connection) return;
    connection.textContent = text;
    connection.classList.toggle('ok', !!ok);
  }

  function applyLanguage() {
    const lang = LANGUAGES.find(l => l.code === viewerLanguage) || LANGUAGES[0];
    document.documentElement.lang = viewerLanguage;
    document.documentElement.dir = lang.dir || 'ltr';
    if (languageSelect) languageSelect.value = viewerLanguage;
    if (languageFlag) languageFlag.textContent = lang.flag || '🌐';
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      if (key) el.textContent = t(key);
    });
    if (current && current.dataset.i18n === 'waiting') current.textContent = t('waiting');
    if (translationNotice) translationNotice.hidden = viewerLanguage === SOURCE_LANGUAGE;
    localStorage.setItem('captionLanguage', viewerLanguage);
  }

  function applyFontScale() {
    document.documentElement.style.setProperty('--caption-scale', fontScale.toFixed(2));
    localStorage.setItem('captionFontScale', fontScale.toString());
  }

  function applyViewerTheme() {
    document.body.classList.toggle('light-mode', viewerTheme === 'light');
    const btn = document.getElementById('toggleTheme');
    if (btn) btn.textContent = viewerTheme === 'light' ? 'Dark' : t('theme');
    localStorage.setItem('captionTheme', viewerTheme);
  }

  function applyComfortMode() {
    document.body.classList.toggle('comfort-mode', comfortMode);
    const btn = document.getElementById('toggleCompact');
    if (btn) btn.textContent = comfortMode ? t('compact') : t('comfort');
    localStorage.setItem('captionComfortMode', comfortMode ? '1' : '0');
  }

  function scheduleCurrentText(text) {
    pendingCurrentText = text;
    if (rafScheduled) return;
    rafScheduled = true;
    requestAnimationFrame(() => {
      if (current && pendingCurrentText !== null) {
        current.textContent = pendingCurrentText;
        current.removeAttribute('data-i18n');
      }
      pendingCurrentText = null;
      rafScheduled = false;
    });
  }

  function showTranslationWarning(message) {
    if (!translationWarning) return;
    if (!message) {
      translationWarning.hidden = true;
      translationWarning.textContent = '';
      return;
    }
    translationWarning.textContent = message || t('translation_not_available');
    translationWarning.hidden = false;
  }

  function normaliseId(text, id) {
    if (id) return String(id);
    return 'text:' + String(text || '').toLowerCase().replace(/\s+/g, ' ').trim().slice(0, 160);
  }

  function addHistory(text, id) {
    if (!history || !text || paused) return;
    const key = normaliseId(text, id);
    if (seenIds.has(key)) return;
    seenIds.add(key);

    const p = document.createElement('p');
    p.textContent = text;
    p.dataset.id = key;
    history.prepend(p);

    while (history.children.length > MAX_HISTORY_ITEMS) {
      const last = history.lastElementChild;
      if (last?.dataset?.id) seenIds.delete(last.dataset.id);
      history.removeChild(last);
    }
  }

  function renderHistoryFromState(items) {
    if (!history || paused) return;
    history.textContent = '';
    seenIds.clear();
    const frag = document.createDocumentFragment();
    const recent = (items || []).slice(-MAX_HISTORY_ITEMS).reverse();
    for (const seg of recent) {
      if (!seg.text) continue;
      const key = normaliseId(seg.text, seg.id);
      if (seenIds.has(key)) continue;
      seenIds.add(key);
      const p = document.createElement('p');
      p.textContent = seg.text;
      p.dataset.id = key;
      frag.appendChild(p);
    }
    history.appendChild(frag);
  }

  function renderState(state) {
    if (paused) return;
    if (state.current && current) scheduleCurrentText(state.current.text);
    if (Array.isArray(state.history)) renderHistoryFromState(state.history);
  }

  function connect() {
    manualReconnect = true;
    if (socket) {
      try { socket.close(); } catch (_) {}
    }
    if (reconnectTimer) clearTimeout(reconnectTimer);
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${protocol}://${location.host}/ws/captions?lang=${encodeURIComponent(viewerLanguage)}`);
    socket = ws;
    let pingTimer = null;

    ws.onopen = () => {
      manualReconnect = false;
      setConnection(t('live'), true);
      ws.send('hello');
      pingTimer = setInterval(() => {
        try { ws.send('ping'); } catch (_) {}
      }, 15000);
    };

    ws.onmessage = (event) => {
      let payload;
      try { payload = JSON.parse(event.data); } catch (_) { return; }

      if (payload.type === 'state') renderState(payload.data);
      if (payload.type === 'viewer_meta') translationState = payload.data || translationState;

      if (payload.type === 'caption') {
        if (paused) return;
        const seg = payload.data || {};
        const text = seg.text || '';
        scheduleCurrentText(text);
        showTranslationWarning(payload.translation_warning);
        if (seg.is_final) addHistory(text, seg.id);
      }

      if (payload.type === 'sensitive' && !paused) scheduleCurrentText(payload.message || 'Captions are paused for a private or sensitive moment.');

      if (payload.type === 'clear') {
        scheduleCurrentText(t('waiting'));
        if (history) history.textContent = '';
        seenIds.clear();
      }
    };

    ws.onclose = () => {
      if (ws !== socket) return;
      if (pingTimer) clearInterval(pingTimer);
      if (manualReconnect) return;
      setConnection(t('reconnecting'), false);
      reconnectTimer = setTimeout(connect, 2000);
    };

    ws.onerror = () => setConnection(t('connection_issue'), false);
  }

  languageSelect?.addEventListener('change', () => {
    viewerLanguage = languageSelect.value || SOURCE_LANGUAGE;
    applyLanguage();
    applyViewerTheme();
    applyComfortMode();
    if (history) history.textContent = '';
    seenIds.clear();
    showTranslationWarning(null);
    connect();
  });

  document.getElementById('largerText')?.addEventListener('click', () => {
    fontScale = Math.min(1.8, fontScale + 0.1);
    applyFontScale();
  });

  document.getElementById('smallerText')?.addEventListener('click', () => {
    fontScale = Math.max(0.65, fontScale - 0.1);
    applyFontScale();
  });

  document.getElementById('toggleTheme')?.addEventListener('click', () => {
    viewerTheme = viewerTheme === 'light' ? 'dark' : 'light';
    applyViewerTheme();
  });

  document.getElementById('toggleCompact')?.addEventListener('click', () => {
    comfortMode = !comfortMode;
    applyComfortMode();
  });

  document.getElementById('pauseScroll')?.addEventListener('click', (e) => {
    paused = !paused;
    e.target.textContent = paused ? t('resume') : t('pause');
    if (paused && current) {
      const frozen = current.textContent || t('waiting');
      current.textContent = frozen + '  ·  ' + t('pause');
    } else {
      connect();
    }
  });

  document.getElementById('clearLocal')?.addEventListener('click', () => {
    if (history) history.textContent = '';
    seenIds.clear();
  });

  applyLanguage();
  applyFontScale();
  applyViewerTheme();
  applyComfortMode();
  connect();
})();
