#!/bin/bash
# H20 DPO 数据消融实验 (自定义镜像, 0 安装时间)
# 实验: tier12_only (1222条) + clean_B_fixed (846条)
# 每个实验: 训练 ~10min + 推理 ~6min
set -e
export LANG=en_US.UTF-8
export PYTHONUNBUFFERED=1

echo "=========================================="
echo " DPO Data Ablation (tier12 + clean_B)"
echo " $(date)"
echo "=========================================="

# ossutil
cd /tmp && curl -sO https://gosspublic.alicdn.com/ossutil/v2/2.2.1/ossutil-2.2.1-linux-amd64.zip \
    && unzip -qo ossutil-2.2.1-linux-amd64.zip && chmod +x ossutil-2.2.1-linux-amd64/ossutil
OSSUTIL=/tmp/ossutil-2.2.1-linux-amd64/ossutil
OSS="-i <OSS_ACCESS_KEY_ID> -k <OSS_ACCESS_KEY_SECRET> -e https://oss-cn-beijing-internal.aliyuncs.com --region cn-beijing"
MIRROR="-i https://mirrors.aliyun.com/pypi/simple/"

# nvcc shim (LlamaFactory torchrun 需要)
export CUDA_HOME=/usr/local/cuda
mkdir -p /usr/local/cuda/bin
CUDA_VER=$(python3 -c "import torch; print(torch.version.cuda)" 2>/dev/null || echo "12.4")
printf '#!/bin/bash\necho "nvcc: NVIDIA (R) Cuda compiler driver"\necho "Cuda compilation tools, release %s, V%s.131"\n' "$CUDA_VER" "$CUDA_VER" > /usr/local/cuda/bin/nvcc
chmod +x /usr/local/cuda/bin/nvcc
echo "nvcc shim: CUDA ${CUDA_VER}"

# 1. 下载模型 + SFT + 评估数据
echo "=== [1/4] Download ==="
mkdir -p $MODEL_ROOT $DATA_ROOT/dpo/sft-checkpoint /data/dpo_data $DATA_ROOT/eval_data /data/l2_results

$OSSUTIL cp oss://qwen3vl-dpo-training/models/Qwen3-VL-8B-Instruct/ /data/model/ -r --parallel 20 $OSS 2>&1 | tail -3 &
P1=$!
$OSSUTIL cp oss://qwen3vl-dpo-training/sft-checkpoint/ $DATA_ROOT/dpo/sft-checkpoint/ -r --parallel 10 $OSS 2>&1 | tail -3 &
P2=$!
$OSSUTIL cp oss://qwen3vl-dpo-training/eval_data/finmme_eval.tar.gz $DATA_ROOT/eval_data/finmme_eval.tar.gz $OSS &
P3=$!

# 下载数据集
$OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/clean_B_lf_v2.json /data/dpo_data/clean_B_lf.json $OSS &
$OSSUTIL cp oss://qwen3vl-dpo-training/data/images/ /data/dpo_data/images/ -r --parallel 20 $OSS 2>&1 | tail -3 &

wait $P1 $P2 $P3
wait
$OSSUTIL cp oss://qwen3vl-dpo-training/scripts/l2_dpo_inference.py $DATA_ROOT/dpo/infer_script.py $OSS
cd $DATA_ROOT/eval_data && tar xzf finmme_eval.tar.gz 2>/dev/null
EVAL_BASE=$( [ -d "$DATA_ROOT/eval_data/data/fin-chart_200" ] && echo "$DATA_ROOT/eval_data/data" || echo "$DATA_ROOT/eval_data" )
echo "Eval base: $EVAL_BASE"

# 上传 tier12 数据到容器 (从本地 Mac 已上传到 OSS)
$OSSUTIL cp oss://qwen3vl-dpo-training/data/v3/dpo_tier12_lf_v2.json /data/dpo_data/dpo_tier12_lf.json $OSS 2>/dev/null

