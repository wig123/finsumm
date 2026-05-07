#!/bin/bash
# V3 DPO-2/3/4 消融实验 (训练 + 推理)
# DPO-2: F-DPO (翻转 delta<0 的对)
# DPO-3: Shuffle (随机打乱 margin，对照组)
# DPO-4: Hybrid (Tier1/2 FCPO gamma=4 + Tier3 标准 DPO margin=1)
#
# 训练: 串行 3 个实验 ~15min
# 推理: 每个模型 8 卡并行 ~6min × 3 = ~18min
# 总计: ~45min

set -e
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8
MIRROR="-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com"

echo "=========================================="
echo " V3 DPO-2/3/4 Full Pipeline"
echo " $(date)"
echo "=========================================="

# === ossutil ===
cd /tmp && curl -sO https://gosspublic.alicdn.com/ossutil/v2/2.2.1/ossutil-2.2.1-linux-amd64.zip \
    && unzip -qo ossutil-2.2.1-linux-amd64.zip && chmod +x ossutil-2.2.1-linux-amd64/ossutil
OSSUTIL=/tmp/ossutil-2.2.1-linux-amd64/ossutil
OSS="-i <OSS_ACCESS_KEY_ID> -k <OSS_ACCESS_KEY_SECRET> -e https://oss-cn-beijing-internal.aliyuncs.com --region cn-beijing"

# === 1. Install ===
echo "=== [1/5] Install ==="
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
    -f https://mirrors.aliyun.com/pytorch-wheels/cu124/ 2>&1 | tail -3
pip uninstall -y trl transformers peft accelerate 2>/dev/null
pip install $MIRROR "transformers==5.2.0" "trl==0.24.0" "peft==0.18.1" "accelerate==1.11.0" 2>&1 | tail -5
$OSSUTIL cp oss://qwen3vl-dpo-training/llamafactory/LLaMA-Factory.tar.gz /tmp/LLaMA-Factory.tar.gz $OSS
cd /tmp && tar xzf LLaMA-Factory.tar.gz && mv LLaMA-Factory $LLAMAFACTORY_PATH 2>/dev/null || true
cd $LLAMAFACTORY_PATH && pip install -e ".[metrics,deepspeed]" $MIRROR 2>&1 | tail -5
pip install $MIRROR "qwen_vl_utils>=0.0.14" "numpy<2" 2>&1 | tail -3
pip install flash-attn $MIRROR --no-build-isolation 2>&1 | tail -3 || true

# FCPO Patch (for per-sample margin)
$OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/patch_fcpo.py /tmp/patch_fcpo.py $OSS
python3 /tmp/patch_fcpo.py $LLAMAFACTORY_PATH || { echo "FATAL: patch failed"; exit 1; }

python3 -c "import torch; print(f'PyTorch: {torch.__version__}, GPUs: {torch.cuda.device_count()}')"

# === 2. Download ===
echo "=== [2/5] Download ==="
mkdir -p $MODEL_ROOT $DATA_ROOT/dpo/data $DATA_ROOT/dpo/sft-checkpoint $OUTPUT_ROOT $DATA_ROOT/eval_data /data/l2_results /data/merged_models

$OSSUTIL cp oss://qwen3vl-dpo-training/models/Qwen3-VL-8B-Instruct/ /data/model/ -r --parallel 20 $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/data/images/ $DATA_ROOT/dpo/data/images/ -r --parallel 20 $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/sft-checkpoint/ $DATA_ROOT/dpo/sft-checkpoint/ -r --parallel 10 $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/eval_data/finmme_eval.tar.gz $DATA_ROOT/eval_data/finmme_eval.tar.gz $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/fdpo_v2.jsonl $DATA_ROOT/dpo/data/fdpo_v2.jsonl $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/shuffle_v2.jsonl $DATA_ROOT/dpo/data/shuffle_v2.jsonl $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/hybrid_v2_g4.jsonl $DATA_ROOT/dpo/data/hybrid_v2_g4.jsonl $OSS &
wait

# Unpack eval data
cd $DATA_ROOT/eval_data && tar xzf finmme_eval.tar.gz 2>/dev/null
EVAL_BASE=$( [ -d "$DATA_ROOT/eval_data/data/fin-chart_200" ] && echo "$DATA_ROOT/eval_data/data" || echo "$DATA_ROOT/eval_data" )
echo "Eval base: $EVAL_BASE"

# === 3. Convert data to LF format ===
echo "=== [3/5] Convert data ==="
python3 << 'PYEOF'
import json, os

IMG_DIR = '$DATA_ROOT/dpo/data/images'

