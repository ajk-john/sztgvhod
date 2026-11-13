# KernelSU-Next DIY 指南（Toolbox）

本分支是在上游 **KernelSU-Next**（`dev` 分支基线）基础上定制的私有 DIY 构建，目标是在保留全部核心功能的前提下：

1. **包名 / 命名空间 / 原生库去品牌化**：把对外可见的包名、Kotlin/AIDL/JNI 命名空间、原生 JNI 与守护进程 `.so` 名称、应用名与桌面图标替换成随机中性标识；
2. **自持签名闭环**：由你本地生成的密钥对管理 APK 签名，并通过内核态 `KSU_NEXT_MANAGER_SIZE` / `KSU_NEXT_MANAGER_HASH` 严格绑定，且仅接受 APK Signature Scheme v2；
3. **自动归档与提交防泄漏**：禁用 `v*` 标签自动公开 Release，启用 `.githooks/pre-commit` 与 `diy/ksu_diy.py` 一致性校验，并用 `diy/fetch_builds.py` 将 GitHub Actions 产物拉回本地 `builds/`。

> 与通用 DIY 脚本的兼容说明：如果其它文档、agent 约定只关注“包名、证书、命名空间、纯 v2 签名”，这些核心约束在本仓库完全适用；以下参数表为 **本仓库（KernelSU-Next DIY）** 的实际生效配置。

---

## 当前公开配置

| 项目 | 正式构建（`dev` / `main` / 手动） | PR 构建（`pull_request`） |
|---|---|---|
| 管理器应用名（`app_name`） | `Toolbox` | `Toolbox PR` |
| APK 文件名前缀 | `Toolbox_` | `Toolbox_` |
| 管理器包名（`KSU_MANAGER_PACKAGE` / `KSU_PACKAGE_NAME`） | `com.shdmmztfcqk.uyopucyly` | `com.shdmmztfcqk.uyopucyly.pr` |
| 代码命名空间（`namespace` / Java / AIDL / JNI） | `io.bpaqxkj.cbpr` | `io.bpaqxkj.cbpr` |
| JNI 原生库名（`CMakeLists.txt` / `System.loadLibrary`） | `libdsorft.so`（target `dsorft`） | `libdsorft.so`（target `dsorft`） |
| 内嵌守护进程库名（`jniLibs`） | `libmbksab.so` | `libmbksab.so` |
| 签名证书主题 | `CN=Toolbox DIY`（有效期 30 年） | 每次 PR 运行临时生成的 JKS |
| `KSU_NEXT_MANAGER_SIZE` | `0x0313`（787 字节） | `generate-key` 作业实时提取 |
| `KSU_NEXT_MANAGER_HASH` | `cb785cce3d6e9bd893b17d019fa0ca71d4122d9dabfa5302fb280cd20886f1a6` | `generate-key` 作业实时提取 |
| 公钥证书文件（已入库） | `diy/manager-cert.pem` | 临时密钥，不入库 |
| 自动更新检查（`KSU_UPDATE_REPO`） | 默认空字符串（禁用请求） | 默认空字符串（禁用请求） |

---

## 各文件改动清单

