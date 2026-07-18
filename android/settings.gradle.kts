pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_SETTINGS)
    repositories {
        google()
        mavenCentral()
        // Локальные .aar (ядро Xray — libv2ray) кладутся в app/libs
        flatDir { dirs("app/libs") }
        maven { url = uri("https://jitpack.io") }
    }
}

rootProject.name = "NexonVPN"
include(":app")
