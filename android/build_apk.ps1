<#
.SYNOPSIS
  一键构建刷题软件 Android APK（Chaquopy + WebView）

.DESCRIPTION
  流程：环境预检（JDK 17/21、Android SDK、Python 3.14、Gradle）
        → 生成 Python 源码/种子 → 写版本号 → Gradle 构建 → 产物复制到 dist/

  前置依赖（一次性）：
    * JDK 17 或 21（JDK 25 不被 Gradle/AGP 支持）。脚本会在常见位置自动查找，
      JAVA_HOME 无效/未设置也不会中断。
    * Android SDK：platform-tools + platforms;android-35 + build-tools;35.0.0
      + licenses/android-sdk-license（无需 NDK，Chaquopy 用预编译 CPython）
    * Gradle 8.9 及以上：wrapper（gradlew.bat）或本地解压的发行包，
      脚本自动查找，也可用 -GradleHome 指定。
    * 与 app/build.gradle.kts 中 chaquopy.version 一致的 Python（当前 3.14）

  首次构建需要联网下载 AGP / Chaquopy 等依赖。国内网络不通时：
    * 走代理：build_apk.bat -Proxy 127.0.0.1:7897
    * 走镜像：build_apk.bat -CnMirrors
    两者可同时使用。

.EXAMPLE
  build_apk.bat                                        # debug APK
  build_apk.bat -Task assembleRelease                  # release APK
  build_apk.bat -Proxy 127.0.0.1:7897 -CnMirrors       # 代理 + 国内镜像
  build_apk.bat -GradleHome D:\Work\AndroidTools\gradle-8.9
