<#
.SYNOPSIS
  一键构建刷题软件 Android APK（Chaquopy + WebView）

.DESCRIPTION
  流程：环境预检（JDK 17/21、Android SDK、Python 3.14）→ 生成 Python 源码/种子
        → 写版本号 → Gradle 构建 → 产物复制到 dist/

  前置依赖（一次性）：
    * JDK 17 或 21（注意：JDK 25 不被 Gradle/AGP 支持），设置 JAVA_HOME
    * Android SDK：platform-tools + platforms;android-35 + build-tools;35.0.0
      （无需 NDK；Chaquopy 使用预编译 CPython）
    * 与 app/build.gradle.kts 中 chaquopy.version 一致的 Python（当前 3.14）
  首次构建需要联网：dl.google.com、repo1.maven.org、services.gradle.org

.EXAMPLE
  pwsh -File android/build_apk.ps1                 # debug APK
  pwsh -File android/build_apk.ps1 -Task assembleRelease
#>
param(
    [ValidateSet("assembleDebug", "assembleRelease")]
    [string]$Task = "assembleDebug",
    [switch]$SkipPrepare
)

$ErrorActionPreference = "Continue"   # 不能用 Stop：PS 5.1 会把原生命令的 stderr 变成终止错误
$AndroidDir = $PSScriptRoot
$Root = Split-Path -Parent $AndroidDir
$Dist = Join-Path $Root "dist"

function Fail($msg) {
    Write-Host ""
    Write-Host "✗ $msg" -ForegroundColor Red
    exit 1
}

function Info($msg) { Write-Host "  $msg" }
function Ok($msg) { Write-Host "  ✓ $msg" -ForegroundColor Green }

Write-Host "=== 刷题软件 Android 构建 ===" -ForegroundColor Cyan

# ---------- 1) JDK 预检 ----------
$javaExe = $null
if ($env:JAVA_HOME) {
    $candidate = Join-Path $env:JAVA_HOME "bin\java.exe"
    if (Test-Path $candidate) { $javaExe = $candidate }
}
if (-not $javaExe) {
    $cmd = Get-Command java -ErrorAction SilentlyContinue
    if ($cmd) { $javaExe = $cmd.Source }
}
if (-not $javaExe) {
    Fail "未找到 Java。请安装 JDK 17（推荐 Eclipse Temurin 17）并设置 JAVA_HOME。`n" +
         "   下载：https://adoptium.net/temurin/releases/?version=17`n" +
         "   注意：你机器上现有的 Oracle JDK 25 不被 Gradle/AGP 支持。"
}
# 用 cmd 包装，避免 PS 5.1 把 java 写到 stderr 的版本信息当成错误
$javaVerLine = (cmd /c "`"$javaExe`" -version 2>&1" | Select-Object -First 1)
if ("$javaVerLine" -match '"(\d+)') {
    $javaMajor = [int]$Matches[1]
    if ($javaMajor -lt 17 -or $javaMajor -gt 21) {
        Fail "当前 Java 版本为 $javaMajor（$javaVerLine），Gradle 8.9 + AGP 8.7 需要 JDK 17~21。`n" +
             "   请安装 JDK 17 并让 JAVA_HOME 指向它（或在 android/gradle.properties 里设 org.gradle.java.home）。"
    }
    Ok "JDK $javaMajor ($javaExe)"
} else {
    Fail "无法识别 Java 版本：$javaVerLine"
}

# ---------- 2) Android SDK 预检 ----------
$sdk = $env:ANDROID_HOME
if (-not $sdk) { $sdk = $env:ANDROID_SDK_ROOT }
if (-not $sdk) {
    $guess = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    if (Test-Path $guess) { $sdk = $guess }
}
if (-not $sdk -or -not (Test-Path $sdk)) {
    Fail "未找到 Android SDK。请安装 command-line tools 并设置 ANDROID_HOME，例如：`n" +
         "   1) 下载 https://developer.android.com/studio#command-tools 解压到 D:\Android\Sdk\cmdline-tools\latest`n" +
         "   2) 执行：sdkmanager `"platform-tools`" `"platforms;android-35`" `"build-tools;35.0.0`"`n" +
         "   3) 设置环境变量 ANDROID_HOME=D:\Android\Sdk（无需 NDK）"
}
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
Ok "Android SDK: $sdk"
if (-not (Test-Path (Join-Path $sdk "platforms\android-35"))) {
    Fail "SDK 缺少 platforms;android-35。请执行：sdkmanager `"platforms;android-35`""
}
if (-not (Test-Path (Join-Path $sdk "build-tools"))) {
    Fail "SDK 缺少 build-tools。请执行：sdkmanager `"build-tools;35.0.0`""
}

