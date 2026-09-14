// 仓库配置：默认走官方源。
// 中国大陆网络受限时启用阿里云镜像，官方源仍作为兜底。启用方式（任选其一）：
//   * 构建脚本参数： build_apk.bat -CnMirrors
//   * 环境变量：     set SHUATI_CN_MIRROR=1
//   * Gradle 参数：  -DcnMirrors=true
//
// 说明：Chaquopy 14 起插件与运行时都发布在 Maven Central，因此不需要额外的 chaquo.com 仓库。
//       若你的环境解析 com.chaquo.python 失败，可在下面两个 repositories 块里补一行
//       maven("https://chaquo.com/maven")
pluginManagement {
    repositories {
        if (System.getenv("SHUATI_CN_MIRROR") == "1" || System.getProperty("cnMirrors") == "true") {
            maven("https://maven.aliyun.com/repository/google")
            maven("https://maven.aliyun.com/repository/central")
            maven("https://maven.aliyun.com/repository/gradle-plugin")
        }
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

val cnMirrors = System.getenv("SHUATI_CN_MIRROR") == "1" || System.getProperty("cnMirrors") == "true"

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_SETTINGS)
    repositories {
        if (cnMirrors) {
            maven("https://maven.aliyun.com/repository/google")
            maven("https://maven.aliyun.com/repository/central")
        }
        google()
        mavenCentral()
    }
}

rootProject.name = "shuati-android"
include(":app")