datasets = {
    'fdpo_v2': '$DATA_ROOT/dpo/data/fdpo_v2.jsonl',
    'shuffle_v2': '$DATA_ROOT/dpo/data/shuffle_v2.jsonl',
    'hybrid_v2_g4': '$DATA_ROOT/dpo/data/hybrid_v2_g4.jsonl',
}

for name, path in datasets.items():
    records = []
    for line in open(path):
        d = json.loads(line)
        images = [os.path.join(IMG_DIR, os.path.basename(p)) for p in d.get('images', [])]
        msgs = d.get('messages', [])
        user_msgs, chosen_text = [], None
        for m in msgs:
            if m['role'] in ('user', 'system'):
                user_msgs.append({"from": "human", "value": m.get('content', '') or ''})
            elif m['role'] == 'assistant':
                chosen_text = m['content']
        rejected_text = d.get('rejected_response', '')
        if not chosen_text or not rejected_text or not user_msgs:
            continue
        record = {
            "conversations": user_msgs,
            "chosen": {"from": "gpt", "value": chosen_text},
            "rejected": {"from": "gpt", "value": rejected_text},
            "margin": d.get('margin', 0.0),
        }
        if images:
            record["images"] = images
        records.append(record)

    out_path = f'$DATA_ROOT/dpo/data/{name}_lf.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False)

    margins = [r["margin"] for r in records]
    pos = sum(1 for m in margins if m > 0)
    mean_m = sum(margins) / len(margins) if margins else 0
    print(f'  {name}: {len(records)} records, margin>0: {pos} ({pos/len(records)*100:.1f}%), mean={mean_m:.4f}')
PYEOF

