# Training Configuration Lessons (V4 Pitfall Record)

**Date**: 2026-03-30

## Required LlamaFactory DPO Configuration

```yaml
# Both settings are essential, otherwise training results will severely degrade
create_new_adapter: true      # DPO creates independent adapter, does not overwrite SFT adapter
template: qwen3_vl_nothink    # Disable thinking mode
```

## Pitfall Details

### 1. Missing `create_new_adapter: true`

**Symptom**: rewards/chosen ~57 (abnormally high), loss ~2.3, evaluation 0.573 (catastrophic)
**Cause**: Without this setting, LlamaFactory directly modifies SFT adapter weights. During inference, SFT is merged first, then DPO is merged, causing SFT to be applied twice.
**After Fix**: rewards/chosen ~0.9 (normal), loss ~0.6, evaluation 0.738

### 2. `template: qwen3_vl` vs `qwen3_vl_nothink`

**Difference**: `qwen3_vl` uses `ReasoningTemplate` (generates `<think>...</think>`), `qwen3_vl_nothink` is a regular template
**Impact**: chosen/rejected in DPO training data do not contain thinking tokens; using thinking template causes format mismatch
**Rule**: LF-2 baseline uses `qwen3_vl_nothink`, all experiments must be consistent

## Complete Correct Configuration (Aligned with LF-2 Baseline)

```yaml
model_name_or_path: /share4/yzy/models/qwen3-vl-8b-instruct
adapter_name_or_path: /share2/ww/qwen3vl-dpo/sft-checkpoint/exp-012-ckpt640
create_new_adapter: true
trust_remote_code: true
stage: dpo
do_train: true
finetuning_type: lora
lora_rank: 256
lora_alpha: 512
lora_target: all
pref_loss: sigmoid
pref_beta: 0.1
template: qwen3_vl_nothink
cutoff_len: 2048
per_device_train_batch_size: 1
gradient_accumulation_steps: 16  # 4 cards × 16 = 64 effective batch
learning_rate: 1.0e-5
num_train_epochs: 1
bf16: true
freeze_vision_tower: true
deepspeed: examples/deepspeed/ds_z2_config.json
save_strategy: epoch
overwrite_output_dir: true
```

## Inference Dual-Layer LoRA Loading (Correct Method)

```python
# 1. Load base model
model = Qwen3VLForConditionalGeneration.from_pretrained(base_path)
# 2. Load SFT adapter → merge into base
model = PeftModel.from_pretrained(model, sft_adapter_path)
model = model.merge_and_unload()
# 3. Load DPO adapter → merge (because create_new_adapter=true, this is an independent increment)
model = PeftModel.from_pretrained(model, dpo_adapter_path)
model = model.merge_and_unload()
```
