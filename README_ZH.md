# Hush Photo — 使用说明（Windows 10/11 x64）

[Русский](README.md) | [English](README_EN.md) | [简体中文](README_ZH.md)

Hush Photo 是一款免费工具，可通过 USB（AFC）从 iPhone 导出照片、视频和实况照片（Live Photos），也可从电脑本地文件夹导出。**不会修改 iPhone 上的原始文件。**

## 1. 准备工作

- 通过 USB 连接 iPhone，解锁设备并在手机上选择**信任此电脑**。Windows 应安装 Apple Devices / Apple Mobile Device Support。
- USB 导出需要 Windows x64 版本的 `libimobiledevice`，包括 `afcclient.exe` 及同一压缩包中的 DLL。配置时填写的是**包含 `afcclient.exe` 的文件夹**，不是该程序的完整路径。

### 配置 AFC 工具路径

任选**一种**方式：

**方式一：放在程序旁（适合便携版）。** 在 `HushPhoto.exe` 旁创建 `native` 文件夹，将 `afcclient.exe` 和 `libimobiledevice` 的 DLL 放入其中，例如 `HushPhoto\native\afcclient.exe`。从源码运行时，`native` 应位于 `iphone_usb.py` 同级目录。

**方式二：使用环境变量（无需复制文件）。** 启动程序前在 PowerShell 中设置：

```powershell
$env:HUSH_AFC_TOOLS = 'D:\Tools\libimobiledevice'
```

请将示例路径替换为你的实际工具目录。该环境变量仅对当前 PowerShell 窗口及从中启动的进程生效。若需永久生效，请在 Windows 的环境变量设置中新增用户变量 `HUSH_AFC_TOOLS`，随后重新启动程序。

**方式三：系统 `PATH`。** 将包含 `afcclient.exe` 的文件夹加入 Windows 的 `PATH` 并重新启动程序。不要直接添加 EXE 文件路径。

**构建便携版 EXE：** 在已设置 `HUSH_AFC_TOOLS` 的命令行中运行 `build_portable.bat`。构建脚本会将 EXE 和 DLL 复制到 `dist\HushPhoto\native`，之后在其他电脑上无需重新配置路径。如果未设置该变量，构建过程不会自动打包 AFC 工具。

**验证：** 在工具目录的 PowerShell 中运行 `.\idevice_id.exe -l` 和 `.\afcclient.exe ls /DCIM`。也可以运行 `Test-Path (Join-Path $env:HUSH_AFC_TOOLS 'afcclient.exe')`，正确配置时应返回 `True`。

## 2. 启动程序

**便携版 EXE：** 从压缩包中解压**整个** `HushPhoto` 文件夹，再运行 `HushPhoto.exe`。无需安装 Python，但不能只复制单独的 EXE 文件。

**从源码运行：** 安装 64 位 Python 3.11 或更高版本，解压项目并运行 `start_windows.bat`。首次运行需要联网安装依赖。

**构建便携版：** 安装 64 位 Python 3.11+ 后运行 `build_portable.bat`。脚本会安装依赖、运行测试，并在成功后生成 `dist\HushPhoto-Windows-Portable.zip`，程序位于 `dist\HushPhoto\HushPhoto.exe`。若未包含 `afcclient.exe`，还需单独配置 USB 导出工具。

## 3. 导出照片和视频

1. 选择数据来源：**通过 USB 连接的 iPhone** 或 **本地文件夹**。
2. 使用 iPhone 时，点击**刷新**并等待媒体列表加载。通过顶部的**照片 / 视频**切换内容。**视频**部分包括**全部视频**、**普通视频**、**实况照片**筛选。若 MOV 与同一目录中同名的照片配对，则将其视为实况照片的视频部分；其他 MOV/MP4 视为普通视频。该识别方法只依赖文件名与目录，并不读取 Apple 内部资源 ID，因此可能存在误判。选择仅对当前分组有效；如需单独导出视频，请进入**视频**分组并选择 MOV/MP4。必要时可继续加载照片缩略图。
3. 指定目标文件夹，点击**配置并导出**。
4. 导出**照片**时，可选**原始文件**、**原始文件 + JPEG**、**JPEG**、**TIFF**。可选择是否包含实况照片的 MOV，并设置 JPEG 质量（默认 97）。导出**视频**时，MOV/MP4 不进行重新编码，保持原始质量。
5. 选择文件整理方式：**按年和月（`2026-10`）**、**不分文件夹**或**保留原始目录结构**，然后开始导出。
6. 等待完成并检查目标文件夹。界面会显示当前文件名、进度、速度和预计剩余时间。

