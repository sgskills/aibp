# 平台规则档案

平台规则会变化。使用 `platform-profiles.json` 作为机器可读档案，按 `platform / version / freshness / effective_date / accessed_at / scope / source / status / enforcement` 管理，不把经验口径写成全平台事实。Skill 所有者确认的经营标准单列为 `operating_defaults`，不能冒充平台官方规则，也不因官方档案到期而自动失效。

## 状态

- `hard`：有可核验当期来源且范围匹配，确定性校验失败时禁止交付；
- `advisory`：旧口径、二手旁证或官方优化建议，只提示，不冒充发布硬门槛；
- `unknown`：未取得可靠口径，不做精确合规声明，提示用户以当前商家后台为准。

平台 profile 的规则值和 `enforcement` 必须一起读取。数值存在但状态不是 `hard` 时，不得作为阻断条件。

## 当前档案说明（2026-08-10）

- 天猫：本地旧稿仍只是 `advisory/unverified_legacy` 平台旁证；同时，Skill 所有者于 2026-09-09 明确把“59–60 旧字节（中文及非 ASCII 字符计 2，ASCII 字符计 1）”设为本 Skill 的天猫经营硬标准。校验器以 `owner_operating_default` 标识该来源，不把它表述为天猫官方发布门槛；默认无空格仍仅为 advisory。
- 京东：官方商家学习中心与信息发布规范页面可定位，但本轮未取得可核验的统一长标题数字上限；长度、空格与符号均为 `unknown`。
- 拼多多：未取得可核验的官方统一标题数字口径；网络二手说法不得进入硬规则。
- 抖店：官方学习中心确认存在商品标题发布/优化指南，并明确标题优化服务规则可动态调整；2026-04-22 的官方说明提到“标题字数 <=28”是自动托管条件之一，不是标题最大长度，因此不得改写成发布上限。

## 更新规则

每次实际调用只检查目标平台。`scripts/platform_guard.py` 校验档案 schema；`freshness.verified_at` 记录上次对档案证据状态的核对日期，`review_after` 必须正好晚 30 天。到期时只把既有 `hard` 状态在本次运行中降为 `unknown`，不修改原文件、不建立定时任务、不联网、不自动延期；advisory/unknown 仍按原等级披露。复核失败也不能重置日期。`offline_metadata_only` 表示只完成结构/日期核验，不是官方正文有效性证明。

档案的 `status=verified` 与 `hard` 规则必须同时具有：目标平台官方 HTTPS 域名的 `official_verified` 来源、可解析的访问/生效日期、明确 claim 及匹配 scope。域名和元数据只能防止明显误配，不能替代人工阅读正文。其他平台的坏数据不得污染当前平台检查。

取得新规则时保存直接页面链接、页面标题、发布日期/生效日期、访问日期、适用平台/类目/店铺类型和原文含义。若只有登录后后台提示，由用户提供截图或原文并登记为 `user_provided_current_backend_rule`；不同来源冲突时保留两者并暂停相关硬断言。

没有运行 `title_guard.py` 时不得写“已精确校验”。平台字段为 `unknown` 时只可写“真实性与已知约束已检查，平台长度/符号硬口径待后台确认”。
