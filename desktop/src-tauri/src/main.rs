// Tauri desktop binary entry — defers all logic to lib.rs so unit tests can target it.
fn main() {
    app_lib::run();
}