按月整理时会优先使用媒体元数据中的拍摄日期；如果无法确定日期，程序不会随意编造。导出**照片**时，启用相应选项后，实况照片通常会同时保存 HEIC/JPEG 和配对 MOV，但同名匹配无法覆盖所有情况。**视频**分组也会显示全部 MOV/MP4，包括实况照片中的 MOV。再次通过 USB 导出时，程序会根据本地记录跳过已验证且未变化的文件。原始视频不会转换格式。

### 视频支持和 iPhone 照片图库的特点

- 支持 **MOV 和 MP4**，包括普通视频和实况照片的 MOV 视频片段。始终保留原格式，不压缩、不重新编码。
- **照片 / 视频**切换仅用于方便选择媒体。导出照片时可以同时保存其配对 MOV。
- Hush Photo 通过 AFC 读取 **DCIM 目录中可访问的文件**，可能包括**最近删除**中的文件。AFC 无法可靠提供其所属相簿信息，程序不会删除手机里的文件。
- AFC 文件数量与 iPhone **照片** App 中的项目数量可能不同。一张实况照片可包含多个实际文件；Windows 文件资源管理器也可能显示不同的文件名或媒体表示。
- 如果某个视频通过 AFC 复制失败，程序会将其记录在错误报告中。这并不代表该视频不在照片图库中；可以尝试通过 Windows 文件资源管理器复制。手工复制的文件不会自动写入 Hush Photo 的导出清单。
- 如果视频仅在 Windows 默认播放器中出现闪烁或花屏，可使用 VLC 播放同一原始文件进行比较；问题可能来自 HEVC/HDR 解码兼容性，而非复制损坏。

## 4. 增量导出与本地文件

- 程序会保存本地导出清单，重复导出时跳过已验证的文件。USB 连接中断后可以重新运行导出：已完成的文件保留，未完成的文件会从头重新复制。
- SHA-256 校验用于确认本地文件与本地清单的一致性，**不是**将文件与 iPhone 上独立计算的 SHA-256 进行比较。
- 导出目标下会建立临时目录 `.hushphoto-staging`；处理完成后会清理临时文件，但可能保留空目录。导出过程中不要删除该目录的文件。
- 缩略图缓存位于 `%LOCALAPPDATA%\HushPhoto\previews`，缩略图为不超过 320×320 的 JPEG，自动容量上限为 500 MiB。为了生成缩略图，程序可能先临时读取 iPhone 上的完整照片，处理完成后删除临时副本。
- 为保留原始数据，建议选择**原始文件 + JPEG**并包含 MOV。JPEG 为有损编码，程序不保证完整的 HDR → SDR 色调映射，因此请保留原始 HEIC。

## 5. 故障排除

- 检查 USB 数据线、iPhone 解锁状态、信任提示和 Apple Devices 的安装情况。
- 在 `afcclient.exe` 所在文件夹打开 PowerShell，运行 `.\idevice_id.exe -l` 以及 `.\afcclient.exe ls /DCIM`。
- 使用便携版时，请检查程序目录附近是否有 `native\afcclient.exe` 及对应 DLL。源代码修改后需要重新构建 EXE，旧 EXE 不会自动更新。
- 如果照片原件只保存在 iCloud，USB 可能无法读取。请先将原件下载到 iPhone。
- 导出失败时，**不要删除手机上的原件**；先检查已经复制的文件。

**注意：** USB 兼容性与 iOS 版本和安装的工具库有关。自动化测试无法替代真实 iPhone 上的验证。

### 临时目录清理

导出完成后，程序只会删除**空的** `.hushphoto-staging` 和 `DCIM` 目录（后者适用于按月份整理文件后的空目录）。非空目录和未完成的文件不会被删除。使用**保留原始目录结构**时，`DCIM` 内有媒体文件，因此会保留。文件 `.hushphoto-manifest.json` 和 `hushphoto_last_export.json` 用于管理增量导出。
