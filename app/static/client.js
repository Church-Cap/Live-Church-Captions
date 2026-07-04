(() => {
  const current = document.getElementById('currentCaption');
  const history = document.getElementById('history');
  const historyWrap = document.getElementById('historyWrap');
  const connection = document.getElementById('connection');
  const languageSelect = document.getElementById('languageSelect');
  const languageSearch = document.getElementById('languageSearch');
  const languageFlag = document.getElementById('languageFlag');
  const languagePickerButton = document.getElementById('languagePickerButton');
  const languagePickerLabel = document.getElementById('languagePickerLabel');
  const languagePickerOverlay = document.getElementById('languagePickerOverlay');
  const languagePickerBackdrop = document.getElementById('languagePickerBackdrop');
  const languagePickerClose = document.getElementById('languagePickerClose');
  const languageList = document.getElementById('languageList');
  const translationNotice = document.getElementById('translationNotice');
  const captionLoadNotice = document.getElementById('captionLoadNotice');
  const viewerHint = document.getElementById('viewerHint');
  const isPhonePage = document.body.classList.contains('phone-page');
  const isPresentationPage = document.body.classList.contains('display-page') || document.body.classList.contains('obs-page');

  const MAX_LIVE_SEGMENTS = 120;
  const MAX_TRANSCRIPT_ITEMS = 1000;
  const SOURCE_LANGUAGE = 'en';
  const UI_STRINGS = window.CC_UI_STRINGS || {};
  const UI_STRING_SOURCES = window.CC_UI_STRING_SOURCES || {};
  const LANGUAGES = window.CC_LANGUAGES || [{code: 'en', native: 'English', flag: '', dir: 'ltr'}];
  let translationState = window.CC_TRANSLATION_STATE || {enabled: false};
  let languageMetadataRefreshTimer = null;
  let languageMetadataRequest = null;
  let screenWakeLock = null;
  let wakeLockRequested = false;

  let paused = false;
  let fontScale = Number(localStorage.getItem('captionFontScale') || '1');
  let comfortMode = localStorage.getItem('captionComfortMode') === '1';
  let transcriptVisible = localStorage.getItem('captionTranscriptVisible') !== '0';
  let viewerThemePreference = initialiseViewerThemePreference();
  let viewerTheme = resolveViewerTheme();
  let viewerLanguage = localStorage.getItem('captionLanguage') || navigator.language?.split('-')[0] || SOURCE_LANGUAGE;
  if (!LANGUAGES.find(l => l.code === viewerLanguage)) viewerLanguage = SOURCE_LANGUAGE;
  if (Array.isArray(translationState.available_languages) && !translationState.available_languages.includes(viewerLanguage)) {
    viewerLanguage = SOURCE_LANGUAGE;
  }
  let pendingCurrentText = null;
  let rafScheduled = false;
  const seenIds = new Set();
  const seenLogIds = new Set();
  let finalSegments = [];
  let logSegments = [];
  let lastRenderedLogIds = new Set();
  let draftLogCounter = 0;
  let activeBlock = null;
  let activeBlockUntil = 0;
  let blockQueue = [];
  let blockTimer = null;
  let currentDraftText = '';
  let systemMessageText = '';
  let systemMessageKey = '';
  let systemMessageFallback = '';
  let lastPartialShownAt = 0;
  let historyLogEnabled = true;
  let socket = null;
  let reconnectTimer = null;
  let manualReconnect = false;
  let captionLoadNoticeTimer = null;
  let captionLoadNoticeShownAt = 0;
  const uiStringRequests = new Map();
  const uiStringResolved = new Set();

  const MIN_PARTIAL_UPDATE_MS = 1100;
  const TARGET_READING_CPS = 19;
  const MIN_BLOCK_MS = 1100;
  const MAX_BLOCK_MS = 3600;
  const BLOCK_BREATHING_ROOM_MS = 180;
  const SUBTITLE_GLIDE_MS = 260;
  const DRAFT_LOG_UPDATE_MS = 3000;
  const MIN_CAPTION_LOAD_NOTICE_MS = 900;
  const MAX_CAPTION_LOAD_NOTICE_MS = 8000;
  let lastDraftLogAt = 0;

  function t(key) {
    return (UI_STRINGS[viewerLanguage] && UI_STRINGS[viewerLanguage][key]) ||
           (UI_STRINGS.en && UI_STRINGS.en[key]) || key;
  }

  async function requestScreenWakeLock() {
    if (!isPhonePage || !('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
    wakeLockRequested = true;
    try {
      screenWakeLock = await navigator.wakeLock.request('screen');
      screenWakeLock.addEventListener('release', () => { screenWakeLock = null; });
    } catch (_) {
      screenWakeLock = null;
    }
  }

  async function refreshScreenWakeLock() {
    if (!isPhonePage || !wakeLockRequested) return;
    if (document.visibilityState === 'visible' && !screenWakeLock) await requestScreenWakeLock();
  }

  function uiText(key, fallback = '') {
    const selected = UI_STRINGS[viewerLanguage] && UI_STRINGS[viewerLanguage][key];
    if (selected && selected !== key) return selected;
    const english = UI_STRINGS[SOURCE_LANGUAGE] && UI_STRINGS[SOURCE_LANGUAGE][key];
    return fallback || english || key;
  }

  async function showSystemMessageFromKey(key, fallback = '') {
    systemMessageKey = key;
    systemMessageFallback = fallback || '';
    systemMessageText = uiText(key, fallback);
    currentDraftText = '';
    renderSubtitleStack();
    if (viewerLanguage !== SOURCE_LANGUAGE) {
      await ensureLanguageUiStrings(viewerLanguage, {showLoading: false});
      const refreshed = uiText(key, fallback);
      if (refreshed !== systemMessageText) {
        systemMessageText = refreshed;
        renderSubtitleStack();
      }
    }
  }

  function setConnection(key, ok) {
    if (!connection) return;
    connection.dataset.connectionKey = key;
    connection.textContent = t(key) || key;
    connection.classList.toggle('ok', !!ok);
  }

  function applyLanguage({fetchUiStrings = true} = {}) {
    const lang = LANGUAGES.find(l => l.code === viewerLanguage) || LANGUAGES[0];
    const marker = languageMarker(lang);
    document.documentElement.lang = viewerLanguage;
    document.documentElement.dir = lang.dir || 'ltr';
    if (languageSelect) languageSelect.value = viewerLanguage;
    if (languageFlag) {
      languageFlag.textContent = marker.text;
      languageFlag.dataset.code = marker.code;
      languageFlag.title = `${languageDisplayName(lang)} · ${marker.code}`;
      languageFlag.classList.toggle('language-code-badge', marker.isBadge);
      languageFlag.classList.toggle('language-flag-chip', marker.isFlag);
    }
    if (languagePickerLabel) languagePickerLabel.textContent = languageDisplayName(lang);
    document.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      if (key) el.textContent = t(key);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (key) el.setAttribute('placeholder', t(key));
    });
    document.querySelectorAll('[data-i18n-aria-label]').forEach((el) => {
      const key = el.getAttribute('data-i18n-aria-label');
      if (key) el.setAttribute('aria-label', t(key));
    });
    document.title = `Church Cap · ${t('live_captions')}`;
    if (connection?.dataset.connectionKey) {
      connection.textContent = t(connection.dataset.connectionKey);
    }
    if (captionLoadNotice && !captionLoadNotice.hidden && captionLoadNotice.dataset.noticeKey) {
      captionLoadNotice.textContent = uiText(captionLoadNotice.dataset.noticeKey, captionLoadNotice.dataset.noticeFallback || '');
    }
    if (systemMessageKey) {
      systemMessageText = uiText(systemMessageKey, systemMessageFallback);
    }
    if (current && current.dataset.i18n === 'waiting') current.textContent = t('waiting');
    if (translationNotice) translationNotice.hidden = viewerLanguage === SOURCE_LANGUAGE;
    localStorage.setItem('captionLanguage', viewerLanguage);
    applyViewerTheme();
    applyComfortMode();
    updateTranscriptToggleButton();
    renderLanguageList(languageSearch?.value || '');
    renderSubtitleStack();
    renderHistoryRoll();
    if (fetchUiStrings) ensureLanguageUiStrings(viewerLanguage);
  }

  function languageDisplayName(lang) {
    if (!lang) return 'English';
    const english = lang.name || lang.native || lang.code?.toUpperCase();
    const native = lang.native || english;
    return native === english ? english : `${english} (${native})`;
  }

  function languageSearchText(lang) {
    return `${lang.code || ''} ${lang.name || ''} ${lang.native || ''}`.toLowerCase();
  }

  function translationCaptionsUnavailable() {
    return !translationState?.enabled;
  }

  function availableCaptionLanguageCodes() {
    if (!translationState?.enabled) return new Set([SOURCE_LANGUAGE]);
    if (Array.isArray(translationState.available_languages)) {
      return new Set(translationState.available_languages);
    }
    const provider = translationState.provider || 'disabled';
    const resources = translationState.resources || {};
    const codes = new Set([SOURCE_LANGUAGE]);
    if (provider === 'argos' || provider === 'both') {
      (resources.argos?.installed_languages || []).forEach(code => codes.add(code));
    }
    if ((provider === 'ct2small100' || provider === 'both') && resources.ct2small100?.status?.ready) {
      (resources.ct2small100?.languages || []).forEach(code => codes.add(code));
    }
    if ((provider === 'small100' || provider === 'both') && resources.small100?.status?.ready) {
      (resources.small100?.languages || []).forEach(code => codes.add(code));
    }
    return codes;
  }

  function requestableCaptionLanguageCodes() {
    if (!translationState?.enabled || translationState?.language_policy !== 'restricted' || translationState?.language_requests_enabled === false) return new Set();
    return new Set(Array.isArray(translationState.requestable_languages) ? translationState.requestable_languages : []);
  }

  function pendingLanguageRequestCodes() {
    return new Set((translationState?.language_requests || []).map(item => String(item.code || '').toLowerCase()));
  }

  function filteredLanguagesForCurrentMode() {
    const available = availableCaptionLanguageCodes();
    const requestable = requestableCaptionLanguageCodes();
    if (!available) return LANGUAGES;
    return LANGUAGES.filter(lang => available.has(lang.code) || requestable.has(lang.code));
  }

  async function refreshLanguageMetadata({reconnectIfNeeded = true} = {}) {
    if (languageMetadataRequest) return languageMetadataRequest;
    languageMetadataRequest = fetch('/api/languages', {cache: 'no-store', headers: {Accept: 'application/json'}})
      .then(async (response) => {
        if (!response.ok) throw new Error(`Language refresh failed: ${response.status}`);
        const data = await response.json();
        if (data.translation) translationState = data.translation;
        if (data.ui_strings) Object.assign(UI_STRINGS, data.ui_strings);
        if (data.ui_string_sources) Object.assign(UI_STRING_SOURCES, data.ui_string_sources);
        const changed = ensureViewerLanguageIsAvailable();
        applyLanguage({fetchUiStrings: false});
        if (changed && reconnectIfNeeded) connect();
        return data;
      })
      .catch(() => null)
      .finally(() => {
        languageMetadataRequest = null;
      });
    return languageMetadataRequest;
  }

  function ensureViewerLanguageIsAvailable() {
    const available = availableCaptionLanguageCodes();
    if (available && !available.has(viewerLanguage)) {
      viewerLanguage = SOURCE_LANGUAGE;
      return true;
    }
    return false;
  }

  function languageMarker(lang) {
    const code = String(lang?.code || 'cc').slice(0, 3).toUpperCase();
    const flag = String(lang?.flag || '').trim();
    if (flag && flag !== '🌐') return {text: flag, code, isBadge: false, isFlag: true};
    return {text: code, code, isBadge: true, isFlag: false};
  }

  async function ensureLanguageUiStrings(code, {showLoading = true} = {}) {
    if (!code || code === SOURCE_LANGUAGE) return;
    if (uiStringResolved.has(code)) return;
    if (uiStringRequests.has(code)) return uiStringRequests.get(code);
    const source = UI_STRING_SOURCES[code] || 'fallback';
    if (UI_STRINGS[code] && source !== 'fallback') {
      uiStringResolved.add(code);
      return;
    }
    const request = (async () => {
      if (showLoading && code === viewerLanguage) showCaptionLoadNotice('connecting');
      try {
        const response = await fetch(`/api/client-ui/${encodeURIComponent(code)}`, {
          headers: {'Accept': 'application/json'},
          cache: 'no-store',
        });
        if (!response.ok) return;
        const payload = await response.json();
        if (payload?.strings && payload.language === code) {
          UI_STRINGS[code] = {
            ...(UI_STRINGS[SOURCE_LANGUAGE] || {}),
            ...(UI_STRINGS[code] || {}),
            ...payload.strings,
          };
          UI_STRING_SOURCES[code] = payload.source || UI_STRING_SOURCES[code] || 'fallback';
          uiStringResolved.add(code);
          if (viewerLanguage === code) applyLanguage({fetchUiStrings: false});
        }
      } catch (_) {
        // Keep the bundled fallback if local UI translation is unavailable.
      } finally {
        uiStringRequests.delete(code);
        if (showLoading && code === viewerLanguage) hideCaptionLoadNotice();
      }
    })();
    uiStringRequests.set(code, request);
    return request;
  }

  function applyFontScale() {
    document.documentElement.style.setProperty('--caption-scale', fontScale.toFixed(2));
    localStorage.setItem('captionFontScale', fontScale.toString());
    renderSubtitleStack();
    renderHistoryRoll();
  }

  function initialiseViewerThemePreference() {
    const stored = localStorage.getItem('captionTheme');
    const manual = localStorage.getItem('captionThemeManual') === '1';
    if (manual && (stored === 'light' || stored === 'dark')) return stored;
    localStorage.removeItem('captionTheme');
    return 'system';
  }

  function systemPrefersLight() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
  }

  function resolveViewerTheme() {
    return viewerThemePreference === 'system'
      ? (systemPrefersLight() ? 'light' : 'dark')
      : viewerThemePreference;
  }

  function applyViewerTheme({persist = false} = {}) {
    viewerTheme = resolveViewerTheme();
    document.body.classList.toggle('light-mode', viewerTheme === 'light');
    const btn = document.getElementById('toggleTheme');
    if (btn) btn.textContent = viewerTheme === 'light' ? t('dark_theme') : t('theme');
    if (persist) {
      localStorage.setItem('captionTheme', viewerThemePreference);
      localStorage.setItem('captionThemeManual', '1');
    }
  }

  function applyComfortMode() {
    document.body.classList.toggle('comfort-mode', comfortMode);
    const btn = document.getElementById('toggleCompact');
    if (btn) btn.textContent = comfortMode ? t('compact') : t('comfort');
    localStorage.setItem('captionComfortMode', comfortMode ? '1' : '0');
    renderSubtitleStack();
    renderHistoryRoll();
  }

  function updateTranscriptToggleButton() {
    const btn = document.getElementById('toggleTranscript');
    if (!btn) return;
    btn.textContent = transcriptVisible ? t('hide_transcript') : t('show_transcript');
    btn.setAttribute('aria-expanded', transcriptVisible ? 'true' : 'false');
    btn.setAttribute('aria-controls', 'historyWrap');
  }

  function applyTranscriptVisibility() {
    document.body.classList.toggle('transcript-hidden', !transcriptVisible);
    if (historyWrap) historyWrap.hidden = !transcriptVisible;
    updateTranscriptToggleButton();
    localStorage.setItem('captionTranscriptVisible', transcriptVisible ? '1' : '0');
    if (transcriptVisible) renderHistoryRoll();
    renderSubtitleStack();
  }

  function subtitleLimits() {
    const landscape = window.matchMedia('(orientation: landscape)').matches || window.innerWidth > window.innerHeight;
    const presentationObs = document.body.classList.contains('obs-page');
    const baseChars = isPresentationPage ? (presentationObs ? 42 : 50) : (landscape ? 52 : 42);
    const estimatedLineHeight = current ? Math.max(24, parseFloat(getComputedStyle(current).lineHeight) || 30) : 30;
    const availableHeight = current ? Math.max(220, current.clientHeight - 24) : 300;
    const capacity = isPresentationPage ? 2 : Math.max(4, Math.floor(availableHeight / estimatedLineHeight));
    return {
      chars: Math.max(28, Math.round(baseChars / Math.max(fontScale, 0.9))),
      maxLines: isPresentationPage ? 2 : Math.max(4, capacity),
    };
  }

  function wordsForCompare(text) {
    return String(text || '')
      .toLowerCase()
      .replace(/[.,;:!?()[\]"']/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .split(' ')
      .filter(Boolean);
  }

  function cleanCaptionText(text) {
    const cleaned = String(text || '').replace(/\s+/g, ' ').trim();
    if (!cleaned) return '';
    if (!/[\p{L}\p{N}]/u.test(cleaned)) return '';
    if (/^[\s.·•…\-–—_,;:!?|\/\\()[\]{}"'`~*+=<>]+$/.test(cleaned)) return '';
    return cleaned;
  }

  function captionContentAvailable() {
    return !!(
      cleanCaptionText(currentDraftText) ||
      cleanCaptionText(activeBlock?.text) ||
      finalSegments.some(seg => cleanCaptionText(seg?.text))
    );
  }

  function showCaptionLoadNotice(key = 'connecting', {fallback = '', requireContent = true} = {}) {
    if (!captionLoadNotice || (requireContent && !captionContentAvailable())) return;
    if (captionLoadNoticeTimer) clearTimeout(captionLoadNoticeTimer);
    captionLoadNotice.dataset.noticeKey = key;
    captionLoadNotice.dataset.noticeFallback = fallback || '';
    captionLoadNotice.textContent = uiText(key, fallback);
    captionLoadNotice.hidden = false;
    captionLoadNoticeShownAt = Date.now();
    captionLoadNoticeTimer = window.setTimeout(() => hideCaptionLoadNotice({force: true}), MAX_CAPTION_LOAD_NOTICE_MS);
  }

  function hideCaptionLoadNotice({force = false} = {}) {
    if (!captionLoadNotice || captionLoadNotice.hidden) return;
    const elapsed = Date.now() - captionLoadNoticeShownAt;
    if (!force && elapsed < MIN_CAPTION_LOAD_NOTICE_MS) {
      if (captionLoadNoticeTimer) clearTimeout(captionLoadNoticeTimer);
      captionLoadNoticeTimer = window.setTimeout(() => hideCaptionLoadNotice({force: true}), MIN_CAPTION_LOAD_NOTICE_MS - elapsed);
      return;
    }
    if (captionLoadNoticeTimer) {
      clearTimeout(captionLoadNoticeTimer);
      captionLoadNoticeTimer = null;
    }
    captionLoadNotice.hidden = true;
    captionLoadNotice.removeAttribute('data-notice-key');
    captionLoadNotice.removeAttribute('data-notice-fallback');
  }

  function bestLineBreakIndex(words, maxChars) {
    if (words.length <= 1) return -1;
    const punctuation = /[,:;.!?]$/;
    const preferredStarts = new Set(['and', 'but', 'or', 'so', 'because', 'for', 'with', 'to', 'in', 'on', 'at', 'from', 'by', 'through', 'that', 'which', 'who']);
    let best = -1;
    let bestScore = Infinity;
    const totalLength = words.join(' ').length;

    for (let i = 1; i < words.length; i += 1) {
      const top = words.slice(0, i).join(' ');
      const bottom = words.slice(i).join(' ');
      if (top.length > maxChars || bottom.length > maxChars) continue;
      let score = Math.abs(top.length - bottom.length) + Math.abs(bottom.length - Math.min(maxChars, totalLength * 0.56)) * 0.2;
      if (punctuation.test(words[i - 1])) score -= 12;
      if (preferredStarts.has(words[i]?.toLowerCase().replace(/^[^\w]+|[^\w]+$/g, ''))) score -= 7;
      if (/^(the|a|an|my|your|his|her|their|our)$/i.test(words[i - 1])) score += 10;
      if (/^(of|to|in|on|at|with|for|from|by)$/i.test(words[i - 1])) score += 8;
      if (score < bestScore) {
        best = i;
        bestScore = score;
      }
    }
    return best;
  }

  function splitSubtitleBlock(text, maxChars) {
    const words = String(text || '').replace(/\s+/g, ' ').trim().split(' ').filter(Boolean);
    if (!words.length) return [];
    const whole = words.join(' ');
    if (whole.length <= maxChars) return [whole];

    const breakIndex = bestLineBreakIndex(words, maxChars);
    if (breakIndex > 0) {
      return [words.slice(0, breakIndex).join(' '), words.slice(breakIndex).join(' ')];
    }

    const lines = [];
    let line = '';
    for (const word of words) {
      const next = line ? `${line} ${word}` : word;
      if (line && next.length > maxChars) {
        lines.push(line);
        line = word;
        if (lines.length >= 1) break;
      } else {
        line = next;
      }
    }
    if (line && lines.length < 2) {
      const remaining = words.slice(lines.join(' ').split(' ').filter(Boolean).length).join(' ');
      lines.push(remaining || line);
    }
    return lines.slice(0, 2);
  }

  function splitCaptionSentences(text) {
    const normalised = String(text || '').replace(/\s+/g, ' ').trim();
    if (!normalised) return [];
    const sentences = normalised.match(/[^.!?]+[.!?]+(?:["')\]]+)?|[^.!?]+$/g) || [normalised];
    return sentences.map(part => part.trim()).filter(Boolean);
  }

  function wrapStreamSentence(sentence, maxChars) {
    const words = String(sentence || '').split(/\s+/).filter(Boolean);
    const lines = [];
    let line = '';
    for (const word of words) {
      const next = line ? `${line} ${word}` : word;
      if (line && next.length > maxChars) {
        lines.push(line);
        line = word;
      } else {
        line = next;
      }
    }
    if (line) lines.push(line);
    return lines;
  }

  function splitCaptionForStream(text, maxChars) {
    return splitCaptionSentences(text).flatMap(sentence => wrapStreamSentence(sentence, maxChars));
  }

  function stripCommittedPrefix(text) {
    const originalWords = String(text || '').replace(/\s+/g, ' ').trim().split(' ').filter(Boolean);
    if (!originalWords.length || !finalSegments.length) return String(text || '').trim();

    const committedWords = wordsForCompare(finalSegments.slice(-4).map(seg => seg.text).join(' '));
    const incomingWords = wordsForCompare(text);
    if (!committedWords.length || !incomingWords.length) return String(text || '').trim();

    const incomingJoined = incomingWords.join(' ');
    const committedJoined = committedWords.join(' ');
    if (committedJoined.endsWith(incomingJoined)) return '';

    const maxOverlap = Math.min(committedWords.length, incomingWords.length, 32);
    for (let n = maxOverlap; n > 0; n -= 1) {
      const committedTail = committedWords.slice(-n).join(' ');
      const incomingHead = incomingWords.slice(0, n).join(' ');
      if (committedTail === incomingHead) {
        return originalWords.slice(n).join(' ').trim();
      }
    }
    return String(text || '').trim();
  }

  function renderSubtitleStack() {
    if (!isPhonePage && !isPresentationPage) {
      const latestFinal = finalSegments.length ? cleanCaptionText(finalSegments[finalSegments.length - 1].text) : '';
      const fallbackText = cleanCaptionText(currentDraftText) || cleanCaptionText(activeBlock?.text) || latestFinal || t('waiting');
      if (current) current.textContent = fallbackText;
      return;
    }
    const limits = subtitleLimits();
    const latestFinalId = finalSegments.length ? finalSegments[finalSegments.length - 1].id : null;
    const systemLineItems = systemMessageText
      ? splitSubtitleBlock(systemMessageText, limits.chars).map((text, index) => ({id: `system:${index}`, text, active: true}))
      : [];
    let visible;
    if (systemLineItems.length) {
      visible = systemLineItems.slice(-limits.maxLines);
    } else {
      const finalItems = finalSegments.flatMap(seg =>
        splitCaptionForStream(seg.text, limits.chars).map((text, index) => ({
          id: `${seg.id}:stream:${index}`,
          text,
          active: seg.id === latestFinalId,
        }))
      );
      const draftItems = currentDraftText
        ? splitCaptionForStream(currentDraftText, limits.chars).map((text, index) => ({
            id: `draft:stream:${index}`,
            text,
            active: true,
          }))
        : [];
      visible = [...finalItems, ...draftItems].slice(-limits.maxLines);
    }

    pendingCurrentText = visible;
    if (rafScheduled) return;
    rafScheduled = true;
    requestAnimationFrame(() => {
      if (current && Array.isArray(pendingCurrentText)) {
        const previousRects = new Map();
        const previousTexts = new Map();
        current.querySelectorAll('.subtitle-line').forEach((el) => {
          const key = el.getAttribute('data-line-key');
          if (key) previousRects.set(key, el.getBoundingClientRect());
          if (key) previousTexts.set(key, el.getAttribute('data-line-text') || el.textContent || '');
        });

        current.textContent = '';
        if (!pendingCurrentText.length) {
          const waiting = document.createElement('span');
          waiting.textContent = t('waiting');
          current.appendChild(waiting);
          current.dataset.i18n = 'waiting';
        } else {
          current.removeAttribute('data-i18n');
          const frag = document.createDocumentFragment();
          const total = pendingCurrentText.length;
          pendingCurrentText.forEach((line, index) => {
            const p = document.createElement('p');
            p.className = `subtitle-line${line.active ? ' active-subtitle-line' : ''}`;
            p.dataset.lineKey = line.id;
            p.dataset.lineText = line.text;
            const ageFromBottom = total - index - 1;
            p.style.setProperty('--stream-opacity', String(Math.max(0.42, 1 - ageFromBottom * 0.075)));
            appendAnimatedWords(p, line.text, previousTexts.get(line.id), line.active);
            frag.appendChild(p);
          });
          current.appendChild(frag);
          animateSubtitleGlide(previousRects);
        }
      }
      pendingCurrentText = null;
      rafScheduled = false;
    });
  }

  function appendAnimatedWords(parent, text, previousText, isActiveLine) {
    const words = String(text || '').split(/(\s+)/).filter(part => part.length);
    const previousWords = String(previousText || '').trim().split(/\s+/).filter(Boolean);
    const currentWords = String(text || '').trim().split(/\s+/).filter(Boolean);
    let commonPrefix = 0;
    while (
      commonPrefix < previousWords.length &&
      commonPrefix < currentWords.length &&
      previousWords[commonPrefix] === currentWords[commonPrefix]
    ) {
      commonPrefix += 1;
    }

    let wordIndex = 0;
    for (const part of words) {
      if (/^\s+$/.test(part)) {
        parent.appendChild(document.createTextNode(part));
        continue;
      }
      const span = document.createElement('span');
      span.className = 'subtitle-word';
      if (isActiveLine && wordIndex === currentWords.length - 1 && wordIndex >= commonPrefix) {
        span.classList.add('subtitle-word-enter');
      }
      span.textContent = part;
      parent.appendChild(span);
      wordIndex += 1;
    }
  }

  function animateSubtitleGlide(previousRects) {
    if (!current || !previousRects.size || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    current.querySelectorAll('.subtitle-line').forEach((el) => {
      const key = el.getAttribute('data-line-key');
      const before = key ? previousRects.get(key) : null;
      if (!before) return;
      const after = el.getBoundingClientRect();
      const deltaY = before.top - after.top;
      if (Math.abs(deltaY) < 1) return;
      el.style.transform = `translateY(${deltaY}px)`;
      el.style.transition = 'none';
      requestAnimationFrame(() => {
        el.style.transition = `transform ${SUBTITLE_GLIDE_MS}ms ease, opacity ${SUBTITLE_GLIDE_MS}ms ease`;
        el.style.transform = '';
      });
      window.setTimeout(() => {
        el.style.transition = '';
        el.style.transform = '';
      }, SUBTITLE_GLIDE_MS + 40);
    });
  }

  function renderHistoryRoll() {
    if (!history || paused) return;
    if (!transcriptVisible) {
      if (historyWrap) historyWrap.hidden = true;
      return;
    }
    if (historyWrap) historyWrap.hidden = false;
    const shouldStickToTop = history.scrollTop <= 24 || !lastRenderedLogIds.size;
    const previousScrollTop = history.scrollTop;
    const previousScrollHeight = history.scrollHeight;
    history.textContent = '';
    if (!historyLogEnabled) {
      const p = document.createElement('p');
      p.className = 'history-placeholder';
      p.textContent = t('history_off');
      history.appendChild(p);
      return;
    }
    const previousRenderedLogIds = lastRenderedLogIds;
    const transcriptEntries = logSegments.slice(-MAX_TRANSCRIPT_ITEMS).slice().reverse();
    lastRenderedLogIds = new Set(transcriptEntries.map(entry => entry.renderId || entry.id));
    if (!transcriptEntries.length) {
      const p = document.createElement('p');
      p.className = 'history-placeholder';
      p.textContent = t('history_empty');
      history.appendChild(p);
      return;
    }
    const frag = document.createDocumentFragment();
    for (const entry of transcriptEntries) {
      const renderId = entry.renderId || entry.id;
      const article = document.createElement('article');
      article.className = 'history-entry';
      article.dataset.id = entry.id;

      const time = document.createElement('time');
      time.className = 'history-time';
      if (entry.createdAt) time.dateTime = entry.createdAt;
      time.textContent = formatLogTime(entry.createdAt || entry.updatedAt);

      const p = document.createElement('p');
      p.textContent = entry.text;

      article.append(time, p);
      frag.appendChild(article);
    }
    history.appendChild(frag);
    if (shouldStickToTop) {
      history.scrollTop = 0;
    } else {
      history.scrollTop = previousScrollTop + Math.max(0, history.scrollHeight - previousScrollHeight);
    }
  }

  function formatLogTime(value) {
    const date = value ? new Date(value) : new Date();
    if (Number.isNaN(date.getTime())) return '';
    const now = new Date();
    const sameDay = date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate();
    const options = sameDay
      ? {hour: '2-digit', minute: '2-digit'}
      : {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'};
    return date.toLocaleString([], options);
  }

  function normaliseId(text, id) {
    if (id) return String(id);
    return 'text:' + String(text || '').toLowerCase().replace(/\s+/g, ' ').trim().slice(0, 160);
  }

  function normaliseLogText(text) {
    return String(text || '')
      .toLowerCase()
      .replace(/[.,;:!?()[\]"']/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function addLogEntry(text, id, {draft = false, createdAt = null} = {}) {
    if (!text || !historyLogEnabled) return;
    const cleanText = String(text || '').replace(/\s+/g, ' ').trim();
    if (!cleanText) return;
    const key = id || `log:${normaliseLogText(cleanText).slice(0, 160)}`;
    const updatedAtMs = Date.now();
    const updatedAt = new Date(updatedAtMs).toISOString();
    const existingIndex = logSegments.findIndex(seg => seg.id === key);
    const existing = existingIndex >= 0 ? logSegments[existingIndex] : null;
    const entry = {
      id: key,
      text: cleanText,
      draft,
      createdAt: createdAt || existing?.createdAt || updatedAt,
      updatedAt,
      updatedAtMs,
      renderId: draft ? `${key}:${updatedAtMs}` : key,
    };
    if (existingIndex >= 0) {
      logSegments[existingIndex] = entry;
    } else {
      const last = logSegments[logSegments.length - 1];
      const nextNorm = normaliseLogText(cleanText);
      const lastNorm = normaliseLogText(last?.text || '');
      if (!id && lastNorm && (nextNorm === lastNorm || lastNorm.endsWith(nextNorm))) return;
      seenLogIds.add(key);
      logSegments.push(entry);
    }
    logSegments = logSegments.slice(-MAX_TRANSCRIPT_ITEMS);
  }

  function nextDraftLogId() {
    draftLogCounter += 1;
    return `draft:live:${draftLogCounter}`;
  }

  function draftTextsOverlap(previousNorm, currentNorm) {
    if (!previousNorm || !currentNorm) return false;
    return currentNorm === previousNorm ||
      currentNorm.startsWith(previousNorm) ||
      previousNorm.startsWith(currentNorm) ||
      currentNorm.includes(previousNorm) ||
      previousNorm.includes(currentNorm);
  }

  function commitDraftLogEntry(entry) {
    if (!entry?.draft) return;
    const index = logSegments.findIndex(seg => seg.id === entry.id);
    if (index < 0) return;
    const committedId = `drafted:${entry.id}`;
    logSegments[index] = {
      ...entry,
      id: committedId,
      draft: false,
      renderId: committedId,
    };
  }

  function addDraftToLog(text, createdAt = null) {
    if (!text || !historyLogEnabled) return;
    const now = Date.now();
    const last = logSegments[logSegments.length - 1];
    const currentNorm = normaliseLogText(text);
    const lastNorm = normaliseLogText(last?.text || '');
    if (last?.draft) {
      if (draftTextsOverlap(lastNorm, currentNorm)) {
        if (currentNorm.length >= lastNorm.length || now - (last.updatedAtMs || 0) >= DRAFT_LOG_UPDATE_MS) {
          addLogEntry(text, last.id, {draft: true, createdAt: last.createdAt || createdAt});
          renderHistoryRoll();
        }
        return;
      }
      commitDraftLogEntry(last);
    }

    const previous = logSegments[logSegments.length - 1];
    const previousNorm = normaliseLogText(previous?.text || '');
    const previousIsProvisional = String(previous?.id || '').startsWith('drafted:draft:live:');
    if (previousIsProvisional && draftTextsOverlap(previousNorm, currentNorm)) {
      if (currentNorm.length > previousNorm.length) {
        addLogEntry(text, previous.id, {draft: false, createdAt: previous.createdAt || createdAt});
        renderHistoryRoll();
      }
      return;
    }
    if (draftTextsOverlap(previousNorm, currentNorm)) return;
    if (now - lastDraftLogAt < DRAFT_LOG_UPDATE_MS && previousNorm && currentNorm.startsWith(previousNorm)) return;
    lastDraftLogAt = now;
    addLogEntry(text, nextDraftLogId(), {draft: true, createdAt});
    renderHistoryRoll();
  }

  function addHistory(segmentOrText, id, {log = true} = {}) {
    const segment = typeof segmentOrText === 'object' && segmentOrText !== null
      ? segmentOrText
      : {text: segmentOrText, id};
    const text = cleanCaptionText(segment.text);
    if (!text || paused) return;
    const key = normaliseId(text, segment.id);
    if (seenIds.has(key)) return;
    seenIds.add(key);

    const limits = subtitleLimits();
    const lines = splitSubtitleBlock(text, limits.chars).map((line, index) => ({id: `${key}:${index}`, text: line}));
    finalSegments.push({id: key, text, lines, createdAt: segment.created_at || segment.createdAt || null});
    finalSegments = finalSegments.slice(-MAX_LIVE_SEGMENTS);
    if (log) {
      const finalNorm = normaliseLogText(text);
      logSegments = logSegments.filter((seg) => {
        if (seg.draft) return false;
        if (!String(seg.id || '').startsWith('drafted:draft:live:')) return true;
        return !draftTextsOverlap(normaliseLogText(seg.text || ''), finalNorm);
      });
      addLogEntry(text, key, {draft: false, createdAt: segment.created_at || segment.createdAt || null});
    }
    currentDraftText = '';
    systemMessageText = '';
    systemMessageKey = '';
    systemMessageFallback = '';
    queueStableBlock({id: key, text, lines});
    renderHistoryRoll();
  }

  function applyTranscriptUpdates(items) {
    if (!Array.isArray(items) || !items.length || !historyLogEnabled) return false;
    for (const seg of items) {
      const text = cleanCaptionText(seg?.text);
      if (!text) continue;
      const key = normaliseId(text, seg.id);
      addLogEntry(text, key, {
        draft: seg.is_final === false,
        createdAt: seg.created_at || seg.createdAt || null,
      });
    }
    renderHistoryRoll();
    return true;
  }

  function renderHistoryFromState(items) {
    if (paused) return;
    finalSegments = [];
    logSegments = [];
    lastRenderedLogIds = new Set();
    seenIds.clear();
    seenLogIds.clear();
    draftLogCounter = 0;
    const recent = (items || []).slice(-MAX_TRANSCRIPT_ITEMS);
    for (const seg of recent) {
      const text = cleanCaptionText(seg.text);
      if (!text) continue;
      const key = normaliseId(text, seg.id);
      addLogEntry(text, key, {draft: seg.is_final === false, createdAt: seg.created_at || seg.createdAt || null});
    }
    systemMessageText = '';
    systemMessageKey = '';
    systemMessageFallback = '';
    renderHistoryRoll();
  }

  function readingDurationMs(text) {
    const chars = String(text || '').replace(/\s+/g, ' ').trim().length;
    const duration = (chars / TARGET_READING_CPS) * 1000 + BLOCK_BREATHING_ROOM_MS;
    return Math.max(MIN_BLOCK_MS, Math.min(MAX_BLOCK_MS, Math.round(duration)));
  }

  function scheduleBlockAdvance() {
    if (blockTimer) clearTimeout(blockTimer);
    blockTimer = null;
    if (!blockQueue.length) return;
    const wait = Math.max(0, activeBlockUntil - Date.now());
    blockTimer = setTimeout(advanceStableBlock, wait);
  }

  function advanceStableBlock() {
    if (blockTimer) clearTimeout(blockTimer);
    blockTimer = null;
    const next = blockQueue.shift();
    if (!next) {
      if (currentDraftText) activeBlock = null;
      renderSubtitleStack();
      return;
    }
    activeBlock = next;
    activeBlockUntil = Date.now() + readingDurationMs(next.text);
    currentDraftText = '';
    renderSubtitleStack();
    renderHistoryRoll();
    scheduleBlockAdvance();
  }

  function queueStableBlock(block) {
    blockQueue.push(block);
    if (!activeBlock || Date.now() >= activeBlockUntil || blockQueue.length > 3) {
      advanceStableBlock();
    } else {
      scheduleBlockAdvance();
      renderSubtitleStack();
    }
  }

  function updateDraft(segmentOrText, {force = false, log = true} = {}) {
    const segment = typeof segmentOrText === 'object' && segmentOrText !== null
      ? segmentOrText
      : {text: segmentOrText};
    const text = cleanCaptionText(segment.text);
    if (paused) return;
    const displayText = stripCommittedPrefix(text);
    if (!displayText) {
      currentDraftText = '';
      if (isPhonePage && log) renderHistoryRoll();
      renderSubtitleStack();
      return;
    }
    const now = Date.now();
    const currentWords = wordsForCompare(currentDraftText);
    const nextWords = wordsForCompare(displayText);
    const wordDelta = Math.abs(nextWords.length - currentWords.length);
    const enoughTime = now - lastPartialShownAt >= MIN_PARTIAL_UPDATE_MS;
    if (!force && currentDraftText && !enoughTime && wordDelta < 3) return;
    currentDraftText = displayText;
    if (log) addDraftToLog(displayText, segment.created_at || segment.createdAt || null);
    systemMessageText = '';
    systemMessageKey = '';
    systemMessageFallback = '';
    lastPartialShownAt = now;
    if (activeBlock && (now >= activeBlockUntil || wordDelta >= 2)) activeBlock = null;
    renderSubtitleStack();
  }

  function renderState(state) {
    if (paused) return;
    historyLogEnabled = state.transcript_saving_enabled !== false && Number(state.transcript_retention_minutes ?? 1) > 0;
    if (Array.isArray(state.history)) renderHistoryFromState(state.history);
    if (state.sensitive_mode) {
      currentDraftText = '';
      showSystemMessageFromKey('sensitive_paused_message', state.current?.text || '');
      return;
    }
    currentDraftText = state.current?.text ? stripCommittedPrefix(cleanCaptionText(state.current.text)) : '';
    if (currentDraftText || finalSegments.length) hideCaptionLoadNotice();
    renderSubtitleStack();
  }

  function applyRetentionState(state) {
    if (!state || paused) return;
    historyLogEnabled = state.transcript_saving_enabled !== false && Number(state.transcript_retention_minutes ?? 1) > 0;
    renderHistoryRoll();
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
      setConnection('live', true);
      ws.send('hello');
      pingTimer = setInterval(() => {
        try { ws.send('ping'); } catch (_) {}
      }, 15000);
    };

    ws.onmessage = (event) => {
      let payload;
      try { payload = JSON.parse(event.data); } catch (_) { return; }

      if (payload.type === 'state') renderState(payload.data);
      if (payload.type === 'viewer_meta') {
        translationState = payload.data || translationState;
        if (ensureViewerLanguageIsAvailable()) {
          applyLanguage();
          connect();
        } else {
          renderLanguageList(languageSearch?.value || '');
        }
      }

      if (payload.type === 'retention') {
        applyRetentionState(payload.data);
      }

      if (payload.type === 'translation_status') {
        applyRetentionState(payload);
      }

      if (payload.type === 'caption') {
        if (paused) return;
        applyRetentionState(payload);
        const seg = payload.data || {};
        const text = cleanCaptionText(seg.text);
        if (!text) {
          currentDraftText = '';
          renderSubtitleStack();
          return;
        }
        hideCaptionLoadNotice();
        seg.text = text;
        const hasTranscriptUpdates = applyTranscriptUpdates(payload.transcript_updates);
        if (seg.is_final) {
          addHistory(seg, null, {log: !hasTranscriptUpdates});
        } else {
          updateDraft(seg, {log: !hasTranscriptUpdates});
        }
      }

      if (payload.type === 'sensitive' && !paused) {
        const messageKey = payload.message_key || (payload.enabled === false ? 'sensitive_resumed_message' : 'sensitive_paused_message');
        showSystemMessageFromKey(messageKey, payload.message || '');
      }

      if (payload.type === 'clear') {
        finalSegments = [];
        logSegments = [];
        lastRenderedLogIds = new Set();
        activeBlock = null;
        activeBlockUntil = 0;
        blockQueue = [];
        if (blockTimer) clearTimeout(blockTimer);
        currentDraftText = '';
        systemMessageText = '';
        systemMessageKey = '';
        systemMessageFallback = '';
        renderSubtitleStack();
        if (history) history.textContent = '';
        seenIds.clear();
        seenLogIds.clear();
        draftLogCounter = 0;
      }
    };

    ws.onclose = () => {
      if (ws !== socket) return;
      if (pingTimer) clearInterval(pingTimer);
      if (manualReconnect) return;
      setConnection('reconnecting', false);
      reconnectTimer = setTimeout(connect, 2000);
    };

    ws.onerror = () => setConnection('connection_issue', false);
  }

  languageSelect?.addEventListener('change', () => {
    changeViewerLanguage(languageSelect.value || SOURCE_LANGUAGE);
  });

  function changeViewerLanguage(code) {
    showCaptionLoadNotice('connecting');
    viewerLanguage = code || SOURCE_LANGUAGE;
    ensureLanguageUiStrings(viewerLanguage);
    applyLanguage();
    applyViewerTheme();
    applyComfortMode();
    if (history) history.textContent = '';
    finalSegments = [];
    logSegments = [];
    lastRenderedLogIds = new Set();
    activeBlock = null;
    activeBlockUntil = 0;
    blockQueue = [];
    if (blockTimer) clearTimeout(blockTimer);
    currentDraftText = '';
    systemMessageText = '';
    seenIds.clear();
    seenLogIds.clear();
    draftLogCounter = 0;
    connect();
  }

  function openLanguagePicker() {
    if (!languagePickerOverlay) return;
    languagePickerOverlay.hidden = false;
    languagePickerButton?.setAttribute('aria-expanded', 'true');
    renderLanguageList(languageSearch?.value || '');
    refreshLanguageMetadata();
    if (languageMetadataRefreshTimer) clearInterval(languageMetadataRefreshTimer);
    languageMetadataRefreshTimer = setInterval(() => refreshLanguageMetadata({reconnectIfNeeded: false}), 10000);
    window.setTimeout(() => languageSearch?.focus(), 0);
  }

  function closeLanguagePicker() {
    if (!languagePickerOverlay) return;
    languagePickerOverlay.hidden = true;
    languagePickerButton?.setAttribute('aria-expanded', 'false');
    if (languageMetadataRefreshTimer) {
      clearInterval(languageMetadataRefreshTimer);
      languageMetadataRefreshTimer = null;
    }
    languagePickerButton?.focus();
  }

  async function submitLanguageRequest(code, button) {
    if (!code) return;
    const original = button?.textContent || 'Request';
    if (button) {
      button.disabled = true;
      button.textContent = 'Sending...';
    }
    try {
      const response = await fetch('/api/language-requests', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({language: code}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || data.error || 'Church Cap could not send that request.');
      if (data.translation) translationState = data.translation;
      renderLanguageList(languageSearch?.value || '');
    } catch (error) {
      if (button) {
        button.disabled = false;
        button.textContent = original;
        button.title = error.message || 'Request failed';
      }
    }
  }

  function renderLanguageList(query = '') {
    if (!languageList) return;
    const q = query.trim().toLowerCase();
    const unavailable = translationCaptionsUnavailable();
    const available = availableCaptionLanguageCodes();
    const requestable = requestableCaptionLanguageCodes();
    const pending = pendingLanguageRequestCodes();
    const matches = filteredLanguagesForCurrentMode().filter(lang => !q || languageSearchText(lang).includes(q));
    languageList.textContent = '';
    if (unavailable) {
      const notice = document.createElement('p');
      notice.className = 'language-empty language-unavailable-notice';
      notice.textContent = t('caption_languages_unavailable');
      languageList.appendChild(notice);
    } else if (requestable.size) {
      const notice = document.createElement('p');
      notice.className = 'language-empty language-unavailable-notice';
      notice.textContent = `The operator has limited translated languages for this service. You can still request another installed language; Church Cap will keep showing the current captions until it is approved.`;
      languageList.appendChild(notice);
    }
    if (!matches.length) {
      const empty = document.createElement('p');
      empty.className = 'language-empty';
      empty.textContent = t('no_languages_found');
      languageList.appendChild(empty);
      return;
    }
    const frag = document.createDocumentFragment();
    matches.forEach((lang) => {
      const isAvailable = available.has(lang.code);
      const isRequestable = requestable.has(lang.code) && !isAvailable;
      const item = document.createElement(isAvailable ? 'button' : 'div');
      if (isAvailable) item.type = 'button';
      item.className = `language-option${lang.code === viewerLanguage ? ' selected' : ''}${isRequestable ? ' requestable-language-option' : ''}`;
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', lang.code === viewerLanguage ? 'true' : 'false');
      item.dataset.code = lang.code;
      const marker = languageMarker(lang);
      const flag = document.createElement('span');
      flag.className = 'language-option-flag';
      flag.dataset.code = marker.code;
      flag.title = `${languageDisplayName(lang)} · ${marker.code}`;
      flag.classList.toggle('language-code-badge', marker.isBadge);
      flag.classList.toggle('language-flag-chip', marker.isFlag);
      flag.textContent = marker.text;
      const text = document.createElement('span');
      text.className = 'language-option-text';
      const title = document.createElement('strong');
      title.textContent = lang.name || lang.native || lang.code.toUpperCase();
      title.dir = 'auto';
      const meta = document.createElement('small');
      meta.dir = 'auto';
      meta.textContent = isRequestable
        ? (pending.has(lang.code) ? `Request sent · ${lang.code}` : `Not enabled · ${lang.code}`)
        : (lang.native && lang.native !== lang.name ? `${lang.native} · ${lang.code}` : lang.code);
      text.append(title, meta);
      item.append(flag, text);
      if (isAvailable) {
        item.addEventListener('click', () => {
          changeViewerLanguage(lang.code);
          closeLanguagePicker();
        });
      } else if (isRequestable) {
        const requestButton = document.createElement('button');
        requestButton.type = 'button';
        requestButton.className = 'language-request-button';
        requestButton.textContent = pending.has(lang.code) ? 'Requested' : 'Request';
        requestButton.disabled = pending.has(lang.code);
        requestButton.addEventListener('click', () => submitLanguageRequest(lang.code, requestButton));
        item.appendChild(requestButton);
      }
      frag.appendChild(item);
    });
    languageList.appendChild(frag);
  }

  languagePickerButton?.addEventListener('click', () => {
    requestScreenWakeLock();
    openLanguagePicker();
  });
  languagePickerBackdrop?.addEventListener('click', closeLanguagePicker);
  languagePickerClose?.addEventListener('click', closeLanguagePicker);
  languageSearch?.addEventListener('input', () => renderLanguageList(languageSearch.value));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && languagePickerOverlay && !languagePickerOverlay.hidden) {
      closeLanguagePicker();
    }
  });
  document.addEventListener('visibilitychange', refreshScreenWakeLock);
  if (isPhonePage) {
    requestScreenWakeLock();
    document.addEventListener('pointerdown', requestScreenWakeLock, {once: true});
  }

  document.getElementById('largerText')?.addEventListener('click', () => {
    fontScale = Math.min(1.8, fontScale + 0.1);
    applyFontScale();
  });

  document.getElementById('smallerText')?.addEventListener('click', () => {
    fontScale = Math.max(0.65, fontScale - 0.1);
    applyFontScale();
  });

  document.getElementById('toggleTheme')?.addEventListener('click', () => {
    viewerThemePreference = resolveViewerTheme() === 'light' ? 'dark' : 'light';
    applyViewerTheme({persist: true});
  });

  document.getElementById('toggleCompact')?.addEventListener('click', () => {
    comfortMode = !comfortMode;
    applyComfortMode();
  });

  document.getElementById('toggleTranscript')?.addEventListener('click', () => {
    transcriptVisible = !transcriptVisible;
    applyTranscriptVisibility();
  });

  document.getElementById('pauseScroll')?.addEventListener('click', (e) => {
    paused = !paused;
    e.target.textContent = paused ? t('resume') : t('pause');
    if (paused && current) {
      const frozen = current.textContent || t('waiting');
      current.textContent = frozen + '  ·  ' + t('paused_marker');
    } else {
      connect();
    }
  });

  document.getElementById('clearLocal')?.addEventListener('click', () => {
    if (history) history.textContent = '';
    finalSegments = [];
    logSegments = [];
    lastRenderedLogIds = new Set();
    activeBlock = null;
    activeBlockUntil = 0;
    blockQueue = [];
    if (blockTimer) clearTimeout(blockTimer);
    currentDraftText = '';
    systemMessageText = '';
    renderSubtitleStack();
    seenIds.clear();
    seenLogIds.clear();
    draftLogCounter = 0;
  });

  window.addEventListener('resize', () => {
    renderSubtitleStack();
    renderHistoryRoll();
  });
  window.matchMedia?.('(prefers-color-scheme: light)').addEventListener?.('change', () => {
    if (viewerThemePreference === 'system') applyViewerTheme();
  });

  applyLanguage();
  applyFontScale();
  applyViewerTheme();
  applyComfortMode();
  applyTranscriptVisibility();
  if (viewerHint) viewerHint.textContent = t('line_by_line');
  renderSubtitleStack();
  connect();
})();
