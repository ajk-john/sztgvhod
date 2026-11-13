# KernelSU-Next DIY 交接记录

## 当前状态

| 项目 | 状态 |
|---|---|
| 上游仓库基线 | KernelSU-Next（`upstream`，工作/默认分支 `dev`） |
| GitHub 仓库 | Public 仓库 `ajk-john/sztgvhod`（`https://github.com/ajk-john/sztgvhod`，`origin`，默认分支 `dev`） |
| 公开参数配置 | 包名 `com.shdmmztfcqk.uyopucyly`（PR `.pr`）、命名空间 `io.bpaqxkj.cbpr`、JNI `libdsorft.so`、守护进程 `libmbksab.so`、应用名 `Toolbox`（PR `Toolbox PR`） |
| 签名证书与指纹 | `diy/manager-cert.pem`（`CN=Toolbox DIY`），`KSU_NEXT_MANAGER_SIZE=0x0313`（787 B），`KSU_NEXT_MANAGER_HASH=cb785cce3d6e9bd893b17d019fa0ca71d4122d9dabfa5302fb280cd20886f1a6` |
| 本地签名资产（`.diy-secrets/`） | 已生成 `.diy-secrets/manager.p12`、`.diy-secrets/KEYSTORE.base64.txt`、`.diy-secrets/signing.properties`、`.diy-secrets/manager-cert.pem`、`.diy-secrets/manager-cert.der`（已被 `.gitignore` 与 `.githooks/pre-commit` 忽略，**严禁提交**） |
| Git 配置与 hooks | 已配置 `core.autocrlf false`、`core.eol lf`、`core.hooksPath .githooks`、`credential.https://github.com.helper`（`gh.exe auth git-credential`）；新克隆需执行 `git config core.hooksPath .githooks`（Windows 下首次暂存 `.githooks/pre-commit` 记得执行 `git update-index --chmod=+x .githooks/pre-commit`） |
| GitHub Secrets 配置 | ✅ 已在 Public 仓库 `ajk-john/sztgvhod` 配置 4 个 Actions Secrets（`KEYSTORE`、`KEYSTORE_PASSWORD`、`KEY_ALIAS`、`KEY_PASSWORD`），待推送 `dev` 分支验证 CI 构建 |
| 本地 CI 产物拉取 | ⏳ 待首次 CI 成功运行后执行 `python diy/fetch_builds.py` 归档至 `builds/` |

---

## 已定决策

1. **纯 v2 APK 签名策略**：`kernel/manager/apk_sign.c` 严格校验单个 v2 签名块、拒绝 ZIP64/v3/v3.1/附加元块及 >1024 B 证书；Gradle 打包后在 CI 使用 Android SDK `apksigner` 仅开启 v2 重签并配合 `diy/ksu_diy.py check --apk` 验证。
2. **移除 `spoofed` 变体与矩阵**：删除 `manager/spoof` 与 `build-manager*.yml` 中的 `spoofed` 双倍矩阵，统一直接产出单套去品牌产物（`Toolbox_*.apk`、`manager`、`mappings`）。
3. **动态 `app_name` 与中性图标**：删除所有 24 份 `values*/strings.xml` 中的 `app_name` 与 15 份 `mipmap-*/ic_launcher*.png`，改由 `manager/app/build.gradle.kts` 动态 `resValue("string", "app_name", managerName)`，并用矢量 `ic_launcher_foreground.xml` / `ic_launcher_monochrome.xml` + `#FF1E110D` 渲染自适应图标。
4. **禁用自动公开 Release 与更新请求**：`release.yml` 取消 `v*` tag push 自动触发（保留 `workflow_dispatch`）；`BuildConfig.UPDATE_REPO` 默认空字符串以禁止 `Downloader.kt` 联网检查上游更新。
5. **与 `20-kernelSU-diy` 彻底隔离**：独立随机生成包名、命名空间、库名、密钥对和 `CN=Toolbox DIY` 证书，且由 `pre-commit` 与 `ksu_diy.py check` 防止任何参数串扰。

---

## 本机环境说明

- **操作系统**：Windows（本仓库局部 Git 配置为 `core.autocrlf false`、`core.eol lf`、`core.hooksPath .githooks`，以及 `credential.https://github.com.helper` 指向 `C:/Users/13160/bin/gh.exe`；新建或维护脚本/文档请保持 LF `\n`）。
- **Python**：使用 `python`（Python 3）；Windows 下 `python3` 可能是 Microsoft Store 占位存根。
- **构建工具链**：本机未安装 JDK / Android SDK / Rust NDK / Docker，编译构建与 APK/LKM 签名验证统一通过 GitHub Actions 完成，再用本机 `gh` CLI + `python diy/fetch_builds.py` 拉取。
- **常用本地命令**：
  ```sh
  git config core.autocrlf false
  git config core.eol lf
  git config core.hooksPath .githooks
  git config credential.https://github.com.helper ""
  git config --add credential.https://github.com.helper "!'C:/Users/13160/bin/gh.exe' auth git-credential"
  python diy/ksu_diy.py info
  python diy/ksu_diy.py check
  python diy/ksu_diy.py cert-info diy/manager-cert.pem .diy-secrets/manager-cert.der
  python diy/fetch_builds.py
  ```

---

## 进行中 / 待办

- [ ] 提交 DIY 改造至 Public GitHub 仓库 `ajk-john/sztgvhod`（`https://github.com/ajk-john/sztgvhod`，默认分支 `dev`）前，确认 `python diy/ksu_diy.py check` 全部通过、`git status` 无 `.diy-secrets/` 或密钥库文件。
- [x] 在 Public GitHub 仓库 `ajk-john/sztgvhod` 配置以下 4 个 Repository Secrets（值取自本机 `.diy-secrets/`）：
  - `KEYSTORE`（`.diy-secrets/KEYSTORE.base64.txt` 内容）
  - `KEYSTORE_PASSWORD`（`.diy-secrets/signing.properties`）
  - `KEY_ALIAS`（`.diy-secrets/signing.properties`）
  - `KEY_PASSWORD`（`.diy-secrets/signing.properties`）
- [ ] 触发并验证 `Build Manager CI` / `Build Manager` 全流程成功（LKM 8 KMI + `ksuinit` + `ksud` + `Toolbox` APK 纯 v2 签名与 `ksu_diy.py check --apk`）。
- [ ] 运行 `python diy/fetch_builds.py` 将首个正式构建归档到 `builds/` 并校验 `SHA256SUMS.txt`。

---

## 工作日志

- **2026-11-13**：完成密钥与自签名证书生成（`CN=Toolbox DIY`，`0x0313` / `cb785cce...`），接入 `kernel/`、`userspace/ksud/`、`manager/` 全量重命名与去品牌化，配置 CI 纯 v2 重签校验流程，补全 `diy/ksu_diy.py`、`diy/fetch_builds.py` 与多 agent 统一说明文档（`DIY.md`、`AGENTS.md`、`CLAUDE.md`、`GEMINI.md`、`diy/HANDOFF.md`）。
