mod browser;
mod lifecycle;
mod model;
mod recovery;
mod startup;
mod tray;
mod updater;
mod window;
#[cfg(target_os = "windows")]
mod windows_job;

use lifecycle::EngineSupervisor;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        // Tauri requires the single-instance plugin to be registered first.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            let _ = window::show_control_window(app);
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(EngineSupervisor::new())
        .manage(updater::UpdateCoordinator::new())
        .invoke_handler(tauri::generate_handler![
            lifecycle::get_supervisor_status,
            lifecycle::start_engine,
            lifecycle::stop_engine,
            lifecycle::restart_engine,
            lifecycle::reset_operator_password,
            lifecycle::factory_reset_application,
            lifecycle::quit_application,
            startup::get_start_at_login,
            startup::set_start_at_login,
            browser::open_church_cap_route,
            updater::check_for_updates,
            updater::install_update,
            window::show_controls,
        ])
        .setup(|app| {
            if let Err(error) = tray::install(app.handle()) {
                eprintln!("CHURCH_CAP_TRAY=unavailable:{error}");
            }
            let _ = app
                .get_webview_window("control")
                .map(|window| window.center());
            lifecycle::start_on_launch(app.handle());
            #[cfg(debug_assertions)]
            lifecycle::run_self_test_if_requested(app.handle());
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "control"
                && let tauri::WindowEvent::CloseRequested { api, .. } = event
            {
                api.prevent_close();
                let _ = window.hide();
            }
        });

    let app = builder
        .build(tauri::generate_context!())
        .expect("Church Cap desktop supervisor failed to build");
    app.run(|app_handle, event| match event {
        tauri::RunEvent::Resumed => lifecycle::revalidate_after_resume(app_handle),
        #[cfg(target_os = "macos")]
        tauri::RunEvent::Reopen { .. } => {
            let _ = window::show_control_window(app_handle);
        }
        tauri::RunEvent::ExitRequested { api, .. } => {
            let supervisor = app_handle.state::<EngineSupervisor>();
            if !supervisor.exit_is_authorized() {
                api.prevent_exit();
                if supervisor.snapshot().captions_live {
                    let _ = window::show_control_window(app_handle);
                } else {
                    lifecycle::quit_supervisor(app_handle);
                }
            }
        }
        _ => {}
    });
}
