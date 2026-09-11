# 维护说明

## 当前状态

- 独立开发来源：位于 AIBP 仓库之外，由维护者单独保留
- 正式发布真源：`https://github.com/sgskills/aibp`
- 许可证：`SGSkills Internal Use License 1.0`（Source Available — Not Open Source）
- 安装版本：由 AIBP 仓库根 `VERSION` 统一生成，不使用独立 Skill 版本作为发布版本

## 更新检查适用性

`sg-review` 已确认属于 AIBP 标准 Skill，30 天惰性更新检查为必需能力：

- 只在本 Skill 被实际调用时按 `SKILL.md` 的受管入口尝试；
- 版本真源固定为 AIBP 仓库根 `VERSION`，安装版本来自 `scripts/update-version.txt`；
- 同一安装版本的 AIBP Skills 共享 30 天缓存，失败也进入间隔；
- 只提醒源码新版，不自动下载、安装、覆盖、提交或发布；
- 用户禁止联网、禁止写入或环境无法执行时跳过，不阻塞评价分析。

更新入口和运行文件由 AIBP 仓库 `tools/sync-update-check.ps1` 统一生成；不得在本 Skill 内维护另一套真源或缓存规则。

## 修改与发布

修改 Skill 时：

1. 先建立可恢复备份；
2. 在 AIBP 发布真源中更新根 `CHANGELOG.md` 和 `VERSION`；
3. 运行单元测试、Golden 和真实前向报告检查；
4. 明确区分机器回归与自然语言报告质量；
5. 迁入 AIBP 时使用清单与哈希核对，不用整目录覆盖发布副本；
6. 安装、提交、推送和发布需要各自授权。