| 模块 | 路径 | 改动内容 |
|---|---|---|
| 内核模块配置 | `kernel/Kbuild` | 新增 `KSU_IS_PR_BUILD ?= 0`，在 `ifndef KSU_MANAGER_PACKAGE` 下默认设为 `com.shdmmztfcqk.uyopucyly`（PR 为 `.pr`）；更新 `KSU_NEXT_MANAGER_SIZE := 0x0313` 与 `KSU_NEXT_MANAGER_HASH` |
| 内核接入脚本 | `kernel/setup.sh` | 克隆仓库支持 `KSU_REPO_URL="${KSU_REPO_URL:-https://github.com/$OWNER/$REPO}"` |
| `ksud` 构建配置 | `userspace/ksud/build.rs` | 声明 `cargo:rerun-if-env-changed=KSU_PACKAGE_NAME`，未指定时默认 `com.shdmmztfcqk.uyopucyly` |
| `ksud` 命令行/热加载 | `userspace/ksud/src/cli.rs`、`late_load.rs` | 3 处默认包名改用 `env!("KSU_PACKAGE_NAME")`，热加载拉起组件改为 `{package_name}/io.bpaqxkj.cbpr.ui.HomeActivity` |
| 管理器构建配置 | `manager/settings.gradle.kts`、`manager/app/build.gradle.kts`、`manager/app/proguard-rules.pro` | `rootProject.name = "Toolbox"`；`namespace = "io.bpaqxkj.cbpr"`；动态注入 `IS_PR_BUILD`、`UPDATE_REPO`、`app_name`；APK 输出改为 `Toolbox_*.apk`；保留 `Natives` / `Natives$Profile` 混淆规则 |
| 管理器源码与 AIDL/JNI | `manager/app/src/main/java/io/bpaqxkj/cbpr/...`、`aidl/io/bpaqxkj/cbpr/IAppInterface.aidl`、`cpp/{CMakeLists.txt,jni.cc}` | 全量迁移 62 个 Java/Kotlin 文件，重命名 `App` / `HomeActivity` / `WebActivity` / `ui/AppService` / `AppTheme` / `IAppInterface`；C++ target 与日志 tag 改为 `dsorft` / `"Manager"`；清理硬编码品牌字面量并改为 `app://webui/` |
| 管理器清单与资源 | `manager/app/src/main/AndroidManifest.xml`、`res/...` | 更新组件类名与主题 `Theme.App` / `Theme.App.WebUI`；替换中性矢量工具箱图标；删除 15 个 `mipmap-*/ic_launcher*.png` 和所有 `values*/strings.xml` 的 `app_name`；删除 `manager/spoof`；更新 `shortcuts.xml` 与 `jniLibs/.gitignore`、`update_binary.sh` |
| CI 工作流 | `.github/workflows/{build-manager,build-manager-ci,build-lkm,ddk-lkm-ksu,ksud,release}.yml` | 移除 `spoofed` 矩阵；PR 增加 `generate-key` 作业传递临时密钥给 LKM 和 `ksud`；`apksigner` 强制纯 v2 重签并校验；执行 `ksu_diy.py check` 与 `--apk` 检查；禁用 `release.yml` tag push 自动发版 |
| 本地脚本与防线 | `build.sh`、`justfile`、`.githooks/pre-commit`、`.gitignore`、`diy/` | 同步 `libmbksab.so` 与 `Toolbox_*.apk`；拦截敏感密钥、上游包名与其它 fork 标识符误提交；忽略 `.diy-secrets/` 与 `builds/` |

---

## 本地密钥与 GitHub Secrets 配置

> ⚠️ **严禁提交密钥**：`.diy-secrets/`、`*.jks`、`*.p12`、`*.pfx`、`*.keystore` 均被 `.gitignore` 和 `.githooks/pre-commit` 双重拦截。**绝不要**把口令、key alias 密文、私钥或 keystore base64 写进仓库文件、commit 信息或对话文档。

本地 `.diy-secrets/` 目录包含（仅供本机保管与填写 GitHub Secrets）：

- `.diy-secrets/manager.p12`：PKCS12 签名密钥库（`CN=Toolbox DIY`）
- `.diy-secrets/KEYSTORE.base64.txt`：`manager.p12` 的纯文本 base64 编码
- `.diy-secrets/manager-cert.pem`：导出的 PEM 公钥证书（公开副本已入库为 `diy/manager-cert.pem`）
- `.diy-secrets/manager-cert.der`：导出的 DER 公钥证书（787 字节 / `0x0313`）
- `.diy-secrets/signing.properties`：本地签名属性参考（字段为 `KEYSTORE_FILE`、`KEYSTORE_PASSWORD`、`KEY_ALIAS`、`KEY_PASSWORD`）

在你的私有 GitHub 仓库 **Settings → Secrets and variables → Actions → Repository secrets** 中填入以下 4 个 Secret：

| Secret 名称 | 来源（来自本机 `.diy-secrets/`，勿泄露原文） |
|---|---|
| `KEYSTORE` | `.diy-secrets/KEYSTORE.base64.txt` 的完整内容 |
| `KEYSTORE_PASSWORD` | `.diy-secrets/signing.properties` 中的 `KEYSTORE_PASSWORD` |
| `KEY_ALIAS` | `.diy-secrets/signing.properties` 中的 `KEY_ALIAS` |
| `KEY_PASSWORD` | `.diy-secrets/signing.properties` 中的 `KEY_PASSWORD` |

