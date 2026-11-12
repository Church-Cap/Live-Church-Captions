import assert from 'node:assert/strict';
import {readFile, stat} from 'node:fs/promises';
import test from 'node:test';
import {runInNewContext} from 'node:vm';

const html = await readFile(new URL('../src/index.html', import.meta.url), 'utf8');
const script = await readFile(new URL('../src/main.js', import.meta.url), 'utf8');
const rustHost = await readFile(new URL('../src-tauri/src/lib.rs', import.meta.url), 'utf8');
const rustLifecycle = await readFile(new URL('../src-tauri/src/lifecycle.rs', import.meta.url), 'utf8');
const rustRecovery = await readFile(new URL('../src-tauri/src/recovery.rs', import.meta.url), 'utf8');
const rustWindow = await readFile(new URL('../src-tauri/src/window.rs', import.meta.url), 'utf8');
const rustUpdater = await readFile(new URL('../src-tauri/src/updater.rs', import.meta.url), 'utf8');
const styles = await readFile(new URL('../src/desktop.css', import.meta.url), 'utf8');
const browserStyles = await readFile(new URL('../../app/static/styles.css', import.meta.url), 'utf8');
const browserMain = await readFile(new URL('../../app/main.py', import.meta.url), 'utf8');
const loginTemplate = await readFile(new URL('../../app/templates/login.html', import.meta.url), 'utf8');
const setupTemplate = await readFile(new URL('../../app/templates/setup.html', import.meta.url), 'utf8');
const setupRecoveryTemplate = await readFile(new URL('../../app/templates/setup_recovery.html', import.meta.url), 'utf8');
const setupPasswordScript = await readFile(new URL('../../app/static/setup-onboarding.js', import.meta.url), 'utf8');
const dmgBuilder = await readFile(new URL('../../scripts/release/build-internal-macos-dmg.sh', import.meta.url), 'utf8');
const publicDmgBuilder = await readFile(new URL('../../scripts/release/build-macos-dmg.sh', import.meta.url), 'utf8');
const macSigner = await readFile(new URL('../../scripts/release/sign-macos-app.sh', import.meta.url), 'utf8');
const macSigningIdentity = await readFile(new URL('../../scripts/release/macos-signing-identity.sh', import.meta.url), 'utf8');
const macPythonFrameworkNormalizer = await readFile(new URL('../../scripts/release/normalize-macos-python-framework.sh', import.meta.url), 'utf8');
const macAppChecker = await readFile(new URL('../../scripts/release/check-macos-app-bundle.sh', import.meta.url), 'utf8');
const macAppNotarizer = await readFile(new URL('../../scripts/release/notarize-macos-app.sh', import.meta.url), 'utf8');
const dmgNotarizer = await readFile(new URL('../../scripts/release/notarize-macos-dmg.sh', import.meta.url), 'utf8');
const macUpdaterBuilder = await readFile(new URL('../../scripts/release/build-macos-updater-artifact.sh', import.meta.url), 'utf8');
const tauriConfig = JSON.parse(await readFile(new URL('../src-tauri/tauri.conf.json', import.meta.url), 'utf8'));
const previewConfig = JSON.parse(await readFile(new URL('../src-tauri/tauri.preview.conf.json', import.meta.url), 'utf8'));
const packageConfig = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
const updaterPublicKey = (await readFile(new URL('../../packaging/updater/church-cap-updater-public.key', import.meta.url), 'utf8')).trim();
const updaterPublicKeyText = Buffer.from(updaterPublicKey, 'base64').toString('utf8');

