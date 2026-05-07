#!/bin/bash
# V3 FCPO Training Pipeline: FCPO-γ1, FCPO-γ2, FCPO-γ4
# 基于 V2 LF-full 验证通过的环境 + FCPO patch
#
# 训练 → Merge → Inference → Upload
# 数据: fcpo_gamma{1,2,4}.jsonl (含 margin 字段)

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8

MIRROR="-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com"

echo "=========================================="
echo " V3 FCPO Training Pipeline"
echo " $(date)"
echo "=========================================="

# === ossutil ===
cd /tmp && curl -sO https://gosspublic.alicdn.com/ossutil/v2/2.2.1/ossutil-2.2.1-linux-amd64.zip \
    && unzip -qo ossutil-2.2.1-linux-amd64.zip && chmod +x ossutil-2.2.1-linux-amd64/ossutil
OSSUTIL=/tmp/ossutil-2.2.1-linux-amd64/ossutil
OSS="-i <OSS_ACCESS_KEY_ID> -k <OSS_ACCESS_KEY_SECRET> -e https://oss-cn-beijing-internal.aliyuncs.com --region cn-beijing"

# === 1. Install ===
echo "=== [1/7] Install ==="
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 \
    -f https://mirrors.aliyun.com/pytorch-wheels/cu124/ 2>&1 | tail -3

pip uninstall -y trl transformers peft accelerate 2>/dev/null
pip install $MIRROR \
    "transformers==5.2.0" "trl==0.24.0" "peft==0.18.1" "accelerate==1.11.0" \
    2>&1 | tail -5

$OSSUTIL cp oss://qwen3vl-dpo-training/llamafactory/LLaMA-Factory.tar.gz /tmp/LLaMA-Factory.tar.gz $OSS
cd /tmp && tar xzf LLaMA-Factory.tar.gz && mv LLaMA-Factory $LLAMAFACTORY_PATH
cd $LLAMAFACTORY_PATH
pip install -e ".[metrics,deepspeed]" $MIRROR 2>&1 | tail -5

pip install $MIRROR "qwen_vl_utils>=0.0.14" "numpy<2" 2>&1 | tail -3
pip install flash-attn $MIRROR --no-build-isolation 2>&1 | tail -3 || echo "flash-attn: skipped"

echo "--- Versions ---"
python3 -c "import torch; print(f'PyTorch: {torch.__version__}, GPUs: {torch.cuda.device_count()}')"
llamafactory-cli version 2>&1 | head -3

# === 2. FCPO Patch ===
echo "=== [2/7] FCPO Patch ==="
$OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/patch_fcpo.py /tmp/patch_fcpo.py $OSS
python3 /tmp/patch_fcpo.py $LLAMAFACTORY_PATH
PATCH_EXIT=$?
if [ $PATCH_EXIT -ne 0 ]; then
    echo "FATAL: FCPO patch failed!"
    exit 1
fi

# === 3. Download ===
echo "=== [3/7] Download ==="
mkdir -p $MODEL_ROOT $DATA_ROOT/dpo/data $DATA_ROOT/dpo/sft-checkpoint $OUTPUT_ROOT $DATA_ROOT/eval_data /data/merged_models /data/l2_results

$OSSUTIL cp oss://qwen3vl-dpo-training/models/Qwen3-VL-8B-Instruct/ /data/model/ -r --parallel 20 $OSS &
P1=$!
$OSSUTIL cp oss://qwen3vl-dpo-training/data/images/ $DATA_ROOT/dpo/data/images/ -r --parallel 20 $OSS &
P2=$!
$OSSUTIL cp oss://qwen3vl-dpo-training/sft-checkpoint/ $DATA_ROOT/dpo/sft-checkpoint/ -r --parallel 10 $OSS &
P3=$!
$OSSUTIL cp oss://qwen3vl-dpo-training/eval_data/finmme_eval.tar.gz $DATA_ROOT/eval_data/finmme_eval.tar.gz $OSS &
P4=$!

