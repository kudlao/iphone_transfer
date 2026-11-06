# Hush Photo

**通过 USB 将 iPhone 照片和视频导出到 Windows，无需云端传输**

[Русский](README.md) · [English](README_EN.md) · [简体中文](README_ZH.md)

Hush Photo 是一款适用于 Windows 10/11（x64）的免费开源媒体导出工具。它通过 USB 和 Apple File Conduit（AFC）读取 iPhone 上可访问的文件，提供媒体浏览、文件选择、原始格式保存及中断后重新导出的功能。

应用也支持处理 Windows 本地文件夹中的照片和视频。**Hush Photo 不是完整的 iPhone 备份工具。**

## 主要功能

- **照片与视频：** 支持导出 HEIC、HEIF、JPEG、PNG、TIFF、DNG、MOV 和 MP4；视频不重新编码。AFC 扫描器可以识别 AAE 附属文件，但界面不提供单独选择导出 AAE 的功能。
- **Live Photos：** 可同时保存静态照片及对应的 MOV。配对依据文件名和所在目录，而不是 Apple 内部的资源标识符。
- **自动识别设备：** 在 USB 检测工具可用时，连接 iPhone 后自动识别并开始扫描；仍可手动发起扫描。
- **媒体浏览：** 随滚动自动加载照片缩略图、按文件名搜索、每页显示 36 个文件，以及独立的照片和视频选择。
- **视频筛选：** 全部视频、普通视频和 Live Photos。导出仅包含当前筛选条件下选中的文件，其他分类的选择会保留。
- **安全重复导出：** 跳过已验证的文件、安全处理重名文件，以及取消进行中的操作。
- **文件组织：** 保留 DCIM 原始目录结构、保存到单个文件夹，或在拍摄日期可用时按年月整理。
- **Windows 界面：** 随系统切换浅色/深色主题，并显示连接状态、传输进度、速度与预计剩余时间。

## 系统要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10/11，x64 |
| iPhone | 设备已解锁，并已选择信任此电脑 |
| USB 访问 | Apple Mobile Device Support 及兼容的 Windows 版 libimobiledevice |
| 源码运行 | 建议使用 Python 3.11 x64；依赖见 `requirements.txt` |
| 便携版 | 解压生成的完整 `HushPhoto` 文件夹；目标电脑无需安装 Python |

请在 Windows 安装 Apple Devices，或其他提供 Apple Mobile Device Support 的 Apple 官方组件。驱动程序及第三方 USB 工具可能影响设备识别。

### 配置 USB 工具

USB 媒体访问需要 `afcclient.exe` 以及**同一版本** libimobiledevice 附带的 DLL。推荐同时提供 `idevice_id.exe`，以便自动检测 iPhone。不要混用不同版本的可执行文件及动态库。

支持以下任一配置方式：

1. **随程序放置：** 将工具放在 `HushPhoto.exe` 同级的 `native` 目录；源码运行时放在 `iphone_usb.py` 同级的 `native` 目录。
2. **环境变量：** 将 `HUSH_AFC_TOOLS` 设置为工具所在目录，例如：
   `$env:HUSH_AFC_TOOLS = 'D:\Tools\libimobiledevice'`
3. **系统 PATH：** 将包含 `afcclient.exe` 的目录加入 `PATH`，然后重新启动程序。

应填写**目录路径**，而不是 EXE 文件的完整路径。可以在工具目录中使用 PowerShell 检查：

```powershell
.\idevice_id.exe -l
.\afcclient.exe ls /DCIM
```

第一条命令应列出已连接设备的标识符，第二条应能读取 DCIM 目录。如果自动检测不可用，可在应用内手动检查连接。

## 使用方法

1. 用 USB 连接并解锁 iPhone，出现提示时选择**信任**。Hush Photo 会在后台检测设备并自动扫描；也可手动检查连接，或点击**刷新**重新扫描。
2. 选择**照片**或**视频**。视频可进一步筛选全部视频、普通视频和 Live Photos。按文件名搜索，滚动或翻页时会自动加载可见照片的缩略图。
3. 选择需要导出的文件。**全选**及**取消选择**只影响当前搜索结果，搜索隐藏的已选文件不会被清除。已选数量显示在媒体库标题下方。
4. 选择保存目录并点击**导出**，检查导出选项后点击**开始导出**。
5. 导出期间会显示当前文件、进度、传输速度、预计剩余时间及取消操作。只要 USB 连接未中断，导出完成后仍可继续使用已扫描的媒体库。

如果需要处理电脑上的文件，请将来源从 **iPhone** 切换为**文件夹**。来源和目标文件夹不能相同，也不能相互包含。

### 导出选项

| 模式 | 输出 |
| --- | --- |
| **原始文件**（默认） | 不重新压缩或转换，保存原始格式 |
| **原始文件 + JPEG** | 同时保存原始照片和用于兼容的 JPEG 副本 |
| **JPEG** | 生成 JPEG 照片；**USB 导出仍会保留原始文件** |
| **TIFF** | 生成 TIFF 照片；**USB 导出仍会保留原始文件** |
| **视频** | 保持 MOV/MP4 原始格式，不重新编码 |

