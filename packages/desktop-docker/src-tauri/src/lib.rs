//! DuckClaw Full Docker launcher (Windows).
//! Checks Docker Desktop, materializes compose+env, runs `docker compose up -d`,
//! waits for Gateway/Admin health, opens the system browser.

use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use rand::Rng;
use serde::Serialize;
use tauri::Manager;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

const DOCKER_DOWNLOAD_URL: &str = "https://www.docker.com/products/docker-desktop/";
const GATEWAY_HEALTH: &str = "http://127.0.0.1:8000/health";
const ADMIN_LOGIN: &str = "http://127.0.0.1:3001/login";
const HEALTH_TIMEOUT_SECS: u64 = 1200; // 20 min first-run image pulls

struct AppState {
    data_dir: PathBuf,
    last_status: Mutex<String>,
    credentials: Mutex<Option<Credentials>>,
}

#[derive(Clone, Serialize)]
struct Credentials {
    email: String,
    password: String,
    api_key: String,
}

#[derive(Serialize)]
struct StatusPayload {
    phase: String,
    detail: String,
    docker_ok: bool,
    ready: bool,
    credentials: Option<Credentials>,
    docker_download_url: String,
}

fn local_app_data_dir() -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));
    base.join("DuckClaw").join("full")
}

fn bundled_stack_dir(resource_dir: &Path) -> PathBuf {
    let nested = resource_dir.join("resources").join("stack");
    if nested.is_dir() {
        return nested;
    }
    let alt = resource_dir.join("stack");
    if alt.is_dir() {
        return alt;
    }
    resource_dir.to_path_buf()
}

fn random_secret(len: usize) -> String {
    const ALPHABET: &[u8] = b"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
    let mut rng = rand::thread_rng();
    (0..len)
        .map(|_| ALPHABET[rng.gen_range(0..ALPHABET.len())] as char)
        .collect()
}

