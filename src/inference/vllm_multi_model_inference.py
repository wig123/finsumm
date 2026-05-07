#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinMME 多模型 vLLM 推理脚本 - 8卡全并行

策略:
  - 8 个独立进程，每进程占 1 张 H20 (96GB)，tensor_parallel_size=1
  - 每个进程对自己的 ~125 个样本一次性提交批量推理 (llm.chat batch API)
  - 模型从 OSS 下载（内网带宽 ~1-2GB/s，快速缓存）

支持模型 (vLLM 0.18.0):
  internvl3-8b     OpenGVLab/InternVL3_5-8B
  nemotron-12b     nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16
  minicpm-v-4_5    openbmb/MiniCPM-V-4_5
  mimo-vl-7b       XiaomiMiMo/MiMo-VL-7B-RL-2508
  ministral-14b    mistralai/Ministral-3-14B-Instruct-2512

用法:
  python vllm_multi_model_inference.py --model internvl3-8b --model-path /workspace/models/internvl3
  python vllm_multi_model_inference.py --model all --oss-model-bucket oss://... --oss-endpoint ...
"""
import os
import sys
import json
import time
import base64
import argparse
import multiprocessing as mp
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# ===== 模型注册表 =====
MODELS = {
    "internvl3-8b": {
        "hf_id": "OpenGVLab/InternVL3_5-8B",
        "ms_id": "OpenGVLab/InternVL3_5-8B",  # ModelScope ID
        "trust_remote_code": True,
        "max_model_len": 16384,
        "dtype": "bfloat16",
        "output_name": "internvl3_5-8b",
        "mimo_register": False,
    },
    "nemotron-12b": {
        "hf_id": "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16",
        "ms_id": "nv-community/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16",
        "trust_remote_code": True,
        "max_model_len": 16384,
        "dtype": "bfloat16",
        "output_name": "nemotron-nano-12b-vl",
        "mimo_register": False,
    },
    "minicpm-v-4_5": {
        "hf_id": "openbmb/MiniCPM-V-4_5",
        "ms_id": "OpenBMB/MiniCPM-V-4_5",
        "trust_remote_code": True,
        "max_model_len": 16384,
        "dtype": "bfloat16",
        "output_name": "minicpm-v-4_5",
        "mimo_register": False,
    },
    "mimo-vl-7b": {
        "hf_id": "XiaomiMiMo/MiMo-VL-7B-RL-2508",
        "ms_id": "XiaomiMiMo/MiMo-VL-7B-RL-2508",
        "trust_remote_code": True,
        "max_model_len": 16384,
        "dtype": "bfloat16",
        "output_name": "mimo-vl-7b-rl",
        "mimo_register": True,   # 需要 register_mimo_in_vllm
        "is_thinking": True,     # 输出含 <think> 需过滤
    },
    "ministral-14b": {
        "hf_id": "mistralai/Ministral-3-14B-Instruct-2512",
        "ms_id": "mistralai/Ministral-3-14B-Instruct-2512",
        "trust_remote_code": False,
        "max_model_len": 16384,
        "dtype": "bfloat16",
        "output_name": "ministral-3-14b",
        "mimo_register": False,
    },
}


# ===== 工具函数 =====

def split_dataset(samples: List[Dict], n: int) -> List[List[Dict]]:
    base, rem = divmod(len(samples), n)
    splits, start = [], 0
    for i in range(n):
        size = base + (1 if i < rem else 0)
        splits.append(samples[start:start + size])
        start += size
    return splits


def encode_image_b64(image_path: str) -> Tuple[str, str]:
    """返回 (base64_str, mime_type)"""
    ext = Path(image_path).suffix.lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode(), mime


def rewrite_image_path(image_path: str, image_base_dir: Optional[str]) -> str:
    if image_base_dir is None:
        return image_path
    # 尝试多种路径映射，返回第一个存在的
    path = Path(image_path)
    parts = path.parts
    candidates = []
    # 策略1: 原始路径拼接 image_base_dir
    try:
        idx = next(i for i, p in enumerate(parts) if p == "data")
        candidates.append(str(Path(image_base_dir) / Path(*parts[idx:])))
    except StopIteration:
        pass
    # 策略2: 只取 source/folder/file 部分
    if len(parts) >= 3:
        candidates.append(str(Path(image_base_dir) / "data" / Path(*parts[-3:])))
    # 策略3: 取 finmme-bench 之后的部分
    for i, p in enumerate(parts):
        if p == "finmme-bench" and i + 1 < len(parts):
            candidates.append(str(Path(image_base_dir) / Path(*parts[i:])))
            break
    # 策略4: 直接拼文件名
    candidates.append(str(Path(image_base_dir) / path.name))
    for c in candidates:
        if Path(c).exists():
            return c
    return candidates[0] if candidates else image_path


def get_prompt(sample: Dict, prompts: Dict[str, str]) -> str:
    if sample.get("source", "") == "sync_300_cn":
        return prompts.get("cn", prompts.get("en", ""))
    return prompts.get("en", prompts.get("cn", ""))


def strip_thinking(text: str) -> str:
    """去除 MiMo 等 thinking 模型的 <think>...</think>"""
    if "<think>" in text and "</think>" in text:
        end = text.rfind("</think>")
        return text[end + len("</think>"):].strip()
    return text


def download_model(model_cfg: Dict, oss_model_base: Optional[str],
                   oss_endpoint: str, cache_dir: str) -> str:
    """
    模型下载策略:
      1. 若 oss_model_base 不为空 → 从 OSS 下载（内网最快）
      2. 否则 → 从 ModelScope 下载（阿里云内部访问快）
    """
    model_name = model_cfg["output_name"]
    local_path = Path(cache_dir) / model_name

    if local_path.exists() and any(local_path.glob("*.safetensors")):
        print(f"[{model_name}] 模型已缓存: {local_path}")
        return str(local_path)

    if oss_model_base:
        oss_path = f"{oss_model_base.rstrip('/')}/{model_name}/"
        print(f"[{model_name}] 从 OSS 下载: {oss_path}")
        local_path.mkdir(parents=True, exist_ok=True)
        ret = os.system(
            f"ossutil cp -r {oss_path} {local_path}/ "
            f"--endpoint {oss_endpoint} -j 16"
        )
        if ret == 0 and any(local_path.glob("*.safetensors")):
            print(f"[{model_name}] OSS 下载完成")
            return str(local_path)
        print(f"[{model_name}] OSS 下载失败，fallback ModelScope")

    print(f"[{model_name}] 从 ModelScope 下载: {model_cfg['ms_id']}")
    import os as _os
    _os.environ["MODELSCOPE_DOWNLOAD_PARALLELS"] = "16"
    from modelscope import snapshot_download
    local_path.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(model_cfg["ms_id"], local_dir=str(local_path), max_workers=16)
    print(f"[{model_name}] ModelScope 下载完成: {path}")
    return str(local_path)


# ===== GPU Worker =====

def gpu_worker(
    gpu_id: int,
    group_id: int,
    samples: List[Dict],
    model_path: str,
    model_cfg: Dict,
    prompts: Dict[str, str],
    output_dir: Path,
    image_base_dir: Optional[str],
    gpu_memory_utilization: float,
):
    try:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)

        model_name = model_cfg["output_name"]
        print(f"[GPU {gpu_id}] 启动 {model_name} | 样本: {len(samples)}")

        # MiMo-VL 需要在 LLM 初始化前注册
        if model_cfg.get("mimo_register", False):
            _mimo_register()

        from vllm import LLM, SamplingParams

        llm = LLM(
            model=model_path,
            trust_remote_code=model_cfg.get("trust_remote_code", True),
            tensor_parallel_size=1,          # 每张 H20 独立跑，无需 TP
            gpu_memory_utilization=gpu_memory_utilization,
            max_model_len=model_cfg.get("max_model_len", 4096),
            dtype=model_cfg.get("dtype", "bfloat16"),
            limit_mm_per_prompt={"image": 1},
            max_num_seqs=64,                 # 允许大批量并发
            enforce_eager=True,              # 禁用 torch.compile，避免 inductor 崩溃
        )
        print(f"[GPU {gpu_id}] 模型加载完成")

        sampling_params = SamplingParams(
            max_tokens=2048,
            temperature=0.0,   # 贪婪解码，确定性输出
            top_p=1.0,
        )

        # ===== 一次性批量构建所有对话 =====
        all_conversations = []
        valid_samples = []

        for sample in samples:
            img_path = rewrite_image_path(sample["image_path"], image_base_dir)
            if not Path(img_path).exists():
                print(f"[GPU {gpu_id}] 图片不存在: {img_path}")
                continue
            try:
                b64, mime = encode_image_b64(img_path)
            except Exception as e:
                print(f"[GPU {gpu_id}] 图片损坏跳过: {img_path} ({e})")
                continue
            prompt_text = get_prompt(sample, prompts)
            all_conversations.append([{
                "role": "user",
                "content": [
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": prompt_text},
                ],
            }])
            valid_samples.append(sample)

        print(f"[GPU {gpu_id}] 提交批量推理: {len(all_conversations)} 个样本")
        t0 = time.time()

        # 一次性提交所有请求，vLLM continuous batching 自动调度
        outputs = llm.chat(
            messages=all_conversations,
            sampling_params=sampling_params,
            use_tqdm=True,
        )

        total_time = time.time() - t0
        avg_time = total_time / max(len(outputs), 1)
        print(f"[GPU {gpu_id}] 批量完成 | 总耗时 {total_time:.1f}s | 平均 {avg_time:.2f}s/样本")

        # ===== 整理结果 =====
        results = []
        is_thinking = model_cfg.get("is_thinking", False)

        for sample, output in zip(valid_samples, outputs):
            text = output.outputs[0].text
            if is_thinking:
                text = strip_thinking(text)
            results.append({
                "id": sample["id"],
                "model": model_name,
                "gpu_id": gpu_id,
                "framework": "vllm",
                "generated_text": text,
                "ground_truth": sample.get("ground_truth", ""),
                "inference_time": output.metrics.finished_time - output.metrics.first_scheduled_time
                    if hasattr(output, "metrics") and output.metrics else avg_time,
                "image_path": sample["image_path"],
                "source": sample.get("source", ""),
            })

        # 处理图片不存在的样本
        missing = set(s["id"] for s in samples) - set(r["id"] for r in results)
        for sid in missing:
            results.append({
                "id": sid,
                "model": model_name,
                "error": "image_not_found",
            })

        out_file = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        print(f"[GPU {gpu_id}] 结果已保存: {out_file}")

    except Exception as e:
        import traceback
        print(f"[GPU {gpu_id}] Worker 崩溃: {e}")
        traceback.print_exc()


def _mimo_register():
    """注册 MiMo-VL 到 vLLM 模型注册表"""
    register_path = "/opt/model_patches/register_mimo_in_vllm.py"
    if not Path(register_path).exists():
        # 尝试从 OSS 获取（启动脚本应已下载到此路径）
        print("[MiMo] 未找到注册文件，尝试直接加载（trust_remote_code 模式）")
        return
    import importlib.util
    spec = importlib.util.spec_from_file_location("register_mimo", register_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("[MiMo] 注册完成")


# ===== 合并结果 =====

def merge_results(output_dir: Path, model_name: str, num_gpus: int) -> None:
    import numpy as np
    all_results = []
    for gpu_id in range(num_gpus):
        f = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        if f.exists():
            with open(f) as fp:
                for line in fp:
                    all_results.append(json.loads(line))

    all_results.sort(key=lambda x: str(x.get("id", "")))

    merged = output_dir / f"{model_name}_results.jsonl"
    with open(merged, "w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    success = [r for r in all_results if "error" not in r]
    fail = len(all_results) - len(success)
    times = [r.get("inference_time", 0) for r in success if r.get("inference_time")]

    print(f"\n{'='*60}")
    print(f"{model_name} 推理汇总")
    print(f"{'='*60}")
    print(f"总样本: {len(all_results)} | 成功: {len(success)} | 失败: {fail}")
    if times:
        print(f"平均耗时: {np.mean(times):.2f}s | 总计: {sum(times):.1f}s")
    print(f"结果文件: {merged}")
    print(f"{'='*60}\n")

    # 清理临时分片文件
    for gpu_id in range(num_gpus):
        tmp = output_dir / f"{model_name}_gpu{gpu_id}.jsonl"
        if tmp.exists():
            tmp.unlink()


# ===== 主函数 =====

def run_model(model_key: str, args):
    model_cfg = MODELS[model_key]
    model_name = model_cfg["output_name"]

    # 下载模型
    model_path = args.model_path or download_model(
        model_cfg,
        oss_model_base=args.oss_model_base,
        oss_endpoint=args.oss_endpoint,
        cache_dir=args.model_cache_dir,
    )

    # 加载数据集
    with open(args.dataset, encoding="utf-8") as f:
        samples = json.load(f)
    print(f"\n{model_name}: 共 {len(samples)} 个样本，分配到 {args.num_gpus} 张 GPU")

    # 加载 prompts
    prompts = {}
    if Path(args.prompt_cn).exists():
        prompts["cn"] = Path(args.prompt_cn).read_text(encoding="utf-8").strip()
    if Path(args.prompt_en).exists():
        prompts["en"] = Path(args.prompt_en).read_text(encoding="utf-8").strip()

    output_dir = Path(args.output_dir)
    splits = split_dataset(samples, args.num_gpus)

    # 启动 8 个 GPU 进程
    procs = []
    for gpu_id in range(args.num_gpus):
        p = mp.Process(
            target=gpu_worker,
            args=(
                gpu_id, gpu_id,
                splits[gpu_id],
                model_path, model_cfg, prompts,
                output_dir, args.image_base_dir,
                args.gpu_memory,
            ),
        )
        p.start()
        procs.append(p)

    for p in procs:
        p.join()

    merge_results(output_dir, model_name, args.num_gpus)


def main():
    parser = argparse.ArgumentParser(description="FinMME vLLM 8卡并行推理")
    parser.add_argument("--model", required=True,
                        choices=list(MODELS.keys()) + ["all"],
                        help="模型名称，'all' 表示顺序跑全部")
    parser.add_argument("--model-path", default=None,
                        help="模型本地路径（覆盖自动下载）")
    parser.add_argument("--dataset",
                        default="/workspace/data/dataset_index_1000.json")
    parser.add_argument("--image-base-dir", default=None,
                        help="图片根目录（用于路径重写）")
    parser.add_argument("--prompt-en", default="/workspace/data/prompt_en.txt")
    parser.add_argument("--prompt-cn", default="/workspace/data/prompt.txt")
    parser.add_argument("--output-dir", default="/workspace/outputs")
    parser.add_argument("--num-gpus", type=int, default=8)
    parser.add_argument("--gpu-memory", type=float, default=0.90,
                        help="vLLM GPU 显存利用率")
    parser.add_argument("--model-cache-dir", default="/workspace/models")
    # OSS 模型缓存（优先）
    parser.add_argument("--oss-model-base", default=None,
                        help="OSS 模型缓存路径, e.g. oss://bucket/models")
    parser.add_argument("--oss-endpoint",
                        default="oss-cn-beijing-internal.aliyuncs.com")
    args = parser.parse_args()

    if args.model == "all":
        for key in MODELS:
            print(f"\n{'#'*60}\n# 开始: {key}\n{'#'*60}")
            run_model(key, args)
    else:
        run_model(args.model, args)


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()
