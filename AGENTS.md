# AIBP 仓库工作规则

## 项目定位

- AIBP 是一个平台中立的 Agent Skill 仓库，采用 Source Available（源码可查看，但非开源）许可。
- 所有 Skill 均平铺在 `skills/<slug>` 下；`core`、`ecommerce` 和 `tooling` 仅用于文档分类和能力路由。
- `ecommerce` 同时涵盖国内电商与跨境电商，不是实际的安装目录。
- 仓库版本以 `VERSION` 为唯一权威来源。

## 语言约定

- 日常沟通和面向维护者的新文档默认使用简体中文，后续维护 `3.0.8` 等版本时继续遵循。
- 命令、代码标识、文件路径、协议字段和测试数据保持其原有形式，不为中文化而改变程序行为。
- 专门提供英文对照的 `README.en.md`、许可证原文和既有作者署名块保持原样。
- 提及下一版本不代表已经升级；只有实际实施经授权的版本变更时，才同步更新版本元数据与相关文档。

## 必须执行的检查

提交前，必须在仓库根目录执行以下命令。本地临时输出保存在 `.work/3.0.7/` 内；执行前，先将测试进程的临时目录配置到该目录。使用本机可用的 Python 3 运行时，但不得将机器专属路径写入仓库。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\validator\test_validate.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\build\test_build.ps1
python -B -m unittest discover -s .\skills\sg-skill-optimizer\tests -p "test_*.py"
python -B .\skills\sg-skill-optimizer\scripts\run_eval.py
python -B .\skills\sg-skill-optimizer\scripts\health_check.py .\skills\sg-skill-optimizer
python -B .\skills\sg-skill-optimizer\scripts\audit_description.py .\skills
python -B -m unittest discover -s .\tests\sg-tmads-report -p "test_*.py"
python -B .\skills\sg-tmads-report\tests\run_regression.py
python -B -m unittest discover -s .\tests\update-check -p "test_*.py"
```

必须逐条检查外部命令的退出码，禁止用后续命令的成功掩盖此前的失败。在 Windows 上运行天猫报表回归时，设置 `PYTHONUTF8=1`。候选版本同步到 `main` 前，更新检查行为还必须通过 macOS 和 Linux 的持续集成（CI）检查。

## 构建与打包

- 不得手工修改 `dist/` 中的构建产物；必须通过 `tools/build.ps1` 重新构建。
- 验证器与构建逻辑必须动态枚举有效的 `skills/*/SKILL.md` 目录，不得硬编码当前 Skill 数量或目录名。
- 每次发布必须包含：每个动态发现的 Skill 各一个 ZIP、一个 AIBP 总包，以及 `SHA256SUMS.txt`。
- 新增或修改 Skill、更新 `VERSION` 后，运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\sync-update-check.ps1`，为所有已发现的 Skill 生成统一管理的更新检查入口和运行文件。文件、入口或版本缺失、偏离生成规范时，验证和构建必须失败，不得静默生成或修复。
- 每个独立 Skill ZIP 必须包含 `scripts/check-update.ps1`、`scripts/check-update.sh` 和 `scripts/update-version.txt`，且不依赖仓库级文件即可运行。运行文件模板位于 `tools/update-check/`；必须先修改模板，再重新生成各 Skill 中的副本。
- 构建检查必须证明：新发现的 Skill 在更新检查契约不完整时失败，补齐后自动进入全部预期产物。保留先失败、后通过的验证证据，以及确定性打包检查。

## 更新检查契约

- 远端版本只读取 `https://raw.githubusercontent.com/sgskills/aibp/main/VERSION`；仅接受标准数字版本 `X.Y.Z`，且仅在远端版本高于已安装版本时提醒。提醒表示有新版源码可用，不代表已经发布正式 Release。
- 仅在 Skill 被实际调用时运行：首次立即尝试，此后每 2,592,000 秒（30×24 小时）最多尝试一次，失败的尝试也计入间隔。已安装版本相同的 Skill 共享缓存。
- 尊重用户禁止联网、禁止写入的要求，以及环境缺少执行能力的限制。网络、缓存和工具故障不得阻塞主任务。禁止下载、安装或执行更新，也不得将用户的普通回复视为更新授权。
- 更新检查必须保持平台中立，使用 PowerShell 5.1 或 `sh`/`curl`，网络耗时预算为五秒。行为测试隔离时间与传输边界；不得用模拟替身替换日期判断、版本比较、验证器或构建逻辑。

## 边界与保护

- 保留 `LICENSE` 中限制性 Source Available 许可的原意，不得将项目描述为开源项目。
- README 中既有作者署名块必须逐字保留，不得推断或添加作者、来源、课程或贡献者。
- 面向用户的中文 Skill 名称，在能够自然表达能力时，优先使用拟人化、职业角色式表述；`sg-skill-optimizer` 显示为 `SG Skill 优化师`，而不是 `SG Skill 优化器`。
- 未经真实安装验证，不得声称与 Codex、WorkBuddy 或其他运行环境完全兼容。
- 禁止提交密钥、令牌、本机绝对路径、缓存、临时输出或 `.work/`。

## 当前状态

- `3.0.7` 是当前源码版本和稳定发布版本。官方下载链接指向该版本的四个独立包、总包及 SHA256 校验清单。历史发布版本继续保留，供回滚使用。版本仍以 `VERSION` 为准；后续发布仍须获得用户授权。
- `sg-aibp` 尚在规划中，实现之前不得提供其链接，或将其宣传为已经存在的路由入口。