fn docker_available() -> Result<(), String> {
    let mut cmd = Command::new("docker");
    cmd.args(["info"]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    match cmd.stdout(Stdio::null()).stderr(Stdio::null()).status() {
        Ok(st) if st.success() => Ok(()),
        Ok(_) => Err(
            "Docker Desktop está instalado pero no responde. Ábrelo y espera a que diga Running."
                .into(),
        ),
        Err(_) => Err(format!(
            "Docker Desktop no está instalado o no está en PATH. Descárgalo en {DOCKER_DOWNLOAD_URL}"
        )),
    }
}

fn ensure_stack_files(data_dir: &Path, resource_dir: &Path) -> Result<Credentials, String> {
    fs::create_dir_all(data_dir).map_err(|e| format!("No se pudo crear {data_dir:?}: {e}"))?;
    let bundled = bundled_stack_dir(resource_dir);
    let compose_src = bundled.join("docker-compose.yml");
    let env_src = bundled.join(".env.example");
    if !compose_src.is_file() {
        return Err(format!(
            "Falta docker-compose.yml embebido en {:?}",
            bundled
        ));
    }
    let compose_dst = data_dir.join("docker-compose.yml");
    // Always refresh compose from bundle (stack definition updates).
    fs::copy(&compose_src, &compose_dst)
        .map_err(|e| format!("No se pudo copiar compose: {e}"))?;

    let ts_src = bundled.join("tailscale-serve.json");
    if ts_src.is_file() {
        let _ = fs::copy(&ts_src, data_dir.join("tailscale-serve.json"));
    }

    let env_dst = data_dir.join(".env");
    let creds = if env_dst.is_file() {
        parse_credentials(&env_dst).unwrap_or_else(|| Credentials {
            email: "admin@duckclaw.local".into(),
            password: "(ver .env local)".into(),
            api_key: "(ver .env local)".into(),
        })
    } else {
        let template = fs::read_to_string(&env_src)
            .map_err(|e| format!("No se pudo leer .env.example: {e}"))?;
        let api_key = random_secret(32);
        let password = random_secret(16);
        let email = "admin@duckclaw.local".to_string();
        let filled = template
            .replace(
                "DUCKCLAW_ADMIN_API_KEY=change-me-local-admin-key",
                &format!("DUCKCLAW_ADMIN_API_KEY={api_key}"),
            )
            .replace(
                "DUCKCLAW_ADMIN_PASSWORD=change-me-min-8-chars",
                &format!("DUCKCLAW_ADMIN_PASSWORD={password}"),
            )
            .replace(
                "DUCKCLAW_ADMIN_EMAIL=admin@duckclaw.local",
                &format!("DUCKCLAW_ADMIN_EMAIL={email}"),
            );
        fs::write(&env_dst, filled).map_err(|e| format!("No se pudo escribir .env: {e}"))?;
        Credentials {
            email,
            password,
            api_key,
        }
    };
    Ok(creds)
}

fn parse_credentials(env_path: &Path) -> Option<Credentials> {
    let text = fs::read_to_string(env_path).ok()?;
    let mut email = None;
    let mut password = None;
    let mut api_key = None;
    for line in text.lines() {
        let line = line.trim();
        if line.starts_with('#') || !line.contains('=') {
            continue;
        }
        let (k, v) = line.split_once('=')?;
        match k.trim() {
            "DUCKCLAW_ADMIN_EMAIL" => email = Some(v.trim().to_string()),
            "DUCKCLAW_ADMIN_PASSWORD" => password = Some(v.trim().to_string()),
            "DUCKCLAW_ADMIN_API_KEY" => api_key = Some(v.trim().to_string()),
            _ => {}
        }
    }
    Some(Credentials {
        email: email?,
        password: password?,
        api_key: api_key?,
    })
}

fn compose_cmd(data_dir: &Path, args: &[&str]) -> Command {
    let mut cmd = Command::new("docker");
    let mut full = vec!["compose".to_string(), "-f".to_string()];
    full.push(
        data_dir
            .join("docker-compose.yml")
            .to_string_lossy()
            .into_owned(),
    );
    for a in args {
        full.push((*a).to_string());
    }
    cmd.args(&full);
    cmd.current_dir(data_dir);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

fn try_load_images_tar(data_dir: &Path) -> Option<String> {
    let candidates = [
        data_dir.join("duckclaw-full-images.tar"),
        data_dir.join("images").join("duckclaw-full-images.tar"),
    ];
    for tar in candidates {
        if !tar.is_file() {
            continue;
        }
        let mut cmd = Command::new("docker");
        cmd.args(["load", "-i"]).arg(&tar);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        match cmd.output() {
            Ok(out) if out.status.success() => {
                return Some(format!("Imágenes cargadas desde {}", tar.display()));
            }
            Ok(out) => {
                let err = String::from_utf8_lossy(&out.stderr);
                return Some(format!("docker load falló: {err}"));
            }
            Err(e) => return Some(format!("docker load error: {e}")),
        }
    }
    None
}

fn images_present() -> bool {
    for img in [
        "duckclaw/gateway:latest",
        "duckclaw/admin:latest",
        "duckclaw/sandbox:latest",
    ] {
        let mut cmd = Command::new("docker");
        cmd.args(["image", "inspect", img]);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        if !cmd
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
        {
            return false;
        }
    }
    true
}

fn compose_up(data_dir: &Path) -> Result<(), String> {
    if !images_present() {
        if let Some(msg) = try_load_images_tar(data_dir) {
            // continue after load attempt
            let _ = msg;
        }
        if !images_present() {
            return Err(
                "Faltan imágenes duckclaw/gateway, duckclaw/admin o duckclaw/sandbox. \
Coloca duckclaw-full-images.tar en la carpeta de datos o constrúyelas con \
scripts/build_desktop_docker.ps1 / docker compose build."
                    .into(),
            );
        }
    }
    let mut cmd = compose_cmd(data_dir, &["up", "-d"]);
    let out = cmd
        .output()
        .map_err(|e| format!("No se pudo ejecutar docker compose: {e}"))?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        let stdout = String::from_utf8_lossy(&out.stdout);
        return Err(format!(
            "docker compose up falló:\n{stderr}\n{stdout}"
        ));
    }
    Ok(())
}

fn compose_stop(data_dir: &Path) -> Result<(), String> {
    let mut cmd = compose_cmd(data_dir, &["stop"]);
    let out = cmd
        .output()
        .map_err(|e| format!("No se pudo ejecutar docker compose stop: {e}"))?;
    if !out.status.success() {
        let stderr = String::from_utf8_lossy(&out.stderr);
        return Err(format!("docker compose stop falló:\n{stderr}"));
    }
    Ok(())
}

fn http_ok(url: &str) -> bool {
    // Minimal HTTP GET without extra crates
    let Some(rest) = url.strip_prefix("http://") else {
        return false;
    };
    let (host_port, path) = rest.split_once('/').unwrap_or((rest, ""));
    let path = if path.is_empty() {
        "/".to_string()
    } else {
        format!("/{path}")
    };
    let (host, port) = if let Some((h, p)) = host_port.split_once(':') {
        (h, p.parse::<u16>().unwrap_or(80))
    } else {
        (host_port, 80)
    };
    let Ok(mut stream) = TcpStream::connect((host, port)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(3)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(3)));
    let req = format!(
        "GET {path} HTTP/1.1\r\nHost: {host_port}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 128];
    match stream.read(&mut buf) {
        Ok(n) if n > 0 => {
            let s = String::from_utf8_lossy(&buf[..n]);
            s.contains(" 200 ") || s.contains(" 302 ") || s.contains(" 307 ") || s.contains(" 304 ")
        }
        _ => false,
    }
}

fn open_browser(url: &str) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let status = Command::new("cmd")
            .args(["/C", "start", "", url])
            .creation_flags(CREATE_NO_WINDOW)
            .status()
            .map_err(|e| format!("No se pudo abrir el navegador: {e}"))?;
        if status.success() {
            return Ok(());
        }
        return Err("Falló al abrir el navegador".into());
    }
    #[cfg(not(windows))]
    {
        let _ = Command::new("xdg-open").arg(url).status();
        Ok(())
    }
}

