use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
#[cfg(not(debug_assertions))]
use tauri_plugin_shell::ShellExt;

struct DesktopState(Mutex<DesktopProcesses>);

struct DesktopProcesses {
    backend: Option<CommandChild>,
    admin: Option<Child>,
}

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn bundled_resources_dir(resource_dir: &Path) -> PathBuf {
    let nested = resource_dir.join("resources");
    if nested.is_dir() {
        return nested;
    }
    resource_dir.to_path_buf()
}

fn wait_port(host: &str, port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    let addr = format!("{host}:{port}");
    while Instant::now() < deadline {
        if std::net::TcpStream::connect(&addr).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

fn navigate_to_login(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.eval("window.location.replace('http://127.0.0.1:3000/login')");
    }
}

fn watch_and_open_login(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        let backend_up = wait_port("127.0.0.1", 8000, Duration::from_secs(180));
        let admin_up = wait_port("127.0.0.1", 3000, Duration::from_secs(180));
        if backend_up && admin_up {
            let handle = app.clone();
            let _ = app.run_on_main_thread(move || navigate_to_login(&handle));
        }
    });
}

fn parse_env_file(path: &Path) -> HashMap<String, String> {
    let mut out = HashMap::new();
    let Ok(content) = std::fs::read_to_string(path) else {
        return out;
    };
    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((key, val)) = line.split_once('=') {
            let val = val.trim().trim_matches('"').trim_matches('\'');
            out.insert(key.trim().to_string(), val.to_string());
        }
    }
    out
}

fn desktop_env_path() -> Option<PathBuf> {
    std::env::var("LOCALAPPDATA")
        .ok()
        .map(|p| PathBuf::from(p).join("DuckClaw").join("desktop.env"))
}

fn read_desktop_env(timeout: Duration) -> HashMap<String, String> {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Some(path) = desktop_env_path() {
            if path.is_file() {
                let env = parse_env_file(&path);
                if env.get("DUCKCLAW_ADMIN_API_KEY").is_some() {
                    return env;
                }
            }
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    HashMap::new()
}

fn admin_server_entry(admin_ui_dir: &Path) -> PathBuf {
    let entry = std::fs::read_to_string(admin_ui_dir.join("SERVER_ENTRY"))
        .unwrap_or_else(|_| "server.js".to_string());
    admin_ui_dir.join(entry.trim())
}

fn write_admin_runtime_env(admin_ui_dir: &Path, env: &HashMap<String, String>) {
    let path = admin_ui_dir.join(".env.local");
    let mut body = String::from("# DuckClaw desktop runtime env (auto)\n");
    body.push_str("LITE_MODE=1\n");
    body.push_str("DUCKCLAW_SPAWN_PROFILE=1\n");
    body.push_str("DUCKCLAW_DISABLE_DOTENV=1\n");
    body.push_str("NEXT_PUBLIC_DUCKCLAW_DESKTOP=1\n");
    body.push_str("DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000\n");
    for (key, val) in env {
        if key.starts_with("DUCKCLAW_") || key.starts_with("OPENROUTER_") {
            body.push_str(key);
            body.push('=');
            body.push_str(val);
            body.push('\n');
        }
    }
    let _ = std::fs::write(path, body);
}

#[cfg(windows)]
fn try_free_port(port: u16) {
    let script = format!(
        "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
    );
    let _ = Command::new("powershell")
        .args(["-NoProfile", "-NonInteractive", "-Command", &script])
        .status();
}

#[cfg(not(windows))]
fn try_free_port(_port: u16) {}

fn dev_sidecar_enabled() -> bool {
    matches!(
        std::env::var("DUCKCLAW_DESKTOP_DEV_SIDECAR").ok().as_deref(),
        Some("1") | Some("true") | Some("yes")
    )
}

fn kill_desktop_processes(state: &DesktopState) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(mut child) = guard.admin.take() {
            let _ = child.kill();
        }
        if let Some(child) = guard.backend.take() {
            let _ = child.kill();
        }
    }
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/F", "/IM", "duckclaw_backend.exe"])
            .status();
        try_free_port(3000);
    }
}

#[tauri::command]
fn prepare_for_update(state: tauri::State<'_, DesktopState>) -> Result<(), String> {
    kill_desktop_processes(&state);
    Ok(())
}

