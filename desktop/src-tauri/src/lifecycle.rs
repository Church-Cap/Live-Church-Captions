use std::collections::VecDeque;
use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{IpAddr, SocketAddr, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex, RwLock};
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Emitter, Manager, State};
use url::{Host, Url};

use crate::model::{
    ENGINE_PROTOCOL_VERSION, EngineCommand, EngineEvent, EngineRequest, SupervisorPhase,
    SupervisorSnapshot,
};

const STATUS_EVENT: &str = "church-cap://supervisor-status";
const OPEN_UPDATES_EVENT: &str = "church-cap://open-updates";
const OPEN_UPDATES_DEBOUNCE: Duration = Duration::from_secs(3);
const MAX_LOG_LINES: usize = 120;
const MAX_LOG_LINE_CHARS: usize = 2_000;
const GRACEFUL_STOP_TIMEOUT: Duration = Duration::from_secs(20);
const HEALTH_CONFIRM_TIMEOUT: Duration = Duration::from_secs(12);
const HEALTH_ATTEMPT_TIMEOUT: Duration = Duration::from_millis(700);
const HEALTH_RETRY_INTERVAL: Duration = Duration::from_millis(200);
const MAX_HEALTH_RESPONSE_BYTES: usize = 16 * 1024;
const MAX_AUTOMATIC_RESTART_ATTEMPTS: u8 = 3;
const RESTART_BUDGET_RESET_DELAY: Duration = Duration::from_secs(60);
const LIVE_CAPTION_STATUSES: [&str; 3] = ["starting", "listening", "sensitive"];

#[derive(Debug, PartialEq, Eq)]
enum PendingBrowserOpen {
    Wait,
    Open,
    Cancel,
}

enum ControlMessage {
    Stop,
    ForceStop,
}

#[derive(Clone)]
pub struct EngineSupervisor {
    snapshot: Arc<RwLock<SupervisorSnapshot>>,
    control: Arc<Mutex<Option<Sender<ControlMessage>>>>,
    log_tail: Arc<Mutex<VecDeque<String>>>,
    exit_authorized: Arc<AtomicBool>,
    quit_started: Arc<AtomicBool>,
}

impl EngineSupervisor {
    pub fn new() -> Self {
        Self {
            snapshot: Arc::new(RwLock::new(SupervisorSnapshot::default())),
            control: Arc::new(Mutex::new(None)),
            log_tail: Arc::new(Mutex::new(VecDeque::with_capacity(MAX_LOG_LINES))),
            exit_authorized: Arc::new(AtomicBool::new(false)),
            quit_started: Arc::new(AtomicBool::new(false)),
        }
    }

    pub fn snapshot(&self) -> SupervisorSnapshot {
        self.snapshot
            .read()
            .expect("supervisor state poisoned")
            .clone()
    }

    fn publish(&self, app: &AppHandle, update: impl FnOnce(&mut SupervisorSnapshot)) {
        let current = {
            let mut snapshot = self.snapshot.write().expect("supervisor state poisoned");
            update(&mut snapshot);
            snapshot.clone()
        };
        let _ = app.emit(STATUS_EVENT, &current);
        crate::tray::sync(app, &current);
    }

    fn record_output(&self, line: &str) {
        let mut tail = self.log_tail.lock().expect("supervisor log state poisoned");
        let bounded: String = line.chars().take(MAX_LOG_LINE_CHARS).collect();
        tail.push_back(bounded);
        while tail.len() > MAX_LOG_LINES {
            tail.pop_front();
        }
    }

    pub(crate) fn start(&self, app: &AppHandle) -> Result<SupervisorSnapshot, String> {
        let current = self.snapshot();
        let controller_available = self
            .control
            .lock()
            .expect("supervisor control state poisoned")
            .is_some();
        if !start_requires_spawn(&current, controller_available) {
            return Ok(current);
        }

        let engine_path = resolve_engine_path(app)?;
        let engine_dir = engine_path
            .parent()
            .ok_or_else(|| "The engine path has no parent directory.".to_string())?;
        let data_dir = church_cap_data_dir(app)?;
        fs::create_dir_all(&data_dir).map_err(|error| {
            format!("Church Cap could not create its application-data directory: {error}")
        })?;
        // v0.8.0 wrappers kept their data in Tauri's identifier-derived folder.
        // Carry an existing installation across once, before the engine can
        // decide the empty canonical folder means first-time setup.
        if let Some(legacy_dir) = legacy_tauri_data_dir(app) {
            crate::recovery::migrate_legacy_app_data(&legacy_dir, &data_dir)?;
        }

        let mut command = Command::new(&engine_path);
        let cache_dir = data_dir.join("cache");
        let huggingface_cache = cache_dir.join("huggingface");
        command
            .current_dir(engine_dir)
            .env("CHURCH_CAP_RUNTIME_MODE", "packaged")
            .env("CHURCH_CAP_DATA_DIR", &data_dir)
            // Keep model downloads inside Church Cap's bounded data tree so a
            // factory reset never has to remove caches shared by other apps.
            .env("XDG_CACHE_HOME", &cache_dir)
            .env("HF_HOME", &huggingface_cache)
            .env("HUGGINGFACE_HUB_CACHE", huggingface_cache.join("hub"))
            .env("CHURCH_CAP_SUPERVISOR_PID", std::process::id().to_string())
            .env("PYTHONUNBUFFERED", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            use windows_sys::Win32::System::Threading::CREATE_NO_WINDOW;
            command.creation_flags(CREATE_NO_WINDOW);
        }
        let mut child = command
            .spawn()
            .map_err(|error| format!("Church Cap could not start its engine: {error}"))?;

        #[cfg(target_os = "windows")]
        let windows_job = crate::windows_job::EngineJob::assign(&child).map_err(|error| {
            let _ = child.kill();
            format!("Church Cap could not take Windows ownership of its engine: {error}")
        })?;

        let pid = child.id();
        let stdin = child.stdin.take();
        let stdout = child.stdout.take();
        let stderr = child.stderr.take();
        let (control_tx, control_rx) = mpsc::channel();
        *self
            .control
            .lock()
            .expect("supervisor control state poisoned") = Some(control_tx);

        self.publish(app, |status| {
            status.phase = SupervisorPhase::Starting;
            status.detail = "Starting the local Church Cap service…".into();
            status.pid = Some(pid);
            status.captions_live = false;
            status.health_confirmed = false;
        });

        if let Some(stdout) = stdout {
            spawn_output_reader(app.clone(), self.clone(), BufReader::new(stdout), true);
        }
        if let Some(stderr) = stderr {
            spawn_output_reader(app.clone(), self.clone(), BufReader::new(stderr), false);
        }

        let app_handle = app.clone();
        let supervisor = self.clone();
        thread::Builder::new()
            .name("church-cap-engine-controller".into())
            .spawn(move || {
                #[cfg(target_os = "windows")]
                let _windows_job = windows_job;
                supervise_child(app_handle, supervisor, &mut child, stdin, control_rx)
            })
            .map_err(|error| {
                format!("Church Cap could not start its engine controller: {error}")
            })?;

        Ok(self.snapshot())
    }

