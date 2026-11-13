# GitHub Copilot 入口

项目说明统一维护在仓库根目录的 `AGENTS.md`（所有 agent 共用），DIY 配置与操作说明维护在 `DIY.md` 和 `diy/HANDOFF.md`。开始任何工作前先阅读：

1. `AGENTS.md`：DIY fork 硬性约束（公开配置、CI 签名、禁止泄露 `.diy-secrets/` 与上游标识）及开发指南；
2. `DIY.md`：KernelSU-Next DIY（Toolbox）完整参数与校验命令（Windows 下使用 `python diy/ksu_diy.py check`，避免触发 Store 存根 `python3`；Linux/CI 下使用 `python3 diy/ksu_diy.py check`）；
3. `diy/HANDOFF.md`：当前状态、已定决策、环境与待办，结束工作前更新它。
