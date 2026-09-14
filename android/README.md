# 刷题软件 · Android 版（Chaquopy + WebView）

把现有 Python 后端（`webui_server.py`，纯标准库）与网页界面打进一个 APK：
**安装即用、完全离线**，个人数据保存在应用私有目录，联网时可在应用内“更新题库”。

> 代码单一真源：Android 工程不复制业务代码；构建前由脚本把运行时文件与题库种子
> 生成到 `app/src/main/python/`（该目录已被 `.gitignore` 忽略）。

## 1. 一次性准备（构建机）

| 依赖 | 版本/说明 |
|---|---|
| JDK | **17 或 21**（[Temurin 17](https://adoptium.net/temurin/releases/?version=17)）；JDK 25 不被 Gradle/AGP 支持 |
| Android SDK | `commandlinetools` + `platform-tools` + `platforms;android-35` + `build-tools;35.0.0`；**无需 NDK** |
| Python | **3.14**（与 `app/build.gradle.kts` 的 `chaquopy.version` 一致；Chaquopy 用本机 Python 编译字节码） |
| 网络 | 首次构建需访问 `dl.google.com`、`repo1.maven.org`、`services.gradle.org`（国内建议挂代理） |

安装 Android SDK 的示例（Windows）：

```powershell
# 1) 下载 commandlinetools 解压到 D:\Android\Sdk\cmdline-tools\latest
# 2) 安装组件
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
# 3) 设置环境变量
setx ANDROID_HOME "D:\Android\Sdk"
setx JAVA_HOME "C:\Program Files\Eclipse Adoptium\jdk-17.0.12.7-hotspot"
```

如果机器上没有 `gradlew`（本工程未提交 wrapper 二进制），二选一：
- **Android Studio** 打开 `android/` 目录，IDE 会自动补齐 wrapper（推荐，最省事）；
- 或安装 Gradle 8.9 后在 `android/` 下执行 `gradle wrapper --gradle-version 8.9`。

## 2. 构建 APK

```bat
REM 最简单：双击 android\build_apk.bat（内部已用 -ExecutionPolicy Bypass，绕过脚本限制）
```

```powershell
# 命令行等价写法（本机 PowerShell 默认禁止运行脚本，必须带 Bypass）
powershell -NoProfile -ExecutionPolicy Bypass -File android\build_apk.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File android\build_apk.ps1 -Task assembleRelease
```

> ⚠️ 修改 `build_apk.ps1` 后请务必保存为 **UTF-8 with BOM**：
> Windows PowerShell 5.1 对无 BOM 的 UTF-8 会按 ANSI 解码，中文注释可能被误解成引号导致语法错误。
> `android_setup_selftest.py` 会检查脚本 BOM 与语法，提交前跑一次即可发现。

脚本会：环境预检（JDK/SDK/Python/gradlew）→ 生成 `app/src/main/python`（运行时 + 种子）→
写版本号（最近 tag + 提交数）→ Gradle 构建 → 产物复制到 `dist/shuati-<版本>-<变体>.apk`。

安装：

```powershell
# 数据线
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r dist\shuati-1.0-debug.apk
# 或把 APK 传到手机，用文件管理器点击安装（首次允许“未知来源”）
```

## 3. 应用行为说明

- 启动时在应用私有目录（`filesDir`，即 Python 的 `SHUATI_HOME`）准备可写数据：
  `data/`（题库）、`pictures/`（图片）、`reports/`、`backups/`；
- **首启种子只补缺失文件**：随包题库/图片会复制进去，但绝不覆盖你已有的题目与个人数据
  （错题本 `wrong_book.json`、记录 `records.json`、回收站、考试记录、进度）；
- APK 升级后若种子版本变化，只补充新增文件，个人数据保留；
- 设置页的「题库更新」走 `sync_bank.py` 的 jsDelivr → raw.githubusercontent 双源 + sha256 校验 +
  自动备份；远程仓库来自随包的 `seed/bank_remote.json`（默认指向本项目的公开仓库）；
- 设置页「运行环境」卡片显示：运行形态（Android 应用/桌面）、APK 版本号、数据目录、
  题库来源、离线种子版本与 Python 版本（版本号由 `BuildConfig.VERSION_NAME` 经 `entry.start` 传入）；
- 返回键：先关弹窗/图库叠加层 → 回首页 → 再按退出应用；
- 编辑器“上传新图片 / 拍照”通过 `onShowFileChooser` 桥接，选中的图片会存到
  `pictures/<科目>/` 并插入题干标记。

## 4. 真机验收清单（装好 APK 后逐项确认）

- [ ] 首启（可开飞行模式）进入仪表盘，科目卡片有题数（数据来自随包种子）；
- [ ] 打开一道带图题，题干/选项/题后图片正常显示（图片来自 `pictures/<科目>/`）；
- [ ] 六题型作答：单选/多选/判断/填空（多空+可换序）/简答（自评）/计算；
- [ ] 错题本、刷题记录、模拟考试可用；**杀掉进程重开**数据仍在；
- [ ] 设置页可见「运行环境」卡片：Android 形态、版本号、数据目录、题库来源、离线种子；
- [ ] 联网后设置页「检查更新 → 立即更新」能拉取远程题库（更新前自动备份到私有目录 backups/）；
- [ ] 编辑器「插入图片 / 上传新图片」能调起相册或拍照，选完图片仍停留在编辑弹窗；
- [ ] 返回键行为：先关弹窗/图库 → 回首页 → 再按退出；旋转屏幕不丢失当前页面；
- [ ] 360×640 窄屏无横向滚动，底部标签栏可用；
- [ ] 覆盖安装新版本 APK：个人数据保留（种子只补缺失文件）。

排查：`adb logcat -s python.stdout python.stderr` 可看 Python 侧日志（HOME 路径、种子版本、端口）。

## 5. 已知限制 / 待办

- WebView 内“存档 zip 下载”（`<a download>`）需要额外的 `DownloadListener` + MediaStore 支持，
  当前未实现（可在电脑端导出存档后手动拷入）；
- 应用退到后台可能被系统回收（服务随进程存活），重开即恢复；未使用前台服务（避免通知与耗电）；
- 只打包 `arm64-v8a`（现代手机均为 64 位）；如需模拟器调试，可在 `app/build.gradle.kts`
  的 `abiFilters` 里加 `"x86_64"`；
- 仅 Android；iOS 需要用 PWA（浏览器“添加到主屏幕”）连本机/局域网服务。

## 5. 目录结构

```
android/
  build_apk.ps1            一键构建脚本（含环境预检）
  prepare_python_src.py    生成 app/src/main/python（运行时 + 题库种子）
  entry.py                 Python 入口：设置 SHUATI_HOME、种子复制、起服务、返回端口
  version.properties       构建时生成（已 gitignore）
  app/
    build.gradle.kts       应用配置（Chaquopy 17 / Python 3.14 / arm64-v8a）
    src/main/
      AndroidManifest.xml  INTERNET 权限、PyApplication、MainActivity
      java/.../MainActivity.java  WebView + 文件选择 + 返回键桥接
      res/                 图标、主题、network_security_config（仅放行 localhost 明文）
      python/              构建期生成（已 gitignore）
```