    fn request_stop(
        &self,
        app: &AppHandle,
        allow_live_interrupt: bool,
    ) -> Result<SupervisorSnapshot, String> {
        let current = self.snapshot();
        if current.captions_live && !allow_live_interrupt {
            return Err(
                "Live captions are active. Confirm the interruption before stopping Church Cap."
                    .into(),
            );
        }
        if !current.phase.engine_is_running() {
            return Ok(current);
        }
        let sender = self
            .control
            .lock()
            .expect("supervisor control state poisoned")
            .clone()
            .ok_or_else(|| "The engine controller is unavailable.".to_string())?;
        self.publish(app, |status| {
            status.phase = SupervisorPhase::Stopping;
            status.detail = "Stopping Church Cap safely…".into();
        });
        sender
            .send(ControlMessage::Stop)
            .map_err(|_| "The engine controller stopped unexpectedly.".to_string())?;
        Ok(self.snapshot())
    }

    fn request_force_stop(&self) {
        if let Some(sender) = self
            .control
            .lock()
            .expect("supervisor control state poisoned")
            .clone()
        {
            let _ = sender.send(ControlMessage::ForceStop);
        }
    }

    pub(crate) fn exit_is_authorized(&self) -> bool {
        self.exit_authorized.load(Ordering::Acquire)
    }

    pub(crate) fn begin_update_install(&self, app: &AppHandle) -> Result<bool, String> {
        let current = self.snapshot();
        ensure_update_install_is_safe(&current)?;
        let restart_engine_on_failure = current.phase == SupervisorPhase::Ready;
        if current.phase == SupervisorPhase::Ready {
            self.request_stop(app, false)?;
            let deadline = Instant::now() + Duration::from_secs(25);
            while Instant::now() < deadline && self.snapshot().pid.is_some() {
                thread::sleep(Duration::from_millis(100));
            }
            if self.snapshot().pid.is_some() {
                return Err(
                    "Church Cap could not stop its local server safely, so the update was not installed."
                        .into(),
                );
            }
        }
        self.publish(app, |status| {
            status.phase = SupervisorPhase::Updating;
            status.detail = "Installing the verified Church Cap update…".into();
            status.captions_live = false;
            status.health_confirmed = false;
        });
        Ok(restart_engine_on_failure)
    }

    pub(crate) fn recover_after_update_failure(
        &self,
        app: &AppHandle,
        detail: String,
        restart_engine: bool,
    ) {
        self.publish(app, |status| {
            status.phase = SupervisorPhase::Error;
            status.detail = detail;
            status.pid = None;
            status.captions_live = false;
            status.health_confirmed = false;
        });
        if !restart_engine {
            return;
        }
        if let Err(error) = self.start(app) {
            self.publish(app, |status| {
                status.phase = SupervisorPhase::RecoveryRequired;
                status.detail = format!(
                    "The update failed and Church Cap could not restart its local server: {error}"
                );
            });
        }
    }
}

/// The data directory every desktop build before v0.9.0's `9a3ec57` used.
/// It must be resolved with the same Tauri call those builds made so the
/// path matches on each platform; a resolution failure just means there is
/// nothing to migrate.
fn legacy_tauri_data_dir(app: &AppHandle) -> Option<PathBuf> {
    app.path().app_local_data_dir().ok()
}

fn church_cap_data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    #[cfg(target_os = "macos")]
    {
        app.path()
            .home_dir()
            .map(|home| {
                home.join("Library")
                    .join("Application Support")
                    .join("Church Cap")
            })
            .map_err(|error| {
                format!("Church Cap could not locate the current user's home directory: {error}")
            })
    }

    #[cfg(target_os = "windows")]
    {
        if let Some(roaming) = std::env::var_os("APPDATA") {
            return Ok(PathBuf::from(roaming).join("Church Cap"));
        }
        app
            .path()
            .home_dir()
            .map(|home| home.join("AppData").join("Roaming").join("Church Cap"))
            .map_err(|error| format!("Church Cap could not locate the current user's application-data directory: {error}"))
    }

    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        if let Some(xdg_data) = std::env::var_os("XDG_DATA_HOME") {
            return Ok(PathBuf::from(xdg_data).join("church-cap"));
        }
        app.path()
            .home_dir()
            .map(|home| home.join(".local").join("share").join("church-cap"))
            .map_err(|error| {
                format!("Church Cap could not locate the current user's data directory: {error}")
            })
    }
}

fn ensure_update_install_is_safe(snapshot: &SupervisorSnapshot) -> Result<(), String> {
    if snapshot.captions_live || snapshot.phase == SupervisorPhase::CaptionsLive {
        return Err(
            "Live captions are active. Stop captions before installing an application update."
                .into(),
        );
    }
    match snapshot.phase {
        SupervisorPhase::Ready | SupervisorPhase::Stopped => Ok(()),
        SupervisorPhase::Error if snapshot.pid.is_none() => Ok(()),
        SupervisorPhase::Starting | SupervisorPhase::Stopping => Err(
            "Church Cap is changing server state. Wait until it is ready or stopped, then install the update."
                .into(),
        ),
        SupervisorPhase::Updating => Err("An application update is already in progress.".into()),
        SupervisorPhase::RecoveryRequired | SupervisorPhase::Error => Err(
            "Church Cap needs recovery before an application update can be installed.".into(),
        ),
        SupervisorPhase::CaptionsLive => unreachable!(),
    }
}

fn ensure_password_reset_is_safe(snapshot: &SupervisorSnapshot) -> Result<(), String> {
    if snapshot.captions_live || snapshot.phase == SupervisorPhase::CaptionsLive {
        return Err(
            "Live captions are active. Stop captions before resetting the operator password."
                .into(),
        );
    }
    match snapshot.phase {
        SupervisorPhase::Ready | SupervisorPhase::Stopped => Ok(()),
        SupervisorPhase::Error | SupervisorPhase::RecoveryRequired if snapshot.pid.is_none() => {
            Ok(())
        }
        SupervisorPhase::Starting | SupervisorPhase::Stopping => Err(
            "Church Cap is changing server state. Wait until it is ready or stopped, then reset the operator password."
                .into(),
        ),
        SupervisorPhase::Updating => {
            Err("Church Cap cannot reset the password while an update is in progress.".into())
        }
        SupervisorPhase::RecoveryRequired | SupervisorPhase::Error => Err(
            "Church Cap must finish stopping its local server before the password can be reset."
                .into(),
        ),
        SupervisorPhase::CaptionsLive => unreachable!(),
    }
}

fn ensure_factory_reset_is_safe(snapshot: &SupervisorSnapshot) -> Result<(), String> {
    if snapshot.captions_live || snapshot.phase == SupervisorPhase::CaptionsLive {
        return Err(
            "Live captions are active. Stop captions before factory resetting Church Cap.".into(),
        );
    }
    match snapshot.phase {
        SupervisorPhase::Ready | SupervisorPhase::Stopped => Ok(()),
        SupervisorPhase::Error | SupervisorPhase::RecoveryRequired if snapshot.pid.is_none() => Ok(()),
        SupervisorPhase::Starting | SupervisorPhase::Stopping => Err(
            "Church Cap is changing server state. Wait until it is ready or stopped, then try factory reset again."
                .into(),
        ),
        SupervisorPhase::Updating => {
            Err("Church Cap cannot be factory reset while an update is in progress.".into())
        }
        SupervisorPhase::RecoveryRequired | SupervisorPhase::Error => Err(
            "Church Cap must finish stopping its local server before factory reset can begin."
                .into(),
        ),
        SupervisorPhase::CaptionsLive => unreachable!(),
    }
}

