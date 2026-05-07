# API 配置

继承自 V2，所有 key 不变。详细文档见 `$DATA_ROOT/dpo-v2/03-API配置.md`。

---

## API 速查

| 用途 | Provider | Model | Base URL |
|------|----------|-------|----------|
| Judge 评估 | API 易 | gemini-2.5-flash-lite-preview-09-2025 | `<YOUR_LLM_PROXY>/v1` |
| Fact 提取 | API 易 | gemini-2.5-flash-lite-preview-09-2025 | 同上 |
| 交叉 Judge | API 易 | gpt-5 / gpt-4.1 | 同上 |
| FactScore | 云雾 AI | claude-sonnet-4-5-20250929 | `<YOUR_LLM_PROXY>/v1` |

## API Keys

```
# API 易（主力）
api_key: <YOUR_API_KEY>
base_url: <YOUR_LLM_PROXY>/v1

# CloseAI（GPT 备用）
api_key: <YOUR_API_KEY>
base_url: <YOUR_LLM_PROXY>/v1

# 云雾 AI（Claude）
api_key: <YOUR_API_KEY>
base_url: <YOUR_LLM_PROXY>/v1

# 阿里云 DLC
AccessKey ID: <OSS_ACCESS_KEY_ID>
AccessKey Secret: <OSS_ACCESS_KEY_SECRET>
```

## 评估参数（固定）

| 参数 | 值 |
|------|-----|
| Judge 模型 | gemini-2.5-flash-lite-preview-09-2025 |
| Judge temperature | 0.0 |
| 维度权重 | Faith 35% + Compl 30% + Anal 25% + Conc 10% |
| 归一化 | weighted_sum / 5.0 → [0, 1] |
| 推理 | greedy (do_sample=False), max_tokens=2048 |
| L2 样本 | 200 (每来源 50) |
| L3 样本 | 1000 (200+200+300+300) |