# FCPO 数据
for G in 1 2 4; do
    $OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/fcpo_gamma${G}.jsonl $DATA_ROOT/dpo/data/fcpo_gamma${G}.jsonl $OSS &
done

wait $P1 && echo "Model: OK" || echo "ERROR: Model"
wait $P2 && echo "Images: OK" || echo "ERROR: Images"
wait $P3 && echo "SFT: OK" || echo "ERROR: SFT"
wait $P4 && echo "Eval: OK" || echo "ERROR: Eval"
wait
echo "FCPO data: $(ls -1 $DATA_ROOT/dpo/data/fcpo_gamma*.jsonl 2>/dev/null | wc -l) files"

# === 4. Convert data ===
echo "=== [4/7] Convert data ==="
python3 << 'PYEOF'
import json, os

IMG_DIR = '$DATA_ROOT/dpo/data/images'

def convert_fcpo(infile, outfile, name):
    """转换 FCPO JSONL → LLaMA-Factory JSON (保留 margin)"""
    records = []
    for line in open(infile):
        d = json.loads(line)
        images = [os.path.join(IMG_DIR, os.path.basename(p)) for p in d.get('images', [])]
        msgs = d.get('messages', [])

        user_msgs = []
        chosen_text = None
        for m in msgs:
            role = m.get('role', '')
            content = m.get('content', '') or ''
            if role in ('user', 'system'):
                user_msgs.append({"from": "human", "value": content})
            elif role == 'assistant':
                chosen_text = content

        rejected_text = d.get('rejected_response', '')
        margin = d.get('margin', 0.0)

        if not chosen_text or not rejected_text or not user_msgs:
            continue

        record = {
            "conversations": user_msgs,
            "chosen": {"from": "gpt", "value": chosen_text},
            "rejected": {"from": "gpt", "value": rejected_text},
            "margin": margin,
        }
        if images:
            record["images"] = images
        records.append(record)

    with open(outfile, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False)

    # 统计 margin 分布
    margins = [r["margin"] for r in records]
    pos = sum(1 for m in margins if m > 0)
    print(f'  {name}: {len(records)} records, margin>0: {pos} ({pos/len(records)*100:.1f}%)')

    # 验证图片
    import random
    for r in random.sample(records, min(3, len(records))):
        for img in r.get('images', []):
            assert os.path.exists(img), f'MISSING: {img}'
    print(f'  {name}: verify OK')

for g in [1, 2, 4]:
    convert_fcpo(
        f'$DATA_ROOT/dpo/data/fcpo_gamma{g}.jsonl',
        f'$DATA_ROOT/dpo/data/fcpo_gamma{g}_lf.json',
        f'gamma{g}'
    )
PYEOF
if [ $? -ne 0 ]; then echo "FATAL: data conversion failed"; exit 1; fi

# dataset_info.json (3 组 FCPO 数据)
cat > $DATA_ROOT/dpo/dataset_info.json << 'EOF'
{
  "fcpo_gamma1": {
    "file_name": "$DATA_ROOT/dpo/data/fcpo_gamma1_lf.json",
    "formatting": "sharegpt",
    "ranking": true,
    "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}
  },
  "fcpo_gamma2": {
    "file_name": "$DATA_ROOT/dpo/data/fcpo_gamma2_lf.json",
    "formatting": "sharegpt",
    "ranking": true,
    "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}
  },
  "fcpo_gamma4": {
    "file_name": "$DATA_ROOT/dpo/data/fcpo_gamma4_lf.json",
    "formatting": "sharegpt",
    "ranking": true,
    "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}
  }
}
EOF

# Eval data
cd $DATA_ROOT/eval_data && tar xzf finmme_eval.tar.gz 2>/dev/null
EVAL_BASE=$( [ -d "$DATA_ROOT/eval_data/data/fin-chart_200" ] && echo "$DATA_ROOT/eval_data/data" || echo "$DATA_ROOT/eval_data" )

# === 5. Training ===
echo "=== [5/7] Training ==="
TRAIN_OK=()

