fn main() {
    // ARIA_ROOT — compile time'da proje dizinini embed et
    let aria_root = std::env::var("ARIA_ROOT_OVERRIDE").unwrap_or_else(|_| {
        let manifest = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        // src-tauri/ → frontend/ → ARIA/
        manifest
            .parent()
            .and_then(|p| p.parent())
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| "/tmp".to_string())
    });

    println!("cargo:rustc-env=ARIA_ROOT={}", aria_root);
    println!("cargo:rerun-if-env-changed=ARIA_ROOT_OVERRIDE");

    tauri_build::build()
}
