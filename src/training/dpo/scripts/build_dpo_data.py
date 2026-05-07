#!/usr/bin/env python3
"""
DPO 数据构建脚本 v2 - 抽样并生成 candidates

流程:
1. 从训练集按四类数据源比例抽样 2000 张图片
2. 使用 SFT 模型 (EXP-012-ckpt640) 生成 6 个 candidates (1 greedy + 5 sample)
3. 输出中间结果，后续离线打分

使用方式:
    # 步骤 1: 抽样 (本地执行)
    python scripts/build_dpo_data.py sample --output data/dpo/sampled_2000.json --total 2000

    # 步骤 2: 生成 candidates (GPU 服务器执行)
    python scripts/build_dpo_data.py generate \
        --input /app$DATA_ROOT/dpo/sampled_2000.json \
        --output /app$DATA_ROOT/dpo/candidates_2000.json \
        --model /app/outputs/exp-012/checkpoint-640 \
        --base-model /app/models/qwen3-vl-8b-instruct
"""

import json
import argparse
import random
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from tqdm import tqdm


# ============== 配置 ==============

# 图片像素限制（避免 OOM）
MAX_PIXELS = 1280 * 32 * 32  # ~1,310,720 pixels
MIN_PIXELS = 256 * 32 * 32   # ~262,144 pixels


@dataclass
class SamplingConfig:
    """抽样配置"""
    total_samples: int = 2000
    random_seed: int = 42
    # 按四类数据源比例分配（基于 all_train.json 原始分布）
    ratios: Dict[str, float] = None

    def __post_init__(self):
        if self.ratios is None:
            # 原始分布: v3=45.0%, v4=26.7%, fin-chart=15.6%, finmme=12.6%
            self.ratios = {
                'v3_synthesis': 0.450,   # syn_v2_, syn_, prog_
                'v4_synthesis': 0.267,   # syn_v4_, syn_v4f_
                'fin-chart': 0.156,      # mc_
                'finmme': 0.127          # finmme_
            }


@dataclass
class GenerationConfig:
    """生成配置"""
    num_greedy: int = 1           # greedy 候选数
    num_sample: int = 5           # sample 候选数
    temperature: float = 0.9
    top_p: float = 0.95
    top_k: int = 50
    max_new_tokens: int = 2048

    @property
    def total_candidates(self) -> int:
        return self.num_greedy + self.num_sample


# ============== 抽样逻辑 ==============

def categorize_sample(image_path: str) -> str:
    """根据图片路径判断数据类别（四类）"""
    # 去除 images/ 前缀
    if image_path.startswith('images/'):
        image_path = image_path[7:]

    if image_path.startswith('syn_v4f_') or image_path.startswith('syn_v4_'):
        return 'v4_synthesis'
    elif image_path.startswith('syn_v2_') or image_path.startswith('syn_') or image_path.startswith('prog_'):
        return 'v3_synthesis'
    elif image_path.startswith('mc_'):
        return 'fin-chart'
    elif image_path.startswith('finmme_'):
        return 'finmme'
    else:
        return 'unknown'


def sample_data(
    input_file: Path,
    config: SamplingConfig
) -> List[Dict]:
    """按四类数据源比例抽样数据"""

    with open(input_file) as f:
        all_data = json.load(f)

    # 按四类分组
    categorized = {cat: [] for cat in config.ratios.keys()}
    categorized['unknown'] = []

    for item in all_data:
        cat = categorize_sample(item['images'][0])
        if cat in categorized:
            categorized[cat].append(item)
        else:
            categorized['unknown'].append(item)

    print(f"原始数据分布 (总计 {len(all_data)} 条):")
    for cat, items in categorized.items():
        if items:
            pct = len(items) / len(all_data) * 100
            print(f"  {cat}: {len(items)} ({pct:.1f}%)")

    # 计算每个类别的抽样数量
    sample_counts = {
        cat: int(config.total_samples * ratio)
        for cat, ratio in config.ratios.items()
    }

    # 处理舍入误差（补到最大类别）
    total_allocated = sum(sample_counts.values())
    if total_allocated < config.total_samples:
        max_cat = max(sample_counts.keys(), key=lambda k: sample_counts[k])
        sample_counts[max_cat] += config.total_samples - total_allocated

    print(f"\n抽样目标 (总计 {config.total_samples} 条):")
    for cat, count in sample_counts.items():
        print(f"  {cat}: {count}")

    # 执行抽样
    random.seed(config.random_seed)
    sampled = []

    for cat, count in sample_counts.items():
        pool = categorized.get(cat, [])
        if len(pool) < count:
            print(f"警告: {cat} 数据不足 ({len(pool)} < {count})，使用全部")
            sampled.extend(pool)
        else:
            sampled.extend(random.sample(pool, count))

    # 打乱顺序
    random.shuffle(sampled)

    # 添加数据来源标记
    for item in sampled:
        item['_source'] = categorize_sample(item['images'][0])

    print(f"\n最终抽样: {len(sampled)} 条")
    return sampled


