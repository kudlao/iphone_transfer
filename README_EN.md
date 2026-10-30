# Hush Photo — User Guide (Windows 10/11 x64)

[Русский](README.md) | [English](README_EN.md) | [简体中文](README_ZH.md)

Free export of photos, videos and Live Photos from iPhone over USB (AFC), or from a local folder. The original files on the iPhone are never modified.

## 1. Requirements and setup

- Connect your iPhone using USB, unlock it and approve **Trust This Computer**. Install Apple Devices / Apple Mobile Device Support on Windows.
- USB access requires the unpacked Windows x64 **libimobiledevice** package, including `afcclient.exe` and its accompanying DLLs. Supply the **directory containing** `afcclient.exe`, not the executable path.

### Configuring the AFC tools

Choose **one** method:

**Option 1 — bundle alongside the application (best for portable use).** Create a `native` directory next to `HushPhoto.exe` and put `afcclient.exe` and its libimobiledevice DLLs there, e.g. `HushPhoto\native\afcclient.exe`. When running from source, `native` should be next to `iphone_usb.py`.

**Option 2 — environment variable (without copying files).** Before starting Hush Photo, set the tools directory in PowerShell:

```powershell
$env:HUSH_AFC_TOOLS = 'D:\Tools\libimobiledevice'
```

Replace the example with your own directory. This setting applies to the current PowerShell session and processes launched from it. To make it permanent, add a user environment variable named `HUSH_AFC_TOOLS` in Windows system settings and restart the app.

**Option 3 — system `PATH`.** Add the directory containing `afcclient.exe` to your Windows `PATH`, then restart the application. Do not add the executable file itself.

**When building a portable EXE:** Run `build_portable.bat` from a shell where `HUSH_AFC_TOOLS` is defined. The build script copies the executable and DLLs into `dist\HushPhoto\native`, so no further configuration is needed on another computer. Without that variable, the tools are not automatically packaged.

**Verify:** From the AFC tools directory, run `.\idevice_id.exe -l` and `.\afcclient.exe ls /DCIM`. To verify the configured path, run `Test-Path (Join-Path $env:HUSH_AFC_TOOLS 'afcclient.exe')`; it should return `True`.

## 2. Running Hush Photo

**Portable EXE:** Extract the **entire** `HushPhoto` directory from the portable archive and launch `HushPhoto.exe`. Python is not required. Do not move the EXE without its supporting files.

**From source:** Install 64-bit Python 3.11+, extract the project, then run `start_windows.bat`. The first run requires internet access to install dependencies.

**Build a portable package:** With 64-bit Python 3.11+ installed, run `build_portable.bat`. It installs dependencies, runs tests and, on success, creates `dist\HushPhoto-Windows-Portable.zip` and `dist\HushPhoto\HushPhoto.exe`. USB export requires additional setup if `afcclient.exe` is not bundled.

## 3. Exporting photos and videos

1. Select **iPhone via USB** or **Local folder** as the source.
2. For iPhone, click **Refresh** and wait for the media list. Use the **Photos / Videos** selector at the top. The **Videos** group has **All videos**, **Video clips** and **Live Photos** filters. A MOV file paired with an image of the same basename in the same directory is categorized as a Live Photo video; other MOV/MP4 files are video clips. This filename-based heuristic does not read Apple's internal asset identifiers, so classification may be imperfect. Selection applies only to the current group. Open **Videos** and select the desired MOV/MP4 files for a video-only export. Load additional photo thumbnails if needed.
3. Choose a destination directory and click **Configure and export**.
4. For **Photos**, choose **Originals**, **Originals + JPEG**, **JPEG**, or **TIFF**. Optionally include Live Photo MOV components and set JPEG quality (default 97). For **Videos**, MOV/MP4 files are copied directly, without transcoding or quality loss.
5. Choose **Year and month (`2026-10`)**, **Flat folder**, or **Original directory structure**; then start the export.
6. Check the output when the operation finishes. The interface displays the current filename, progress, speed and estimated remaining time.

Year/month organization uses the capture date when metadata provides one; Hush Photo does not invent a date when it is unavailable. When exporting **Photos**, a Live Photo usually includes its HEIC/JPEG still and matching MOV when that option is enabled; basename matching cannot identify every possible pairing. All MOV/MP4 files, including Live Photo MOV components, are also accessible under **Videos**. Verified, unchanged copies are skipped on subsequent USB exports. Original videos are never converted.

### Video support and iPhone library details

- **MOV and MP4** are supported, including standalone clips and Live Photo MOV components. Files are preserved in their original format without compression or transcoding.
- The **Photos / Videos** selector separates media lists for convenience. When exporting photos, you may include corresponding MOV files.
- Hush Photo reads accessible **DCIM files over AFC**. These may include files from **Recently Deleted**. Hush Photo cannot reliably identify that album through AFC and does not delete anything from the phone.
- The number of AFC files may differ from the number of assets in the Apple Photos app. A single Live Photo may contain multiple physical files, and Windows Explorer may expose different names or representations.
- If an AFC video transfer fails, the app records an error. This does not prove the video is absent from Apple Photos. You may try Windows File Explorer. Files copied manually are not automatically added to the Hush Photo manifest.
- If an iPhone video has visual artifacts in the default Windows player, test the same original in VLC. HEVC/HDR playback support may be the issue rather than file transfer.

## 4. Repeated exports and local data

- Hush Photo maintains a local manifest of previously exported files and skips verified copies. If the USB connection fails, run the export again. Completed files remain intact; an incomplete file is restarted from the beginning.
- SHA-256 verification checks the locally downloaded file against the local manifest; it does **not** compare against an independently obtained iPhone SHA-256.
- A temporary `.hushphoto-staging` directory is created under the destination. Temporary files are removed after processing; some empty directories may remain. Do not delete staging files while exporting.
- Thumbnail cache: `%LOCALAPPDATA%\HushPhoto\previews`, JPEG thumbnails up to 320×320 pixels, with an automatic 500 MiB limit. Creating a thumbnail may temporarily download the complete source image from the iPhone; the temporary source is deleted afterward.
- To keep original source data, use **Originals + JPEG** with MOV components. JPEG encoding is lossy; full HDR-to-SDR tone mapping is not guaranteed. Preserve the original HEIC files.

## 5. Troubleshooting

- Check the USB cable, unlock the iPhone, confirm computer trust and install Apple Devices.
- From the folder with `afcclient.exe`, run `.\idevice_id.exe -l` and `.\afcclient.exe ls /DCIM` in PowerShell.
- For the portable edition, ensure `native\afcclient.exe` and the DLLs are present alongside the app. Rebuild after modifying source files: an existing EXE is not updated automatically.
- Photos whose originals are stored only in iCloud may be unavailable over USB. Download the originals to the iPhone first.
- If an export fails, **do not delete originals from the phone**. Verify downloaded files before taking further action.

**Note:** USB behavior depends on the iOS version and installed libraries. Automated tests cannot replace verification on a physical iPhone.

### Temporary directory cleanup

After export, Hush Photo removes **only empty** `.hushphoto-staging` and `DCIM` directories (the latter when files are reorganized by month). Non-empty directories and incomplete source files are not removed. In **Original directory structure** mode, `DCIM` remains because it contains exported media. The `.hushphoto-manifest.json` and `hushphoto_last_export.json` files are used to track incremental exports.
