# 输入合同

## 最低输入

开始生产标题前必须同时具备：

1. `target_platform`：天猫、京东、拼多多、抖店，或用户给出的其他国内货架平台；
2. `product_name_or_original_title`：商品名称或原标题；
3. `product_facts`：足以确认商品是什么的事实，至少能区分核心类目和商品形态。

缺少最低输入时，不要凭图片背景、示例词或常识补成完整商品。能往返时只问最高价值缺口；不能往返时标明缺口并处理安全部分。

## 可选输入

- 商品图片及图片中明确可见的信息；
- 类目、品牌归属、属性、规格、型号、数量、套装内容、材质、工艺、功能、适用场景和卖点；
- 搜索词排行，以及指标名称、窗口、范围、采集时间和排名方向；
- 竞品标题、竞品类目和竞品是否同款/相似款；
- 主打词、必留词、禁用词；
- 原标题及希望保留的既有流量词组；
- 本次明确写法与已获准使用的偏好 profile。

## 事实分层

| 层级 | 定义 | 能否直接进入标题 |
|---|---|---|
| 已确认 | 用户明确提供、可靠商品资料明确载明、图片清晰可见且无需资质推断 | 可以，仍需做合规检查 |
| 合理推断 | 从类目、图片或上下文推得，但存在其他合理解释 | 默认不作为精确属性；可用于追问和排序说明 |
| 待确认 | 需要资质、授权、精确参数、特殊产地/工艺或强功能证据 | 确认前不得进入标题 |

简单模式只记录最终标题使用词、必留/禁用词和被拒绝的高风险词；深度模式再记录全部候选词的 `term / fact_status / source_type / source_location / category_match / risk / note`。提示词示例、模型常识和其他商品资料都不是当前商品词源。

## 校验输入 schema

每个候选至少提供非空字符串 `platform`、`title`，以及非空列表 `title_core_terms`、`keyword_sources`。`title_core_terms` 是候选实际使用的事实词组清单，不是抽样清单；不得通过省略字段、空列表或只登记低风险词绕过检查。每条 `keyword_sources` 至少有非空的 `term / status / source`，`term` 与候选词组对应；`status` 仅接受校验器声明的已确认状态才可放行。

提供原标题时，额外传入非空 `original_title` 和 `revision` 对象。`revision.mode` 只能是：`keep`（原样保留）、`micro_edit`（微调）或 `rebuild`（受限重构）。`keep` 的最终标题必须与原标题完全一致；`micro_edit` 必须保留原标题未声明删除内容的相对顺序。确需删除时，`revision.removals` 使用 `{term, reason_code}` 对象列表，理由仅限 `duplicate / forbidden_term / unverified_attribute / platform_hard_conflict`。`rebuild` 只用于原标题不合格且微调无法修复的情况，并须提供 `revision.reason_code`：`platform_hard_conflict / required_term_conflict / risk_conflict / original_structure_unusable`。不得把“想优化”“想换排序”作为删除或重构理由。

`required_terms / forbidden_terms / unverified_attributes / repeat_sensitive_terms` 若出现必须是字符串列表；`current_requirements / context` 必须是对象；`preference_profiles / trend_claims / competitor_claims` 必须是对象列表。字段或元素类型错误、空词源、重复词源均 fail-closed。当前用户硬约束只允许校验器明确支持的字段，未知硬约束不能静默忽略。

## 搜索数据可比性

只有指标定义、统计范围、时间粒度、排名方向和采集方式均一致时，才比较两个窗口。7 天与 30 天窗口天然重叠，除非来源明确给出可比较含义，不要据排名差直接声称趋势。无法确认时写“口径不可比”，保留各窗口各自的静态信号。

竞品标题频次与平台搜索需求是两种证据：前者只能支持“竞品常用”，后者必须来自明确的搜索数据源。
