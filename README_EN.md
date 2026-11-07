# Hush Photo

**Export iPhone photos and videos to Windows without cloud transfers**

[Русский](README.md) · [English](README_EN.md) · [简体中文](README_ZH.md)

Hush Photo is a free, open-source application for transferring media from an iPhone to a Windows 10/11 (x64) computer. It reads accessible files over USB using Apple File Conduit (AFC), provides a searchable media browser, preserves original files, and supports repeat exports after an interrupted transfer.

You can also process photos and videos from a local folder. **Hush Photo is not a complete iPhone backup solution.**

**Interface examples:** [iPhone connection, media browser, and export options](docs/INTERFACE.md) (illustrative screenshots with synthetic media).

## Features

- **Photos and videos:** export HEIC, HEIF, JPEG, PNG, TIFF, DNG, MOV, and MP4. Videos are copied without transcoding. The AFC scanner can detect AAE sidecars, but the picker does not offer them for separate export.
- **Live Photos:** preserve a still image and its paired MOV when both share the same name and directory. Pairing does not use Apple's internal asset identifiers.
- **Automatic USB discovery:** scan automatically when a connected iPhone is detected; manual scanning remains available when device discovery tools are unavailable.
- **Media browser:** on-demand photo thumbnails while scrolling, filename search, 36-item pages, and separate photo/video selection.
- **Video filters:** All videos, Video clips, and Live Photos. Only selected items from the active filter are exported; selections in other categories are retained.
- **Reliable repeat exports:** verified copies can be skipped, name collisions are resolved safely, and operations can be canceled.
- **Organization:** preserve the DCIM layout, use a single destination folder, or organize by capture month when metadata allows.
- **Windows interface:** system light/dark appearance, connection status, transfer progress, throughput, and estimated remaining time.

## Requirements

| Component | Requirement |
| --- | --- |
| Operating system | Windows 10/11, x64 |
| iPhone | Unlocked, with computer trust approved |
| USB access | Apple Mobile Device Support and a compatible Windows build of libimobiledevice |
| Source installation | Python 3.11 x64 recommended; packages in `requirements.txt` |
| Portable package | The complete `HushPhoto` folder from the generated archive; Python is not required on the target PC |