# ---------- 3) Python 预检（Chaquopy 的 buildPython 需与 app 的 python 版本主次号一致） ----------
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { Fail "未找到 python，请安装 Python 3.14 并加入 PATH（Chaquopy 打包需要）" }
$pyVer = (& python -c "import sys;print('%d.%d'%sys.version_info[:2])").Trim()
if ($pyVer -ne "3.14") {
    Fail "构建机 Python 为 $pyVer，但 android/app/build.gradle.kts 里 chaquopy.version = \`"3.14\`"。`n" +
         "   二者主次版本必须一致：安装 Python 3.14，或把 chaquopy.version 改成 $pyVer。"
}
Ok "Python $pyVer"

# ---------- 4) Gradle wrapper 预检 ----------
Push-Location $AndroidDir
try {
    if (-not (Test-Path (Join-Path $AndroidDir "gradlew.bat"))) {
        $gradle = Get-Command gradle -ErrorAction SilentlyContinue
        if ($gradle) {
            Info "未找到 gradlew，尝试用本地 Gradle 生成 wrapper（8.9）…"
            & gradle wrapper --gradle-version 8.9
        } else {
            Fail "缺少 gradle wrapper（gradlew.bat / gradle-wrapper.jar）。两种解决方式：`n" +
                 "   A) 用 Android Studio 打开 android/ 目录，IDE 会自动生成 wrapper；`n" +
                 "   B) 安装 Gradle 8.9 后在本目录执行：gradle wrapper --gradle-version 8.9"
        }
    }

    # ---------- 5) 版本号（取最近 tag + 提交数） ----------
    $versionName = "1.0"
    $versionCode = "1"
    try {
        $tag = (& git -C $Root describe --tags --abbrev=0 2>$null)
        if ($tag) { $versionName = ($tag -replace '^v', '').Trim() }
        $count = (& git -C $Root rev-list --count HEAD 2>$null)
        if ($count) { $versionCode = $count.Trim() }
    } catch { }
    @("versionName=$versionName", "versionCode=$versionCode") |
        Set-Content -Path (Join-Path $AndroidDir "version.properties") -Encoding ASCII
    Ok "版本：$versionName (versionCode $versionCode)"

    # ---------- 6) 生成 Python 源码 + 种子 ----------
    if (-not $SkipPrepare) {
        Info "生成 Python 源码/种子 …"
        & python (Join-Path $AndroidDir "prepare_python_src.py")
        if ($LASTEXITCODE -ne 0) { Fail "prepare_python_src.py 失败" }
    }
    & python (Join-Path $AndroidDir "prepare_python_src.py") --check
    if ($LASTEXITCODE -ne 0) { Fail "staging 校验失败" }

    # ---------- 7) 构建 ----------
    Write-Host "=== 开始 Gradle 构建（首次会下载 Gradle 发行包与 Chaquopy 组件）===" -ForegroundColor Cyan
    & (Join-Path $AndroidDir "gradlew.bat") $Task --no-daemon
    if ($LASTEXITCODE -ne 0) { Fail "Gradle 构建失败（查看上面的错误；常见：代理未开、SDK 许可未接受）" }

    # ---------- 8) 复制产物 ----------
    $variant = if ($Task -eq "assembleRelease") { "release" } else { "debug" }
    $apk = Join-Path $AndroidDir "app\build\outputs\apk\$variant\app-$variant.apk"
    if (-not (Test-Path $apk)) { Fail "未找到构建产物：$apk" }
    New-Item -ItemType Directory -Force -Path $Dist | Out-Null
    $out = Join-Path $Dist "shuati-$versionName-$variant.apk"
    Copy-Item $apk $out -Force
    $size = [math]::Round((Get-Item $out).Length / 1MB, 1)
    Ok "APK：$out（$size MB）"
    Write-Host ""
    Write-Host "安装到手机：" -ForegroundColor Cyan
    Write-Host "  · 数据线：$sdk\platform-tools\adb.exe install -r `"$out`""
    Write-Host "  · 或把 APK 传到手机，用文件管理器点击安装（首次需允许“未知来源”）"
}
finally {
    Pop-Location
}
