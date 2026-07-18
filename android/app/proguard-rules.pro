# Ядро Xray (gomobile) — не обфусцируем, вызывается по именам из нативного слоя
-keep class libv2ray.** { *; }
-keep class go.** { *; }
-dontwarn libv2ray.**
-dontwarn go.**

# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.**
-keepclassmembers class com.nexonvpn.app.** {
    *** Companion;
}
-keepclasseswithmembers class com.nexonvpn.app.data.remote.** {
    kotlinx.serialization.KSerializer serializer(...);
}
