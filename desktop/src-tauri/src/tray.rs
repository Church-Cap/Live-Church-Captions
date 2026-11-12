use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, Wry};

use crate::browser::{self, ChurchCapRoute};
use crate::lifecycle::{self, EngineSupervisor};
use crate::model::{SupervisorPhase, SupervisorSnapshot};
use crate::window;

const OPEN_OPERATOR: &str = "open-operator";
const SHOW_CONTROLS: &str = "show-controls";
const RESTART_ENGINE: &str = "restart-engine";
const STOP_ENGINE: &str = "stop-engine";
const QUIT: &str = "quit";
const TRAY_ID: &str = "church-cap";

struct TrayControls {
    status: MenuItem<Wry>,
    open_operator: MenuItem<Wry>,
    restart_engine: MenuItem<Wry>,
    stop_engine: MenuItem<Wry>,
}

#[derive(Debug, PartialEq, Eq)]
struct TrayPresentation {
    status_text: &'static str,
    tooltip: &'static str,
    open_enabled: bool,
    restart_enabled: bool,
    stop_enabled: bool,
    stop_text: &'static str,
}

fn presentation(snapshot: &SupervisorSnapshot) -> TrayPresentation {
    use SupervisorPhase::*;
    let healthy = snapshot.health_confirmed && matches!(snapshot.phase, Ready | CaptionsLive);
    match snapshot.phase {
        Stopped => TrayPresentation {
            status_text: "Status: Stopped",
            tooltip: "Church Cap — Stopped",
            open_enabled: false,
            restart_enabled: false,
            stop_enabled: true,
            stop_text: "Start Server",
        },
        Starting => TrayPresentation {
            status_text: "Status: Starting…",
            tooltip: "Church Cap — Starting",
            open_enabled: false,
            restart_enabled: false,
            stop_enabled: true,
            stop_text: "Stop Server",
        },
        Ready => TrayPresentation {
            status_text: if healthy {
                "Status: Ready"
            } else {
                "Status: Confirming health…"
            },
            tooltip: if healthy {
                "Church Cap — Ready"
            } else {
                "Church Cap — Confirming health"
            },
            open_enabled: healthy,
            restart_enabled: healthy,
            stop_enabled: true,
            stop_text: "Stop Server",
        },
        CaptionsLive => TrayPresentation {
            status_text: "Status: Captions live",
            tooltip: "Church Cap — Captions live",
            open_enabled: healthy,
            restart_enabled: true,
            stop_enabled: true,
            stop_text: "Stop Server…",
        },
        Stopping => TrayPresentation {
            status_text: "Status: Stopping…",
            tooltip: "Church Cap — Stopping",
            open_enabled: false,
            restart_enabled: false,
            stop_enabled: false,
            stop_text: "Stop Server",
        },
        Updating => TrayPresentation {
            status_text: "Status: Updating…",
            tooltip: "Church Cap — Updating",
            open_enabled: false,
            restart_enabled: false,
            stop_enabled: false,
            stop_text: "Stop Server",
        },
        RecoveryRequired => TrayPresentation {
            status_text: "Status: Needs attention",
            tooltip: "Church Cap — Needs attention",
            open_enabled: false,
            restart_enabled: false,
            stop_enabled: true,
            stop_text: "Start Server",
        },
        Error => TrayPresentation {
            status_text: "Status: Error",
            tooltip: "Church Cap — Error",
            open_enabled: false,
            restart_enabled: false,
            stop_enabled: true,
            stop_text: "Start Server",
        },
    }
}