# ============== Candidate 生成逻辑 ==============

def generate_candidates(
    input_file: Path,
    output_file: Path,
    model_path: str,
    base_model_path: str,
    config: GenerationConfig,
    resume_from: int = 0
):
    """使用 SFT 模型生成 candidates: 1 greedy + N sample"""

    # 延迟导入，仅在 GPU 服务器上需要
    try:
        import torch
        from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
        from peft import PeftModel
    except ImportError as e:
        print(f"错误: 缺少依赖 {e}")
        print("请在 GPU 服务器上运行此命令")
        return

    # 加载数据
    with open(input_file) as f:
        samples = json.load(f)

    print(f"加载 {len(samples)} 条样本")
    print(f"生成配置: {config.num_greedy} greedy + {config.num_sample} sample = {config.total_candidates} candidates")

    # 加载模型
    print(f"加载基座模型: {base_model_path}")
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        base_model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="eager"
    )

    print(f"加载 LoRA 权重: {model_path}")
    model = PeftModel.from_pretrained(model, model_path)
    # 合并 LoRA 权重，减少显存占用
    model = model.merge_and_unload()
    model.eval()

    processor = AutoProcessor.from_pretrained(base_model_path)
    # 设置图片像素限制，避免大图片 OOM
    processor.image_processor.max_pixels = MAX_PIXELS
    processor.image_processor.min_pixels = MIN_PIXELS
    print(f"图片像素限制: max={MAX_PIXELS:,}, min={MIN_PIXELS:,}")

    # 显示显存使用
    mem = torch.cuda.memory_allocated() / 1024**3
    print(f"模型加载后显存: {mem:.2f} GB")
    print("开始生成候选...")
    import sys
    sys.stdout.flush()

    # 准备输出
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 加载已有结果 (支持断点续传)
    results = []
    if output_file.exists() and resume_from > 0:
        with open(output_file) as f:
            results = json.load(f)
        print(f"从 checkpoint 恢复，已有 {len(results)} 条结果")

    # 生成 candidates
    data_dir = input_file.parent.parent  # /app/data

    def generate_single(inputs, do_sample: bool, temperature: float = 1.0) -> str:
        """生成单个响应"""
        with torch.no_grad():
            gen_kwargs = {
                "max_new_tokens": config.max_new_tokens,
                "pad_token_id": processor.tokenizer.pad_token_id,
                "do_sample": do_sample,
            }
            if do_sample:
                gen_kwargs.update({
                    "temperature": temperature,
                    "top_p": config.top_p,
                    "top_k": config.top_k,
                })

            outputs = model.generate(**inputs, **gen_kwargs)

        generated_ids = outputs[0][inputs['input_ids'].shape[1]:]
        return processor.decode(generated_ids, skip_special_tokens=True)

    from PIL import Image
    import time

    start_time = time.time()
    for idx, sample in enumerate(samples[resume_from:]):
        sample_idx = idx + resume_from

        # 每 10 个样本输出进度
        if sample_idx % 10 == 0:
            elapsed = time.time() - start_time
            eta = elapsed / max(idx + 1, 1) * (len(samples) - resume_from - idx - 1) if idx > 0 else 0
            print(f"[{sample_idx}/{len(samples)}] 已用时: {elapsed/60:.1f}min, 预计剩余: {eta/60:.1f}min")
            sys.stdout.flush()

        # 构建输入
        image_path = data_dir / sample['images'][0]
        messages = sample['messages']

        # 提取 system 和 human 消息
        system_msg = None
        human_msg = None
        for msg in messages:
            if msg['from'] == 'system':
                system_msg = msg['value']
            elif msg['from'] == 'human':
                human_msg = msg['value']

        # 准备输入
        try:
            # 加载图片
            image = Image.open(image_path).convert("RGB")

            # 构建消息（使用 PIL Image 对象）
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
            ).to(model.device)

        except Exception as e:
            print(f"警告: 样本 {sample_idx} 输入处理失败: {e}")
            results.append({
                'index': sample_idx,
                'image': sample['images'][0],
                'messages': messages,
                'candidates': [],
                'candidates_meta': [],
                'ground_truth': next((msg['value'] for msg in messages if msg['from'] == 'gpt'), None),
                '_source': sample.get('_source', ''),
                'error': str(e)
            })
            torch.cuda.empty_cache()
            continue

        # 生成 candidates: 先 greedy 再 sample
        candidates = []
        candidates_meta = []  # 记录每个 candidate 的生成方式

        # 1. Greedy 生成
        for i in range(config.num_greedy):
            try:
                response = generate_single(inputs, do_sample=False)
                candidates.append(response)
                candidates_meta.append({'type': 'greedy', 'index': i})
            except Exception as e:
                print(f"警告: 样本 {sample_idx} greedy 生成失败: {e}")
                candidates.append("")
                candidates_meta.append({'type': 'greedy', 'index': i, 'error': str(e)})

        # 2. Sample 生成
        for i in range(config.num_sample):
            try:
                response = generate_single(inputs, do_sample=True, temperature=config.temperature)
                candidates.append(response)
                candidates_meta.append({'type': 'sample', 'index': i, 'temperature': config.temperature})
            except Exception as e:
                print(f"警告: 样本 {sample_idx} sample 生成失败: {e}")
                candidates.append("")
                candidates_meta.append({'type': 'sample', 'index': i, 'error': str(e)})

        # 保存结果
        result = {
            'index': sample_idx,
            'image': sample['images'][0],
            'messages': messages,
            'candidates': candidates,
            'candidates_meta': candidates_meta,
            'ground_truth': next(
                (msg['value'] for msg in messages if msg['from'] == 'gpt'),
                None
            ),
            '_source': sample.get('_source', '')
        }
        results.append(result)

        # 清理显存
        del inputs, image
        torch.cuda.empty_cache()

        # 定期保存 checkpoint
        if (sample_idx + 1) % 50 == 0:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"Checkpoint 已保存: {sample_idx + 1}/{len(samples)}")

    # 最终保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n完成! 生成 {len(results)} 条样本，每条 {config.total_candidates} 个 candidates")
    print(f"  - Greedy: {config.num_greedy}")
    print(f"  - Sample (T={config.temperature}): {config.num_sample}")
    print(f"输出文件: {output_file}")


