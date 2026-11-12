const tauri = window.__TAURI__;
const invoke = tauri?.core?.invoke;
const listen = tauri?.event?.listen;

const defaultStatus = {
  phase: invoke ? 'starting' : 'stopped',
  detail: invoke
    ? 'Connecting to the native Church Cap supervisor…'
    : 'Control-window preview. Start it through Tauri to manage the engine.',
  supervisor_version: '0.9.0',
  engine_version: null,
  engine_protocol_version: 2,
  pid: null,
  captions_live: false,
  health_confirmed: false,
};

let status = defaultStatus;
let actionPending = false;
let updateBusy = false;
let statusRefreshInFlight = false;
let updateState = {
  status: 'idle',
  current_version: '0.9.0',
  version: null,
  notes: null,
  detail: 'Church Cap checks a platform-specific signed channel. Updates are never installed automatically.',
};
let startAtLoginState = {
  available: false,
  enabled: false,
  requires_approval: false,
  detail: invoke
    ? 'Checking platform registration…'
    : 'Start at login is available in the installed desktop application.',
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const phaseCopy = {
  stopped: ['Church Cap is stopped', 'Stopped'],
  starting: ['Church Cap is starting', 'Starting'],
  ready: ['Church Cap is ready', 'Ready'],
  captions_live: ['Captions are live', 'Live'],
  stopping: ['Church Cap is stopping', 'Stopping'],
  updating: ['Church Cap is updating', 'Updating'],
  recovery_required: ['Church Cap needs attention', 'Recovery'],
  error: ['Church Cap could not start', 'Error'],
};

function render(nextStatus = status) {
  status = {...status, ...nextStatus};
  const [heading, label] = phaseCopy[status.phase] || phaseCopy.error;
  const ready = ['ready', 'captions_live'].includes(status.phase) && status.health_confirmed;
  const running = ['starting', 'ready', 'captions_live', 'stopping'].includes(status.phase);
  const busy = actionPending || updateBusy || ['starting', 'stopping', 'updating'].includes(status.phase);

  $('#serviceHeading').textContent = heading;
  $('#serviceDetail').textContent = status.detail || (ready ? 'The local browser interface is available.' : '');
  $('#headerStatus').textContent = label;
  $('#headerStatus').className = `status-pill ${status.phase}`;
  $('#statusOrb').className = `status-orb ${status.phase}`;
  $('#browserAvailability').textContent = ready ? 'Available' : 'Waiting for server';
  $('#supervisorVersion').textContent = `v${status.supervisor_version || '0.9.0'}`;
  $('#engineVersion').textContent = status.engine_version ? `v${status.engine_version}` : 'Not connected';
  $('#protocolVersion').textContent = String(status.engine_protocol_version ?? 2);
  $('#enginePid').textContent = status.pid ? String(status.pid) : 'Not running';
  $('#healthStatus').textContent = status.health_confirmed ? 'Confirmed' : 'Waiting';
  $('#liveNotice').hidden = !status.captions_live;

  $('#openOperator').disabled = !ready || actionPending;
  $('#startEngine').disabled = running || actionPending;
  $('#restartEngine').disabled = !running || busy;
  $('#stopEngine').disabled = !running || busy;
  $('#quitApplication').disabled = actionPending;
  $$('[data-route]').forEach((button) => { button.disabled = !ready || busy; });
  const passwordResetAvailable = ['ready', 'stopped', 'error', 'recovery_required'].includes(status.phase);
  $('#resetOperatorPassword').disabled = !invoke || busy || status.captions_live || !passwordResetAvailable;
  $('#factoryResetApplication').disabled = !invoke || busy || status.captions_live || !passwordResetAvailable;
  renderUpdate();
}

function renderUpdate(nextState = updateState) {
  updateState = {...updateState, ...nextState};
  const available = updateState.status === 'available';
  const progressVisible = ['downloading', 'verified', 'installing'].includes(updateState.status);
  const heading = available && updateState.version
    ? `Church Cap ${updateState.version} is available`
    : updateState.status === 'up_to_date'
      ? 'Church Cap is up to date'
      : updateState.status === 'channel_unpublished'
        ? 'Update channel not published yet'
        : ['downloading', 'verified', 'installing'].includes(updateState.status)
          ? 'Updating Church Cap'
          : 'Application updates';
  $('#updateHeading').textContent = heading;
  $('#updateDetail').textContent = updateState.detail || '';
  $('#checkUpdates').disabled = !invoke || updateBusy;
  $('#installUpdate').hidden = !available;
  $('#installUpdate').disabled = updateBusy || status.captions_live;
  $('#installUpdate').textContent = status.captions_live
    ? 'Stop captions to install'
    : 'Download and install';
  $('#updateNotesPanel').hidden = !(available && updateState.notes);
  $('#updateNotes').textContent = updateState.notes || '';
  const progress = $('#updateProgress');
  progress.hidden = !progressVisible;
  if (progressVisible) {
    if (updateState.total > 0) {
      progress.removeAttribute('data-indeterminate');
      progress.max = updateState.total;
      progress.value = Math.min(updateState.downloaded || 0, updateState.total);
    } else {
      progress.removeAttribute('value');
      progress.dataset.indeterminate = 'true';
    }
  }
}

function showError(error) {
  const message = typeof error === 'string' ? error : error?.message || String(error);
  $('#errorMessage').textContent = message;
  $('#errorNotice').hidden = false;
}

function renderStartAtLogin(nextState = startAtLoginState) {
  startAtLoginState = {...startAtLoginState, ...nextState};
  const control = $('#startAtLogin');
  control.checked = Boolean(startAtLoginState.enabled);
  control.disabled = !invoke || !startAtLoginState.available || actionPending;
  $('#loginItemStatus').textContent = startAtLoginState.detail;
}

async function refreshStartAtLogin() {
  if (!invoke) {
    renderStartAtLogin();
    return;
  }
  renderStartAtLogin({...startAtLoginState, available: false, detail: 'Checking platform registration…'});
  try {
    renderStartAtLogin(await invoke('get_start_at_login'));
  } catch (error) {
    renderStartAtLogin({available: false, enabled: false, detail: 'Start-at-login status is unavailable.'});
    showError(error);
  }
}

async function refreshSupervisorStatus(reportError = false) {
  if (!invoke || statusRefreshInFlight) return;
  statusRefreshInFlight = true;
  try {
    render(await invoke('get_supervisor_status'));
  } catch (error) {
    if (reportError) showError(error);
  } finally {
    statusRefreshInFlight = false;
  }
}

async function changeStartAtLogin(enabled) {
  actionPending = true;
  render();
  renderStartAtLogin();
  try {
    renderStartAtLogin(await invoke('set_start_at_login', {enabled}));
  } catch (error) {
    showError(error);
    await refreshStartAtLogin();
  } finally {
    actionPending = false;
    render();
    renderStartAtLogin();
  }
}

async function checkForUpdates(revealResult = false) {
  if (!invoke || updateBusy) return;
  updateBusy = true;
  renderUpdate({status: 'checking', detail: 'Checking the signed Church Cap update channel…'});
  render();
  try {
    renderUpdate(await invoke('check_for_updates'));
  } catch (error) {
    renderUpdate({status: 'error', detail: 'The update check could not be completed.'});
    showError(error);
  } finally {
    updateBusy = false;
    render();
    if (revealResult) $('#updatePanel').scrollIntoView({block: 'nearest'});
  }
}

function requestUpdateInstall() {
  if (!invoke || updateBusy || status.captions_live || updateState.status !== 'available') return;
  const version = updateState.version || 'the available version';
  $('#updateInstallDialogDescription').textContent = `Download, verify and install Church Cap ${version}? The local server will stop just before installation and Church Cap will relaunch.`;
  const dialog = $('#updateInstallDialog');
  if (!dialog.open) dialog.showModal();
}

async function installAvailableUpdate() {
  const dialog = $('#updateInstallDialog');
  if (!dialog.open || !invoke || updateBusy || status.captions_live || updateState.status !== 'available') return;
  dialog.close();
  const version = updateState.version || 'the available version';
  updateBusy = true;
  renderUpdate({status: 'downloading', detail: `Preparing Church Cap ${version}…`, downloaded: 0, total: null});
  render();
  try {
    renderUpdate(await invoke('install_update'));
  } catch (error) {
    renderUpdate({status: 'error', detail: 'The update was not installed. Church Cap will continue using the current version.'});
    showError(error);
  } finally {
    updateBusy = false;
    render();
    await refreshSupervisorStatus();
  }
}

function requestOperatorPasswordReset() {
  if (!invoke || actionPending) return;
  if (status.captions_live) {
    showError('Stop live captions before resetting the operator password.');
    return;
  }

  const dialog = $('#passwordResetDialog');
  $('#resetPasswordStatus').textContent = 'Confirm account recovery in the window that opened. You can create a password and choose a security mode after Church Cap restarts.';
  if (!dialog.open) {
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  }
}

async function performOperatorPasswordReset() {
  if (!invoke || actionPending) return;
  const dialog = $('#passwordResetDialog');
  if (dialog.open) dialog.close();

  actionPending = true;
  $('#resetPasswordStatus').textContent = 'Resetting operator access and restarting Church Cap…';
  render();
  try {
    render(await invoke('reset_operator_password'));
    $('#resetPasswordStatus').textContent = 'Account reset. Church Cap will open setup for a new password and security-mode choice when the local server is ready.';
  } catch (error) {
    const message = String(error);
    $('#resetPasswordStatus').textContent = message.includes('password was reset')
      ? 'The password was reset, but Church Cap needs attention before setup can reopen. Review the message above.'
      : 'The operator password was not reset. Review the message above and try again.';
    showError(error);
  } finally {
    await refreshSupervisorStatus();
    actionPending = false;
    render();
  }
}

function requestFactoryReset() {
  if (!invoke || actionPending) return;
  if (status.captions_live) {
    showError('Stop live captions before factory resetting Church Cap.');
    return;
  }
  const dialog = $('#factoryResetDialog');
  const confirmation = $('#factoryResetConfirmation');
  confirmation.value = '';
  $('#confirmFactoryReset').disabled = true;
  if (!dialog.open) {
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  }
  confirmation.focus();
}

function updateFactoryResetConfirmation() {
  $('#confirmFactoryReset').disabled = $('#factoryResetConfirmation').value !== 'RESET';
}

async function performFactoryReset() {
  if (!invoke || actionPending || $('#factoryResetConfirmation').value !== 'RESET') return;
  const dialog = $('#factoryResetDialog');
  if (dialog.open) dialog.close();
  actionPending = true;
  render();
  try {
    render(await invoke('factory_reset_application'));
    localStorage.clear();
    sessionStorage.clear();
  } catch (error) {
    showError(error);
  } finally {
    await refreshSupervisorStatus();
    actionPending = false;
    render();
  }
}

function setAutomaticUpdateChecks(enabled) {
  localStorage.setItem('church-cap-automatic-update-checks', enabled ? '1' : '0');
  if (enabled) checkForUpdates();
}

async function runAction(command, args = {}) {
  if (!invoke) {
    showError('This is a browser preview. Run the Tauri desktop host to use native controls.');
    return;
  }
  actionPending = true;
  render();
  try {
    const result = await invoke(command, args);
    if (result) render(result);
  } catch (error) {
    showError(error);
  } finally {
    // An action can race a health/event transition. Reconcile with the
    // Rust-owned snapshot so a failed stale Start cannot remain on screen.
    await refreshSupervisorStatus();
    actionPending = false;
    render();
  }
}

function interruptionApproved(action) {
  if (!status.captions_live) return true;
  return window.confirm(`${action} will interrupt live captions and clear prepared Service Context. Continue?`);
}

function selectTab(name) {
  $$('.tab').forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  $$('.tab-panel').forEach((panel) => {
    const active = panel.dataset.panel === name;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  });
}

function handleOpenUpdates() {
  selectTab('settings');
  if (!updateBusy) checkForUpdates(true);
}

async function initialize() {
  render();
  renderStartAtLogin();
  const automaticChecksEnabled = localStorage.getItem('church-cap-automatic-update-checks') === '1';
  $('#automaticUpdateChecks').checked = automaticChecksEnabled;
  $$('.tab').forEach((tab) => tab.addEventListener('click', () => selectTab(tab.dataset.tab)));
  $('#dismissError').addEventListener('click', () => { $('#errorNotice').hidden = true; });
  $('#startEngine').addEventListener('click', () => runAction('start_engine'));
  $('#stopEngine').addEventListener('click', () => {
    if (interruptionApproved('Stopping Church Cap')) {
      runAction('stop_engine', {allowLiveInterrupt: status.captions_live});
    }
  });
  $('#restartEngine').addEventListener('click', () => {
    if (interruptionApproved('Restarting Church Cap')) {
      runAction('restart_engine', {allowLiveInterrupt: status.captions_live});
    }
  });
  $('#quitApplication').addEventListener('click', () => {
    if (interruptionApproved('Quitting Church Cap')) {
      runAction('quit_application', {allowLiveInterrupt: status.captions_live});
    }
  });
  $('#startAtLogin').addEventListener('change', (event) => {
    changeStartAtLogin(event.currentTarget.checked);
  });
  $('#automaticUpdateChecks').addEventListener('change', (event) => {
    setAutomaticUpdateChecks(event.currentTarget.checked);
  });
  $('#checkUpdates').addEventListener('click', () => checkForUpdates());
  $('#installUpdate').addEventListener('click', requestUpdateInstall);
  $('#confirmUpdateInstall').addEventListener('click', installAvailableUpdate);
  $('#resetOperatorPassword').addEventListener('click', requestOperatorPasswordReset);
  $('#confirmPasswordReset').addEventListener('click', performOperatorPasswordReset);
  $('#factoryResetApplication').addEventListener('click', requestFactoryReset);
  $('#factoryResetConfirmation').addEventListener('input', updateFactoryResetConfirmation);
  $('#confirmFactoryReset').addEventListener('click', performFactoryReset);
  $('#showLegalInformation').addEventListener('click', () => {
    const dialog = $('#legalDialog');
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else dialog.setAttribute('open', '');
  });
  $('#openOperator').addEventListener('click', () => runAction('open_church_cap_route', {route: 'operator'}));
  $$('[data-route]').forEach((button) => button.addEventListener('click', () => {
    runAction('open_church_cap_route', {route: button.dataset.route});
  }));

  if (!invoke) return;
  try {
    if (listen) {
      await listen('church-cap://supervisor-status', (event) => render(event.payload));
      await listen('church-cap://update-progress', (event) => renderUpdate({status: event.payload.phase, ...event.payload}));
      await listen('church-cap://open-updates', handleOpenUpdates);
    }
    // Subscribe first so Ready cannot be lost between the initial snapshot
    // request and slower settings hydration.
    await refreshSupervisorStatus(true);
    await refreshStartAtLogin();
    await refreshSupervisorStatus();
    window.setInterval(() => refreshSupervisorStatus(), 2000);
    window.addEventListener('focus', () => refreshSupervisorStatus());
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refreshSupervisorStatus();
    });
    if (automaticChecksEnabled) window.setTimeout(checkForUpdates, 1500);
  } catch (error) {
    showError(error);
  }
}

initialize();
