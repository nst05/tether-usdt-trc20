import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("org.jetbrains.kotlin.jvm")
}

// Ядро намеренно собрано как обычный Kotlin-модуль без единой зависимости,
// кроме stdlib: те же файлы переносятся в Kotlin Multiplatform (commonMain)
// заменой плагина на org.jetbrains.kotlin.multiplatform — правки кода не нужны.
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}

tasks.withType<Test>().configureEach {
    testLogging { events("passed", "failed", "skipped") }
}