# ============== CLI ==============

def main():
    parser = argparse.ArgumentParser(description="DPO 数据构建工具 v2")
    subparsers = parser.add_subparsers(dest='command', help='子命令')

    # sample 子命令
    sample_parser = subparsers.add_parser('sample', help='从训练集抽样')
    sample_parser.add_argument(
        '--input', type=Path,
        default=Path('$DATA_ROOT/sft/data/all_train.json'),
        help='输入训练集文件'
    )
    sample_parser.add_argument(
        '--output', type=Path,
        default=Path('$DATA_ROOT/sft/data/dpo/sampled_2000.json'),
        help='输出抽样文件'
    )
    sample_parser.add_argument('--total', type=int, default=2000, help='抽样总数')
    sample_parser.add_argument('--seed', type=int, default=42, help='随机种子')

    # generate 子命令
    gen_parser = subparsers.add_parser('generate', help='生成 candidate 响应')
    gen_parser.add_argument('--input', type=Path, required=True, help='抽样文件')
    gen_parser.add_argument('--output', type=Path, required=True, help='输出文件')
    gen_parser.add_argument(
        '--model', type=str,
        default='/app/outputs/exp-012/checkpoint-640',
        help='SFT 模型路径 (LoRA)'
    )
    gen_parser.add_argument(
        '--base-model', type=str,
        default='/app/models/qwen3-vl-8b-instruct',
        help='基座模型路径'
    )
    gen_parser.add_argument('--num-greedy', type=int, default=1, help='Greedy 候选数')
    gen_parser.add_argument('--num-sample', type=int, default=5, help='Sample 候选数')
    gen_parser.add_argument('--temperature', type=float, default=0.9, help='采样温度')
    gen_parser.add_argument('--top-p', type=float, default=0.95, help='Top-p 采样')
    gen_parser.add_argument('--top-k', type=int, default=50, help='Top-k 采样')
    gen_parser.add_argument('--resume-from', type=int, default=0, help='从指定索引恢复')

    args = parser.parse_args()

    if args.command == 'sample':
        config = SamplingConfig(
            total_samples=args.total,
            random_seed=args.seed
        )
        sampled = sample_data(args.input, config)

        # 保存
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(sampled, f, ensure_ascii=False, indent=2)
        print(f"抽样结果已保存: {args.output}")

    elif args.command == 'generate':
        config = GenerationConfig(
            num_greedy=args.num_greedy,
            num_sample=args.num_sample,
            temperature=args.temperature,
            top_p=args.top_p,
            top_k=args.top_k
        )
        generate_candidates(
            input_file=args.input,
            output_file=args.output,
            model_path=args.model,
            base_model_path=args.base_model,
            config=config,
            resume_from=args.resume_from
        )
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