#>
param(
    [ValidateSet("assembleDebug", "assembleRelease")]
    [string]$Task = "assembleDebug",
    [switch]$SkipPrepare,
    [switch]$Clean,
    [string]$GradleHome = "",
    [string]$Proxy = "",
    [switch]$CnMirrors
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
function Warn($msg) { Write-Host "  ! $msg" -ForegroundColor Yellow }

Write-Host "=== 刷题软件 Android 构建 ===" -ForegroundColor Cyan

# ---------- 1) JDK 预检（自动探测，不盲信 JAVA_HOME） ----------
function Get-JavaMajor([string]$exe) {
    # 用 cmd 包装，避免 PS 5.1 把 java 写到 stderr 的版本信息当成错误
    $line = (cmd /c "`"$exe`" -version 2>&1" | Select-Object -First 1)
    if ("$line" -match '"(\d+)') { return [int]$Matches[1] }
    return 0
}

$javaCandidates = @()
if ($env:JAVA_HOME) {
    $p = Join-Path $env:JAVA_HOME "bin\java.exe"
    if (Test-Path $p) { $javaCandidates += $p }
    else { Warn "JAVA_HOME 指向的目录里没有 bin\java.exe：$env:JAVA_HOME（已忽略）" }
}
$javaRoots = @(
    "C:\Program Files\Java", "C:\Program Files\Eclipse Adoptium", "C:\Program Files\Microsoft",
    "C:\Program Files\Zulu", "C:\Program Files\Android\Android Studio\jbr",
    (Join-Path $env:LOCALAPPDATA "Programs\Android Studio\jbr"),
    (Join-Path $env:USERPROFILE ".jdks"),
    "D:\Work", "D:\Java", "D:\Android", "C:\Java"
)
foreach ($r in $javaRoots) {
    if (-not (Test-Path $r)) { continue }
    if (Test-Path (Join-Path $r "bin\java.exe")) { $javaCandidates += (Join-Path $r "bin\java.exe"); continue }
    Get-ChildItem $r -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'jdk|jre|jbr|temurin|zulu|corretto|java' } |
        ForEach-Object {
            $exe = Join-Path $_.FullName "bin\java.exe"
            if (Test-Path $exe) { $javaCandidates += $exe }
        }
}
$cmdJava = Get-Command java -ErrorAction SilentlyContinue
if ($cmdJava) { $javaCandidates += $cmdJava.Source }

$javaExe = $null
$javaMajor = 0
$rejected = @()
foreach ($c in ($javaCandidates | Select-Object -Unique)) {
    $m = Get-JavaMajor $c
    if ($m -ge 17 -and $m -le 21) { $javaExe = $c; $javaMajor = $m; break }
    if ($m -gt 0) { $rejected += "JDK $m ($c)" }
}
if (-not $javaExe) {
    $extra = ""
    if ($rejected.Count -gt 0) { $extra = "`n   找到但不兼容： " + ($rejected -join "；") }
    Fail ("未找到 JDK 17~21。请安装 JDK 17（推荐 Eclipse Temurin 17）并设置 JAVA_HOME。" + $extra + "`n" +
          "   下载：https://adoptium.net/temurin/releases/?version=17`n" +
          "   注意：JDK 25 等新版本不被 Gradle 8.9 / AGP 8.7 支持。")
}
$env:JAVA_HOME = Split-Path -Parent (Split-Path -Parent $javaExe)
Ok "JDK $javaMajor（$javaExe）"

# ---------- 2) Android SDK 预检 ----------
$sdk = $env:ANDROID_HOME
if (-not $sdk) { $sdk = $env:ANDROID_SDK_ROOT }
if (-not $sdk) { $sdk = [Environment]::GetEnvironmentVariable("ANDROID_HOME", "User") }
if (-not $sdk) { $sdk = [Environment]::GetEnvironmentVariable("ANDROID_SDK_ROOT", "User") }
if (-not $sdk) {
    foreach ($guess in @((Join-Path $env:LOCALAPPDATA "Android\Sdk"), "D:\Work\AndroidTools", "D:\Android\Sdk")) {
        if (Test-Path $guess) { $sdk = $guess; break }
    }
}
if (-not $sdk -or -not (Test-Path $sdk)) {
    Fail ("未找到 Android SDK。请安装 command-line tools 并设置 ANDROID_HOME，例如：`n" +
          "   1) 下载 https://developer.android.com/studio#command-tools 解压到 D:\Android\Sdk\cmdline-tools\latest`n" +
          "   2) 执行：sdkmanager `"platform-tools`" `"platforms;android-35`" `"build-tools;35.0.0`"`n" +
          "   3) 设置环境变量 ANDROID_HOME=D:\Android\Sdk（无需 NDK）")
}
$env:ANDROID_HOME = $sdk
$env:ANDROID_SDK_ROOT = $sdk
Ok "Android SDK: $sdk"
if (-not (Test-Path (Join-Path $sdk "platforms\android-35"))) {
    Fail "SDK 缺少 platforms;android-35。请执行：sdkmanager `"platforms;android-35`""
}
if (-not (Test-Path (Join-Path $sdk "build-tools\35.0.0"))) {
    $bt = @(Get-ChildItem (Join-Path $sdk "build-tools") -Directory -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty Name)
    $found = if ($bt.Count -gt 0) { "当前只有：" + ($bt -join ", ") } else { "build-tools 目录为空" }
    Fail ("SDK 缺少 build-tools;35.0.0（AGP 8.7 默认需要它）。$found`n" +
          "   请执行：sdkmanager `"build-tools;35.0.0`"")
}
Ok "platforms;android-35 + build-tools;35.0.0"
if (-not (Test-Path (Join-Path $sdk "platform-tools\adb.exe"))) {
    Warn "SDK 里没有 platform-tools\adb.exe，构建不受影响，但装到手机时需要：sdkmanager `"platform-tools`""
}
if (-not (Test-Path (Join-Path $sdk "licenses\android-sdk-license"))) {
    Warn "缺少 licenses\android-sdk-license，AGP 自动补装组件时会失败（组件齐全时可忽略）"
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

# ---------- 4) Gradle 定位（wrapper 优先，其次本地发行包） ----------
function Resolve-LocalGradle([string]$explicit) {
    $cands = @()
    if ($explicit) { $cands += $explicit }
    foreach ($e in @($env:SHUATI_GRADLE_HOME, $env:GRADLE_HOME)) { if ($e) { $cands += $e } }
    foreach ($r in @("D:\Work\AndroidTools", "D:\Work", "D:\", "C:\Gradle",
                     (Join-Path $env:USERPROFILE "gradle"), (Join-Path $env:LOCALAPPDATA "Gradle"))) {
        if (Test-Path $r) {
            Get-ChildItem $r -Directory -Filter "gradle-*" -ErrorAction SilentlyContinue |
                ForEach-Object { $cands += $_.FullName }
        }
    }
    $cmd = Get-Command gradle -ErrorAction SilentlyContinue
    if ($cmd) { $cands += (Split-Path -Parent (Split-Path -Parent $cmd.Source)) }
    foreach ($c in $cands) {
        $bat = Join-Path $c "bin\gradle.bat"
        if (Test-Path $bat) { return $bat }
    }
    return $null
}

function Get-GradleVersion([string]$bat) {
    $out = cmd /c "`"$bat`" --version 2>&1"
    $line = $out | Select-String -Pattern "^Gradle " | Select-Object -First 1
    if ("$line" -match "Gradle\s+(\d+)\.(\d+)") { return @([int]$Matches[1], [int]$Matches[2]) }
    return @(0, 0)
}

$localGradle = Resolve-LocalGradle $GradleHome
$wrapperBat = Join-Path $AndroidDir "gradlew.bat"
$gradleExe = $null

if ($localGradle) {
    $gv = Get-GradleVersion $localGradle
    if ($gv[0] -gt 8 -or ($gv[0] -eq 8 -and $gv[1] -ge 9)) {
        Ok "Gradle $($gv[0]).$($gv[1])（$localGradle）"
        $gradleExe = $localGradle
    } else {
        Warn "本地 Gradle $($gv[0]).$($gv[1]) 低于 8.9，AGP 8.7 需要 8.9+：$localGradle"
    }
}
if (-not $gradleExe -and (Test-Path $wrapperBat)) {
    Ok "使用 gradle wrapper：$wrapperBat"
    $gradleExe = $wrapperBat
}
if (-not $gradleExe) {
    Fail ("未找到可用的 Gradle 8.9+。三种解决方式（任选其一）：`n" +
          "   A) 下载 gradle-8.9-bin.zip 解压到 D:\Work\AndroidTools\gradle-8.9（脚本自动识别）`n" +
          "      官方： https://services.gradle.org/distributions/gradle-8.9-bin.zip`n" +
          "      国内： https://mirrors.cloud.tencent.com/gradle/gradle-8.9-bin.zip`n" +
          "              https://repo.huaweicloud.com/gradle/gradle-8.9-bin.zip`n" +
          "      然后重跑本脚本，或显式指定：build_apk.bat -GradleHome <解压目录>`n" +
          "   B) 用 Android Studio 打开 android\ 目录后 Sync，IDE 会生成 wrapper；`n" +
          "   C) 任意已有的 Gradle 8.9+ 在本目录执行：gradle wrapper --gradle-version 8.9 --distribution-type bin")
}

# ---------- 5) 代理 / 镜像参数 ----------
$proxyAddr = $Proxy
if (-not $proxyAddr) { $proxyAddr = $env:SHUATI_PROXY }
if (-not $proxyAddr) { $proxyAddr = $env:HTTPS_PROXY }
if (-not $proxyAddr) { $proxyAddr = $env:HTTP_PROXY }
if (-not $proxyAddr) {
    $ie = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" -ErrorAction SilentlyContinue
    if ($ie -and $ie.ProxyEnable -eq 1 -and $ie.ProxyServer -and ("$($ie.ProxyServer)" -match "(\d+\.\d+\.\d+\.\d+:\d+)")) {
        $proxyAddr = $Matches[1]
        Info "检测到系统代理：$proxyAddr（用 -Proxy 可覆盖）"
    }
}
$gradleArgs = @()
if ($proxyAddr) {
    $proxyAddr = $proxyAddr -replace "^https?://", ""
    $parts = $proxyAddr -split ":", 2
    if ($parts.Count -eq 2) {
        $gradleArgs += "-Dhttp.proxyHost=$($parts[0])", "-Dhttp.proxyPort=$($parts[1])"
        $gradleArgs += "-Dhttps.proxyHost=$($parts[0])", "-Dhttps.proxyPort=$($parts[1])"
        $gradleArgs += "-Dhttp.nonProxyHosts=localhost|127.0.0.1|0.0.0.0"
        Ok "Gradle 走代理：$proxyAddr"
    } else {
        Warn "代理格式应为 host:port，已忽略：$proxyAddr"
    }
}
if ($CnMirrors) {
    # -D 供 settings.gradle.kts 用 System.getProperty 读取，-P 作为通用项目属性兜底
    $gradleArgs += "-DcnMirrors=true", "-PcnMirrors=true"
    Ok "启用国内镜像（阿里云 google / central / gradle-plugin）"
}

Push-Location $AndroidDir
try {
    # 有本地 Gradle 且缺 wrapper 时，顺手补一份 wrapper（离线操作，方便别人用 Android Studio 打开）
    if ($localGradle -and -not (Test-Path $wrapperBat)) {
        Info "生成 gradle wrapper（gradlew.bat / gradle-wrapper.jar）…"
        & $gradleExe wrapper --gradle-version 8.9 --distribution-type bin | Out-Null
        if (Test-Path $wrapperBat) { Ok "wrapper 已生成" } else { Warn "wrapper 生成失败（不影响本次构建）" }
    }

    # ---------- 6) 版本号（取最近 tag + 提交数） ----------
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

    # ---------- 7) 生成 Python 源码 + 种子 ----------
    if (-not $SkipPrepare) {
        Info "生成 Python 源码/种子 …"
        & python (Join-Path $AndroidDir "prepare_python_src.py")
        if ($LASTEXITCODE -ne 0) { Fail "prepare_python_src.py 失败" }
    }
    & python (Join-Path $AndroidDir "prepare_python_src.py") --check
    if ($LASTEXITCODE -ne 0) { Fail "staging 校验失败" }

    # ---------- 8) 构建 ----------
    $tasks = @()
    if ($Clean) { $tasks += "clean" }
    $tasks += $Task
    Write-Host "=== 开始 Gradle 构建（首次会下载 Gradle 发行包与 Chaquopy 组件）===" -ForegroundColor Cyan
    Write-Host "  $gradleExe $($gradleArgs -join ' ') $($tasks -join ' ') --no-daemon" -ForegroundColor DarkGray
    & $gradleExe @gradleArgs @tasks --no-daemon
    if ($LASTEXITCODE -ne 0) {
        Fail ("Gradle 构建失败。常见原因与对策：`n" +
              "   · 依赖下载失败/超时 → 加代理或镜像重跑：build_apk.bat -Proxy 127.0.0.1:7897 -CnMirrors`n" +
              "   · 提示 SDK 许可未接受 → sdkmanager --licenses（走代理时加 --proxy=http --proxy_host=127.0.0.1 --proxy_port=7897）`n" +
              "   · 想看详细堆栈 → 手动执行：`"$gradleExe`" $Task --no-daemon --stacktrace")
    }

    # ---------- 9) 复制产物 ----------
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
