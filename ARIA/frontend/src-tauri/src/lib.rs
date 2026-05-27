use std::net::TcpStream;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;

// Backend process handle — global, app kapanınca kill edilir
static BACKEND: Mutex<Option<Child>> = Mutex::new(None);

/// ARIA dizinini bul — executable'ın yanındaki resources veya geliştirme yolu
fn aria_root() -> PathBuf {
    // Build: .app/Contents/Resources/aria içinde
    if let Ok(exe) = std::env::current_exe() {
        let resources = exe
            .parent().unwrap_or(&exe)
            .parent().unwrap_or(&exe)
            .join("Resources/aria");
        if resources.exists() {
            return resources;
        }
    }
    // Dev: proje dizini
    PathBuf::from(env!("ARIA_ROOT"))
}

/// Port 8000'in açık olup olmadığını kontrol et
fn api_ready() -> bool {
    TcpStream::connect("127.0.0.1:8000").is_ok()
}

/// Python API'yi başlat
fn start_api() {
    if api_ready() {
        log::info!("ARIA API zaten çalışıyor");
        return;
    }

    let root = aria_root();
    let uvicorn = root.join(".venv/bin/uvicorn");
    let pythonpath = root.join("src");

    log::info!("ARIA API başlatılıyor: {:?}", root);

    match Command::new(&uvicorn)
        .arg("ARIA.api:app")
        .arg("--host").arg("0.0.0.0")
        .arg("--port").arg("8000")
        .env("PYTHONPATH", &pythonpath)
        .current_dir(&root)
        .spawn()
    {
        Ok(child) => {
            *BACKEND.lock().unwrap() = Some(child);
            log::info!("API process başlatıldı, hazır olması bekleniyor...");

            // API'nin hazır olmasını bekle (max 30sn)
            for _ in 0..60 {
                if api_ready() {
                    log::info!("✅ ARIA API hazır");
                    return;
                }
                thread::sleep(Duration::from_millis(500));
            }
            log::warn!("API 30sn içinde yanıt vermedi");
        }
        Err(e) => {
            log::error!("API başlatılamadı: {}", e);
        }
    }
}

/// Backend process'i durdur
fn stop_api() {
    if let Ok(mut guard) = BACKEND.lock() {
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            log::info!("ARIA API durduruldu");
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // API'yi arka planda başlat
    thread::spawn(start_api);

    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build())
        .setup(|_app| {
            Ok(())
        })
        .on_window_event(|_window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                stop_api();
            }
        })
        .run(tauri::generate_context!())
        .expect("ARIA başlatılamadı");
}
