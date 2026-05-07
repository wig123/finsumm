#!/bin/bash
# V3 FCPO-v2 训练 (仅训练，不推理)
# 数据: fcpo_v2_gamma{1,2,4}.jsonl (gemini-3-flash + 1-100 标度)

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8
MIRROR="-i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com"

echo "=========================================="
echo " V3 FCPO-v2 Train Only"
echo " $(date)"
echo "=========================================="

cd /tmp && curl -sO https://gosspublic.alicdn.com/ossutil/v2/2.2.1/ossutil-2.2.1-linux-amd64.zip \
    && unzip -qo ossutil-2.2.1-linux-amd64.zip && chmod +x ossutil-2.2.1-linux-amd64/ossutil
OSSUTIL=/tmp/ossutil-2.2.1-linux-amd64/ossutil
OSS="-i <OSS_ACCESS_KEY_ID> -k <OSS_ACCESS_KEY_SECRET> -e https://oss-cn-beijing-internal.aliyuncs.com --region cn-beijing"

# Install
pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 -f https://mirrors.aliyun.com/pytorch-wheels/cu124/ 2>&1 | tail -3
pip uninstall -y trl transformers peft accelerate 2>/dev/null
pip install $MIRROR "transformers==5.2.0" "trl==0.24.0" "peft==0.18.1" "accelerate==1.11.0" 2>&1 | tail -5
$OSSUTIL cp oss://qwen3vl-dpo-training/llamafactory/LLaMA-Factory.tar.gz /tmp/LLaMA-Factory.tar.gz $OSS
cd /tmp && tar xzf LLaMA-Factory.tar.gz && mv LLaMA-Factory $LLAMAFACTORY_PATH
cd $LLAMAFACTORY_PATH && pip install -e ".[metrics,deepspeed]" $MIRROR 2>&1 | tail -5
pip install $MIRROR "qwen_vl_utils>=0.0.14" "numpy<2" 2>&1 | tail -3
pip install flash-attn $MIRROR --no-build-isolation 2>&1 | tail -3 || true

# FCPO Patch
$OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/patch_fcpo.py /tmp/patch_fcpo.py $OSS
python3 /tmp/patch_fcpo.py $LLAMAFACTORY_PATH || { echo "FATAL: patch failed"; exit 1; }

# Download
mkdir -p $MODEL_ROOT $DATA_ROOT/dpo/data $DATA_ROOT/dpo/sft-checkpoint $OUTPUT_ROOT
$OSSUTIL cp oss://qwen3vl-dpo-training/models/Qwen3-VL-8B-Instruct/ /data/model/ -r --parallel 20 $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/data/images/ $DATA_ROOT/dpo/data/images/ -r --parallel 20 $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/sft-checkpoint/ $DATA_ROOT/dpo/sft-checkpoint/ -r --parallel 10 $OSS &
for G in 1 2 4; do
    $OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/fcpo_v2_gamma${G}.jsonl $DATA_ROOT/dpo/data/fcpo_v2_gamma${G}.jsonl $OSS &
done
wait

# Convert data
python3 << 'PYEOF'
import json, os
IMG_DIR = '$DATA_ROOT/dpo/data/images'
for g in [1, 2, 4]:
    records = []
    for line in open(f'$DATA_ROOT/dpo/data/fcpo_v2_gamma{g}.jsonl'):
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
        if not chosen_text or not rejected_text or not user_msgs: continue
        record = {"conversations": user_msgs, "chosen": {"from": "gpt", "value": chosen_text},
                  "rejected": {"from": "gpt", "value": rejected_text}, "margin": d.get('margin', 0.0)}
        if images: record["images"] = images
        records.append(record)
    with open(f'$DATA_ROOT/dpo/data/fcpo_v2_gamma{g}_lf.json', 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False)
    margins = [r["margin"] for r in records]
    pos = sum(1 for m in margins if m > 0)
    print(f'  v2_gamma{g}: {len(records)} records, margin>0: {pos} ({pos/len(records)*100:.1f}%)')
PYEOF

cat > $DATA_ROOT/dpo/dataset_info.json << 'EOF'
{"fcpo_v2_gamma1": {"file_name": "$DATA_ROOT/dpo/data/fcpo_v2_gamma1_lf.json", "formatting": "sharegpt", "ranking": true, "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}},
 "fcpo_v2_gamma2": {"file_name": "$DATA_ROOT/dpo/data/fcpo_v2_gamma2_lf.json", "formatting": "sharegpt", "ranking": true, "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}},
 "fcpo_v2_gamma4": {"file_name": "$DATA_ROOT/dpo/data/fcpo_v2_gamma4_lf.json", "formatting": "sharegpt", "ranking": true, "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected", "images": "images"}}}
EOF

# Train
TRAIN_OK=()
run_exp() {
    local NAME=$1 DATASET=$2
    echo "========== Training $NAME =========="
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
        echo ">>> $NAME: TRAIN SUCCESS"
        TRAIN_OK+=("$NAME")
        $OSSUTIL cp $OUTPUT_ROOT/$NAME/ oss://qwen3vl-dpo-training/llamafactory/outputs/$NAME/ -r --parallel 10 $OSS 2>&1 | tail -1
    else
        echo ">>> $NAME: TRAIN FAILED"
    fi
}

run_exp "FCPO-v2g1" "fcpo_v2_gamma1"
run_exp "FCPO-v2g2" "fcpo_v2_gamma2"
run_exp "FCPO-v2g4" "fcpo_v2_gamma4"

echo "=========================================="
echo " Training done: OK=[${TRAIN_OK[*]}]"
echo " $(date)"
echo "=========================================="