fn start_requires_spawn(snapshot: &SupervisorSnapshot, controller_available: bool) -> bool {
    !snapshot.phase.engine_is_running() && snapshot.pid.is_none() && !controller_available
}

pub fn start_on_launch(app: &AppHandle) {
    let supervisor = app.state::<EngineSupervisor>();
    supervisor.publish(app, |status| status.restart_attempts = 0);
    if let Err(error) = supervisor.start(app) {
        supervisor.publish(app, |status| {
            status.phase = SupervisorPhase::Error;
            status.detail = error;
        });
    }
}

#[cfg(debug_assertions)]
pub fn run_self_test_if_requested(app: &AppHandle) {
    let recovery_test =
        std::env::var("CHURCH_CAP_SUPERVISOR_RECOVERY_SELF_TEST").as_deref() == Ok("1");
    if std::env::var("CHURCH_CAP_SUPERVISOR_SELF_TEST").as_deref() != Ok("1") && !recovery_test {
        return;
    }

    let supervisor = app.state::<EngineSupervisor>().inner().clone();
    let app_handle = app.clone();
    thread::spawn(move || {
        let ready_deadline = Instant::now() + Duration::from_secs(120);
        while Instant::now() < ready_deadline {
            let snapshot = supervisor.snapshot();
            let phase = snapshot.phase;
            if phase == SupervisorPhase::Ready && snapshot.health_confirmed {
                break;
            }
            if matches!(
                phase,
                SupervisorPhase::Error | SupervisorPhase::RecoveryRequired
            ) {
                eprintln!("CHURCH_CAP_SUPERVISOR_TEST=failed_before_ready");
                app_handle.exit(2);
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }

        let ready = supervisor.snapshot();
        if ready.phase != SupervisorPhase::Ready || !ready.health_confirmed {
            eprintln!("CHURCH_CAP_SUPERVISOR_TEST=readiness_timeout");
            supervisor.request_force_stop();
            app_handle.exit(2);
            return;
        }
        if recovery_test {
            let first_pid = ready.pid;
            supervisor.request_force_stop();
            let recovery_deadline = Instant::now() + Duration::from_secs(120);
            while Instant::now() < recovery_deadline {
                let recovered = supervisor.snapshot();
                if recovered.phase == SupervisorPhase::Ready
                    && recovered.health_confirmed
                    && recovered.pid.is_some()
                    && recovered.pid != first_pid
                {
                    break;
                }
                if recovered.phase == SupervisorPhase::RecoveryRequired {
                    eprintln!("CHURCH_CAP_SUPERVISOR_RECOVERY_TEST=failed");
                    app_handle.exit(2);
                    return;
                }
                thread::sleep(Duration::from_millis(100));
            }
            let recovered = supervisor.snapshot();
            if recovered.phase != SupervisorPhase::Ready
                || !recovered.health_confirmed
                || recovered.pid.is_none()
                || recovered.pid == first_pid
            {
                eprintln!("CHURCH_CAP_SUPERVISOR_RECOVERY_TEST=timeout");
                supervisor.request_force_stop();
                app_handle.exit(2);
                return;
            }
            println!("CHURCH_CAP_SUPERVISOR_RECOVERY_TEST=passed");
        }
        if let Err(error) = supervisor.request_stop(&app_handle, false) {
            eprintln!("CHURCH_CAP_SUPERVISOR_TEST=stop_failed:{error}");
            supervisor.request_force_stop();
            app_handle.exit(2);
            return;
        }

        let stop_deadline = Instant::now() + Duration::from_secs(25);
        while Instant::now() < stop_deadline {
            if supervisor.snapshot().phase == SupervisorPhase::Stopped {
                println!("CHURCH_CAP_SUPERVISOR_TEST=passed");
                app_handle.exit(0);
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        eprintln!("CHURCH_CAP_SUPERVISOR_TEST=shutdown_timeout");
        supervisor.request_force_stop();
        app_handle.exit(2);
    });
}

fn resolve_engine_path(app: &AppHandle) -> Result<PathBuf, String> {
    #[cfg(debug_assertions)]
    if let Some(configured) = std::env::var_os("CHURCH_CAP_ENGINE_PATH") {
        return validate_engine_path(PathBuf::from(configured));
    }

    let executable = if cfg!(windows) {
        "church-cap-engine.exe"
    } else {
        "church-cap-engine"
    };
    let path = app
        .path()
        .resource_dir()
        .map_err(|error| error.to_string())?
        .join("engine")
        .join("church-cap-engine")
        .join(executable);
    validate_engine_path(path)
}

fn validate_engine_path(path: PathBuf) -> Result<PathBuf, String> {
    if !path.is_file() {
        return Err(format!(
            "The packaged Church Cap engine is missing: {}",
            path.display()
        ));
    }
    path.canonicalize()
        .map_err(|error| format!("The Church Cap engine path is invalid: {error}"))
}

fn spawn_output_reader<R: std::io::Read + Send + 'static>(
    app: AppHandle,
    supervisor: EngineSupervisor,
    reader: BufReader<R>,
    parse_events: bool,
) {
    thread::spawn(move || {
        let mut last_open_updates = None;
        for line in reader.lines().map_while(Result::ok) {
            supervisor.record_output(&line);
            if parse_events {
                if let Some(event) = EngineEvent::parse(&line) {
                    apply_engine_event(&app, &supervisor, event);
                } else if let Some(request) = EngineRequest::parse(&line)
                    && accepts_engine_request(&supervisor.snapshot(), &request)
                {
                    let now = Instant::now();
                    if last_open_updates.is_none_or(|last: Instant| {
                        now.duration_since(last) >= OPEN_UPDATES_DEBOUNCE
                    }) {
                        last_open_updates = Some(now);
                        if let Err(error) = crate::window::show_control_window(&app) {
                            supervisor.record_output(&format!(
                                "Could not show control window for update check: {error}"
                            ));
                        }
                        if let Err(error) = app.emit(OPEN_UPDATES_EVENT, ()) {
                            supervisor.record_output(&format!(
                                "Could not dispatch update check: {error}"
                            ));
                        }
                    }
                }
            }
        }
    });
}

fn apply_engine_event(app: &AppHandle, supervisor: &EngineSupervisor, event: EngineEvent) {
    if !event_belongs_to_owned_engine(&supervisor.snapshot(), event.pid) {
        supervisor.record_output(&format!(
            "Ignored a lifecycle event from stale engine PID {}.",
            event.pid
        ));
        return;
    }
    if event.protocol_version != ENGINE_PROTOCOL_VERSION
        || event.app_version != env!("CARGO_PKG_VERSION")
    {
        supervisor.publish(app, |status| {
            status.phase = SupervisorPhase::RecoveryRequired;
            status.detail = format!(
                "The desktop host and engine are incompatible (host {}, engine {}, protocol {}).",
                env!("CARGO_PKG_VERSION"),
                event.app_version,
                event.protocol_version
            );
            status.engine_version = Some(event.app_version);
            status.engine_protocol_version = event.protocol_version;
        });
        supervisor.request_force_stop();
        return;
    }

    let event_state = event.state.clone();
    let event_pid = event.pid;
    let viewer_url = event.viewer_url.clone();
    supervisor.publish(app, |status| {
        status.engine_version = Some(event.app_version);
        status.engine_protocol_version = event.protocol_version;
        status.viewer_url = event.viewer_url;
        status.operator_url = event.operator_url;
        status.pid = Some(event.pid);
        apply_runtime_state(status, &event_state, event.detail);
    });

    if event_state == "ready" {
        spawn_health_confirmation(app.clone(), supervisor.clone(), viewer_url, event_pid);
    }
}

fn event_belongs_to_owned_engine(snapshot: &SupervisorSnapshot, event_pid: u32) -> bool {
    snapshot.pid == Some(event_pid)
}

fn accepts_engine_request(snapshot: &SupervisorSnapshot, request: &EngineRequest) -> bool {
    event_belongs_to_owned_engine(snapshot, request.pid)
        && request.protocol_version == ENGINE_PROTOCOL_VERSION
        && request.request == "open_updates"
}

fn apply_runtime_state(status: &mut SupervisorSnapshot, state: &str, detail: String) {
    match state {
        "starting" => {
            status.phase = SupervisorPhase::Starting;
            status.captions_live = false;
            status.health_confirmed = false;
            status.detail = detail;
        }
        "ready" => {
            status.phase = SupervisorPhase::Starting;
            status.captions_live = false;
            status.health_confirmed = false;
            status.detail = "Confirming the local Church Cap service…".into();
        }
        "captions_live" if status.health_confirmed => {
            status.phase = SupervisorPhase::CaptionsLive;
            status.captions_live = true;
            status.detail = detail;
        }
        "captions_idle" if status.health_confirmed => {
            status.phase = SupervisorPhase::Ready;
            status.captions_live = false;
            status.detail = detail;
        }
        // Engine text output is informative, not authoritative for process
        // ownership. A supervisor-issued stop publishes Stopping before it
        // sends the shutdown command, and `supervise_child` alone publishes
        // terminal Stopped after observing actual OS process exit. Ignoring
        // these lines also prevents buffered output from an old process from
        // overwriting a newly recovered engine's state.
        "stopping" | "stopped" => {}
        "error" => {
            status.phase = SupervisorPhase::Error;
            status.captions_live = false;
            status.health_confirmed = false;
            status.detail = detail;
        }
        _ => {}
    }
}

#[derive(Debug, serde::Deserialize)]
struct HealthResponse {
    ok: bool,
    status: String,
    app_version: String,
    runtime_mode: String,
    engine_protocol_version: u16,
}

fn spawn_health_confirmation(
    app: AppHandle,
    supervisor: EngineSupervisor,
    viewer_url: String,
    engine_pid: u32,
) {
    let error_app = app.clone();
    let error_supervisor = supervisor.clone();
    if let Err(error) = thread::Builder::new()
        .name("church-cap-health-confirmation".into())
        .spawn(move || {
            let deadline = Instant::now() + HEALTH_CONFIRM_TIMEOUT;
            let mut last_error = "The health endpoint did not respond.".to_string();
            while Instant::now() < deadline {
                match request_health(&viewer_url) {
                    Ok(response) => match validate_health(&response) {
                        Ok(()) => {
                            if supervisor.snapshot().pid == Some(engine_pid)
                                && supervisor.snapshot().phase == SupervisorPhase::Starting
                            {
                                let captions_live =
                                    LIVE_CAPTION_STATUSES.contains(&response.status.as_str());
                                supervisor.publish(&app, |status| {
                                    status.phase = if captions_live {
                                        SupervisorPhase::CaptionsLive
                                    } else {
                                        SupervisorPhase::Ready
                                    };
                                    status.captions_live = captions_live;
                                    status.health_confirmed = true;
                                    status.detail = if captions_live {
                                        "Live captions are active.".into()
                                    } else {
                                        "The local Church Cap browser service is ready.".into()
                                    };
                                });
                                schedule_restart_budget_reset(
                                    app.clone(),
                                    supervisor.clone(),
                                    engine_pid,
                                );
                            }
                            return;
                        }
                        Err(error) => last_error = error,
                    },
                    Err(error) => last_error = error,
                }
                thread::sleep(HEALTH_RETRY_INTERVAL);
            }

            if supervisor.snapshot().pid == Some(engine_pid)
                && supervisor.snapshot().phase == SupervisorPhase::Starting
            {
                supervisor.publish(&app, |status| {
                    status.phase = SupervisorPhase::RecoveryRequired;
                    status.health_confirmed = false;
                    status.detail = format!(
                        "Church Cap started but its local health check failed: {last_error}"
                    );
                });
                supervisor.request_force_stop();
            }
        })
    {
        error_supervisor.publish(&error_app, |status| {
            status.phase = SupervisorPhase::RecoveryRequired;
            status.health_confirmed = false;
            status.detail = format!("Church Cap could not start its health-check worker: {error}");
        });
        error_supervisor.request_force_stop();
    }
}

fn health_endpoint(viewer_url: &str) -> Result<(SocketAddr, String), String> {
    let mut url = Url::parse(viewer_url)
        .map_err(|error| format!("The engine supplied an invalid viewer address: {error}"))?;
    if url.scheme() != "http" || !url.username().is_empty() || url.password().is_some() {
        return Err("The engine health address must be an unauthenticated local HTTP URL.".into());
    }
    let ip = match url.host() {
        Some(Host::Ipv4(ip)) if ip.is_loopback() => IpAddr::V4(ip),
        Some(Host::Ipv6(ip)) if ip.is_loopback() => IpAddr::V6(ip),
        Some(Host::Domain(host)) if host.eq_ignore_ascii_case("localhost") => {
            IpAddr::V4(std::net::Ipv4Addr::LOCALHOST)
        }
        _ => return Err("The engine health address must use the loopback interface.".into()),
    };
    let port = url
        .port_or_known_default()
        .ok_or_else(|| "The engine health address has no port.".to_string())?;
    url.set_path("/health");
    url.set_query(None);
    url.set_fragment(None);
    Ok((SocketAddr::new(ip, port), url.path().to_string()))
}

fn request_health(viewer_url: &str) -> Result<HealthResponse, String> {
    let (address, path) = health_endpoint(viewer_url)?;
    let mut stream = TcpStream::connect_timeout(&address, HEALTH_ATTEMPT_TIMEOUT)
        .map_err(|error| format!("health connection failed: {error}"))?;
    stream
        .set_read_timeout(Some(HEALTH_ATTEMPT_TIMEOUT))
        .map_err(|error| format!("health read timeout could not be set: {error}"))?;
    stream
        .set_write_timeout(Some(HEALTH_ATTEMPT_TIMEOUT))
        .map_err(|error| format!("health write timeout could not be set: {error}"))?;
    let request = format!(
        "GET {path} HTTP/1.1\r\nHost: {address}\r\nAccept: application/json\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| format!("health request failed: {error}"))?;

    let mut response = Vec::new();
    stream
        .take((MAX_HEALTH_RESPONSE_BYTES + 1) as u64)
        .read_to_end(&mut response)
        .map_err(|error| format!("health response failed: {error}"))?;
    parse_health_http_response(&response)
}

fn parse_health_http_response(response: &[u8]) -> Result<HealthResponse, String> {
    if response.len() > MAX_HEALTH_RESPONSE_BYTES {
        return Err("health response exceeded the safe size limit".into());
    }
    let header_end = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "health response was not valid HTTP".to_string())?;
    let headers = std::str::from_utf8(&response[..header_end])
        .map_err(|_| "health response headers were not UTF-8".to_string())?;
    let status = headers.lines().next().unwrap_or_default();
    if !(status.starts_with("HTTP/1.1 200 ") || status.starts_with("HTTP/1.0 200 ")) {
        return Err(format!("health endpoint returned {status}"));
    }
    serde_json::from_slice(&response[header_end + 4..])
        .map_err(|error| format!("health response was not valid JSON: {error}"))
}

fn validate_health(response: &HealthResponse) -> Result<(), String> {
    if !response.ok {
        return Err("health endpoint reported that the engine was not ready".into());
    }
    if response.app_version != env!("CARGO_PKG_VERSION")
        || response.engine_protocol_version != ENGINE_PROTOCOL_VERSION
        || response.runtime_mode != "packaged"
    {
        return Err(format!(
            "health compatibility mismatch (host {}, engine {}, protocol {}, runtime {})",
            env!("CARGO_PKG_VERSION"),
            response.app_version,
            response.engine_protocol_version,
            response.runtime_mode
        ));
    }
    Ok(())
}

fn automatic_restart_delay(
    previous_phase: SupervisorPhase,
    exit_succeeded: bool,
    attempts: u8,
) -> Option<Duration> {
    if exit_succeeded
        || matches!(
            previous_phase,
            SupervisorPhase::Stopping
                | SupervisorPhase::Updating
                | SupervisorPhase::RecoveryRequired
        )
        || attempts >= MAX_AUTOMATIC_RESTART_ATTEMPTS
    {
        return None;
    }
    Some(Duration::from_secs(match attempts {
        0 => 1,
        1 => 3,
        _ => 10,
    }))
}

fn schedule_automatic_restart(
    app: AppHandle,
    supervisor: EngineSupervisor,
    delay: Duration,
    expected_attempt: u8,
) {
    let error_app = app.clone();
    let error_supervisor = supervisor.clone();
    if let Err(error) = thread::Builder::new()
        .name("church-cap-restart-backoff".into())
        .spawn(move || {
            thread::sleep(delay);
            let snapshot = supervisor.snapshot();
            if supervisor.quit_started.load(Ordering::Acquire)
                || snapshot.phase != SupervisorPhase::Error
                || snapshot.pid.is_some()
                || snapshot.restart_attempts != expected_attempt
            {
                return;
            }
            if let Err(error) = supervisor.start(&app) {
                supervisor.publish(&app, |status| {
                    status.phase = SupervisorPhase::Error;
                    status.detail = format!(
                        "Church Cap could not complete automatic restart attempt {expected_attempt}: {error}"
                    );
                });
            }
        })
    {
        error_supervisor.publish(&error_app, |status| {
            status.phase = SupervisorPhase::RecoveryRequired;
            status.detail = format!("Church Cap could not schedule automatic recovery: {error}");
        });
    }
}

fn schedule_restart_budget_reset(app: AppHandle, supervisor: EngineSupervisor, engine_pid: u32) {
    let expected_attempts = supervisor.snapshot().restart_attempts;
    if expected_attempts == 0 {
        return;
    }
    let _ = thread::Builder::new()
        .name("church-cap-restart-budget-reset".into())
        .spawn(move || {
            thread::sleep(RESTART_BUDGET_RESET_DELAY);
            let snapshot = supervisor.snapshot();
            if snapshot.pid == Some(engine_pid)
                && snapshot.phase.engine_is_running()
                && snapshot.health_confirmed
                && snapshot.restart_attempts == expected_attempts
            {
                supervisor.publish(&app, |status| status.restart_attempts = 0);
            }
        });
}

pub fn revalidate_after_resume(app: &AppHandle) {
    let supervisor = app.state::<EngineSupervisor>().inner().clone();
    let snapshot = supervisor.snapshot();
    if !matches!(
        snapshot.phase,
        SupervisorPhase::Ready | SupervisorPhase::CaptionsLive
    ) {
        return;
    }
    let Some(pid) = snapshot.pid else {
        return;
    };
    supervisor.publish(app, |status| {
        status.phase = SupervisorPhase::Starting;
        status.captions_live = false;
        status.health_confirmed = false;
        status.detail = "Checking the local Church Cap service after wake…".into();
    });
    spawn_health_confirmation(app.clone(), supervisor, snapshot.viewer_url, pid);
}

fn supervise_child(
    app: AppHandle,
    supervisor: EngineSupervisor,
    child: &mut Child,
    mut stdin: Option<std::process::ChildStdin>,
    commands: Receiver<ControlMessage>,
) {
    let mut stop_deadline: Option<Instant> = None;
    loop {
        match commands.recv_timeout(Duration::from_millis(100)) {
            Ok(ControlMessage::Stop) => {
                if let Some(input) = stdin.as_mut() {
                    let _ = input.write_all(EngineCommand::shutdown_line().as_bytes());
                    let _ = input.flush();
                }
                stop_deadline = Some(Instant::now() + GRACEFUL_STOP_TIMEOUT);
            }
            Ok(ControlMessage::ForceStop) => {
                let _ = child.kill();
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                let _ = child.kill();
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {}
        }

        if stop_deadline.is_some_and(|deadline| Instant::now() >= deadline) {
            supervisor.record_output("Graceful engine shutdown timed out; forcing termination.");
            let _ = child.kill();
            stop_deadline = None;
        }

        match child.try_wait() {
            Ok(Some(exit)) => {
                let previous = supervisor.snapshot();
                let restart_delay = automatic_restart_delay(
                    previous.phase,
                    exit.success(),
                    previous.restart_attempts,
                );
                let next_attempt = previous.restart_attempts.saturating_add(1);
                *supervisor
                    .control
                    .lock()
                    .expect("supervisor control state poisoned") = None;
                supervisor.publish(&app, |status| {
                    status.pid = None;
                    status.captions_live = false;
                    status.health_confirmed = false;
                    if previous.phase == SupervisorPhase::RecoveryRequired {
                        status.phase = SupervisorPhase::RecoveryRequired;
                    } else if previous.phase == SupervisorPhase::Stopping || exit.success() {
                        status.phase = SupervisorPhase::Stopped;
                        status.detail = "Church Cap stopped safely.".into();
                    } else if let Some(delay) = restart_delay {
                        status.phase = SupervisorPhase::Error;
                        status.restart_attempts = next_attempt;
                        status.detail = format!(
                            "The Church Cap engine exited unexpectedly ({exit}). Restarting in {} second{} (attempt {next_attempt}/{MAX_AUTOMATIC_RESTART_ATTEMPTS}); captions will remain stopped.",
                            delay.as_secs(),
                            if delay.as_secs() == 1 { "" } else { "s" },
                        );
                    } else {
                        status.phase = SupervisorPhase::Error;
                        status.detail = format!(
                            "The Church Cap engine exited unexpectedly ({exit}). Automatic recovery paused after {MAX_AUTOMATIC_RESTART_ATTEMPTS} attempts; open the controls to try again."
                        );
                    }
                });
                if let Some(delay) = restart_delay {
                    schedule_automatic_restart(app, supervisor, delay, next_attempt);
                }
                return;
            }
            Ok(None) => {}
            Err(error) => {
                supervisor.publish(&app, |status| {
                    status.phase = SupervisorPhase::Error;
                    status.detail =
                        format!("Church Cap could not inspect its engine process: {error}");
                });
                return;
            }
        }
    }
}

#[tauri::command]
pub fn get_supervisor_status(
    app: AppHandle,
    supervisor: State<'_, EngineSupervisor>,
) -> SupervisorSnapshot {
    let snapshot = supervisor.snapshot();
    // Reapply the native presentation whenever the centred window performs
    // its periodic/focus reconciliation. This repairs any OS menu refresh
    // that was deferred while the application was in the background.
    crate::tray::sync(&app, &snapshot);
    snapshot
}

#[tauri::command]
pub fn start_engine(
    app: AppHandle,
    supervisor: State<'_, EngineSupervisor>,
) -> Result<SupervisorSnapshot, String> {
    supervisor.publish(&app, |status| status.restart_attempts = 0);
    let started = supervisor.start(&app)?;
    let engine_pid = started
        .pid
        .ok_or_else(|| "Church Cap started without an engine process identifier.".to_string())?;
    schedule_operator_open_when_ready(app, supervisor.inner().clone(), engine_pid)?;
    Ok(started)
}

fn pending_browser_open(snapshot: &SupervisorSnapshot, engine_pid: u32) -> PendingBrowserOpen {
    if snapshot.pid != Some(engine_pid) {
        return PendingBrowserOpen::Cancel;
    }
    if snapshot.health_confirmed
        && matches!(
            snapshot.phase,
            SupervisorPhase::Ready | SupervisorPhase::CaptionsLive
        )
    {
        return PendingBrowserOpen::Open;
    }
    if matches!(
        snapshot.phase,
        SupervisorPhase::Stopped
            | SupervisorPhase::Stopping
            | SupervisorPhase::Updating
            | SupervisorPhase::RecoveryRequired
            | SupervisorPhase::Error
    ) {
        return PendingBrowserOpen::Cancel;
    }
    PendingBrowserOpen::Wait
}

fn schedule_operator_open_when_ready(
    app: AppHandle,
    supervisor: EngineSupervisor,
    engine_pid: u32,
) -> Result<(), String> {
    thread::Builder::new()
        .name("church-cap-open-after-start".into())
        .spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(120);
            while Instant::now() < deadline {
                match pending_browser_open(&supervisor.snapshot(), engine_pid) {
                    PendingBrowserOpen::Wait => thread::sleep(Duration::from_millis(100)),
                    PendingBrowserOpen::Open => {
                        if let Err(error) = crate::browser::open_route_internal(
                            &app,
                            crate::browser::ChurchCapRoute::Operator,
                        ) {
                            eprintln!("Church Cap could not open the browser after Start: {error}");
                        }
                        return;
                    }
                    PendingBrowserOpen::Cancel => return,
                }
            }
            eprintln!("Church Cap did not become ready in time to open the browser after Start.");
        })
        .map(|_| ())
        .map_err(|error| format!("Church Cap could not schedule browser opening: {error}"))
}

#[tauri::command]
pub fn stop_engine(
    app: AppHandle,
    supervisor: State<'_, EngineSupervisor>,
    allow_live_interrupt: bool,
) -> Result<SupervisorSnapshot, String> {
    supervisor.request_stop(&app, allow_live_interrupt)
}

#[tauri::command]
pub fn restart_engine(
    app: AppHandle,
    supervisor: State<'_, EngineSupervisor>,
    allow_live_interrupt: bool,
) -> Result<SupervisorSnapshot, String> {
    supervisor.request_stop(&app, allow_live_interrupt)?;
    let owned = supervisor.inner().clone();
    let app_handle = app.clone();
    thread::Builder::new()
        .name("church-cap-manual-restart".into())
        .spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(25);
            while Instant::now() < deadline {
                if owned.snapshot().phase == SupervisorPhase::Stopped {
                    owned.publish(&app_handle, |status| status.restart_attempts = 0);
                    if let Err(error) = owned.start(&app_handle) {
                        owned.publish(&app_handle, |status| {
                            status.phase = SupervisorPhase::RecoveryRequired;
                            status.detail = format!(
                                "Church Cap stopped safely but could not restart its local server: {error}"
                            );
                            status.pid = None;
                            status.captions_live = false;
                            status.health_confirmed = false;
                        });
                    }
                    return;
                }
                thread::sleep(Duration::from_millis(100));
            }
            owned.publish(&app_handle, |status| {
                status.phase = SupervisorPhase::RecoveryRequired;
                status.detail =
                    "Church Cap could not restart because its previous server did not stop safely."
                        .into();
            });
        })
        .map_err(|error| format!("Church Cap could not schedule its server restart: {error}"))?;
    Ok(supervisor.snapshot())
}

