// 58:12 Connect — Tauri desktop entry point.
//
// Lifecycle on launch:
//   1. Resolve the bundled resource directory (where backend/, mongo/, cloudflared/ live).
//   2. Spawn portable MongoDB (mongod --dbpath ${app_data_dir}/mongo-data --port 27017 --bind_ip 127.0.0.1).
//   3. Spawn the bundled FastAPI backend (PyInstaller-built `backend` binary listening on :8001).
//   4. (Optional) Start a Cloudflare Named Tunnel using a config file the user pastes via Settings.
//   5. Open the Tauri window pointing at http://127.0.0.1:8001/.
//
// Lifecycle on quit:
//   • Kill child processes in reverse order (cloudflared → backend → mongod).
//
// This is a SCAFFOLD — the actual binaries are dropped into desktop/resources/ at build time
// by the bundling script. To produce a working installer:
//   1. PyInstaller-build the backend on the target OS:    pyinstaller backend/server.py
//   2. Drop a portable MongoDB binary into resources/mongo/    (mongo-server-{platform})
//   3. Drop the cloudflared binary into resources/cloudflared/ (cloudflared-{platform})
//   4. Run `cargo tauri build` on the target OS.

use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use once_cell::sync::Lazy;
use tauri::{Manager, RunEvent};

static MONGO_PROC: Lazy<Mutex<Option<Child>>> = Lazy::new(|| Mutex::new(None));
static BACKEND_PROC: Lazy<Mutex<Option<Child>>> = Lazy::new(|| Mutex::new(None));
static CFLARED_PROC: Lazy<Mutex<Option<Child>>> = Lazy::new(|| Mutex::new(None));

#[derive(serde::Serialize)]
struct ServiceStatus {
    mongo: bool,
    backend: bool,
    cloudflared: bool,
    backend_url: String,
}

#[tauri::command]
fn services_status() -> ServiceStatus {
    let mongo = MONGO_PROC.lock().unwrap().as_mut().map(|c| c.try_wait().ok().flatten().is_none()).unwrap_or(false);
    let backend = BACKEND_PROC.lock().unwrap().as_mut().map(|c| c.try_wait().ok().flatten().is_none()).unwrap_or(false);
    let cloudflared = CFLARED_PROC.lock().unwrap().as_mut().map(|c| c.try_wait().ok().flatten().is_none()).unwrap_or(false);
    ServiceStatus {
        mongo,
        backend,
        cloudflared,
        backend_url: "http://127.0.0.1:8001".to_string(),
    }
}

#[tauri::command]
fn start_cloudflare_tunnel(config_yaml: String, app: tauri::AppHandle) -> Result<String, String> {
    // Persist the user-provided cloudflared config to ${app_data_dir}/cloudflared/config.yml
    let app_data = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let cfg_dir = app_data.join("cloudflared");
    std::fs::create_dir_all(&cfg_dir).map_err(|e| e.to_string())?;
    let cfg_path = cfg_dir.join("config.yml");
    std::fs::write(&cfg_path, config_yaml).map_err(|e| e.to_string())?;

    // Stop the existing tunnel if running so the new config takes effect.
    if let Some(mut p) = CFLARED_PROC.lock().unwrap().take() {
        let _ = p.kill();
    }

    let cflared_bin = resource_path(&app, "cloudflared/cloudflared")
        .ok_or("cloudflared binary missing — bundle resources/cloudflared/")?;
    let child = Command::new(cflared_bin)
        .args(["tunnel", "--config"])
        .arg(cfg_path)
        .arg("run")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("Failed to start cloudflared: {e}"))?;
    *CFLARED_PROC.lock().unwrap() = Some(child);
    Ok("Cloudflare Tunnel started".into())
}

#[tauri::command]
fn stop_cloudflare_tunnel() -> Result<(), String> {
    if let Some(mut p) = CFLARED_PROC.lock().unwrap().take() {
        p.kill().map_err(|e| e.to_string())?;
    }
    Ok(())
}

fn resource_path(app: &tauri::AppHandle, rel: &str) -> Option<std::path::PathBuf> {
    app.path().resource_dir().ok().map(|d| d.join(rel))
}

fn spawn_mongo(app: &tauri::AppHandle) -> std::io::Result<Child> {
    let app_data = app.path().app_data_dir().expect("app data dir");
    let dbpath = app_data.join("mongo-data");
    std::fs::create_dir_all(&dbpath)?;
    let mongo_bin = resource_path(app, "mongo/mongod").expect("portable mongod missing");
    Command::new(mongo_bin)
        .args(["--dbpath"])
        .arg(&dbpath)
        .args(["--bind_ip", "127.0.0.1", "--port", "27017", "--quiet"])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
}

fn spawn_backend(app: &tauri::AppHandle) -> std::io::Result<Child> {
    let backend_bin = resource_path(app, "backend/server").expect("backend bundle missing");
    let app_data = app.path().app_data_dir().expect("app data dir");
    let uploads = app_data.join("uploads");
    std::fs::create_dir_all(&uploads)?;
    Command::new(backend_bin)
        .env("MONGO_URL", "mongodb://127.0.0.1:27017")
        .env("DB_NAME", "5812_desktop")
        .env("UPLOADS_DIR", uploads)
        .env("HOST", "127.0.0.1")
        .env("PORT", "8001")
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
}

async fn wait_for_backend() {
    let client = reqwest::Client::new();
    for _ in 0..40 {
        if let Ok(r) = client.get("http://127.0.0.1:8001/api/health").send().await {
            if r.status().is_success() {
                return;
            }
        }
        tokio::time::sleep(Duration::from_millis(500)).await;
    }
    log::warn!("Backend did not respond to /api/health within 20s; opening window anyway");
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    env_logger::init();
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            services_status,
            start_cloudflare_tunnel,
            stop_cloudflare_tunnel
        ])
        .setup(|app| {
            let handle = app.handle().clone();
            // Mongo first (backend depends on it)
            match spawn_mongo(&handle) {
                Ok(c) => *MONGO_PROC.lock().unwrap() = Some(c),
                Err(e) => log::error!("Failed to spawn mongod: {e}"),
            }
            // Backend
            match spawn_backend(&handle) {
                Ok(c) => *BACKEND_PROC.lock().unwrap() = Some(c),
                Err(e) => log::error!("Failed to spawn backend: {e}"),
            }
            // Wait for backend health, then proceed.
            let handle2 = handle.clone();
            tauri::async_runtime::spawn(async move {
                wait_for_backend().await;
                if let Some(window) = handle2.get_webview_window("main") {
                    let _ = window.eval("window.location.reload();");
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while running tauri application")
        .run(|_app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // Kill children in reverse order so the backend gets a chance to flush.
                if let Some(mut p) = CFLARED_PROC.lock().unwrap().take() {
                    let _ = p.kill();
                }
                if let Some(mut p) = BACKEND_PROC.lock().unwrap().take() {
                    let _ = p.kill();
                }
                if let Some(mut p) = MONGO_PROC.lock().unwrap().take() {
                    let _ = p.kill();
                }
            }
        });
}
