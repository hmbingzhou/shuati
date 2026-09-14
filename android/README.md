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
| 网络 | 首次构建需访问 `dl.google.com`、`repo1.maven.org`、`services.gradle.org`（国内见下方“代理与镜像”） |
| Gradle | **8.9 及以上**；仓库已含 wrapper（`gradlew` / `gradlew.bat`），脚本仍会自动查找本地发行包 |

安装 Android SDK 的示例（Windows）：

```powershell
# 1) 下载 commandlinetools 解压，并整理成 <SDK>\cmdline-tools\latest\bin\sdkmanager.bat
# 2) 安装组件
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
# 3) 设置环境变量
setx ANDROID_HOME "D:\Android\Sdk"
setx JAVA_HOME "C:\Program Files\Eclipse Adoptium\jdk-17.0.12.7-hotspot"
```

### 国内网络：代理与镜像（重点）

Gradle 与 sdkmanager **都不会自动使用 Windows“系统代理”**，必须显式给参数。先确认代理真的能出海：

```powershell
# 端口换成你代理软件的混合端口（Clash 常见 7890 / 7897）
curl.exe -x http://127.0.0.1:7897 -s -o NUL -w "%{http_code}`n" https://dl.google.com/android/repository/repository2-3.xml
# 200 = 可用；000 = 连不上；502 = 代理在跑但境外节点不通（要去代理软件里换节点）
```

构建脚本内置了代理与镜像开关：

```bat
android\build_apk.bat -Proxy 127.0.0.1:7897             REM 依赖下载走代理
android\build_apk.bat -CnMirrors                        REM 依赖走阿里云镜像（google / central / gradle-plugin）
android\build_apk.bat -CnMirrors -Proxy none            REM 完全不用代理，只走镜像（系统代理是坏的时）
android\build_apk.bat -Proxy 127.0.0.1:7897 -CnMirrors  REM 两个一起用
```

不带参数直接双击也有自动降级逻辑：

- 自动读取系统代理（`HKCU\...\Internet Settings`），但**会先探测它能否访问外网**；
  探测失败就忽略并提示，避免坏代理让构建白等几分钟；
- 若 `dl.google.com` 不可达而阿里云镜像可用，**自动启用国内镜像**（等价于 `-CnMirrors`）。

> 实现提醒：脚本**不会**给 Gradle 传 `-Dhttp.nonProxyHosts`——它的值里含 `|`，
> 而 `.bat` 会被 cmd 重新解析，会把 `|` 当管道符报“`'127.0.0.1'` 不是内部或外部命令”。
> JDK 默认本就绕过 `localhost`/`127.*`，无需再设。

sdkmanager 同样不吃系统代理，要单独传：

```powershell
$sm = "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat"
(1..50 | ForEach-Object { "y" }) | & $sm --proxy=http --proxy_host=127.0.0.1 --proxy_port=7897 --licenses
& $sm --proxy=http --proxy_host=127.0.0.1 --proxy_port=7897 `
    "platform-tools" "platforms;android-35" "build-tools;35.0.0"
& $sm --list_installed
```

### 手工下载 SDK 组件（sdkmanager 不通时的兜底）

官网直接下 zip 也行，但解压后**必须整理成 AGP 认识的固定目录名**（最容易踩的一步）：

```
<SDK>/                                   例如 D:\Work\AndroidTools
  cmdline-tools/latest/bin/sdkmanager.bat
  platform-tools/adb.exe                 <- platform-tools-latest-windows.zip 里内层 platform-tools/ 整个搬过来
  platforms/android-35/android.jar       <- platform-35-ext14_r01.zip 里的 android-35/
  platforms/android-35/source.properties
  build-tools/35.0.0/aapt2.exe           <- build-tools_r35_windows.zip 里的 35.0.0/
  build-tools/35.0.0/source.properties
  licenses/android-sdk-license           <- 注意：没有 .txt 后缀！
```

