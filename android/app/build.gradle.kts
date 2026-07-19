import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

// Базовый URL сервера подписки (sub_page_url из админки NexonVPN).
// Задаётся в local.properties: nexon.baseUrl=https://vpn.yourdomain.com
// или через переменную окружения NEXON_BASE_URL (используется в CI).
val nexonBaseUrl: String = run {
    val fromEnv = System.getenv("NEXON_BASE_URL")
    if (!fromEnv.isNullOrBlank()) return@run fromEnv
    val lp = rootProject.file("local.properties")
    if (lp.exists()) {
        val p = Properties().apply { lp.inputStream().use { load(it) } }
        p.getProperty("nexon.baseUrl")?.takeIf { it.isNotBlank() }?.let { return@run it }
    }
    "https://vpn.example.com"
}

android {
    namespace = "com.nexonvpn.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.nexonvpn.app"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        // Домен сервера подписки NexonVPN
        buildConfigField("String", "BASE_URL", "\"$nexonBaseUrl\"")
        // Идентификатор клиента, попадает в User-Agent (сервер по нему отличает VPN-клиент от браузера)
        buildConfigField("String", "CLIENT_UA", "\"NexonVPN/1.0.0 (Android)\"")

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")
        }
    }

    // Флейворы ядра:
    //  • stub — заглушка libv2ray (APK собирается всегда, туннель не работает — только UI/логика);
    //  • full — реальное ядро Xray из app/libs/libv2ray.aar + jniLibs/*/libtun2socks.so.
    flavorDimensions += "core"
    productFlavors {
        create("stub") {
            dimension = "core"
            applicationIdSuffix = ".stub"
            versionNameSuffix = "-stub"
        }
        create("full") {
            dimension = "core"
        }
    }

    signingConfigs {
        create("release") {
            // Значения подставляются в CI из secrets, локально — из keystore.properties
            val ksProps = rootProject.file("keystore.properties")
            if (ksProps.exists()) {
                val p = Properties().apply { ksProps.inputStream().use { load(it) } }
                storeFile = file(p.getProperty("storeFile"))
                storePassword = p.getProperty("storePassword")
                keyAlias = p.getProperty("keyAlias")
                keyPassword = p.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            val ksProps = rootProject.file("keystore.properties")
            if (ksProps.exists()) signingConfig = signingConfigs.getByName("release")
        }
        debug {
            applicationIdSuffix = ".debug"
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
        // tun2socks запускается как процесс из nativeLibraryDir — .so должен быть распакован
        jniLibs.useLegacyPackaging = true
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.09.03")
    implementation(composeBom)

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.activity:activity-compose:1.9.2")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.6")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.6")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.6")
    implementation("androidx.lifecycle:lifecycle-service:2.8.6")

    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.8.1")

    // Хранилище настроек (uuid устройства, подписка)
    implementation("androidx.datastore:datastore-preferences:1.1.1")

    // Сеть + JSON
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // Ядро Xray (gomobile AAR из AndroidLibXrayLite) — только для флейвора full.
    // Кладётся в app/libs/libv2ray.aar; CI собирает его перед сборкой (android.yml).
    "fullImplementation"(fileTree(mapOf("dir" to "libs", "include" to listOf("*.aar"))))

    debugImplementation("androidx.compose.ui:ui-tooling")
}
