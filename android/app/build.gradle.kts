import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

// 版本号由 android/build_apk.ps1 写入 version.properties（取最近 git tag + 提交数）
val versionProps = Properties().apply {
    val f = rootProject.file("version.properties")
    if (f.exists()) FileInputStream(f).use { load(it) }
}
// 可选：release 签名（keystore.properties 已被 .gitignore 忽略）
val keystoreProps = Properties().apply {
    val f = rootProject.file("keystore.properties")
    if (f.exists()) FileInputStream(f).use { load(it) }
}

android {
    namespace = "com.hmbingzhou.shuati"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.hmbingzhou.shuati"
        minSdk = 24
        targetSdk = 35
        versionCode = (versionProps.getProperty("versionCode") ?: "1").toInt()
        versionName = versionProps.getProperty("versionName") ?: "1.0"

        // 只打包 64 位 ARM（现代手机；Python 3.12+ 不支持 32 位）
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    // MainActivity 需要读取 BuildConfig.VERSION_NAME（AGP 8 默认关闭该特性）
    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            isShrinkResources = false
        }
    }

    if (keystoreProps.getProperty("storeFile") != null) {
        signingConfigs {
            create("release") {
                storeFile = rootProject.file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
        buildTypes.getByName("release") {
            signingConfig = signingConfigs.getByName("release")
        }
    }

    packaging {
        resources.excludes += setOf("META-INF/*.kotlin_module")
    }
}

chaquopy {
    defaultConfig {
        // 与构建机 python 主次版本一致（本机为 Python 3.14）
        version = "3.14"
        buildPython("python")
    }
}
