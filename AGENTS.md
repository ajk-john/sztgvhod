# AGENTS.md

## DIY fork：先读这一节

本仓库是 **KernelSU-Next** 的私有 DIY 分支（主工作分支为 `dev`，CI 监听 `main` 与 `dev`），面向多 agent / 本地工具链共用。完整定制说明见 [DIY.md](DIY.md)，当前进度与本机环境交接见 [diy/HANDOFF.md](diy/HANDOFF.md)。

### 公开配置参数（可写在代码与文档中的公开标识符）

| 参数 | 值 |
|---|---|
| 管理器包名 (`KSU_MANAGER_PACKAGE` / `KSU_PACKAGE_NAME`) | `com.shdmmztfcqk.uyopucyly`（PR 为 `com.shdmmztfcqk.uyopucyly.pr`） |
| 管理器应用名 | `Toolbox`（PR 为 `Toolbox PR`），APK 前缀 `Toolbox_` |
| 代码命名空间 | `io.bpaqxkj.cbpr`（`io/bpaqxkj/cbpr`，JNI `io_bpaqxkj_cbpr`） |
| JNI 原生库 | `libdsorft.so`（CMake target `dsorft`） |
| 内嵌守护进程库 | `libmbksab.so` |
| 证书大小与 SHA-256（`kernel/Kbuild`） | `KSU_NEXT_MANAGER_SIZE = 0x0313`（787 字节），`KSU_NEXT_MANAGER_HASH = cb785cce3d6e9bd893b17d019fa0ca71d4122d9dabfa5302fb280cd20886f1a6` |
| 公开证书文件 | `diy/manager-cert.pem`（`CN=Toolbox DIY`） |

### 硬性红线（所有修改必须遵守）

1. **绝不泄露或提交签名材料**：`.diy-secrets/`、`*.jks`、`*.p12`、`*.pfx`、`*.keystore` 以及其中的密码、alias、keystore base64 原文禁止写入任何被跟踪文件、commit 或对话产物。
2. **绝不引入上游或其它 fork 标识**：禁止在交付代码、配置或文档中留下上游原始包名、原 APK 文件名前缀、原版 JNI / 守护进程 `.so` 名称、`KernelSUApplication`、`WebUIActivity`、`KsuService`、`KernelSUTheme` 或其它 DIY fork 的随机标识符。
3. **APK 必须纯 v2 签名**：`kernel/manager/apk_sign.c` 只接受 APK Signature Scheme v2（禁用 v1/v3/v4，拒绝 ZIP64 与非 verity-padding 附加块，证书 <= 1024 字节）。CI 中已在 Gradle 后用 `apksigner` 重签并调用 `diy/ksu_diy.py check --apk` 校验。
4. **保持组件对齐与无固定 app_name**：不要在 `manager/app/src/main/res/values*/strings.xml` 中恢复 `app_name`（改由 `manager/app/build.gradle.kts` 通过 `resValue` 动态生成），不要加回 `mipmap-*/ic_launcher*.png` 或 `manager/spoof`。
5. **每次改完代码必须跑一致性检查**（Windows 下使用 `python`，不要用 Store 存根 `python3`）：
   ```sh
   python diy/ksu_diy.py check
   ```
   新克隆仓库先启用 git hook：`git config core.hooksPath .githooks`。

---

## Project Overview

KernelSU-Next is a kernel-based root solution for Android GKI devices (plus LKM + SuSFS support). It consists of three main components plus DIY tooling:

- **Kernel (`kernel/`)**: Loadable kernel module (`kernelsu.ko`) and built-in kernel integration, plus `kernel/susfs/` (`susfs_guard_lkm.ko`), enforcing manager package & APK v2 signature verification in `kernel/manager/apk_sign.c`.
- **Userspace (`userspace/ksud/`, `userspace/ksuinit/`)**: Rust daemon & CLI (`ksud`, staged into manager APKs as `lib/<abi>/libmbksab.so`) and init shim (`ksuinit`).
- **Manager (`manager/`)**: Jetpack Compose Android application (`Toolbox`), packaged with `libdsorft.so` (JNI), `libadbroot.so` (`cpp/adbroot.cc`), and `libmbksab.so`.
- **DIY Tooling (`diy/`)**: `diy/ksu_diy.py` (consistency check & rotation helper), `diy/fetch_builds.py` (GitHub Actions artifact archiver), `diy/manager-cert.pem`, and `diy/HANDOFF.md`.

