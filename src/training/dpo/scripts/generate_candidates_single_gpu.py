#!/usr/bin/env python3
"""
单 GPU 候选生成脚本 - 用于 8 卡数据并行

使用方式:
    python generate_candidates_single_gpu.py \
        --gpu-id 0 \
        --start-idx 0 \
        --end-idx 250 \
        --input /app$DATA_ROOT/dpo/sampled_2000.json \
        --output /app$DATA_ROOT/dpo/candidates_gpu0.json
"""

import os
import json
import argparse
import time
import sys
from pathlib import Path

# 在导入 torch 之前设置 GPU
parser = argparse.ArgumentParser(description="单 GPU 候选生成")
parser.add_argument("--gpu-id", type=int, required=True, help="GPU ID (0-7)")
parser.add_argument("--start-idx", type=int, required=True, help="起始样本索引")
parser.add_argument("--end-idx", type=int, required=True, help="结束样本索引 (不含)")
parser.add_argument("--input", type=Path, required=True, help="输入样本文件")
parser.add_argument("--output", type=Path, required=True, help="输出文件")
parser.add_argument("--model", type=str, default="/app/outputs/exp-012/checkpoint-640", help="LoRA 模型路径")
parser.add_argument("--base-model", type=str, default="/app/models/qwen3-vl-8b-instruct", help="基座模型路径")
parser.add_argument("--num-greedy", type=int, default=1, help="Greedy 生成数量")
parser.add_argument("--num-sample", type=int, default=5, help="Sample 生成数量")
parser.add_argument("--max-new-tokens", type=int, default=2048, help="最大生成 token 数")
parser.add_argument("--temperature", type=float, default=0.9, help="采样温度")
parser.add_argument("--checkpoint-interval", type=int, default=20, help="Checkpoint 保存间隔")
parser.add_argument("--image-base-dir", type=Path, default=None, help="图片基础目录 (默认: input 文件的上两级)")
args = parser.parse_args()

# 设置 GPU
os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu_id)
os.environ["TORCHDYNAMO_DISABLE"] = "1"  # 禁用 torch.compile

import torch
from PIL import Image
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor, GenerationConfig
from peft import PeftModel

# 配置
MAX_PIXELS = 1280 * 32 * 32  # ~1.3M pixels
MIN_PIXELS = 256 * 32 * 32