**USB export prerequisite:** Apple Mobile Device Support and a compatible Windows build of libimobiledevice are required. See [Configure USB tools](#configure-usb-tools) below for supported ways to locate the installed utilities and libraries.

Install Apple Devices on Windows, or another official Apple component providing Apple Mobile Device Support. Drivers and third-party USB tools can affect device access.

### Configure USB tools

USB media access requires `afcclient.exe` and matching DLL dependencies from the **same** libimobiledevice distribution. `idevice_id.exe` is recommended for automatic device detection.

Choose one location:

1. **Bundled tools:** place the binaries under `native` beside `HushPhoto.exe` (portable), or beside `iphone_usb.py` (running from source).
2. **Environment variable:** point `HUSH_AFC_TOOLS` to the directory containing the utilities:
   `$env:HUSH_AFC_TOOLS = 'D:\Tools\libimobiledevice'`
3. **System PATH:** add the tools directory to `PATH` and restart Hush Photo.

Supply a **directory**, not the full path to an executable. To verify the utilities in PowerShell:

```powershell
.\idevice_id.exe -l
.\afcclient.exe ls /DCIM
```

The first command should list the connected device ID; the second should show its accessible DCIM contents. When automatic detection is unavailable, use the application's manual connection check.

## Using Hush Photo

1. Connect the iPhone via USB, unlock it, and select **Trust** when prompted. Hush Photo checks for the device in the background and starts scanning automatically. You can also check the connection manually or use **Refresh** to rescan.
2. Select **Photos** or **Videos**. Video filters distinguish All videos, Video clips, and Live Photos. Search by filename; thumbnails of photos are fetched automatically while scrolling or changing pages.
3. Select the files to export. **Select all** and **Clear selection** affect the current search results without clearing hidden selections. The selection count appears beneath the Media Library heading.
4. Choose the destination folder and click **Export**. Review the export options, then click **Start export**.
5. Progress, the current file, speed, approximate ETA, and cancel controls are available during the operation. The scanned library remains available afterward unless the USB connection has been lost.

To process existing files on your PC, switch the source from **iPhone** to **Folder**. Source and destination directories must not overlap.

### Export options

| Mode | Output |
| --- | --- |
| **Originals** (default) | Source files without recompression or format conversion |
| **Originals + JPEG** | Original photos and additional JPEG compatibility copies |
| **JPEG** | JPEG derivatives; **USB exports also retain the originals** |
| **TIFF** | TIFF derivatives; **USB exports also retain the originals** |
| **Videos** | MOV and MP4 files copied without transcoding |

JPEG quality is adjustable from 85 to 100 (default: 97). JPEG compression is lossy; full HDR-to-SDR tone mapping is not provided. Keep originals for archival purposes.

The **Keep Live Photo motion (MOV)** option includes a same-name MOV from the same directory when exporting its still photo. It does not affect explicitly selected video-only exports.

**Destination structure:**
- **By year and month:** `YYYY-MM` based on available capture metadata; items without a reliable date go into `Без даты` (No date).
- **Original structure:** preserve the relative source path, including DCIM for USB exports.
- **Single folder:** place files in the selected destination; handle identical filenames without overwriting unrelated content.

## Data integrity and storage

Hush Photo does not modify files on the iPhone. Files are staged before being published to their final locations, preventing an interrupted download from replacing an existing export.

For **USB exports**, `.hushphoto-manifest.json` and `hushphoto_last_export.json` are stored in the destination directory. Repeat exports validate the locally stored size and SHA-256 digest before skipping an existing copy. This is **not** an independent comparison against an on-device iPhone checksum.

For **local-folder exports**, Hush Photo compares SHA-256 hashes to avoid duplicate content and writes `export_report.txt`.

Photo thumbnails are generated locally and cached temporarily at `%LOCALAPPDATA%\HushPhoto\previews`. They load in small batches for visible items and are cleared on normal application exit. Files left behind by a crash are cleaned at the next start, including temporary downloaded originals. **Cache cleanup never removes exported media.**

## Known limitations

- AFC may expose only part of the Photos library. iCloud-only items might not be stored on the device. DCIM file counts can differ from the number of items shown in Apple's Photos app.
- AFC cannot reliably identify the **Recently Deleted** album. Hush Photo does not delete files from the iPhone and cannot guarantee that this album is excluded.
- Live Photo MOV classification is based on filenames and directories and may be imperfect.
- Video previews are represented by file-type cards; video-frame thumbnails are not generated.
- After a physical USB disconnection, a new scan is required. Resume behavior skips completed and validated files; it does not continue a partially written file from the exact interrupted byte.
- The portable build does not automatically include libimobiledevice unless those tools are provided during packaging.

## Run, test, and build

**Run from source:**

```powershell
.\start_windows.bat
```

The launcher installs missing Python packages before starting the app. If dependencies are already installed, you can run `py modern_ui.py` directly.

**Run automated tests:**

```powershell
py -m unittest -q tests_next tests_preview_cache test_media_groups tests_iphone_scan test_ui_smoke
```

GUI tests require an interactive Windows session. Physical USB export still needs testing with an actual iPhone.

**Build portable on your own Windows PC:**

Before building, put a compatible `afcclient.exe` and its DLLs under the project's `native` directory (preferably with `idevice_id.exe`), or point `HUSH_AFC_TOOLS` to their directory. Apple Mobile Device Support is also required for iPhone access.

```powershell
.\build_portable.bat
```

The script locally creates a Python environment, installs dependencies, runs tests, and builds `dist\HushPhoto` and `dist\HushPhoto-Windows-Portable.zip`. Copy the **entire** package, not just the EXE. If AFC tools were not supplied, the ZIP is still created but iPhone USB export will not work. Close `HushPhoto.exe` before rebuilding.

## Troubleshooting

| Symptom | Suggested checks |
| --- | --- |
| iPhone is not detected | USB cable, unlock/trust prompt, Apple Mobile Device Support, `idevice_id.exe -l` |
| Scan does not start | `afcclient.exe` and its DLLs, `native` / `HUSH_AFC_TOOLS` / `PATH`; try the manual scan |
| Scan stops with an error | Reconnect and unlock the iPhone; verify access to DCIM |
| Photo preview is missing | The original may be available only in iCloud, or the preview may be unreadable; export can still work |
| Transfer is interrupted | Export to the same destination again; validated copies will be skipped |
| HEVC/HDR video does not play correctly | Verify the original using a player with appropriate codec support |

## License

Hush Photo source code is distributed under the [MIT license](LICENSE). Third-party components, including Apple Mobile Device Support and libimobiledevice, are subject to their respective licensing and redistribution terms; review those terms before bundling binaries.
