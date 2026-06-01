# Releasing a desktop build

The desktop bundle is built by GitHub Actions on every git tag matching `v*`.
You don't need a Mac or a Windows box yourself — GitHub's runners do the work.

## TL;DR: cut a release

```bash
# From the repo root, on the branch you want to ship
git tag -a v0.1.0 -m "First desktop release"
git push origin v0.1.0
```

That triggers `.github/workflows/desktop-release.yml`. ~15 minutes later you'll
have a **draft release** on the GitHub repo's *Releases* page with:

- `5812-Connect_0.1.0_x64_en-US.msi`         (Windows installer)
- `5812-Connect_0.1.0_x64-setup.exe`         (Windows NSIS installer)
- `5812-Connect_0.1.0_aarch64.dmg`           (macOS installer)
- `5812-Connect_0.1.0_amd64.deb`             (Debian / Ubuntu)
- `5812-Connect_0.1.0_amd64.AppImage`        (Linux universal)
- `latest.json`                              (auto-updater manifest)

Smoke-test on one box, then click **Publish release** in the GitHub UI to make
it public.

## Manual run (no tag)

The workflow also accepts `workflow_dispatch`. From the GitHub Actions tab →
**Desktop Release** → **Run workflow** → optional release tag input. Useful for
testing the pipeline without polluting your tag history.

## What runs in CI

For each platform (macOS, Ubuntu, Windows):

1. Checks out the repo.
2. Installs Rust, Node 20, Python 3.11.
3. Linux: installs `libwebkit2gtk-4.1-dev` + GTK / appindicator dev headers.
4. PyInstaller-bundles `backend/server.py` → `desktop/resources/backend/server[.exe]`.
5. `yarn build`s the React frontend → `desktop/dist/`.
6. Downloads a portable `mongod` for the matching platform.
7. Downloads a `cloudflared` binary for the matching platform.
8. `tauri-apps/tauri-action@v0` runs `cargo tauri build`, packages the installers, signs them if secrets are configured, and uploads them as draft-release assets.

Total runtime ≈ 12 min on Linux, ≈ 14 min on macOS, ≈ 18 min on Windows (cold).
The Rust cache (`swatinem/rust-cache@v2`) cuts subsequent builds to ≈ 4-6 min.

## Code-signing — set these GitHub repo secrets

Without these, builds are unsigned (Gatekeeper / SmartScreen will warn end users
on first launch, but they can still install via *More info → Run anyway*).

### macOS (Apple Developer ID)

| Secret | What it is |
|---|---|
| `APPLE_SIGNING_IDENTITY` | e.g. `"Developer ID Application: 58:12 Global Inc (XXXXXXXXXX)"` |
| `APPLE_CERTIFICATE` | Base64-encoded `.p12` cert export (`base64 < cert.p12 | pbcopy`) |
| `APPLE_CERTIFICATE_PASSWORD` | Password used when exporting the `.p12` |
| `APPLE_ID` | Apple ID email used for notarisation |
| `APPLE_PASSWORD` | App-specific password from appleid.apple.com |
| `APPLE_TEAM_ID` | 10-char team ID from developer.apple.com |

### Windows (EV code-signing cert)

| Secret | What it is |
|---|---|
| `WINDOWS_CERT_THUMBPRINT` | SHA1 thumbprint of your EV cert in the GitHub-runner's cert store. The runner pre-installs common roots, but you'll need to side-load the cert via the action — see [tauri-action docs](https://github.com/tauri-apps/tauri-action) for the recipe. |

### Auto-updater signing

Both Apple + Windows signing protect the *installer*. The Tauri auto-updater
plugin separately signs each *update artifact* with its own keypair (so the
running app refuses to install a tampered update).

| Secret | What it is |
|---|---|
| `TAURI_SIGNING_PRIVATE_KEY` | Contents of the file produced by `cargo tauri signer generate ~/.tauri/5812.key` |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | The password you set when generating it |

Then in `desktop/src-tauri/tauri.conf.json`:

1. Paste the matching public key (`~/.tauri/5812.key.pub`) into
   `plugins.updater.pubkey`.
2. Flip `plugins.updater.active` to `true`.
3. Update `plugins.updater.endpoints` to your real release-server URL.

## After a release — point users at the download

The "download link" is just the GitHub Releases URL once you publish:

- `https://github.com/<your-org>/<your-repo>/releases/latest` — always
  resolves to the latest published (non-draft, non-prerelease) build.
- `https://github.com/<your-org>/<your-repo>/releases/tag/v0.1.0` — a
  specific version.

Drop those URLs into your WordPress site, a `/downloads` page on the cloud
deployment, or hand them to partner orgs directly.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Workflow fails on Linux with `libwebkit2gtk-4.1-dev: package not found` | Ubuntu version drift — the step uses 22.04. Upgrade `runs-on:` or add the universe repo. |
| macOS DMG build hangs at "Signing app bundle" | `APPLE_CERTIFICATE_PASSWORD` doesn't match the `.p12` export password. Re-export. |
| Windows MSI build fails with `wix: command not found` | The runner image dropped WiX. Add `- uses: johnwason/vcvarsall-action@v0.11` + `choco install -y wixtoolset` ahead of the tauri-action step. |
| Auto-updater can't verify a release | The pubkey in `tauri.conf.json` doesn't match the signing key in CI. Regenerate the keypair, paste the pub side, re-tag. |
| Builds succeed but installers are 0 bytes | `tauri-action` couldn't find the `frontendDist`. Confirm `desktop/dist/index.html` exists in the build job logs (step "Build frontend"). |
