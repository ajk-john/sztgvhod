@file:Suppress("UnstableApiUsage")

import com.android.build.gradle.internal.api.BaseVariantOutputImpl
import com.android.build.gradle.tasks.PackageAndroidArtifact

plugins {
    alias(libs.plugins.agp.app)
    alias(libs.plugins.kotlin)
    alias(libs.plugins.compose.compiler)
    alias(libs.plugins.ksp)
    alias(libs.plugins.lsplugin.apksign)
    id("kotlin-parcelize")
}

val managerVersionCode: Int by rootProject.extra
val managerVersionName: String by rootProject.extra

val isPrBuild = findProperty("IS_PR_BUILD")?.toString()?.toBoolean() == true
val defaultManagerPackageName = if (isPrBuild) "com.shdmmztfcqk.uyopucyly.pr" else "com.shdmmztfcqk.uyopucyly"
val defaultManagerName = if (isPrBuild) "Toolbox PR" else "Toolbox"
val managerPackageName = findProperty("KSU_PACKAGE_NAME")?.toString() ?: defaultManagerPackageName
val managerName = findProperty("KSU_NAME")?.toString() ?: defaultManagerName
// GitHub "owner/repo" whose releases the manager checks for updates; empty disables the check
val managerUpdateRepo = findProperty("KSU_UPDATE_REPO")?.toString() ?: System.getenv("KSU_UPDATE_REPO") ?: ""

apksign {
    storeFileProperty = "KEYSTORE_FILE"
    storePasswordProperty = "KEYSTORE_PASSWORD"
    keyAliasProperty = "KEY_ALIAS"
    keyPasswordProperty = "KEY_PASSWORD"
}

android {
    namespace = "io.bpaqxkj.cbpr"

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    buildFeatures {
        aidl = true
        buildConfig = true
        resValues = true
        compose = true
        prefab = true
    }

    defaultConfig {
        applicationId = managerPackageName

        buildConfigField("boolean", "IS_PR_BUILD", isPrBuild.toString())
        buildConfigField("String", "UPDATE_REPO", "\"${managerUpdateRepo.replace("\"", "\\\"")}\"")
        resValue("string", "app_name", managerName)
    }

    kotlinOptions {
        jvmTarget = "21"
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
        resources {
            // https://stackoverflow.com/a/58956288
            // It will break Layout Inspector, but it's unused for release build.
            excludes += "META-INF/*.version"
            // https://github.com/Kotlin/kotlinx.coroutines?tab=readme-ov-file#avoiding-including-the-debug-infrastructure-in-the-resulting-apk
            excludes += "DebugProbesKt.bin"
            // https://issueantenna.com/repo/kotlin/kotlinx.coroutines/issues/3158
            excludes += "kotlin-tooling-metadata.json"
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
        }
    }

    applicationVariants.all {
        outputs.forEach {
            val output = it as BaseVariantOutputImpl
            output.outputFileName = "Toolbox_${managerVersionName}_${managerVersionCode}-$name.apk"
        }
        kotlin.sourceSets {
            getByName(name) {
                kotlin.srcDir("build/generated/ksp/$name/kotlin")
            }
        }
    }

    // https://stackoverflow.com/a/77745844
    tasks.withType<PackageAndroidArtifact> {
        doFirst { appMetadata.asFile.orNull?.writeText("") }
    }

    dependenciesInfo {
        includeInApk = false
        includeInBundle = false
    }

    bundle {
        language {
            enableSplit = false
        }
    }

}

ksp {
    arg("compose-destinations.defaultTransitions", "none")
}

tasks.register<Copy>("mergeScripts") {
    into("${project.projectDir}/src/main/resources/META-INF/com/google/android")
    from(rootProject.file("scripts/update_binary.sh")) {
        rename { "update-binary" }
    }
    from(rootProject.file("scripts/updater_script.sh")) {
        rename { "updater-script" }
    }
}

tasks.named("preBuild") {
    dependsOn("mergeScripts")
}

dependencies {
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.navigation.compose)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.material.icons.extended)
    implementation(libs.androidx.compose.material)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)

    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)

    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.viewmodel.compose)

    implementation(libs.compose.destinations.core)
    ksp(libs.compose.destinations.ksp)

    implementation(libs.com.github.topjohnwu.libsu.core)
    implementation(libs.com.github.topjohnwu.libsu.service)
    implementation(libs.com.github.topjohnwu.libsu.io)

    implementation(libs.dev.rikka.rikkax.parcelablelist)

    implementation(libs.io.coil.kt.coil.compose)

    implementation(libs.kotlinx.coroutines.core)

    implementation(libs.me.zhanghai.android.appiconloader.coil)

    implementation(libs.sheet.compose.dialogs.core)
    implementation(libs.sheet.compose.dialogs.list)
    implementation(libs.sheet.compose.dialogs.input)

    implementation(libs.markdown)
    implementation(libs.androidx.webkit)

    implementation(libs.lsposed.cxx)

    implementation(libs.mmrl.ui)
    implementation("androidx.biometric:biometric:1.4.0-beta01")
}