fn set_status(state: &AppState, msg: &str) {
    if let Ok(mut g) = state.last_status.lock() {
        *g = msg.to_string();
    }
}

#[tauri::command]
fn get_status(state: tauri::State<'_, AppState>) -> StatusPayload {
    let detail = state
        .last_status
        .lock()
        .map(|g| g.clone())
        .unwrap_or_default();
    let docker_ok = docker_available().is_ok();
    let ready = http_ok(GATEWAY_HEALTH) && http_ok(ADMIN_LOGIN);
    let credentials = state.credentials.lock().ok().and_then(|g| g.clone());
    StatusPayload {
        phase: if ready {
            "ready".into()
        } else if docker_ok {
            "starting".into()
        } else {
            "need_docker".into()
        },
        detail,
        docker_ok,
        ready,
        credentials,
        docker_download_url: DOCKER_DOWNLOAD_URL.into(),
    }
}

#[tauri::command]
fn open_docker_download() -> Result<(), String> {
    open_browser(DOCKER_DOWNLOAD_URL)
}

#[tauri::command]
fn open_admin() -> Result<(), String> {
    open_browser(ADMIN_LOGIN)
}

#[tauri::command]
fn stop_stack(state: tauri::State<'_, AppState>) -> Result<(), String> {
    set_status(&state, "Deteniendo stack…");
    compose_stop(&state.data_dir)?;
    set_status(&state, "Stack detenido.");
    Ok(())
}

#[tauri::command]
fn start_stack(app: tauri::AppHandle, state: tauri::State<'_, AppState>) -> Result<(), String> {
    let data_dir = state.data_dir.clone();
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))?;

    set_status(&state, "Comprobando Docker Desktop…");
    docker_available()?;

    set_status(&state, "Preparando compose y .env…");
    let creds = ensure_stack_files(&data_dir, &resource_dir)?;
    if let Ok(mut g) = state.credentials.lock() {
        *g = Some(creds);
    }

    set_status(
        &state,
        "Levantando stack (primera vez puede tardar varios minutos descargando imágenes)…",
    );
    let data_dir_bg = data_dir.clone();
    let app_bg = app.clone();
    std::thread::spawn(move || {
        let state = app_bg.state::<AppState>();
        if let Err(e) = compose_up(&data_dir_bg) {
            set_status(&state, &e);
            return;
        }
        set_status(
            &state,
            "Esperando healthcheck del Gateway y Admin…",
        );
        let deadline = Instant::now() + Duration::from_secs(HEALTH_TIMEOUT_SECS);
        let mut n = 0u32;
        while Instant::now() < deadline {
            n += 1;
            let gw = http_ok(GATEWAY_HEALTH);
            let adm = http_ok(ADMIN_LOGIN);
            if gw && adm {
                set_status(&state, "Listo. Abriendo Admin…");
                let _ = open_browser(ADMIN_LOGIN);
                return;
            }
            set_status(
                &state,
                &format!(
                    "Esperando servicios… ({n}) gateway={} admin={}",
                    if gw { "ok" } else { "…" },
                    if adm { "ok" } else { "…" }
                ),
            );
            std::thread::sleep(Duration::from_secs(2));
        }
        set_status(
            &state,
            "Timeout esperando health. Revisa Docker Desktop → Containers (duckclaw-full).",
        );
    });
    Ok(())
}

pub fn run() {
    let data_dir = local_app_data_dir();
    tauri::Builder::default()
        .manage(AppState {
            data_dir,
            last_status: Mutex::new("Listo para iniciar.".into()),
            credentials: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            get_status,
            start_stack,
            stop_stack,
            open_admin,
            open_docker_download
        ])
        .run(tauri::generate_context!())
        .expect("error while running DuckClaw Full launcher");
}
