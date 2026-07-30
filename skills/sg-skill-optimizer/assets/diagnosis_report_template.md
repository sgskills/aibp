# Skill 诊断报告：{{skill_name}}

> 生成时间：{{date}} ｜ 诊断人：sg-skill-optimizer ｜ 目标 Skill 版本：{{version}}

## 0. 优化维度锁定
- 本次主攻：☐ 结构与上下文 ☐ 触发与路由 ☐ 任务契约 ☐ 执行流程 ☐ 输出稳定 ☐ 运行稳定与故障恢复 ☐ 工具化 ☐ 评测回归 ☐ 沉淀演进 ☐ 安全边界 ☐ 可维护性
- 用户诉求原话：{{user_request}}
- 本次输入来源：{{input_source}}

## 1. 证据总览（来自 health_check.py / run_eval.py）
- 适用项静态分：{{total_score}}/100
- 证据覆盖：{{score_coverage}}%
- 等级：{{grade}}
- 回归状态：{{evaluation_state}}（MISSING / SPEC_ONLY / EXECUTABLE / VERIFIED）
- 回归通过率：{{regression_pass_rate}}
- 置信度：{{confidence}}（FULL / PARTIAL / LOW）
- 红线项：{{blocker_count}} 个
- 说明：MANUAL / N/A 项必须显式展示；静态满分不等于真实表现满分。
- 完整报告状态：{{complete_report_status}}（不得只输出总分或评级）

## 2. 诊断结论（先读这里）
- 整体判断：{{overall_judgement}}
- 优先关注维度：{{priority_dimensions}}
- 检查项分布：OK {{ok_count}} ｜ WARN {{warn_count}} ｜ FAIL {{fail_count}} ｜ MANUAL {{manual_count}} ｜ N/A {{not_applicable_count}}
- 触发冲突审计：{{skills_root_audit_status}}

| 维度 | 权重 | 得分 | 状态 | 主要证据 |
|------|------:|------:|------|----------|
| 结构与上下文健康 | 12 | {{structure_score}} | {{structure_status}} | {{structure_evidence}} |
| 触发与路由质量 | 15 | {{trigger_score}} | {{trigger_status}} | {{trigger_evidence}} |
| 任务契约清晰度 | 9 | {{contract_score}} | {{contract_status}} | {{contract_evidence}} |
| 执行流程可操作性 | 9 | {{flow_score}} | {{flow_status}} | {{flow_evidence}} |
| 输出稳定性 | 10 | {{output_score}} | {{output_status}} | {{output_evidence}} |
| 运行稳定性与故障恢复 | 10 | {{runtime_score}} | {{runtime_status}} | {{runtime_evidence}} |
| 工具化与确定性 | 8 | {{tooling_score}} | {{tooling_status}} | {{tooling_evidence}} |
| 评测与回归能力 | 10 | {{evaluation_score}} | {{evaluation_status}} | {{evaluation_evidence}} |
| 沉淀与演进 | 5 | {{iteration_score}} | {{iteration_status}} | {{iteration_evidence}} |
| 安全与边界 | 8 | {{safety_score}} | {{safety_status}} | {{safety_evidence}} |
| 可维护性 | 4 | {{maintainability_score}} | {{maintainability_status}} | {{maintainability_evidence}} |

## 3. 红线项（必须先修）
- {{blocker_1}}
- {{blocker_2}}
- {{blocker_3}}

## 4. 维度深挖
| 维度 | 问题数 | 最关键问题 | 证据 | 建议 |
|------|------:|------------|------|------|
| {{dimension}} | {{issue_count}} | {{key_issue}} | {{evidence}} | {{recommendation}} |

## 5. 触发审计（仅在提供 skills-root 时运行）
- description 字符数：{{desc_len}}（Codex 单 Skill 建议 ≤1024）
- 触发词前置：{{frontload_status}}
- 反触发词：{{anti_trigger_status}}
- 跨 Skill 触发冲突：{{trigger_conflict_status}}（无根目录时为 N/A，不扣分）
- Skills 总预算：{{budget_status}}

## 6. 安全与稳定性专项审计
| 检查项 | 状态 | 证据 | 建议 |
|--------|------|------|------|
| 真实写操作/外部发布边界 | {{write_boundary_status}} | {{write_boundary_evidence}} | {{write_boundary_recommendation}} |
| 权限确认/备份/回滚 | {{permission_status}} | {{permission_evidence}} | {{permission_recommendation}} |
| 敏感信息/账号/token/客户数据 | {{sensitive_status}} | {{sensitive_evidence}} | {{sensitive_recommendation}} |
| 幂等与可重复执行 | {{idempotency_status}} | {{idempotency_evidence}} | {{idempotency_recommendation}} |
| 工具失败/缺文件/缺权限降级 | {{fallback_status}} | {{fallback_evidence}} | {{fallback_recommendation}} |
| 依赖与前置条件 | {{dependency_status}} | {{dependency_evidence}} | {{dependency_recommendation}} |

## 7. 已做到（保持）
| 维度 | 方法 | 现状 |
|------|------|------|
| {{dimension}} | {{method}} | {{status}} |

## 8. 待优化清单（按 ROI 排序）
| 优先级 | 维度 | 问题 | 状态 | 证据 | 对应方法 | 改进动作 | 预期收益 |
|--------|------|------|------|------|----------|----------|----------|
| 🥇 | {{dimension}} | {{issue}} | {{status}} | {{evidence}} | #{{n}} | {{action}} | {{impact}} |
| 🥈 | | | | | |
| 🥉 | | | | | |

## 9. 系统化待确认执行计划
| 阶段 | 优先级 | 改动对象 | 具体动作 | 验收方式 | 状态 |
|------|--------|----------|----------|----------|------|
| 红线先修 | {{priority}} | {{target_file_or_section}} | {{action}} | {{verification}} | 待用户确认 |
| 高 ROI 修复 | {{priority}} | {{target_file_or_section}} | {{action}} | {{verification}} | 待用户确认 |
| 维度深挖 | {{priority}} | {{target_file_or_section}} | {{action}} | {{verification}} | 待用户确认 |
| 回归沉淀 | {{priority}} | {{target_file_or_section}} | {{action}} | {{verification}} | 待用户确认 |

## 10. 需人工复核 / 未运行 / N/A
- 质量合理性：{{quality_manual_note}}
- 专家判断阈值：{{decision_tree_note}}
- 敏感信息/权限边界：{{safety_manual_note}}
- 未运行检查项：{{skipped_check_note}}
- N/A 项：{{not_applicable_note}}

## 11. 确认状态与执行记录
- 用户确认状态：{{confirmation_status}}
- 待确认修改：{{pending_changes}}
- 确认后已执行：{{executed_changes}}
- Diff 摘要：{{diff_summary}}

## 12. 验证与回归
- 改后体检：`python scripts/health_check.py {{skill_dir}}`
- JSON 回归：`python scripts/health_check.py {{skill_dir}} --format json`
- 触发冲突：`python scripts/health_check.py {{skill_dir}} --skills-root {{skills_root}}`
- Golden Set：{{golden_set_plan}}
- 可执行回归：先人工确认目标 runner 可信，再运行 `python scripts/health_check.py {{skill_dir}} --verify-eval --allow-target-code`

## 13. 沉淀
- 本次踩坑/经验写入：{{patch_path}}
- 版本号更新：{{old_ver}} → {{new_ver}}
- 后续观察点：{{follow_up_metric}}