test('desktop identity and centred control window remain stable', () => {
  assert.equal(tauriConfig.productName, 'Church Cap');
  assert.equal(tauriConfig.version, packageConfig.version);
  assert.equal(tauriConfig.identifier, 'org.churchcap.desktop');
  const control = tauriConfig.app.windows.find((window) => window.label === 'control');
  assert.ok(control);
  assert.equal(control.center, true);
  assert.equal(control.width, 780);
  assert.equal(control.height, 720);
  assert.match(styles, /footer\s*\{[\s\S]*position:\s*sticky;[\s\S]*bottom:\s*0;/);
});

test('local preview cannot hand control to or reset data from the installed app', () => {
  assert.equal(previewConfig.productName, 'Church Cap Preview');
  assert.equal(previewConfig.identifier, 'org.churchcap.desktop.preview');
  assert.notEqual(previewConfig.identifier, tauriConfig.identifier);
  assert.equal(previewConfig.bundle.createUpdaterArtifacts, false);
  assert.deepEqual(previewConfig.bundle.targets, ['app']);
  const control = previewConfig.app.windows.find((window) => window.label === 'control');
  assert.equal(control.title, 'Church Cap Preview');
});

test('first-run security choices preserve readable card width', () => {
  assert.match(
    browserStyles,
    /\.stacked-form input:not\(\[type="radio"\]\):not\(\[type="checkbox"\]\)/,
  );
  assert.match(
    browserStyles,
    /\.setup-choice-card input\s*\{[^}]*width:\s*1rem;[^}]*flex:\s*0 0 auto;/,
  );
  assert.match(browserStyles, /\.setup-choice-copy\s*\{[^}]*min-width:\s*0;/);
  assert.match(browserStyles, /\.recommended-badge\s*\{[^}]*rgba\(34, 197, 94/);
  assert.match(browserStyles, /\.caution-badge\s*\{[^}]*rgba\(249, 115, 22/);
  assert.ok(
    setupTemplate.indexOf('value="secure_operator"') < setupTemplate.indexOf('value="easy_offline"'),
    'Secure operator mode must be shown before Easy offline mode',
  );
  assert.match(setupTemplate, /recommended-badge">Recommended/);
  assert.match(setupTemplate, /caution-badge">Caution/);
  assert.match(setupTemplate, /id="easyOfflineInfoButton"[^>]*aria-haspopup="dialog"/);
  assert.match(setupTemplate, /id="easyOfflineInfoDialog"/);
  const setupFormStart = setupTemplate.indexOf('<form method="post" action="/setup"');
  const setupFormEnd = setupTemplate.indexOf('</form>', setupFormStart);
  const saveButton = setupTemplate.indexOf('id="saveOperatorPassword"');
  const easyOfflineDialog = setupTemplate.indexOf('id="easyOfflineInfoDialog"');
  assert.ok(setupFormStart >= 0 && setupFormStart < saveButton && saveButton < setupFormEnd);
  assert.ok(setupFormEnd < easyOfflineDialog, 'the dialog must not introduce nested forms into setup');
  assert.match(setupTemplate, /id="saveOperatorPassword"/);
  assert.match(setupTemplate, /Other computers or tablets on the same private network/);
  assert.match(setupTemplate, /data-onboarding-step="5"/);
  assert.match(setupTemplate, /role="progressbar"/);
  assert.match(setupPasswordScript, /easyOfflineInfoButton\?\.addEventListener\('click'/);
  assert.match(setupPasswordScript, /easyOfflineInfoDialog\.showModal\(\)/);
});

test('password recovery preserves the existing language and performance setup', () => {
  assert.match(rustRecovery, /operator_password_recovery\.flag/);
  assert.match(rustRecovery, /password-reset\\n/);
  assert.match(setupRecoveryTemplate, /performance settings will stay unchanged/);
  assert.doesNotMatch(setupRecoveryTemplate, /name="language_setup"/);
});

test('desktop bundles the generated white-glass Church Cap icon set', async () => {
  assert.deepEqual(
    tauriConfig.bundle.icon,
    [
      'icons/32x32.png',
      'icons/128x128.png',
      'icons/128x128@2x.png',
      'icons/icon.icns',
      'icons/icon.ico',
    ],
  );
  for (const icon of tauriConfig.bundle.icon) {
    const iconPath = new URL(`../src-tauri/${icon}`, import.meta.url);
    assert.ok((await stat(iconPath)).size > 0, `${icon} should be generated`);
  }
  assert.match(packageConfig.scripts.icons, /church-cap-app-icon-white-glass\.png/);
  const canonicalIcon = await readFile(new URL('../../assets/branding/church-cap-app-icon-white-glass.png', import.meta.url));
  assert.ok(canonicalIcon.length > 0, 'canonical white-glass icon should exist');
  const generated = await readFile(new URL('../src-tauri/icons/icon.png', import.meta.url));
  const oldGreyscaleDigest = 'ddc06a8d8a3eb47ed89aaef631926332eef1e00e31fffdc7bd6ac8f84029d343';
  const oldTransparentMarkDigest = 'bb019cca42820703df423123e85711615b0f81202175794d9b03f8b8e2284aa3';
  const croppedWhiteGlassDigest = '026f5b0623ff53908177cbbda136f858e7f668de16c438a281c5ccb6f9973915';
  const {createHash} = await import('node:crypto');
  const digest = createHash('sha256').update(generated).digest('hex');
  assert.notEqual(digest, oldGreyscaleDigest);
  assert.notEqual(digest, oldTransparentMarkDigest);
  assert.notEqual(digest, croppedWhiteGlassDigest);
});

test('macOS menu bar uses a compact transparent template icon', async () => {
  const trayIcon = await readFile(new URL('../src-tauri/icons/tray-template.png', import.meta.url));
  assert.deepEqual([...trayIcon.subarray(0, 8)], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  assert.equal(trayIcon.readUInt32BE(16), 36);
  assert.equal(trayIcon.readUInt32BE(20), 36);
  assert.equal(trayIcon[25], 6, 'tray icon should retain an alpha channel');
  const traySource = await readFile(new URL('../src-tauri/src/tray.rs', import.meta.url), 'utf8');
  assert.match(traySource, /include_bytes!\("\.\.\/icons\/tray-template\.png"\)/);
  assert.match(traySource, /icon_as_template\(cfg!\(target_os = "macos"\)\)/);
  assert.match(traySource, /run_on_main_thread/);
  assert.match(traySource, /could not refresh its Start\/Stop label/);
});

test('macOS DMG uses the branded drag-to-Applications layout', async () => {
  const background = new URL('../../packaging/macos/dmg/church-cap-dmg-background.tiff', import.meta.url);
  const retinaBackground = new URL('../../packaging/macos/dmg/church-cap-dmg-background@2x.png', import.meta.url);
  assert.ok((await stat(background)).size > 0, 'multi-resolution DMG background should exist');
  assert.ok((await stat(retinaBackground)).size > 0, 'Retina DMG background should exist');
  assert.match(dmgBuilder, /generate-macos-dmg-background\.swift/);
  assert.match(dmgBuilder, /\/usr\/bin\/xcrun swift .*generate-macos-dmg-background\.swift/);
  assert.match(dmgBuilder, /tiffutil -cathidpicheck/);
  assert.match(dmgBuilder, /set background picture of viewOptions/);
  assert.match(dmgBuilder, /set position of item "Church Cap\.app"[\s\S]*\{165, 245\}/);
  assert.match(dmgBuilder, /set position of item "Applications"[\s\S]*\{495, 245\}/);
  assert.match(dmgBuilder, /set bounds of container window to \{120, 120, 780, 610\}/);
  assert.match(dmgBuilder, /CFBundleShortVersionString/);
  assert.match(dmgBuilder, /VOLUME_NAME="Church Cap \$APP_VERSION"/);
});

test('macOS public DMG notarization is fail-closed and retains evidence', () => {
  assert.match(dmgNotarizer, /refusing to notarize an internal\/ad-hoc DMG/);
  assert.match(dmgNotarizer, /macos-signing-identity\.sh/);
  assert.match(dmgNotarizer, /notarytool history/);
  assert.match(dmgNotarizer, /notarytool submit[\s\S]*--wait[\s\S]*--output-format json/);
  assert.match(dmgNotarizer, /notarytool log/);
  assert.match(dmgNotarizer, /stapler staple/);
  assert.match(dmgNotarizer, /stapler validate/);
  assert.match(dmgNotarizer, /spctl --assess --type open/);
});

test('macOS production signing defers Gatekeeper until Apple notarization', () => {
  assert.match(macSigner, /Developer ID Application/);
  assert.match(macSigner, /--options runtime --timestamp/);
  assert.match(macSigner, /Authority=\$IDENTITY/);
  assert.match(macSigner, /TeamIdentifier=not set/);
  assert.match(macSigner, /Timestamp=/);
  assert.doesNotMatch(macSigner, /spctl --assess/);
  assert.match(macSigner, /Gatekeeper assessment is intentionally deferred/);
});

test('macOS signing can select an otherwise ambiguous Developer ID by fingerprint', () => {
  assert.match(macSigningIdentity, /CHURCH_CAP_CODESIGN_IDENTITY_SHA1/);
  assert.match(macSigningIdentity, /\[\[:xdigit:\]\]\{40\}/);
  assert.match(macSigningIdentity, /security find-identity -v -p codesigning/);
  assert.match(macSigningIdentity, /grep -F "\\"\$requested_name\\""/);
  assert.match(macSigningIdentity, /grep -Fi "\$normalized_sha1"/);
  assert.match(macSigner, /SIGNING_IDENTITY="\$CHURCH_CAP_RESOLVED_CODESIGN_IDENTITY"/);
  assert.match(macSigner, /codesign --force --sign "\$SIGNING_IDENTITY"/);
  assert.match(dmgNotarizer, /codesign --force --sign "\$SIGNING_IDENTITY"/);
});

test('macOS signing restores and verifies the canonical Python.framework layout', () => {
  assert.match(macPythonFrameworkNormalizer, /expected exactly one concrete Python\.framework version directory/);
  assert.match(macPythonFrameworkNormalizer, /ln -s "\$VERSION_NAME" "\$PYTHON_FRAMEWORK\/Versions\/Current"/);
  assert.match(macPythonFrameworkNormalizer, /ln -s "Versions\/Current\/Python" "\$PYTHON_FRAMEWORK\/Python"/);
  assert.match(macPythonFrameworkNormalizer, /ln -s "Versions\/Current\/Resources" "\$PYTHON_FRAMEWORK\/Resources"/);
  assert.match(macSigner, /normalize-macos-python-framework\.sh/);
  assert.match(macSigner, /"\$code_path" == "\$PYTHON_FRAMEWORK\/"\*/);
  assert.match(macSigner, /codesign --verify --strict --verbose=2 "\$PYTHON_FRAMEWORK"/);
  assert.match(macAppChecker, /Python\.framework\/Python must be a symlink/);
  assert.match(macAppChecker, /Python\.framework\/Versions\/Current must be a symlink/);
});

test('macOS app payload notarization is fail-closed and produces a stapled updater input', () => {
  assert.match(macAppNotarizer, /macos-signing-identity\.sh/);
  assert.match(macAppNotarizer, /check-macos-app-bundle\.sh/);
  assert.match(macAppNotarizer, /codesign --verify --deep --strict/);
  assert.match(macAppNotarizer, /notarytool history/);
  assert.match(macAppNotarizer, /ditto -c -k --keepParent/);
  assert.match(macAppNotarizer, /notarytool submit[\s\S]*--wait[\s\S]*--output-format json/);
  assert.match(macAppNotarizer, /notarytool log/);
  assert.match(macAppNotarizer, /stapler staple/);
  assert.match(macAppNotarizer, /stapler validate/);
  assert.match(macAppNotarizer, /spctl --assess --type execute/);
});

test('macOS production DMG builder accepts only a notarized Developer ID app', () => {
  assert.match(publicDmgBuilder, /production DMG output must not use the internal artifact name/);
  assert.match(publicDmgBuilder, /macos-signing-identity\.sh/);
  assert.match(publicDmgBuilder, /check-macos-app-bundle\.sh/);
  assert.match(publicDmgBuilder, /Authority=\$IDENTITY/);
  assert.match(publicDmgBuilder, /TeamIdentifier=not set/);
  assert.match(publicDmgBuilder, /stapler validate/);
  assert.match(publicDmgBuilder, /spctl --assess --type execute/);
  assert.match(publicDmgBuilder, /CHURCH_CAP_MACOS_DMG_KIND="public"/);
  assert.match(publicDmgBuilder, /build-internal-macos-dmg\.sh/);
});

test('control window stays browser-first and exposes required lifecycle actions', () => {
  for (const label of ['Open Church Cap', 'Start server', 'Restart server', 'Stop server', 'Quit Church Cap']) {
    assert.match(html, new RegExp(`>${label}<`));
  }
  for (const route of ['operator', 'viewer', 'display', 'obs']) {
    assert.match(html, new RegExp(`data-route="${route}"`));
  }
  assert.match(html, /Closing this window keeps Church Cap available/);
  assert.match(html, /Making Church Easier to Follow/);
  assert.doesNotMatch(html, /Local captions, browser first/);
  assert.match(html, new RegExp(`<span>v${packageConfig.version.replaceAll('.', '\\.') }<\\/span>`));
  assert.doesNotMatch(html, new RegExp(`Version ${packageConfig.version.replaceAll('.', '\\.')} development`));
  assert.match(html, /id="showLegalInformation"/);
  assert.match(html, /id="legalDialog"/);
  assert.match(html, /github\.com\/Church-Cap\/Live-Church-Captions/);
  assert.match(html, /software is provided “as is”, without warranty of any kind/i);
  assert.match(script, /status\.health_confirmed/);
  assert.match(html, /id="healthStatus"/);
  assert.match(html, /Live captions are active/);
  assert.match(script, /interruptionApproved\('Quitting Church Cap'\)/);
  assert.match(rustHost, /RunEvent::Reopen \{ \.\. \}.*show_control_window\(app_handle\)/s);
  assert.match(rustWindow, /app\.show\(\)/);
  assert.match(rustWindow, /activateIgnoringOtherApps\(true\)/);
  assert.ok(rustWindow.indexOf('window.show()') < rustWindow.indexOf('window.center()'));
});

test('control window reconciles native status without a startup event gap', () => {
  const listener = script.indexOf("listen('church-cap://supervisor-status'");
  const firstRefresh = script.indexOf('await refreshSupervisorStatus(true)');
  assert.ok(listener >= 0 && listener < firstRefresh, 'status listener must be registered before hydration');
  assert.match(script, /setInterval\(\(\) => refreshSupervisorStatus\(\), 2000\)/);
  assert.match(script, /addEventListener\('focus', \(\) => refreshSupervisorStatus\(\)\)/);
  assert.match(script, /if \(!document\.hidden\) refreshSupervisorStatus\(\)/);
  assert.match(script, /finally \{[\s\S]*await refreshSupervisorStatus\(\)/);
});

test('operator update request opens Settings and checks once while busy', () => {
  assert.match(script, /listen\('church-cap:\/\/open-updates', handleOpenUpdates\)/);
  const handler = script.match(/function handleOpenUpdates\(\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(handler, 'update event handler must exist');
  const calls = [];
  const context = {
    updateBusy: false,
    selectTab: (tab) => calls.push(['tab', tab]),
    checkForUpdates: (revealResult) => calls.push(['check', revealResult]),
  };
  runInNewContext(`${handler}\nhandleOpenUpdates();`, context);
  context.updateBusy = true;
  runInNewContext('handleOpenUpdates();', context);
  assert.deepEqual(calls, [['tab', 'settings'], ['check', true], ['tab', 'settings']]);
  assert.match(script, /async function checkForUpdates\(revealResult = false\) \{\s*if \(!invoke \|\| updateBusy\) return;/);
  assert.match(script, /if \(revealResult\) \$\('#updatePanel'\)\.scrollIntoView\(\{block: 'nearest'\}\)/);
  const checkButton = html.indexOf('id="checkUpdates"');
  const resultPanel = html.indexOf('id="updatePanel"');
  const recoveryButton = html.indexOf('id="resetOperatorPassword"');
  assert.ok(checkButton < resultPanel && resultPanel < recoveryButton);
  assert.doesNotMatch(handler, /install_update|installAvailableUpdate/);
});

test('update installation requires in-app consent and preserves progress handling', async () => {
  assert.match(html, /<dialog[^>]*id="updateInstallDialog"[^>]*aria-labelledby="updateInstallDialogTitle"/);
  assert.match(html, /id="updateInstallDialogDescription"/);
  assert.match(html, /id="confirmUpdateInstall"/);
  assert.match(html, /<form method="dialog"><button type="submit">Cancel<\/button><\/form>/);
  assert.doesNotMatch(script.match(/function requestUpdateInstall\(\)[\s\S]*?\n\}/)?.[0], /window\.confirm/);
  assert.match(script, /addEventListener\('click', requestUpdateInstall\)/);
  assert.match(script, /addEventListener\('click', installAvailableUpdate\)/);
  assert.match(script, /listen\('church-cap:\/\/update-progress', \(event\) => renderUpdate\(\{status: event\.payload\.phase, \.\.\.event\.payload\}\)\)/);

  const dialog = {open: false, showModal() { this.open = true; }, close() { this.open = false; }};
  const description = {textContent: ''};
  const calls = [];
  const context = {
    invoke: async (command) => { calls.push(command); return {status: 'installing'}; },
    updateBusy: false,
    status: {captions_live: false},
    updateState: {status: 'available', version: '0.9.1'},
    $: (selector) => selector === '#updateInstallDialog' ? dialog : description,
    renderUpdate: (state) => calls.push(['renderUpdate', state.status]),
    render: () => {},
    refreshSupervisorStatus: async () => {},
    showError: (error) => { throw error; },
  };
  const request = script.match(/function requestUpdateInstall\(\) \{[\s\S]*?\n\}/)?.[0];
  const install = script.match(/async function installAvailableUpdate\(\) \{[\s\S]*?\n\}/)?.[0];
  assert.ok(request && install);
  runInNewContext(`${request}\n${install}\nrequestUpdateInstall();`, context);
  assert.equal(dialog.open, true);
  assert.match(description.textContent, /Church Cap 0\.9\.1/);
  dialog.close();
  await runInNewContext('installAvailableUpdate()', context);
  assert.deepEqual(calls, [], 'cancelled dialog must not invoke the installer');
  context.status.captions_live = true;
  runInNewContext('requestUpdateInstall();', context);
  assert.equal(dialog.open, false, 'live captions prevent opening consent');
  context.status.captions_live = false;
  runInNewContext('requestUpdateInstall();', context);
  await runInNewContext('installAvailableUpdate()', context);
  assert.equal(dialog.open, false);
  assert.deepEqual(calls, [['renderUpdate', 'downloading'], 'install_update', ['renderUpdate', 'installing']]);
});

test('start-at-login and native password recovery are safely exposed', () => {
  assert.match(html, /id="startAtLogin" disabled/);
  assert.match(script, /invoke\('get_start_at_login'\)/);
  assert.match(script, /invoke\('set_start_at_login', \{enabled\}\)/);
  assert.match(html, /id="checkUpdates"/);
  assert.doesNotMatch(html.slice(Math.max(0, html.indexOf('id="checkUpdates"') - 80), html.indexOf('id="checkUpdates"') + 80), /disabled/);
  assert.match(html, /<button type="button" id="resetOperatorPassword">/);
  assert.match(html, /Reset password or change security mode/);
  assert.match(html, /id="passwordResetDialog"/);
  assert.match(html, /id="confirmPasswordReset"/);
  assert.match(html, /What does the security mode change\?/);
  assert.match(html, /Secure operator mode — recommended/);
  assert.match(html, /Easy offline mode/);
  assert.match(html, /Managed-device HTTPS mode/);
  assert.match(html, /Even if you only want to change the security mode/);
  assert.match(script, /requestOperatorPasswordReset/);
  assert.match(script, /passwordResetDialog/);
  assert.match(script, /confirmPasswordReset.*performOperatorPasswordReset/);
  assert.doesNotMatch(script, /Reset the operator password\? Church Cap will stop/);
  assert.match(script, /invoke\('reset_operator_password'\)/);
  assert.match(script, /Stop live captions before resetting the operator password/);
  assert.match(rustHost, /lifecycle::reset_operator_password/);
  assert.match(rustLifecycle, /ensure_password_reset_is_safe/);
  assert.match(rustLifecycle, /crate::recovery::reset_operator_auth/);
  assert.match(rustRecovery, /AUTH_BACKUP_FILE/);
  assert.match(rustRecovery, /AUTH_PRIMARY_FILE/);
  const passwordRecoveryProduction = rustRecovery
    .split('pub fn reset_operator_auth')[1]
    .split('fn restore_staged_items')[0];
  assert.doesNotMatch(passwordRecoveryProduction, /remove_dir_all|Command::new|std::process::Command/);
  assert.match(html, /id="factoryResetApplication"/);
  assert.match(html, /id="factoryResetConfirmation"/);
  assert.match(script, /invoke\('factory_reset_application'\)/);
  assert.match(rustHost, /lifecycle::factory_reset_application/);
  assert.match(rustRecovery, /FACTORY_RESET_DIRECTORIES/);
  assert.match(rustRecovery, /FACTORY_RESET_MARKER/);
  const diagnostics = html.indexOf('>Diagnostics<');
  assert.notEqual(diagnostics, -1);
  assert.match(html.slice(Math.max(0, diagnostics - 140), diagnostics), /<button type="button" disabled>/);
});

test('operator login uses desktop recovery except on Linux', () => {
  assert.match(browserMain, /"desktop_password_reset": system in \{"Darwin", "Windows"\}/);
  assert.match(browserMain, /"linux_password_reset": system == "Linux"/);
  assert.match(loginTemplate, /if desktop_password_reset/);
  assert.match(loginTemplate, /Church Cap desktop manager/);
  assert.match(loginTemplate, /elif linux_password_reset/);
  assert.match(loginTemplate, /\.\/reset-operator-password\.sh/);
  assert.doesNotMatch(loginTemplate, /reset-operator-password\.cmd|macOS\/Linux/);
});

test('frontend invokes only the narrow supervisor allow list', () => {
  const invoked = [...script.matchAll(/(?:runAction|invoke)\('([^']+)'/g)].map((match) => match[1]);
  assert.deepEqual(
    [...new Set(invoked)].sort(),
    [
      'check_for_updates',
      'factory_reset_application',
      'get_start_at_login',
      'get_supervisor_status',
      'install_update',
      'open_church_cap_route',
      'quit_application',
      'reset_operator_password',
      'restart_engine',
      'set_start_at_login',
      'start_engine',
      'stop_engine',
    ],
  );
  assert.doesNotMatch(script, /eval\s*\(|new Function|plugin-shell|Command\.sidecar/);
});

test('signed updater remains Rust-owned and protects live captions', () => {
  assert.equal(tauriConfig.bundle.createUpdaterArtifacts, true);
  assert.deepEqual(tauriConfig.plugins.updater.endpoints, [
    'https://raw.githubusercontent.com/Church-Cap/Live-Church-Captions/main/updates/desktop/{{target}}-{{arch}}/latest.json',
  ]);
  assert.equal(tauriConfig.plugins.updater.windows.installMode, 'passive');
  assert.match(tauriConfig.plugins.updater.pubkey, /^[A-Za-z0-9+/=]+$/);
  assert.equal(tauriConfig.plugins.updater.pubkey, updaterPublicKey);
  const publicKeyId = updaterPublicKeyText.match(/minisign public key: ([A-F0-9]{16})/)?.[1];
  const rustKeyId = rustUpdater.match(/UPDATER_PUBLIC_KEY_ID: &str = "([A-F0-9]{16})"/)?.[1];
  assert.equal(publicKeyId, '25BF3CCF4B6CBB01');
  assert.equal(rustKeyId, publicKeyId);
  assert.deepEqual(tauriConfig.plugins.updater.endpoints, [
    'https://raw.githubusercontent.com/Church-Cap/Live-Church-Captions/main/updates/desktop/{{target}}-{{arch}}/latest.json',
  ]);
  assert.equal(tauriConfig.plugins.updater.windows.installMode, 'passive');
  assert.match(rustHost, /tauri_plugin_updater::Builder::new\(\)\.build\(\)/);
  assert.match(rustUpdater, /\.download\([\s\S]*begin_update_install[\s\S]*\.install\(bytes\)/);
  assert.match(rustUpdater, /if supervisor\.snapshot\(\)\.captions_live/);
  assert.match(script, /Stop captions to install/);
  assert.match(script, /Updates are never installed automatically/);
  assert.match(macUpdaterBuilder, /Developer ID Application/);
  assert.match(macUpdaterBuilder, /TeamIdentifier=not set/);
  assert.match(macUpdaterBuilder, /stapler validate/);
  assert.match(macUpdaterBuilder, /Church Cap\.app\/"/);
  assert.match(macUpdaterBuilder, /sign-updater-artifact\.sh/);
});

test('frontend assets are local and the webview CSP is restrictive', () => {
  assert.doesNotMatch(html, /(?:src|href)="https?:\/\//);
  assert.doesNotMatch(tauriConfig.app.security.csp, /unsafe-eval|unsafe-inline/);
});
