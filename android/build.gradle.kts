// 顶层构建脚本：只声明插件版本，具体配置在 app/build.gradle.kts
// 版本矩阵（固定，避免踩坑）：
//   Android Gradle Plugin 8.7.x  →  需要 Gradle 8.9+ 与 JDK 17/21
//   Chaquopy 17.0.0              →  支持 AGP 7.3.x–9.2.x、Python 3.10–3.14、minSdk ≥ 24
plugins {
    id("com.android.application") version "8.7.3" apply false
    id("com.chaquo.python") version "17.0.0" apply false
}
