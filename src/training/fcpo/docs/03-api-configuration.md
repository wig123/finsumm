# API Configuration

Inherited from V2, all keys remain unchanged. For detailed documentation, see `$DATA_ROOT/dpo-v2/03-api-configuration.md`.

---

## API Quick Reference

| Purpose | Provider | Model | Base URL |
|------|----------|-------|----------|
| Judge Evaluation | API Yi | gemini-2.5-flash-lite-preview-09-2025 | `<YOUR_LLM_PROXY>/v1` |
| Fact Extraction | API Yi | gemini-2.5-flash-lite-preview-09-2025 | Same as above |
| Cross Judge | API Yi | gpt-5 / gpt-4.1 | Same as above |
| FactScore | Yunwu AI | claude-sonnet-4-5-20250929 | `<YOUR_LLM_PROXY>/v1` |

## API Keys

```
# API Yi (Primary)
api_key: <YOUR_API_KEY>
base_url: <YOUR_LLM_PROXY>/v1

# CloseAI (GPT Backup)
api_key: <YOUR_API_KEY>
base_url: <YOUR_LLM_PROXY>/v1

# Yunwu AI (Claude)
api_key: <YOUR_API_KEY>
base_url: <YOUR_LLM_PROXY>/v1

# Alibaba Cloud DLC
AccessKey ID: <OSS_ACCESS_KEY_ID>
AccessKey Secret: <OSS_ACCESS_KEY_SECRET>
```

## Evaluation Parameters (Fixed)

| Parameter | Value |
|------|-----|
| Judge Model | gemini-2.5-flash-lite-preview-09-2025 |
| Judge temperature | 0.0 |
| Dimension Weights | Faith 35% + Compl 30% + Anal 25% + Conc 10% |
| Normalization | weighted_sum / 5.0 → [0, 1] |
| Inference | greedy (do_sample=False), max_tokens=2048 |
| L2 Samples | 200 (50 per source) |
| L3 Samples | 1000 (200+200+300+300) |