#[tauri::command]
pub fn reset_operator_password(
    app: AppHandle,
    supervisor: State<'_, EngineSupervisor>,
) -> Result<SupervisorSnapshot, String> {
    let data_dir = church_cap_data_dir(&app)?;
    ensure_password_reset_is_safe(&supervisor.snapshot())?;

    if supervisor.snapshot().phase.engine_is_running() {
        supervisor.request_stop(&app, false)?;
        let deadline = Instant::now() + Duration::from_secs(25);
        while Instant::now() < deadline && supervisor.snapshot().pid.is_some() {
            thread::sleep(Duration::from_millis(100));
        }
        if supervisor.snapshot().pid.is_some() {
            return Err(
                "Church Cap could not stop its local server safely, so the operator password was not reset."
                    .into(),
            );
        }
    }

    supervisor.publish(&app, |status| {
        status.phase = SupervisorPhase::Updating;
        status.detail = "Resetting operator access…".into();
        status.captions_live = false;
        status.health_confirmed = false;
    });

    if let Err(error) = crate::recovery::reset_operator_auth(&data_dir) {
        if let Err(restart_error) = supervisor.start(&app) {
            supervisor.publish(&app, |status| {
                status.phase = SupervisorPhase::RecoveryRequired;
                status.detail = format!(
                    "{error} Church Cap also could not restart its local server: {restart_error}"
                );
            });
        }
        return Err(format!("{error} The existing password was left in place."));
    }

    let started = supervisor.start(&app).map_err(|error| {
        supervisor.publish(&app, |status| {
            status.phase = SupervisorPhase::RecoveryRequired;
            status.detail = format!(
                "The operator password was reset, but Church Cap could not restart: {error}"
            );
        });
        format!(
            "The operator password was reset, but Church Cap could not restart its local server: {error}"
        )
    })?;
    let engine_pid = started.pid.ok_or_else(|| {
        "The operator password was reset, but Church Cap restarted without an engine process identifier."
            .to_string()
    })?;
    if let Err(error) =
        schedule_operator_open_when_ready(app, supervisor.inner().clone(), engine_pid)
    {
        eprintln!(
            "The operator password was reset, but Church Cap could not schedule the setup page: {error}"
        );
    }
    Ok(started)
}