# dataset_info.json
cat > $DATA_ROOT/dpo/dataset_info.json << 'EOF'
{
  "fdpo_v2": {"file_name": "$DATA_ROOT/dpo/data/fdpo_v2_lf.json", "formatting": "sharegpt", "ranking": true, "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}},
  "shuffle_v2": {"file_name": "$DATA_ROOT/dpo/data/shuffle_v2_lf.json", "formatting": "sharegpt", "ranking": true, "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}},
  "hybrid_v2_g4": {"file_name": "$DATA_ROOT/dpo/data/hybrid_v2_g4_lf.json", "formatting": "sharegpt", "ranking": true, "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}}
}
EOF

# === 4. Train ===
echo "=== [4/5] Train (3 experiments) ==="
TRAIN_OK=()

run_exp() {
    local NAME=$1 DATASET=$2
    echo ""
    echo "========== Training $NAME =========="
    echo "  Start: $(date)"

    cat > $DATA_ROOT/dpo/${NAME}_config.yaml << CFGEOF
model_name_or_path: $MODEL_ROOT
adapter_name_or_path: $DATA_ROOT/dpo/sft-checkpoint/exp-012-ckpt640
create_new_adapter: true
image_max_pixels: 262144
video_max_pixels: 16384
trust_remote_code: true
stage: dpo
do_train: true
finetuning_type: lora
lora_rank: 256
lora_alpha: 512
lora_target: all
pref_beta: 0.1
pref_loss: sigmoid
dataset_dir: $DATA_ROOT/dpo
dataset: $DATASET
template: qwen3_vl_nothink
cutoff_len: 2048
preprocessing_num_workers: 16
dataloader_num_workers: 4
output_dir: $OUTPUT_ROOT/$NAME
logging_steps: 1
save_steps: 999999
save_total_limit: 1
overwrite_output_dir: true
save_only_model: true
report_to: none
per_device_train_batch_size: 8
gradient_accumulation_steps: 1
learning_rate: 1.0e-5
num_train_epochs: 1.0
lr_scheduler_type: cosine
warmup_ratio: 0.1
bf16: true
ddp_timeout: 180000000
gradient_checkpointing: true
neat_packing: false
deepspeed: examples/deepspeed/ds_z2_config.json
CFGEOF

    cd $LLAMAFACTORY_PATH
    FORCE_TORCHRUN=1 NNODES=1 NPROC_PER_NODE=8 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
        llamafactory-cli train $DATA_ROOT/dpo/${NAME}_config.yaml

    if [ $? -eq 0 ]; then
        echo ">>> $NAME: TRAIN SUCCESS ($(date))"
        TRAIN_OK+=("$NAME")
        $OSSUTIL cp $OUTPUT_ROOT/$NAME/ oss://qwen3vl-dpo-training/llamafactory/outputs/$NAME/ -r --parallel 10 $OSS 2>&1 | tail -1
    else
        echo ">>> $NAME: TRAIN FAILED"
    fi
}

run_exp "FDPO-v2" "fdpo_v2"
run_exp "Shuffle-v2" "shuffle_v2"
run_exp "Hybrid-v2g4" "hybrid_v2_g4"

echo ""
echo "=========================================="
echo " Training done: OK=[${TRAIN_OK[*]}]"
echo " $(date)"
echo "=========================================="

# === 5. Inference (8-GPU parallel) ===
echo "=== [5/5] Inference ==="

SFT=$DATA_ROOT/dpo/sft-checkpoint/exp-012-ckpt640

# Merge models on CPU
for NAME in "${TRAIN_OK[@]}"; do
    ADAPTER_FILE=$(find $OUTPUT_ROOT/$NAME -name "adapter_model.safetensors" -type f | head -1)
    [ -z "$ADAPTER_FILE" ] && echo "$NAME: no adapter, skip" && continue
    ADAPTER_DIR=$(dirname "$ADAPTER_FILE")

    echo "  Merging $NAME..."
    python3 -c "
import torch, gc
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
from peft import PeftModel

model = Qwen3VLForConditionalGeneration.from_pretrained('/data/model', torch_dtype=torch.bfloat16, device_map='cpu')
model = PeftModel.from_pretrained(model, '$SFT')
model = model.merge_and_unload(); gc.collect()
model = PeftModel.from_pretrained(model, '$ADAPTER_DIR')
model = model.merge_and_unload(); gc.collect()
model.save_pretrained('/data/merged_models/$NAME')
AutoProcessor.from_pretrained('/data/model').save_pretrained('/data/merged_models/$NAME')
del model; gc.collect()
print('  $NAME: merge done')
"
    [ $? -ne 0 ] && echo "ERROR: $NAME merge failed"
done

# Write parallel inference script
cat > /tmp/parallel_infer.py << 'INFEREOF'
import os, json, time, gc, sys
import torch
import torch.multiprocessing as mp
from pathlib import Path

NAME = os.environ["EXP_NAME"]
MERGED = f"/data/merged_models/{NAME}"
EVAL_BASE = os.environ["EVAL_BASE"]
OUTPUT_DIR = "/data/l2_results"
NUM_GPUS = torch.cuda.device_count()
L2_COUNT = 50

PROMPT_CN = "你是一位严谨的、专注于金融领域的图表分析专家。你的唯一任务是接收一张金融图表，并严格遵循一个由四部分组成的结构，生成一份客观、独立的分析报告。\n\n**核心规则:**\n1. **遵循结构:** 你的报告必须严格包含【图表构成】、【数据关系】、【模式特征】、和【核心洞察】这四个部分的标题。\n2. **信息封闭原则:** 你的所有分析必须完全且仅来源于图表本身的视觉信息。\n3. **纯净输出:** 你的回答必须是纯文本，直接从【图表构成】开始。\n\n请严格按照以上结构分析你看到的金融图表。"
PROMPT_EN = "You are a rigorous chart analysis expert specializing in the financial domain. Your sole task is to receive a financial chart and generate an objective, independent analysis report strictly following a four-part structure.\n\n**Core Rules:**\n1. **Follow the Structure:** Your report must strictly include these four section headers: [Chart Composition], [Data Relationships], [Pattern Characteristics], and [Core Insights].\n2. **Information Closure Principle:** All your analysis must be derived entirely and solely from the visual information in the chart itself.\n3. **Clean Output:** Your response must be plain text, starting directly from [Chart Composition].\n\nPlease strictly follow the four-layer structure to analyze the financial chart you see."

DATASETS = ["fin-chart_200", "finmme_200", "sync_300_cn", "sync_300_en"]

def collect_samples():
    samples = []
    for dataset in DATASETS:
        dataset_path = Path(EVAL_BASE) / dataset
        if not dataset_path.exists():
            print(f"  WARN: {dataset} not found"); continue
        count = 0
        for subdir in sorted(dataset_path.iterdir()):
            if not subdir.is_dir(): continue
            img = None
            for n in ["chart.png", "image.png", "chart.jpg", "image.jpg"]:
                p = subdir / n
                if p.exists(): img = str(p); break
            if not img:
                for f in subdir.iterdir():
                    if f.suffix.lower() in [".png", ".jpg", ".jpeg"]: img = str(f); break
            if not img: continue
            gt_file = subdir / "gt.txt"
            gt = gt_file.read_text(encoding='utf-8').strip() if gt_file.exists() else ""
            samples.append({"id": subdir.name, "image_path": img, "ground_truth": gt, "source": dataset})
            count += 1
            if count >= L2_COUNT: break
        print(f"  {dataset}: {count} samples")
    return samples

def worker(gpu_id, sample_chunk, merged_path, result_file):
    device = f"cuda:{gpu_id}"
    from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
    from qwen_vl_utils import process_vision_info

    model = Qwen3VLForConditionalGeneration.from_pretrained(
        merged_path, torch_dtype=torch.bfloat16, device_map=device
    )
    processor = AutoProcessor.from_pretrained(merged_path, max_pixels=1280*28*28, min_pixels=256*28*28)
    model.eval()

    results = []
    for i, sample in enumerate(sample_chunk):
        prompt_text = PROMPT_CN if sample["source"] == "sync_300_cn" else PROMPT_EN
        messages = [{"role": "user", "content": [
            {"type": "image", "image": sample["image_path"]},
            {"type": "text", "text": prompt_text},
        ]}]
        try:
            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = processor(text=[text], images=image_inputs, videos=video_inputs,
                              padding=True, return_tensors="pt").to(device)
            ts = time.time()
            with torch.no_grad():
                output_ids = model.generate(**inputs, max_new_tokens=2048, do_sample=False)
            input_len = inputs.input_ids.shape[1]
            generated = processor.decode(output_ids[0][input_len:], skip_special_tokens=True)
            results.append({
                "id": sample["id"], "model": NAME,
                "generated_text": generated, "ground_truth": sample["ground_truth"],
                "inference_time": time.time() - ts, "image_path": sample["image_path"],
                "source": sample["source"],
            })
        except Exception as e:
            results.append({"id": sample["id"], "model": NAME, "error": str(e),
                           "image_path": sample["image_path"], "source": sample["source"]})
        if (i+1) % 5 == 0 or (i+1) == len(sample_chunk):
            print(f"  [GPU {gpu_id}] {i+1}/{len(sample_chunk)}", flush=True)

    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    del model; gc.collect(); torch.cuda.empty_cache()

if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)

    print(f"=== {NAME}: parallel inference ===")
    samples = collect_samples()
    print(f"  Total: {len(samples)} samples, {NUM_GPUS} GPUs")

    chunk_size = (len(samples) + NUM_GPUS - 1) // NUM_GPUS
    chunks = [samples[i:i+chunk_size] for i in range(0, len(samples), chunk_size)]

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    t0 = time.time()

    processes = []
    for gpu_id in range(min(NUM_GPUS, len(chunks))):
        result_file = f"{OUTPUT_DIR}/{NAME}_gpu{gpu_id}.json"
        p = mp.Process(target=worker, args=(gpu_id, chunks[gpu_id], MERGED, result_file))
        p.start()
        processes.append(p)
        print(f"  GPU {gpu_id}: {len(chunks[gpu_id])} samples")

    for p in processes:
        p.join()

    # Merge results
    all_results = []
    for gpu_id in range(min(NUM_GPUS, len(chunks))):
        rf = f"{OUTPUT_DIR}/{NAME}_gpu{gpu_id}.json"
        if os.path.exists(rf):
            with open(rf, encoding="utf-8") as f:
                all_results.extend(json.load(f))
            os.remove(rf)

    out_file = f"{OUTPUT_DIR}/{NAME}_results.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for r in sorted(all_results, key=lambda x: x["id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = [r for r in all_results if "error" not in r]
    elapsed = time.time() - t0
    print(f"  {NAME}: {len(success)}/{len(all_results)} ok, {elapsed:.0f}s ({elapsed/60:.1f}min)")
INFEREOF

# Run inference for each trained model
for NAME in "${TRAIN_OK[@]}"; do
    [ ! -d "/data/merged_models/$NAME" ] && echo "$NAME: no merged model, skip" && continue
    echo ""
    echo "--- $NAME inference ---"
    EXP_NAME=$NAME EVAL_BASE=$EVAL_BASE python3 /tmp/parallel_infer.py

    if [ -f /data/l2_results/${NAME}_results.jsonl ]; then
        echo ">>> $NAME: OK ($(wc -l < /data/l2_results/${NAME}_results.jsonl) samples)"
        $OSSUTIL cp /data/l2_results/${NAME}_results.jsonl \
            oss://qwen3vl-dpo-training/llamafactory/l2_results/${NAME}_results.jsonl $OSS --force 2>&1 | tail -1
    else
        echo ">>> $NAME: FAILED"
    fi
done

# Upload all results
$OSSUTIL cp /data/l2_results/ oss://qwen3vl-dpo-training/llamafactory/l2_results/ -r --parallel 10 $OSS 2>&1 | tail -2

echo ""
echo "=========================================="
echo " ALL DONE $(date)"
echo "=========================================="
for f in /data/l2_results/*_results.jsonl; do
    [ -f "$f" ] && echo "  $(basename $f _results.jsonl): $(wc -l < $f) samples"
done
