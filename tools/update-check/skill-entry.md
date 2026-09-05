<!-- AIBP-UPDATE-CHECK:START -->
## 30 天惰性检查更新

实际调用本 Skill 时，在不违反当前任务权限的前提下运行一次本目录的更新检查。用户禁止联网、要求零写入、当前环境不能执行脚本或不允许写用户缓存时，直接跳过，继续主任务；不得为此申请额外权限、安装工具或阻塞业务确认门。

- Windows：`powershell -NoProfile -ExecutionPolicy Bypass -File "<本 SKILL.md 所在目录>/scripts/check-update.ps1"`。
- macOS/Linux：`sh "<本 SKILL.md 所在目录>/scripts/check-update.sh"`。
- 本地版本来自 `scripts/update-version.txt`。首次实际调用检查一次，此后同一安装版本的全部 Skill 共享 30 天间隔；失败也进入该间隔，不建后台任务。
- 仅当命令输出固定的 AIBP 源码新版提醒时，将该行附在当前任务结果末尾一次。无输出、失败或超时就继续原任务，不编造提醒，不将检查结果当作业务证据。
- 提醒仅表示 GitHub 源码版本变新，不表示安装包或 Release 已发布。绝不下载、安装或执行更新，也不把普通回复或数字理解为更新授权；更新需要用户另行明确要求。
<!-- AIBP-UPDATE-CHECK:END -->