#[tauri::command]
pub fn factory_reset_application(
    app: AppHandle,
    supervisor: State<'_, EngineSupervisor>,
) -> Result<SupervisorSnapshot, String> {
    let data_dir = church_cap_data_dir(&app)?;
    ensure_factory_reset_is_safe(&supervisor.snapshot())?;

    if supervisor.snapshot().phase.engine_is_running() {
        supervisor.request_stop(&app, false)?;
        let deadline = Instant::now() + Duration::from_secs(25);
        while Instant::now() < deadline && supervisor.snapshot().pid.is_some() {
            thread::sleep(Duration::from_millis(100));
        }
        if supervisor.snapshot().pid.is_some() {
            return Err(
                "Church Cap could not stop its local server safely, so no factory reset was performed."
                    .into(),
            );
        }
    }

    supervisor.publish(&app, |status| {
        status.phase = SupervisorPhase::Updating;
        status.detail = "Factory resetting Church Cap…".into();
        status.captions_live = false;
        status.health_confirmed = false;
    });

    if let Err(error) = crate::recovery::factory_reset_app_data(&data_dir) {
        if let Err(restart_error) = supervisor.start(&app) {
            supervisor.publish(&app, |status| {
                status.phase = SupervisorPhase::RecoveryRequired;
                status.detail = format!(
                    "{error} Church Cap also could not restart its local server: {restart_error}"
                );
            });
        }
        return Err(error);
    }
    // The canonical reset marker is already in place, so the engine will run
    // first-time setup whatever happens here. Clearing the pre-v0.9.0 folder
    // keeps an old password file and downloaded models from outliving a reset.
    let legacy_warning = legacy_tauri_data_dir(&app).and_then(|legacy_dir| {
        crate::recovery::clear_legacy_app_data(&legacy_dir, &data_dir).err()
    });

    let started = supervisor.start(&app).map_err(|error| {
        supervisor.publish(&app, |status| {
            status.phase = SupervisorPhase::RecoveryRequired;
            status.detail =
                format!("Factory reset completed, but Church Cap could not restart: {error}");
        });
        format!(
            "Factory reset completed, but Church Cap could not restart its local server: {error}"
        )
    })?;
    let engine_pid = started.pid.ok_or_else(|| {
        "Factory reset completed, but Church Cap restarted without an engine process identifier."
            .to_string()
    })?;
    schedule_operator_open_when_ready(app, supervisor.inner().clone(), engine_pid)?;
    if let Some(warning) = legacy_warning {
        return Err(format!(
            "Factory reset completed and Church Cap restarted, but its previous data folder could not be fully cleared: {warning}"
        ));
    }
    Ok(started)
}