---

## Repository Structure

- `kernel/`: `Kbuild`, `Kconfig`, `Makefile`, `setup.sh`, `core/`, `feature/`, `hook/`, `include/`, `infra/`, `manager/`, `policy/`, `preinit/`, `runtime/`, `selinux/`, `sulog/`, `supercall/`, `susfs/`, `tools/`
- `uapi/`: Shared C headers (`app_profile.h`, `feature.h`, `ksu.h`, `selinux.h`, `sulog.h`, `supercall.h`) defining the kernel/userspace supercall & UAPI contract
- `userspace/ksud/`: Rust CLI & daemon (`src/{cli.rs, late_load.rs, apk_sign.rs, ksu_uapi.rs, ...}`, `build.rs`, `bin/{aarch64,x86_64,riscv64}/`)
- `userspace/ksuinit/`: Rust init binary
- `manager/`: Android Gradle project (`app/build.gradle.kts`, `settings.gradle.kts`, `proguard-rules.pro`)
  - `manager/app/src/main/java/io/bpaqxkj/cbpr/`: Kotlin/Java source (`App.kt`, `Natives.kt`, `ui/HomeActivity.kt`, `ui/AppService.kt`, `ui/webui/WebActivity.kt`, `ui/util/KsuCli.kt`, `ui/util/Downloader.kt`, ...)
  - `manager/app/src/main/aidl/io/bpaqxkj/cbpr/IAppInterface.aidl`
  - `manager/app/src/main/cpp/`: Native JNI (`CMakeLists.txt`, `jni.cc`, `ksu.cc`, `ksu.h`, `adbroot.cc`, plus `uapi` symlink to `../../../../../uapi`)
- `.github/workflows/`: `build-manager-ci.yml` (push/PR on `main` & `dev`), `build-manager.yml` (`workflow_dispatch`/`workflow_call`), `build-lkm.yml`, `ddk-lkm-ksu.yml`, `ddk-lkm-susfs.yml`, `ksud.yml`, `ksuinit.yml`, `release.yml` (tag push disabled)

---

## Component Workflows & Pitfalls

1. **Kernel & UAPI changes**: Kernel Kbuild variables for this codebase are `KSU_IS_PR_BUILD`, `KSU_MANAGER_PACKAGE`, `KSU_NEXT_MANAGER_SIZE`, and `KSU_NEXT_MANAGER_HASH` (`kernel/Kbuild`). Any UAPI header change in `uapi/` affects `kernel/`, `userspace/ksud/` (`src/ksu_uapi.h` / bindgen), and `manager/app/src/main/cpp/`.
2. **`manager/app/src/main/cpp/uapi` on Windows**: Checked out as a git symlink placeholder file (`../../../../../uapi`). **Never edit, delete, or overwrite `manager/app/src/main/cpp/uapi` on Windows**, or you will break the symlink in Git.
3. **`AppService` placement**: `AppService.kt` lives at `manager/app/src/main/java/io/bpaqxkj/cbpr/ui/AppService.kt` (`package io.bpaqxkj.cbpr.ui`) and runs via `libsu`'s `RootService`, so it is NOT declared as a `<service>` entry in `AndroidManifest.xml`.
4. **Local environment limits & CI builds**: Windows hosts without JDK / Android SDK / Rust NDK / Docker rely on GitHub Actions (`build-manager-ci.yml` / `build-manager.yml`) for builds. Keep all authored scripts, workflows, hooks, and docs with **LF (`\n`)** line endings.
5. **Commit discipline**: Run `python diy/ksu_diy.py check` before committing, keep secrets out of commits, and stage carefully when `.githooks/pre-commit` is active.
