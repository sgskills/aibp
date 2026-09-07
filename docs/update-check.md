# AIBP 检查更新契约

`3.0.7` 的检查器在 Skill 被实际调用时读取官方源码版本，仅提醒新版，不下载、安装或执行更新。主任务始终优先。它不是后台定时器，也不创建自动任务。

## 用户会看到什么

- 首次实际调用检查一次；此后距上次尝试达到 30×24 小时（2,592,000 秒）才再次检查。
- 同一安装版本的 Skill 共用检查记录，连续调用不同 Skill 不会重复联网。不同安装版本分开记录。
- 只有远端标准 `X.Y.Z` 版本严格高于本地安装版本，才在当前结果末尾添加固定的源码新版提醒和官方仓库链接。同版本、旧版本及无法确认的响应都不提醒。
- 检查失败也消耗本次检查机会，并等待下一个 30 天周期；断网时不会在每次调用中重试。
- 用户要求禁止联网、零写入，或者 Agent 没有命令执行能力时，跳过检查。缺少工具、缓存不可写、超时、无效响应等故障不阻断业务任务。

宿主 Agent 需要遵循 `SKILL.md` 中的检查入口；仅复制文件不能保证任何宿主都会执行。用户的普通回复不构成更新授权，实际更新仍由用户单独决定。`3.0.6` 的旧安装包不含此入口，不会自行获得检查功能。

## 版本与网络边界

仓库根 `VERSION` 是源码版本唯一真源。准备工具把该版本写入每个 Skill 的 `scripts/update-version.txt`，使单独解压的 Skill 也能确定自己的安装版本。

运行时只读取固定地址：

```text
https://raw.githubusercontent.com/sgskills/aibp/main/VERSION
```

地址不能由远端响应指定。仅解析版本元数据，不执行响应内容，不把响应正文显示成指令，不使用远端提供的下载地址。比较按三个数字分量进行，例如 `3.0.10` 高于 `3.0.9`；不是字符串排序。检查器最多使用 5 秒网络预算，失败静默返回主任务。

源码版本与 Release 独立：当前源码与稳定安装包均为 `3.0.7`，可从 [最新稳定版](https://github.com/sgskills/aibp/releases/latest) 下载。检查器仍以源码 VERSION 为真源；未来的源码新版提醒不承诺同时存在同版本 tag、Release 或安装包。

## 平台与缓存

| 平台 | 检查命令（从 Skill 目录运行） | 默认缓存根 |
| --- | --- | --- |
| Windows | `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check-update.ps1` | `%LOCALAPPDATA%\SGSkills\aibp` |
| macOS | `sh ./scripts/check-update.sh` | `$HOME/Library/Caches/SGSkills/aibp` |
| Linux | `sh ./scripts/check-update.sh` | `$XDG_CACHE_HOME/sgskills/aibp`；未配置时为 `$HOME/.cache/sgskills/aibp` |

缓存按安装版本分目录，不写入 Skill 安装目录。Windows 检查器兼容 PowerShell 5.1；macOS/Linux 使用系统 `sh`、`curl` 及常见命令，不要求安装 Python 或 Node.js。Python 仅用于开发测试。

检查器在联网前记录尝试时间，并处理同版本并发调用、残留锁、缓存损坏及系统时钟倒退。缓存不可用时不联网；未来时间记录采用保守处理，避免时钟变化导致反复检查。状态不是用户业务数据，不上传本地文件或任务内容。

## 文件契约与新增 Skill

统一模板位于 `tools/update-check/`：`check-update.ps1`、`check-update.sh`、`skill-entry.md`。维护者修改模板后，用准备工具同步生成副本；不要分别手改各 Skill 的受管内容。

每个直属 `skills/<slug>/SKILL.md` 必须包含受管的检查入口，且同目录具备：

```text
scripts/check-update.ps1
scripts/check-update.sh
scripts/update-version.txt
```

新增 Skill 的正常流程为：

1. 在 `skills/<slug>` 建立合规 Skill，保持平铺结构。
2. 从仓库根运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\sync-update-check.ps1`。
3. 运行 `AGENTS.md` 的全部检查，再运行 `tools/build.ps1`。
4. 审查实际差异、测试和构建结果后，按已授权范围同步源码；发布安装包需单独的发布流程。

准备、验证和构建都动态枚举 `skills/*/SKILL.md`，不维护固定名称或数量。验证和构建故意不调用准备工具：遗漏任一必需文件、入口不完整、安装版本不一致或副本偏离模板时，直接失败，避免漏配置进入仓库或安装包。未来的新 Skill 使用同一流程，无需另外提醒修改清单。

每个单独 ZIP 都携带完整运行文件，总包包含所有动态发现的 Skill。检查不依赖 `tools/` 或其他 Skill，测试证明从仓库外隔离解压后仍可执行。开发测试、缓存、备份及 `.work/` 不进入安装包。

## 验证与回滚

更新检查测试用可注入时间与本地传输替身，覆盖首次、未满/恰满 30 天、新版/同版/旧版、跨位数版本、非法响应、断网、超时、损坏缓存、时钟倒退、并发与不可写缓存；不依赖真实 GitHub 网络。替身不得代替版本比较、日期判断、validator 或 build。

动态纳入测试先加入缺检查文件的新 Skill，验证和构建必须非零退出；补齐后自动进入单包和总包。还要验证缺入口、模板漂移、版本漂移、独立包内容和可复现构建。已有业务测试保持原有断言，版本显示断言随展示版本严格同步。

Windows CI 运行完整检查，macOS/Linux CI 运行原生检查器行为测试。通过情况以对应提交的实际测试日志为准；静态检查、脚本回归和真实 Agent 输出对照分别记录，不能相互代替。

实施期间的备份、进度与失败证据保存在 `.work/3.0.7/`，不得提交或打包。回滚仅恢复本轮确认范围内的文件和构建产物，保留其他人的改动；恢复后重新运行验证，不重写已发布的历史。