- ⚠️ 平台包要下**基础包** `platform-35_r01.zip`（或更高 revision），**不要**下
  `platform-35-ext14_r01.zip`：后者是扩展包（`AndroidVersion.IsBaseSdk=false`、
  `AndroidVersion.ExtensionLevel=14`），会被注册成 `platforms;android-35-ext14`，
  构建时报 `Failed to find Platform SDK with path: platforms;android-35`。
  判断方法：`platforms\android-35\source.properties` 里应当没有 `ExtensionLevel` 且
  `IsBaseSdk=true`；
- build-tools 版本已在 `app/build.gradle.kts` 里显式写死为 `35.0.0`：AGP 8.7 默认要
  34.0.0，不写死就会去 `dl.google.com` 自动下载（国内网络下会超时失败）；
- 目录名必须正好是 `platform-tools`、`platforms\android-35`、`build-tools\35.0.0`；
  从 zip 解出来的外壳目录（`platform-tools-latest-windows\`、`platform-35-ext14_r01\`、
  `build-tools_r35_windows\`）不能保留；
- `licenses\android-sdk-license` 是**无扩展名**文件，内容为接受许可时写入的 SHA1 哈希（每行一个）；
  文件名多一个 `.txt` AGP 就不认，会在自动补装组件时报“license not accepted”；
- 自检三条：`platform-tools\adb.exe version` 能打印版本；
  `platforms\android-35\source.properties` 里 `Platform.Version=15`；
  `build-tools\35.0.0\source.properties` 里 `Pkg.Revision=35.0.0`。

### Gradle 发行包

仓库已提交 wrapper（`gradlew` / `gradlew.bat` / `gradle/wrapper/gradle-wrapper.jar`，
指向 Gradle 8.9），Android Studio 直接打开即可；命令行下 `build_apk.ps1` 会**优先**用本地
已解压的 Gradle 发行包（省掉 wrapper 的发行包下载），没有才退回 wrapper。

定位顺序：`-GradleHome` → `SHUATI_GRADLE_HOME` / `GRADLE_HOME`
→ `D:\Work\AndroidTools\gradle-*`、`D:\Work\gradle-*`、`D:\gradle-*`、`C:\Gradle\gradle-*`
→ PATH 上的 `gradle` → `android\gradlew.bat`；版本低于 8.9 会被跳过。

想用本地发行包（推荐，离线也能配置阶段起步）：下载 `gradle-8.9-bin.zip` 解压到
`D:\Work\AndroidTools\gradle-8.9`（确保存在 `gradle-8.9\bin\gradle.bat`），脚本会自动识别；
也可显式指定 `android\build_apk.bat -GradleHome D:\Work\AndroidTools\gradle-8.9`。

- 官方：https://services.gradle.org/distributions/gradle-8.9-bin.zip
- 国内：https://mirrors.cloud.tencent.com/gradle/gradle-8.9-bin.zip
  、https://repo.huaweicloud.com/gradle/gradle-8.9-bin.zip

## 2. 构建 APK

```bat
REM 最简单：双击 android\build_apk.bat（内部已用 -ExecutionPolicy Bypass，绕过脚本限制）
```

```powershell
# 命令行等价写法（本机 PowerShell 默认禁止运行脚本，必须带 Bypass）
powershell -NoProfile -ExecutionPolicy Bypass -File android\build_apk.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File android\build_apk.ps1 -Task assembleRelease
powershell -NoProfile -ExecutionPolicy Bypass -File android\build_apk.ps1 -Proxy 127.0.0.1:7897 -CnMirrors
```

| 参数 | 作用 |
|---|---|
| `-Task assembleDebug\|assembleRelease` | 构建变体，默认 debug |
| `-Proxy host:port` | 让 Gradle 依赖下载走代理；省略时自动读系统代理设置 |
| `-CnMirrors` | 依赖走阿里云镜像（等价于 `-DcnMirrors=true` 或环境变量 `SHUATI_CN_MIRROR=1`） |
| `-GradleHome <目录>` | 指定本地 Gradle 发行包目录 |
| `-Clean` | 构建前先执行 `clean` |
| `-SkipPrepare` | 跳过重新生成 `app/src/main/python`（调试脚本时用） |

> ⚠️ 修改 `build_apk.ps1` 后请务必保存为 **UTF-8 with BOM**：
> Windows PowerShell 5.1 对无 BOM 的 UTF-8 会按 ANSI 解码，中文注释可能被误解成引号导致语法错误。
> `android_setup_selftest.py` 会检查脚本 BOM 与语法，提交前跑一次即可发现。

脚本会：环境预检（JDK / SDK / Python / Gradle，其中 JDK 与 Gradle 都会自动探测，
`JAVA_HOME` 失效或未设置也不影响）→ 生成 `app/src/main/python`（运行时 + 种子）→
写版本号（最近 tag + 提交数）→ Gradle 构建 → 产物复制到 `dist/shuati-<版本>-<变体>.apk`。

安装：

```powershell
# 数据线
& "$env:ANDROID_HOME\platform-tools\adb.exe" install -r dist\shuati-1.0-debug.apk
# 或把 APK 传到手机，用文件管理器点击安装（首次允许“未知来源”）
```

### 在 GitHub Actions 上构建（本机没有可用网络/代理时）

仓库自带工作流 `.github/workflows/build-apk.yml`：在 GitHub 的 runner 上安装 JDK 17 +
Python 3.14 + Android SDK 35 + Gradle 8.9，执行 `prepare_python_src.py` 与 `assembleDebug`，
最后把 APK 作为 Artifacts 上传。

1. 把代码推到 GitHub；
2. 仓库 → **Actions** → 左侧 **Build APK** → **Run workflow**
   （推送 main 且改动命中 `android/**`、`webui/**` 等路径时也会自动触发）；
3. 运行结束后在该次运行的 **Artifacts** 区下载 `shuati-debug-apk`；
4. 传到手机安装（首次需允许“未知来源”）。

注意：

- runner 自带外网，本机代理不通不影响 CI；
- CI 产出的是 **debug** 签名包（自用足够）；release 签名需要把 keystore 放进 Secrets 再改工作流；
- 工作流里的 Python 版本必须与 `app/build.gradle.kts` 的 `chaquopy.version` 保持一致。

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

## 5. release 签名（可选，自用可直接用 debug 包）

```powershell
# 1) 生成密钥库（放到仓库外或 android/ 下；*.jks 已被 .gitignore 忽略）
keytool -genkeypair -v -keystore shuati-release.jks -alias shuati `
        -keyalg RSA -keysize 2048 -validity 3650

# 2) 在 android/keystore.properties 写入（路径相对 android/ 目录）
@"
storeFile=../shuati-release.jks
storePassword=你的库密码
keyAlias=shuati
keyPassword=你的密钥密码
"@ | Set-Content android\keystore.properties -Encoding ASCII

# 3) 构建 release
android\build_apk.bat -Task assembleRelease
```

未提供 `keystore.properties` 时，release 变体也会构建，但使用系统默认签名（仅适合自用测试）。

## 6. 已知限制 / 待办

- WebView 内“存档 zip 下载”（`<a download>`）需要额外的 `DownloadListener` + MediaStore 支持，
  当前未实现（可在电脑端导出存档后手动拷入）；
- 应用退到后台可能被系统回收（服务随进程存活），重开即恢复；未使用前台服务（避免通知与耗电）；
- 只打包 `arm64-v8a`（现代手机均为 64 位）；如需模拟器调试，可在 `app/build.gradle.kts`
  的 `abiFilters` 里加 `"x86_64"`；
- 仅 Android；iOS 需要用 PWA（浏览器“添加到主屏幕”）连本机/局域网服务。

## 7. 目录结构

```
android/
  build_apk.ps1            一键构建脚本（环境预检 + 代理/镜像开关）
  settings.gradle.kts      仓库配置（-PcnMirrors 时启用阿里云镜像）
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