fn spawn_admin(
    node_exe: &Path,
    admin_ui_dir: &Path,
    env: &HashMap<String, String>,
) -> Result<Child, String> {
    let server_js = admin_server_entry(admin_ui_dir);
    if !node_exe.is_file() {
        return Err(format!("missing node.exe: {}", node_exe.display()));
    }
    if !server_js.is_file() {
        return Err(format!("missing admin server: {}", server_js.display()));
    }

    #[cfg(windows)]
    try_free_port(3000);

    write_admin_runtime_env(admin_ui_dir, env);

    let mut cmd = Command::new(node_exe);
    cmd.arg(&server_js)
        .current_dir(admin_ui_dir)
        .env("PORT", "3000")
        .env("HOSTNAME", "127.0.0.1")
        .env("NODE_ENV", "production")
        .env("DUCKCLAW_GATEWAY_URL", "http://127.0.0.1:8000");

    for (key, val) in env {
        if key.starts_with("DUCKCLAW_") || key.starts_with("OPENROUTER_") {
            cmd.env(key, val);
        }
    }

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    cmd.spawn().map_err(|e| e.to_string())
}

#[cfg(not(debug_assertions))]
fn spawn_backend(app: &tauri::AppHandle, desktop_env: &HashMap<String, String>) -> Result<CommandChild, String> {
    // ponytail: dev hot-reload only; production uses bundled sidecar (updater replaces install dir).
    if dev_sidecar_enabled() {
        if let Ok(local) = std::env::var("LOCALAPPDATA") {
            let exe = PathBuf::from(local).join("DuckClaw").join("duckclaw_backend.exe");
            if exe.is_file() {
                let mut cmd = app.shell().command(&exe);
                cmd = cmd
                    .env("LITE_MODE", "1")
                    .env("DUCKCLAW_SPAWN_PROFILE", "1")
                    .env("DUCKCLAW_DISABLE_DOTENV", "1");
                for (key, val) in desktop_env {
                    if key.starts_with("DUCKCLAW_") || key.starts_with("OPENROUTER_") {
                        cmd = cmd.env(key, val);
                    }
                }
                let (_rx, child) = cmd.spawn().map_err(|e| e.to_string())?;
                return Ok(child);
            }
        }
    }

    let sidecar = app
        .shell()
        .sidecar("duckclaw_backend")
        .map_err(|e| e.to_string())?;
    let (_rx, child) = sidecar.spawn().map_err(|e| e.to_string())?;
    Ok(child)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(DesktopState(Mutex::new(DesktopProcesses {
            backend: None,
            admin: None,
        })))
        .invoke_handler(tauri::generate_handler![prepare_for_update]);

    #[cfg(not(any(target_os = "android", target_os = "ios")))]
    {
        builder = builder
            .plugin(tauri_plugin_updater::Builder::new().build())
            .plugin(tauri_plugin_process::init());
    }

    builder
        .setup(|app| {
            #[cfg(debug_assertions)]
            {
                let _ = app;
                return Ok(());
            }
            #[cfg(not(debug_assertions))]
            {
                let desktop_env = read_desktop_env(Duration::from_secs(30));
                let backend_child = spawn_backend(app.handle(), &desktop_env)?;

                if !wait_port("127.0.0.1", 8000, Duration::from_secs(120)) {
                    eprintln!("duckclaw_backend did not open port 8000 in time");
                }
                let resource_dir = app.path().resource_dir().map_err(|e| e.to_string())?;
                let bundled = bundled_resources_dir(&resource_dir);
                let node_exe = bundled.join("node").join("node.exe");
                let admin_ui_dir = bundled.join("admin-ui");

                let admin_child = match spawn_admin(&node_exe, &admin_ui_dir, &desktop_env) {
                    Ok(child) => Some(child),
                    Err(err) => {
                        eprintln!("admin server spawn failed: {err}");
                        None
                    }
                };

                if let Some(state) = app.try_state::<DesktopState>() {
                    let mut guard = state.0.lock().unwrap();
                    guard.backend = Some(backend_child);
                    guard.admin = admin_child;
                }
                watch_and_open_login(app.handle().clone());
                Ok(())
            }
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<DesktopState>() {
                    kill_desktop_processes(&state);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running DuckClaw desktop");
}