---

## 为什么必须「纯 v2」签名

`kernel/manager/apk_sign.c` 在内核态直接解析管理器 APK 末尾的 APK Signing Block：

- 仅接受 **APK Signature Scheme v2（block ID `0x7109871a`）**，除 verity padding（`0x42726577`）外拒绝任何额外签名块（v3、v3.1、source stamp、dependency info 等）；
- 拒绝 ZIP64 APK，要求证书 DER 长度不超过 `1024` 字节（当前为 `787` 字节 = `0x0313`）；
- CI 在 `./gradlew assembleRelease` 后会显式使用 Android SDK `apksigner` 执行：
  `--v1-signing-enabled false --v2-signing-enabled true --v3-signing-enabled false --v4-signing-enabled false`
  并用 `apksigner verify --verbose` 和 `diy/ksu_diy.py check --apk` 双重校验。

---

## 本地日常工具与校验

### 1. 启用 pre-commit 钩子（每次克隆后执行一次）

```sh
git config core.hooksPath .githooks
```

> Windows 提示：如在 Windows 下修改或初次暂存 `.githooks/pre-commit`，请执行 `git update-index --chmod=+x .githooks/pre-commit` 保持可执行权限位（`100755`）。

### 2. 运行 DIY 一致性自检（Windows 下优先使用 `python`）

```sh
python diy/ksu_diy.py info
python diy/ksu_diy.py check
python diy/ksu_diy.py verify-namespace
python diy/ksu_diy.py cert-info diy/manager-cert.pem
python diy/ksu_diy.py check --apk path/to/Toolbox_xxx-release.apk
```

### 3. 需要轮换包名 / 证书 / 命名空间时

```sh
python diy/ksu_diy.py set-package com.new.randompkg
python diy/ksu_diy.py set-cert path/to/new-cert.pem
python diy/ksu_diy.py set-namespace io.new.randns
python diy/ksu_diy.py check
```

### 4. 从 GitHub Actions 拉取并归档构建产物

GitHub Actions 产物默认最多保留 90 天。每次 CI 构建完成后，在已登录 `gh` CLI 的机器执行：

```sh
python diy/fetch_builds.py              # 拉取 main / dev 上未归档的成功构建
python diy/fetch_builds.py --run <id>    # 仅拉取/重存指定 Actions run ID
python diy/fetch_builds.py --index-only # 仅重新生成 builds/README.md
```

产物保存在被 git 忽略的 `builds/<versionCode>-<sha8>/`，内含管理器 APK、全部 KMI 的 KernelSU LKM 与 SuSFS LKM、`ksud`、`ksuinit`、`mappings-<code >.zip`、`SHA256SUMS.txt`、`build.json` 和 `BUILD_INFO.md`。

---

## 刷机与匹配原则

- **管理器与内核 / LKM 必须成对来自同一次（或同一包名 + 证书配置的）构建**。
- LKM 模式需同时确认设备的 KMI（例如 `android14-6.1`）并使用对应的 `lkm-aarch64-<kmi>_kernelsu.ko`（如需 SuSFS 则搭配对应 `lkm-aarch64-<kmi>_susfs_guard_lkm.ko`），或使用同次构建产物中的 `ksud` 修补 `boot` / `init_boot`。

---

## 合并上游更新建议流程

1. 先拉取上游 `KernelSU-Next` 变更并解决代码冲突（尤其关注 `kernel/Kbuild`、`userspace/ksud/src/{cli.rs,late_load.rs}`、`manager/app/`）。
2. 如上游新增了原包名、类名或旧服务/界面引用，可先运行 `python diy/ksu_diy.py set-namespace io.bpaqxkj.cbpr` / `set-package com.shdmmztfcqk.uyopucyly`，再运行 `python diy/ksu_diy.py check`。
3. 推送到私有仓库触发 `Build Manager CI`，构建成功后用 `python diy/fetch_builds.py` 拉取并校验证书与 APK 内容。