run_exp() {
    local NAME=$1 DATASET=$2

    echo ""
    echo "=========================================="
    echo " Training $NAME (data=$DATASET)"
    echo " $(date)"
    echo "=========================================="

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
plot_loss: true
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
    FORCE_TORCHRUN=1 NNODES=1 NPROC_PER_NODE=8 \
        PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
        llamafactory-cli train $DATA_ROOT/dpo/${NAME}_config.yaml

    if [ $? -eq 0 ]; then
        echo ">>> $NAME: TRAIN SUCCESS"
        TRAIN_OK+=("$NAME")
        $OSSUTIL cp $OUTPUT_ROOT/$NAME/ oss://qwen3vl-dpo-training/llamafactory/outputs/$NAME/ -r --parallel 10 $OSS 2>&1 | tail -1
    else
        echo ">>> $NAME: TRAIN FAILED"
    fi
}

run_exp "FCPO-g1" "fcpo_gamma1"
run_exp "FCPO-g2" "fcpo_gamma2"
run_exp "FCPO-g4" "fcpo_gamma4"

echo ""
echo "=========================================="
echo " Training done: OK=[${TRAIN_OK[*]}]"
echo "=========================================="
[ ${#TRAIN_OK[@]} -eq 0 ] && echo "No successful training." && exit 1

# === 6. Merge + Inference ===
echo "=== [6/7] Merge + Inference ==="

SFT=$DATA_ROOT/dpo/sft-checkpoint/exp-012-ckpt640

for NAME in "${TRAIN_OK[@]}"; do
    ADAPTER=$(find $OUTPUT_ROOT/$NAME -name "adapter_model.safetensors" -type f 2>/dev/null | head -1 | xargs dirname 2>/dev/null)
    [ -z "$ADAPTER" ] && ADAPTER="$OUTPUT_ROOT/$NAME"
    [ ! -f "$ADAPTER/adapter_model.safetensors" ] && echo "$NAME: no adapter, skip" && continue

    echo ""
    echo "=========================================="
    echo " $NAME: merge + infer"
    echo " $(date)"
    echo "=========================================="

    python3 << PYEOF
import os, json, time, gc, torch
from pathlib import Path
from PIL import Image

os.environ['NCCL_P2P_DISABLE'] = '1'
os.environ['NCCL_IB_DISABLE'] = '1'

from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
from peft import PeftModel
from qwen_vl_utils import process_vision_info

NAME = "$NAME"
SFT_PATH = "$SFT"
DPO_PATH = "$ADAPTER"
MODEL_PATH = "/data/model"
EVAL_BASE = "$EVAL_BASE"
OUTPUT_DIR = "/data/l2_results"

MAX_PIXELS = 1280 * 28 * 28
MIN_PIXELS = 256 * 28 * 28
L2_COUNT = 50
DATASETS = ["fin-chart_200", "finmme_200", "sync_300_cn", "sync_300_en"]

PROMPT_CN = "你是一位严谨的、专注于金融领域的图表分析专家。你的唯一任务是接收一张金融图表，并严格遵循一个由四部分组成的结构，生成一份客观、独立的分析报告。\n\n**核心规则:**\n1. **遵循结构:** 你的报告必须严格包含【图表构成】、【数据关系】、【模式特征】、和【核心洞察】这四个部分的标题。\n2. **信息封闭原则:** 你的所有分析必须完全且仅来源于图表本身的视觉信息。\n3. **纯净输出:** 你的回答必须是纯文本，直接从【图表构成】开始。\n\n请严格按照以上结构分析你看到的金融图表。"
PROMPT_EN = "You are a rigorous chart analysis expert specializing in the financial domain. Your sole task is to receive a financial chart and generate an objective, independent analysis report strictly following a four-part structure.\n\n**Core Rules:**\n1. **Follow the Structure:** Your report must strictly include these four section headers: [Chart Composition], [Data Relationships], [Pattern Characteristics], and [Core Insights].\n2. **Information Closure Principle:** All your analysis must be derived entirely and solely from the visual information in the chart itself.\n3. **Clean Output:** Your response must be plain text, starting directly from [Chart Composition].\n\nPlease strictly follow the four-layer structure to analyze the financial chart you see."

print(f"=== {NAME}: Loading base model ===")
model = Qwen3VLForConditionalGeneration.from_pretrained(
    MODEL_PATH, torch_dtype=torch.bfloat16, device_map="auto"
)
processor = AutoProcessor.from_pretrained(MODEL_PATH, max_pixels=MAX_PIXELS, min_pixels=MIN_PIXELS)

print(f"  Merging SFT adapter: {SFT_PATH}")
model = PeftModel.from_pretrained(model, SFT_PATH)
model = model.merge_and_unload()
gc.collect(); torch.cuda.empty_cache()

print(f"  Merging DPO adapter: {DPO_PATH}")
model = PeftModel.from_pretrained(model, DPO_PATH)
model = model.merge_and_unload()
gc.collect(); torch.cuda.empty_cache()
model.eval()
print(f"  Model ready on {model.device}")

samples = []
for dataset in DATASETS:
    dataset_path = Path(EVAL_BASE) / dataset
    if not dataset_path.exists():
        print(f"  WARN: {dataset} not found")
        continue
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

print(f"  Total: {len(samples)} samples")

results = []
t0 = time.time()
for i, sample in enumerate(samples):
    source = sample["source"]
    prompt_text = PROMPT_CN if source == "sync_300_cn" else PROMPT_EN

    messages = [{"role": "user", "content": [
        {"type": "image", "image": sample["image_path"]},
        {"type": "text", "text": prompt_text},
    ]}]

    try:
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(text=[text], images=image_inputs, videos=video_inputs,
                          padding=True, return_tensors="pt").to(model.device)

        ts = time.time()
        with torch.no_grad():
            output_ids = model.generate(**inputs, max_new_tokens=2048, do_sample=False)
        input_len = inputs.input_ids.shape[1]
        generated = processor.decode(output_ids[0][input_len:], skip_special_tokens=True)
        infer_time = time.time() - ts

        results.append({
            "id": sample["id"], "model": NAME,
            "generated_text": generated, "ground_truth": sample["ground_truth"],
            "inference_time": infer_time, "image_path": sample["image_path"],
            "source": source,
        })
    except Exception as e:
        results.append({"id": sample["id"], "model": NAME, "error": str(e),
                       "image_path": sample["image_path"], "source": source})

    if (i+1) % 20 == 0 or (i+1) == len(samples):
        print(f"  Progress: {i+1}/{len(samples)} ({time.time()-t0:.0f}s)")

os.makedirs(OUTPUT_DIR, exist_ok=True)
out_file = f"{OUTPUT_DIR}/{NAME}_results.jsonl"
with open(out_file, "w", encoding="utf-8") as f:
    for r in sorted(results, key=lambda x: x["id"]):
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

success = [r for r in results if "error" not in r]
print(f"  {NAME}: {len(success)}/{len(results)} success, saved to {out_file}")
PYEOF

    INFER_EXIT=$?
    if [ $INFER_EXIT -eq 0 ] && [ -f /data/l2_results/${NAME}_results.jsonl ]; then
        echo ">>> $NAME: inference OK"
        $OSSUTIL cp /data/l2_results/${NAME}_results.jsonl \
            oss://qwen3vl-dpo-training/llamafactory/l2_results/${NAME}_results.jsonl $OSS --force 2>&1 | tail -1
    else
        echo ">>> $NAME: inference FAILED"
    fi

    python3 -c "import torch; torch.cuda.empty_cache()" 2>/dev/null
done

# === 7. Upload ===
echo "=== [7/7] Upload ==="
$OSSUTIL cp /data/l2_results/ oss://qwen3vl-dpo-training/llamafactory/l2_results/ -r --parallel 10 $OSS 2>&1 | tail -2

echo ""
echo "=========================================="
echo " ALL DONE $(date)"
echo "=========================================="
for f in /data/l2_results/*_results.jsonl; do
    [ -f "$f" ] && echo "  $(basename $f _results.jsonl): $(wc -l < $f) samples"
done