JPEG 质量可在 85–100 之间调整，默认值为 97。JPEG 是有损格式；程序不提供完整的 HDR 到 SDR 色调映射。长期归档建议保存原始文件。

选中**保留 Live Photo 动态视频（MOV）**时，如果同一目录中存在同名 MOV，导出静态照片会同时加入该视频；单独选择视频导出不需要此选项。

**目录结构：**
- **按年月整理：** 使用拍摄日期生成 `YYYY-MM` 文件夹；无法确定日期的文件放入 `Без даты`（无日期）。
- **原始目录结构：** 保留来源相对路径，USB 导出时包括 DCIM 目录。
- **单个文件夹：** 所有文件保存到所选目录，遇到重名文件时不会覆盖其他不同内容。

## 数据完整性与本地存储

Hush Photo 不会修改 iPhone 上的文件。导出先写入临时位置，确认完成后再保存到目标路径，以避免传输中断覆盖已有文件。

**USB 导出**会在目标目录保存 `.hushphoto-manifest.json` 和 `hushphoto_last_export.json`。重复导出时，通过本地文件大小及 SHA-256 校验判断是否可以跳过已保存的文件。此校验**不等于**独立获取并比较 iPhone 端的 SHA-256。

**本地文件夹导出**通过 SHA-256 避免复制相同内容，并生成 `export_report.txt`。

照片缩略图在电脑上生成，并临时保存在 `%LOCALAPPDATA%\HushPhoto\previews`。程序只按需加载可见区域的缩略图；正常关闭时清除缓存。若程序异常退出，残留缓存及临时原图会在下次启动时清除。**缓存清理不会删除已导出的媒体文件。**

## 已知限制

- AFC 不一定能够访问“照片”应用中的全部内容。仅存储在 iCloud 的照片可能不在设备本地；DCIM 文件数量与“照片”应用显示的项目数量可能不同。
- 通过 AFC 无法可靠识别**最近删除**相簿。Hush Photo 不会删除 iPhone 文件，也不能保证导出列表一定排除该相簿。
- Live Photos 的 MOV 分类依赖文件名和目录，可能存在个别识别误差。
- 视频以文件类型卡片显示，当前不生成视频画面缩略图。
- USB 物理连接断开后需要重新扫描。继续导出会跳过已完成且验证通过的文件，但不会从未完成文件的中间字节继续传输。
- 如果构建时没有提供 libimobiledevice 工具，便携版不会自动附带这些二进制文件。

## 启动、测试与打包

**从源码运行：**

```powershell
.\start_windows.bat
```

脚本仅在缺少 Python 依赖时安装对应软件包。依赖已安装后也可直接运行 `py modern_ui.py`。

**运行测试：**

```powershell
py -m unittest -q tests_next tests_preview_cache test_media_groups tests_iphone_scan test_ui_smoke
```

图形界面测试需要运行中的 Windows 桌面会话。实际 USB 导出仍需使用真实 iPhone 验证。

**创建便携版：**

```powershell
.\build_portable.bat
```

脚本复用 `.build-venv` 环境、安装依赖并运行测试，随后生成 `dist\HushPhoto` 及压缩包 `dist\HushPhoto-Windows-Portable.zip`。构建过程分为五个步骤，便于定位错误。重新构建前请关闭正在运行的 `HushPhoto.exe`。

如果 `HUSH_AFC_TOOLS` 指向包含 `afcclient.exe` 的目录，或仓库中有 `native\afcclient.exe`，构建脚本会将相应的 EXE 和 DLL 复制到便携版。移至其他电脑时，必须解压**完整**的 `HushPhoto` 文件夹，不能只复制 EXE。

**关于 GitHub Actions 构建：**名为 `HushPhoto-Windows-Portable-Requires-AFC-Tools` 的构建产物有意不包含第三方 libimobiledevice EXE/DLL。它可用于处理本地文件夹；通过 USB 导出 iPhone 文件还需要另外提供匹配的 `afcclient.exe`、DLL 和 Apple Mobile Device Support（见上文“配置 USB 工具”）。EXE 构建成功并不代表已验证 USB 连接。

## 常见问题

| 问题 | 建议检查 |
| --- | --- |
| 无法识别 iPhone | USB 线、解锁及信任提示、Apple Mobile Device Support、`idevice_id.exe -l` |
| 未开始扫描 | `afcclient.exe` 和 DLL、`native` / `HUSH_AFC_TOOLS` / `PATH`；尝试手动扫描 |
| 扫描中断 | 重新连接并解锁设备，确认 DCIM 可访问 |
| 照片缩略图为空 | 原图可能仅存在于 iCloud，或缩略图无法读取；原始文件仍可能可以导出 |
| 传输中断 | 重新导出到相同目录，已验证的文件将被跳过 |
| HEVC/HDR 视频播放异常 | 使用支持相应编解码器的播放器检查原始视频 |

## 许可证

Hush Photo 源代码使用 [MIT 许可证](LICENSE)。Apple Mobile Device Support 和 libimobiledevice 等第三方组件适用各自的许可及再分发条款。分发包含这些组件的二进制包前，请确认相关要求。