# 2. 修正图片路径
echo "=== [2/4] Fix image paths ==="
python3 << 'PYEOF'
import json
for name, path in [("tier12", "/data/dpo_data/dpo_tier12_lf.json"), ("clean_B", "/data/dpo_data/clean_B_lf.json")]:
    with open(path) as f:
        data = json.load(f)
    for d in data:
        d["images"] = [p.replace("/home/ww/qwen3vl-dpo/data/images/", "/data/dpo_data/images/") for p in d["images"]]
    json.dump(data, open(path, "w"), ensure_ascii=False)
    print(f"{name}: {len(data)} items, paths fixed")
PYEOF

# dataset_info.json
python3 -c "
import json
di = {
    'tier12': {'file_name': '/data/dpo_data/dpo_tier12_lf.json', 'formatting': 'sharegpt', 'ranking': True, 'columns': {'messages': 'conversations', 'chosen': 'chosen', 'rejected': 'rejected', 'images': 'images'}},
    'clean_B': {'file_name': '/data/dpo_data/clean_B_lf.json', 'formatting': 'sharegpt', 'ranking': True, 'columns': {'messages': 'conversations', 'chosen': 'chosen', 'rejected': 'rejected', 'images': 'images'}}
}
json.dump(di, open('/data/dpo_data/dataset_info.json', 'w'), indent=2)
print('dataset_info ready')
"

# 3. 训练 + 推理循环
echo "=== [3/4] Train + Infer ==="
SFT=$DATA_ROOT/dpo/sft-checkpoint/exp-012-ckpt640

for NAME in tier12 clean_B; do
    echo ""
    echo "=========================================="
    echo " ${NAME}: train + infer"
    echo " $(date)"
    echo "=========================================="

    # 训练 config
    cat > $DATA_ROOT/dpo/${NAME}_config.yaml << CFGEOF
model_name_or_path: $MODEL_ROOT
adapter_name_or_path: ${SFT}
create_new_adapter: true
image_max_pixels: 262144
trust_remote_code: true
stage: dpo
do_train: true
finetuning_type: lora
lora_rank: 256
lora_alpha: 512
lora_target: all
pref_beta: 0.1
pref_loss: sigmoid
dataset_dir: /data/dpo_data
dataset: ${NAME}
template: qwen3_vl_nothink
cutoff_len: 2048
preprocessing_num_workers: 16
dataloader_num_workers: 4
output_dir: $DATA_ROOT/dpo/outputs/${NAME}
logging_steps: 1
save_steps: 999999
save_total_limit: 1
save_only_model: true
report_to: none
per_device_train_batch_size: 1
gradient_accumulation_steps: 1
learning_rate: 1.0e-5
num_train_epochs: 1
lr_scheduler_type: cosine
warmup_ratio: 0.1
bf16: true
ddp_timeout: 180000000
gradient_checkpointing: true
deepspeed: $LLAMAFACTORY_PATH/examples/deepspeed/ds_z2_config.json
CFGEOF

    # 训练
    echo "--- ${NAME}: training ---"
    cd $LLAMAFACTORY_PATH
    FORCE_TORCHRUN=1 NNODES=1 NPROC_PER_NODE=8 \
        llamafactory-cli train $DATA_ROOT/dpo/${NAME}_config.yaml
    echo "--- ${NAME}: training done $(date) ---"

    # 推理
    ADAPTER=$(ls -d $DATA_ROOT/dpo/outputs/${NAME}/checkpoint-* | tail -1)
    echo "--- ${NAME}: inference (adapter=$ADAPTER) ---"
    python3 $DATA_ROOT/dpo/infer_script.py \
        --model-name ${NAME} \
        --base-model $MODEL_ROOT \
        --sft-adapter $SFT \
        --dpo-adapter $ADAPTER \
        --data-base $EVAL_BASE \
        --output-dir /data/l2_results \
        --num-gpus 8
    echo "--- ${NAME}: inference done $(date) ---"

    # 上传结果
    $OSSUTIL cp /data/l2_results/${NAME}_results.jsonl oss://qwen3vl-dpo-training/results/h20_${NAME}_results.jsonl $OSS 2>/dev/null
    $OSSUTIL cp $ADAPTER/ oss://qwen3vl-dpo-training/checkpoints/h20_${NAME}/ -r $OSS 2>/dev/null
    echo "--- ${NAME}: uploaded ---"
done

echo "=== [4/4] Done ==="
echo "All experiments complete: $(date)"