def log(msg):
    """带时间戳和 GPU ID 的日志"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[GPU{args.gpu_id}][{timestamp}] {msg}")
    sys.stdout.flush()

def main():
    log("=" * 50)
    log(f"单 GPU 候选生成")
    log(f"样本范围: [{args.start_idx}, {args.end_idx})")
    log(f"总样本数: {args.end_idx - args.start_idx}")
    log("=" * 50)

    # 加载数据
    log("加载样本...")
    with open(args.input) as f:
        all_samples = json.load(f)
    samples = all_samples[args.start_idx:args.end_idx]
    log(f"本 GPU 处理 {len(samples)} 个样本")

    # 检查已有结果 (断点续传)
    results = []
    resume_from = 0
    if args.output.exists():
        with open(args.output) as f:
            results = json.load(f)
        resume_from = len(results)
        log(f"发现已有结果，从第 {resume_from} 个样本继续")

    if resume_from >= len(samples):
        log("所有样本已处理完毕!")
        return

    # 加载模型
    log(f"加载基座模型: {args.base_model}")
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        args.base_model,
        torch_dtype=torch.bfloat16,
        device_map="cuda:0",  # 只有一个可见 GPU
        attn_implementation="sdpa"  # PyTorch 2.x SDPA，比 eager 快 ~1.2-1.5x
    )

    log(f"加载 LoRA: {args.model}")
    model = PeftModel.from_pretrained(model, args.model)
    model = model.merge_and_unload()
    model.eval()

    processor = AutoProcessor.from_pretrained(args.base_model)
    processor.image_processor.max_pixels = MAX_PIXELS
    processor.image_processor.min_pixels = MIN_PIXELS

    mem = torch.cuda.memory_allocated() / 1024**3
    log(f"模型加载完成，显存: {mem:.2f} GB")

    # 数据目录
    data_dir = args.image_base_dir if args.image_base_dir else args.input.parent.parent  # /app/data

    # 预构建 GenerationConfig (transformers 5.x 要求通过 GenerationConfig 传递生成参数)
    greedy_gen_config = GenerationConfig(
        max_new_tokens=args.max_new_tokens,
        pad_token_id=processor.tokenizer.pad_token_id,
        do_sample=False,
    )
    sample_gen_config = GenerationConfig(
        max_new_tokens=args.max_new_tokens,
        pad_token_id=processor.tokenizer.pad_token_id,
        do_sample=True,
        temperature=args.temperature,
        top_p=0.95,
        top_k=50,
    )
    log(f"GenerationConfig 已创建: greedy(do_sample=False), sample(temp={args.temperature}, top_p=0.95, top_k=50)")

    def generate_single(inputs, do_sample: bool) -> str:
        """生成单个响应"""
        gen_config = sample_gen_config if do_sample else greedy_gen_config
        with torch.no_grad():
            outputs = model.generate(**inputs, generation_config=gen_config)

        generated_ids = outputs[0][inputs['input_ids'].shape[1]:]
        return processor.decode(generated_ids, skip_special_tokens=True)

    # 开始生成
    log("开始生成候选...")
    start_time = time.time()
    total_candidates = args.num_greedy + args.num_sample

    for local_idx, sample in enumerate(samples[resume_from:]):
        global_idx = args.start_idx + resume_from + local_idx

        # 进度日志
        elapsed = time.time() - start_time
        processed = local_idx + 1
        if processed > 1:
            eta = elapsed / processed * (len(samples) - resume_from - processed)
            log(f"[{resume_from + local_idx + 1}/{len(samples)}] "
                f"全局索引: {global_idx}, "
                f"已用: {elapsed/60:.1f}min, ETA: {eta/60:.1f}min")
        else:
            log(f"[{resume_from + local_idx + 1}/{len(samples)}] 全局索引: {global_idx}")

        # 准备输入 (兼容 'image' 字符串 和 'images' 列表两种格式)
        img_field = sample.get('images', [sample['image']])[0] if 'images' in sample else sample['image']
        image_path = data_dir / img_field
        messages = sample['messages']

        system_msg = None
        human_msg = None
        for msg in messages:
            if msg['from'] == 'system':
                system_msg = msg['value']
            elif msg['from'] == 'human':
                human_msg = msg['value']

        try:
            image = Image.open(image_path).convert("RGB")

            qwen_messages = []
            if system_msg:
                qwen_messages.append({"role": "system", "content": system_msg})
            qwen_messages.append({
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": human_msg.replace("<image>\n", "").replace("<image>", "")}
                ]
            })

            text = processor.apply_chat_template(
                qwen_messages, tokenize=False, add_generation_prompt=True
            )
            inputs = processor(
                text=[text],
                images=[image],
                return_tensors="pt"
            ).to("cuda:0")

        except Exception as e:
            log(f"警告: 样本 {global_idx} 输入处理失败: {e}")
            results.append({
                'index': global_idx,
                'image': img_field,
                'messages': messages,
                'candidates': [],
                'candidates_meta': [],
                'ground_truth': next((m['value'] for m in messages if m['from'] == 'gpt'), None),
                '_source': sample.get('_source', ''),
                'error': str(e)
            })
            torch.cuda.empty_cache()
            continue

        # 生成 candidates
        candidates = []
        candidates_meta = []

        # Greedy
        for i in range(args.num_greedy):
            try:
                response = generate_single(inputs, do_sample=False)
                candidates.append(response)
                candidates_meta.append({'type': 'greedy', 'index': i})
            except Exception as e:
                log(f"警告: 样本 {global_idx} greedy 生成失败: {e}")
                candidates.append("")
                candidates_meta.append({'type': 'greedy', 'index': i, 'error': str(e)})

        # Sample
        for i in range(args.num_sample):
            try:
                response = generate_single(inputs, do_sample=True)
                candidates.append(response)
                candidates_meta.append({'type': 'sample', 'index': i, 'temperature': args.temperature})
            except Exception as e:
                log(f"警告: 样本 {global_idx} sample 生成失败: {e}")
                candidates.append("")
                candidates_meta.append({'type': 'sample', 'index': i, 'error': str(e)})

        # 保存结果
        result = {
            'index': global_idx,
            'image': img_field,
            'messages': messages,
            'candidates': candidates,
            'candidates_meta': candidates_meta,
            'ground_truth': next((m['value'] for m in messages if m['from'] == 'gpt'), None),
            '_source': sample.get('_source', '')
        }
        results.append(result)

        # 清理显存
        del inputs, image
        torch.cuda.empty_cache()

        # Checkpoint
        if (resume_from + local_idx + 1) % args.checkpoint_interval == 0:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            log(f"Checkpoint 已保存: {len(results)} 条")

    # 最终保存
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start_time
    log("=" * 50)
    log(f"完成! 生成 {len(results)} 条样本")
    log(f"每条 {total_candidates} 个 candidates")
    log(f"总耗时: {elapsed/60:.1f} 分钟")
    log(f"平均: {elapsed/len(results):.1f} 秒/样本")
    log("=" * 50)

if __name__ == "__main__":
    main()