pub fn install(app: &AppHandle) -> tauri::Result<()> {
    let status = MenuItem::with_id(app, "status", "Status: Stopped", false, None::<&str>)?;
    let open_operator =
        MenuItem::with_id(app, OPEN_OPERATOR, "Open Church Cap", false, None::<&str>)?;
    let show_controls =
        MenuItem::with_id(app, SHOW_CONTROLS, "Show Controls…", true, None::<&str>)?;
    let restart_engine =
        MenuItem::with_id(app, RESTART_ENGINE, "Restart Server", false, None::<&str>)?;
    let stop_engine = MenuItem::with_id(app, STOP_ENGINE, "Start Server", true, None::<&str>)?;
    let status_separator = PredefinedMenuItem::separator(app)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, QUIT, "Quit Church Cap", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &status,
            &status_separator,
            &open_operator,
            &show_controls,
            &restart_engine,
            &stop_engine,
            &separator,
            &quit,
        ],
    )?;

    #[cfg(target_os = "macos")]
    let icon = tauri::image::Image::from_bytes(include_bytes!("../icons/tray-template.png"))?;
    #[cfg(not(target_os = "macos"))]
    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or_else(|| tauri::Error::AssetNotFound("default window icon".into()))?;

    TrayIconBuilder::with_id(TRAY_ID)
        .icon(icon)
        .icon_as_template(cfg!(target_os = "macos"))
        .tooltip("Church Cap")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            OPEN_OPERATOR => {
                let _ = browser::open_route_internal(app, ChurchCapRoute::Operator);
            }
            SHOW_CONTROLS => {
                let _ = window::show_control_window(app);
            }
            RESTART_ENGINE => {
                let supervisor = app.state::<EngineSupervisor>();
                if supervisor.snapshot().captions_live {
                    let _ = window::show_control_window(app);
                } else {
                    let _ = lifecycle::restart_engine(app.clone(), supervisor, false);
                }
            }
            STOP_ENGINE => {
                let supervisor = app.state::<EngineSupervisor>();
                let snapshot = supervisor.snapshot();
                if snapshot.captions_live {
                    let _ = window::show_control_window(app);
                } else if snapshot.phase.engine_is_running() {
                    let _ = lifecycle::stop_engine(app.clone(), supervisor, false);
                } else {
                    let _ = lifecycle::start_engine(app.clone(), supervisor);
                }
            }
            QUIT => {
                let supervisor = app.state::<EngineSupervisor>();
                if supervisor.snapshot().captions_live {
                    let _ = window::show_control_window(app);
                } else {
                    lifecycle::quit_supervisor(app);
                }
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let _ = window::show_control_window(tray.app_handle());
            }
        })
        .build(app)?;
    app.manage(TrayControls {
        status,
        open_operator,
        restart_engine,
        stop_engine,
    });
    sync(app, &app.state::<EngineSupervisor>().snapshot());
    Ok(())
}

pub fn sync(app: &AppHandle, snapshot: &SupervisorSnapshot) {
    let app_handle = app.clone();
    let current = snapshot.clone();
    if let Err(error) = app.run_on_main_thread(move || {
        sync_on_main_thread(&app_handle, &current);
    }) {
        eprintln!("Church Cap could not schedule its native menu refresh: {error}");
    }
}

fn sync_on_main_thread(app: &AppHandle, snapshot: &SupervisorSnapshot) {
    let Some(controls) = app.try_state::<TrayControls>() else {
        return;
    };
    let state = presentation(snapshot);
    if let Err(error) = controls.status.set_text(state.status_text) {
        eprintln!("Church Cap could not refresh its menu status: {error}");
    }
    if let Err(error) = controls.open_operator.set_enabled(state.open_enabled) {
        eprintln!("Church Cap could not refresh its Open action: {error}");
    }
    if let Err(error) = controls.restart_engine.set_enabled(state.restart_enabled) {
        eprintln!("Church Cap could not refresh its Restart action: {error}");
    }
    if let Err(error) = controls.stop_engine.set_enabled(state.stop_enabled) {
        eprintln!("Church Cap could not refresh its Start/Stop action: {error}");
    }
    if let Err(error) = controls.stop_engine.set_text(state.stop_text) {
        eprintln!("Church Cap could not refresh its Start/Stop label: {error}");
    }
    if let Some(tray) = app.tray_by_id(TRAY_ID)
        && let Err(error) = tray.set_tooltip(Some(state.tooltip))
    {
        eprintln!("Church Cap could not refresh its menu-bar tooltip: {error}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tray_actions_follow_the_confirmed_shared_snapshot() {
        let mut snapshot = SupervisorSnapshot {
            phase: SupervisorPhase::Ready,
            ..SupervisorSnapshot::default()
        };
        let unconfirmed = presentation(&snapshot);
        assert!(!unconfirmed.open_enabled);
        assert!(!unconfirmed.restart_enabled);

        snapshot.health_confirmed = true;
        let ready = presentation(&snapshot);
        assert_eq!(ready.status_text, "Status: Ready");
        assert!(ready.open_enabled);
        assert!(ready.restart_enabled);

        snapshot.phase = SupervisorPhase::Stopped;
        snapshot.health_confirmed = false;
        let stopped = presentation(&snapshot);
        assert_eq!(stopped.stop_text, "Start Server");
        assert!(stopped.stop_enabled);
    }

    #[test]
    fn live_caption_actions_route_through_confirming_controls() {
        let snapshot = SupervisorSnapshot {
            phase: SupervisorPhase::CaptionsLive,
            captions_live: true,
            health_confirmed: true,
            ..SupervisorSnapshot::default()
        };
        let live = presentation(&snapshot);
        assert_eq!(live.status_text, "Status: Captions live");
        assert_eq!(live.stop_text, "Stop Server…");
        assert!(live.restart_enabled);
    }
}