#[tauri::command]
pub fn quit_application(
    app: AppHandle,
    supervisor: State<'_, EngineSupervisor>,
    allow_live_interrupt: bool,
) -> Result<(), String> {
    if supervisor.snapshot().captions_live && !allow_live_interrupt {
        return Err(
            "Live captions are active. Confirm the interruption before quitting Church Cap.".into(),
        );
    }
    quit_supervisor(&app);
    Ok(())
}

pub fn quit_supervisor(app: &AppHandle) {
    let supervisor = app.state::<EngineSupervisor>().inner().clone();
    if supervisor.quit_started.swap(true, Ordering::AcqRel) {
        return;
    }
    let app_handle = app.clone();
    let _ = supervisor.request_stop(app, true);
    thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(22);
        while Instant::now() < deadline && supervisor.snapshot().phase.engine_is_running() {
            thread::sleep(Duration::from_millis(100));
        }
        if supervisor.snapshot().phase.engine_is_running() {
            supervisor.request_force_stop();
        }
        supervisor.exit_authorized.store(true, Ordering::Release);
        app_handle.exit(0);
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_missing_engine_paths() {
        let missing = std::path::Path::new("definitely-not-a-church-cap-engine").to_path_buf();
        let error = validate_engine_path(missing).expect_err("missing engine should fail");
        assert!(error.contains("missing"));
    }

    #[test]
    fn accepts_only_loopback_health_endpoints() {
        let (address, path) = health_endpoint("http://127.0.0.1:8080/viewer?unsafe=yes")
            .expect("loopback URL should be accepted");
        assert_eq!(address, "127.0.0.1:8080".parse().unwrap());
        assert_eq!(path, "/health");
        assert!(health_endpoint("https://127.0.0.1:8080/").is_err());
        assert!(health_endpoint("http://example.com:8080/").is_err());
        assert!(health_endpoint("http://user@127.0.0.1:8080/").is_err());
    }

    #[test]
    fn validates_bounded_compatible_health_responses() {
        let body = format!(
            "{{\"ok\":true,\"status\":\"idle\",\"app_version\":\"{}\",\"runtime_mode\":\"packaged\",\"engine_protocol_version\":{}}}",
            env!("CARGO_PKG_VERSION"),
            ENGINE_PROTOCOL_VERSION
        );
        let raw = format!(
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
            body.len()
        );
        let response = parse_health_http_response(raw.as_bytes()).expect("health should parse");
        validate_health(&response).expect("health should be compatible");
        assert!(parse_health_http_response(b"HTTP/1.1 503 Unavailable\r\n\r\n{}").is_err());
    }

    #[test]
    fn caption_events_require_confirmed_health_and_restore_ready() {
        let mut snapshot = SupervisorSnapshot {
            phase: SupervisorPhase::Starting,
            ..SupervisorSnapshot::default()
        };
        apply_runtime_state(
            &mut snapshot,
            "captions_live",
            "Live captions are active.".into(),
        );
        assert_eq!(snapshot.phase, SupervisorPhase::Starting);
        assert!(!snapshot.captions_live);

        snapshot.phase = SupervisorPhase::Ready;
        snapshot.health_confirmed = true;
        apply_runtime_state(
            &mut snapshot,
            "captions_live",
            "Live captions are active.".into(),
        );
        assert_eq!(snapshot.phase, SupervisorPhase::CaptionsLive);
        assert!(snapshot.captions_live);

        apply_runtime_state(
            &mut snapshot,
            "captions_idle",
            "The caption session has stopped.".into(),
        );
        assert_eq!(snapshot.phase, SupervisorPhase::Ready);
        assert!(!snapshot.captions_live);
        assert!(snapshot.health_confirmed);
    }

    #[test]
    fn terminal_text_events_cannot_override_an_owned_server() {
        let mut snapshot = SupervisorSnapshot {
            phase: SupervisorPhase::CaptionsLive,
            pid: Some(42),
            captions_live: true,
            health_confirmed: true,
            ..SupervisorSnapshot::default()
        };
        apply_runtime_state(
            &mut snapshot,
            "stopped",
            "The caption session stopped.".into(),
        );
        assert_eq!(snapshot.phase, SupervisorPhase::CaptionsLive);
        assert!(snapshot.captions_live);
        assert!(snapshot.health_confirmed);
        assert_eq!(snapshot.pid, Some(42));

        apply_runtime_state(&mut snapshot, "stopping", "Engine stopping.".into());
        assert_eq!(snapshot.phase, SupervisorPhase::CaptionsLive);
    }

    #[test]
    fn lifecycle_events_must_match_the_exact_owned_engine_pid() {
        let snapshot = SupervisorSnapshot {
            pid: Some(42),
            ..SupervisorSnapshot::default()
        };
        assert!(event_belongs_to_owned_engine(&snapshot, 42));
        assert!(!event_belongs_to_owned_engine(&snapshot, 41));
        assert!(!event_belongs_to_owned_engine(
            &SupervisorSnapshot::default(),
            42
        ));
    }

    #[test]
    fn update_requests_require_owned_pid_protocol_and_exact_request() {
        let snapshot = SupervisorSnapshot {
            pid: Some(42),
            ..SupervisorSnapshot::default()
        };
        let mut request = EngineRequest::parse("CHURCH_CAP_ENGINE_REQUEST={\"request\":\"open_updates\",\"protocol_version\":2,\"pid\":42}").unwrap();
        assert!(accepts_engine_request(&snapshot, &request));
        request.pid = 41;
        assert!(!accepts_engine_request(&snapshot, &request));
        request.pid = 42;
        request.protocol_version = 1;
        assert!(!accepts_engine_request(&snapshot, &request));
        request.protocol_version = ENGINE_PROTOCOL_VERSION;
        request.request = "install_update".into();
        assert!(!accepts_engine_request(&snapshot, &request));
        request.request = "open_updates".into();
        assert!(!accepts_engine_request(
            &SupervisorSnapshot::default(),
            &request
        ));
    }

    #[test]
    fn automatic_restart_policy_is_bounded_and_skips_intentional_exits() {
        assert_eq!(
            automatic_restart_delay(SupervisorPhase::Ready, false, 0),
            Some(Duration::from_secs(1))
        );
        assert_eq!(
            automatic_restart_delay(SupervisorPhase::CaptionsLive, false, 1),
            Some(Duration::from_secs(3))
        );
        assert_eq!(
            automatic_restart_delay(SupervisorPhase::Starting, false, 2),
            Some(Duration::from_secs(10))
        );
        assert_eq!(
            automatic_restart_delay(SupervisorPhase::Ready, false, 3),
            None
        );
        assert_eq!(
            automatic_restart_delay(SupervisorPhase::Stopping, false, 0),
            None
        );
        assert_eq!(
            automatic_restart_delay(SupervisorPhase::Ready, true, 0),
            None
        );
    }

    #[test]
    fn explicit_start_opens_only_the_matching_healthy_engine() {
        let mut snapshot = SupervisorSnapshot {
            phase: SupervisorPhase::Starting,
            pid: Some(42),
            ..SupervisorSnapshot::default()
        };
        assert_eq!(
            pending_browser_open(&snapshot, 42),
            PendingBrowserOpen::Wait
        );

        snapshot.phase = SupervisorPhase::Ready;
        snapshot.health_confirmed = true;
        assert_eq!(
            pending_browser_open(&snapshot, 42),
            PendingBrowserOpen::Open
        );

        snapshot.pid = Some(43);
        assert_eq!(
            pending_browser_open(&snapshot, 42),
            PendingBrowserOpen::Cancel
        );
    }

    #[test]
    fn updates_never_interrupt_live_captions_or_transitional_processes() {
        let live = SupervisorSnapshot {
            phase: SupervisorPhase::CaptionsLive,
            captions_live: true,
            health_confirmed: true,
            pid: Some(42),
            ..SupervisorSnapshot::default()
        };
        assert!(
            ensure_update_install_is_safe(&live)
                .unwrap_err()
                .contains("Stop captions")
        );

        for phase in [SupervisorPhase::Starting, SupervisorPhase::Stopping] {
            let transitional = SupervisorSnapshot {
                phase,
                pid: Some(42),
                ..SupervisorSnapshot::default()
            };
            assert!(ensure_update_install_is_safe(&transitional).is_err());
        }

        assert!(ensure_update_install_is_safe(&SupervisorSnapshot::default()).is_ok());
        let ready = SupervisorSnapshot {
            phase: SupervisorPhase::Ready,
            pid: Some(42),
            health_confirmed: true,
            ..SupervisorSnapshot::default()
        };
        assert!(ensure_update_install_is_safe(&ready).is_ok());
    }

    #[test]
    fn password_reset_requires_a_stable_non_live_server_state() {
        let live = SupervisorSnapshot {
            phase: SupervisorPhase::CaptionsLive,
            captions_live: true,
            health_confirmed: true,
            pid: Some(42),
            ..SupervisorSnapshot::default()
        };
        assert!(
            ensure_password_reset_is_safe(&live)
                .unwrap_err()
                .contains("Stop captions")
        );

        for phase in [
            SupervisorPhase::Starting,
            SupervisorPhase::Stopping,
            SupervisorPhase::Updating,
        ] {
            let transitional = SupervisorSnapshot {
                phase,
                pid: Some(42),
                ..SupervisorSnapshot::default()
            };
            assert!(ensure_password_reset_is_safe(&transitional).is_err());
        }

        assert!(ensure_password_reset_is_safe(&SupervisorSnapshot::default()).is_ok());
        let ready = SupervisorSnapshot {
            phase: SupervisorPhase::Ready,
            pid: Some(42),
            health_confirmed: true,
            ..SupervisorSnapshot::default()
        };
        assert!(ensure_password_reset_is_safe(&ready).is_ok());
    }

    #[test]
    fn factory_reset_requires_a_stable_non_live_server_state() {
        let live = SupervisorSnapshot {
            phase: SupervisorPhase::CaptionsLive,
            captions_live: true,
            pid: Some(42),
            ..SupervisorSnapshot::default()
        };
        assert!(
            ensure_factory_reset_is_safe(&live)
                .unwrap_err()
                .contains("Stop captions")
        );
        for phase in [
            SupervisorPhase::Starting,
            SupervisorPhase::Stopping,
            SupervisorPhase::Updating,
        ] {
            let transitional = SupervisorSnapshot {
                phase,
                pid: Some(42),
                ..SupervisorSnapshot::default()
            };
            assert!(ensure_factory_reset_is_safe(&transitional).is_err());
        }
        assert!(ensure_factory_reset_is_safe(&SupervisorSnapshot::default()).is_ok());
    }

    #[test]
    fn stale_display_state_cannot_spawn_a_duplicate_engine() {
        let mut snapshot = SupervisorSnapshot {
            phase: SupervisorPhase::Stopped,
            pid: Some(42),
            ..SupervisorSnapshot::default()
        };
        assert!(!start_requires_spawn(&snapshot, true));
        assert!(!start_requires_spawn(&snapshot, false));

        snapshot.pid = None;
        snapshot.phase = SupervisorPhase::Error;
        assert!(!start_requires_spawn(&snapshot, true));
        assert!(start_requires_spawn(&snapshot, false));
    }
}
