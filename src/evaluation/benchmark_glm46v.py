#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FinMME Benchmark - GLM-4.6V-Flash 8-GPU Parallel Inference
"""
import os
import json
import time
import argparse
import torch
import torch.multiprocessing as mp
from pathlib import Path
from typing import Dict, List
from tqdm import tqdm
from PIL import Image
import filelock

mp.set_start_method('spawn', force=True)

MODEL_PATH = "$MODEL_ROOT/GLM-4.6V-Flash"
DATA_BASE = "/data/finmme-bench/data"
OUTPUT_BASE = "/data/finmme-bench/outputs/glm46v"
DATASETS = ["fin-chart_200", "finmme_200", "sync_300_cn", "sync_300_en"]


def get_all_samples() -> List[Dict]:
    all_samples = []
    for dataset in DATASETS:
        dataset_path = Path(DATA_BASE) / dataset
        if not dataset_path.exists():
            continue
        for subdir in sorted(dataset_path.iterdir()):
            if not subdir.is_dir():
                continue
            image_file = None
            for img_name in ["chart.png", "image.png", "chart.jpg", "image.jpg"]:
                img_path = subdir / img_name
                if img_path.exists():
                    image_file = str(img_path)
                    break
            if not image_file:
                for f in subdir.iterdir():
                    if f.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                        image_file = str(f)
                        break
            if not image_file:
                continue
            gt_file = subdir / "ground_truth.txt"
            ground_truth = ""
            if gt_file.exists():
                with open(gt_file, "r", encoding="utf-8") as f:
                    ground_truth = f.read().strip()
            all_samples.append({
                "id": subdir.name,
                "image_path": image_file,
                "ground_truth": ground_truth,
                "source": dataset
            })
    return all_samples


def load_model(gpu_id: int):
    from transformers import Glm46VProcessor, Glm46VForConditionalGeneration
    device = f"cuda:{gpu_id}"
    processor = Glm46VProcessor.from_pretrained(MODEL_PATH)
    model = Glm46VForConditionalGeneration.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
        device_map=device,
    )
    model.eval()
    return model, processor, device


def inference_worker(
    gpu_id: int,
    samples: List[Dict],
    prompt_cn: str,
    prompt_en: str,
    output_file: str,
    progress_queue: mp.Queue
):
    torch.cuda.set_device(gpu_id)
    try:
        model, processor, device = load_model(gpu_id)
        print(f"GPU {gpu_id}: Model loaded, VRAM: {torch.cuda.memory_allocated(gpu_id)/1e9:.1f}GB")
    except Exception as e:
        print(f"GPU {gpu_id}: Failed to load model: {e}")
        return

    lock = filelock.FileLock(f"{output_file}.lock")

    for sample in samples:
        sample_id = sample["id"]
        image_path = sample["image_path"]
        source = sample.get("source", "")
        prompt_text = prompt_cn if source == "sync_300_cn" else prompt_en
        prompt_lang = "zh" if source == "sync_300_cn" else "en"

        try:
            image = Image.open(image_path).convert("RGB")
            messages = [{"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt_text}
            ]}]
            inputs = processor.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True,
                return_dict=True, return_tensors="pt"
            ).to(device)

            start_time = time.time()
            with torch.no_grad():
                outputs = model.generate(**inputs, max_new_tokens=2048, do_sample=False)
            inference_time = time.time() - start_time

            input_len = inputs["input_ids"].shape[1]
            generated_text = processor.decode(outputs[0][input_len:], skip_special_tokens=True)

            result = {
                "id": sample_id, "model": "GLM-4.6V-Flash",
                "generated_text": generated_text,
                "ground_truth": sample.get("ground_truth", ""),
                "inference_time": inference_time,
                "image_path": image_path, "source": source, "prompt_lang": prompt_lang,
            }
        except Exception as e:
            result = {
                "id": sample_id, "model": "GLM-4.6V-Flash",
                "error": str(e), "image_path": image_path, "source": source,
            }

        with lock:
            with open(output_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        progress_queue.put(1)

    del model
    torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-cn", type=str, default="/data/finmme-bench/prompt.txt")
    parser.add_argument("--prompt-en", type=str, default="/data/finmme-bench/prompt_en.txt")
    parser.add_argument("--output-dir", type=str, default=OUTPUT_BASE)
    parser.add_argument("--num-gpus", type=int, default=8)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "glm46v_results.jsonl"

    with open(args.prompt_cn, "r", encoding="utf-8") as f:
        prompt_cn = f.read().strip()
    with open(args.prompt_en, "r", encoding="utf-8") as f:
        prompt_en = f.read().strip()

    samples = get_all_samples()
    print(f"Total samples: {len(samples)}")

    # Resume support
    completed_ids = set()
    if output_file.exists():
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    completed_ids.add(json.loads(line)["id"])
                except:
                    pass
    pending = [s for s in samples if s["id"] not in completed_ids]
    print(f"Completed: {len(completed_ids)} | Pending: {len(pending)}")

    if not pending:
        print("All done!")
        return

    # Distribute samples
    samples_per_gpu = [[] for _ in range(args.num_gpus)]
    for i, s in enumerate(pending):
        samples_per_gpu[i % args.num_gpus].append(s)

    progress_queue = mp.Queue()
    processes = []
    for gpu_id in range(args.num_gpus):
        if not samples_per_gpu[gpu_id]:
            continue
        p = mp.Process(target=inference_worker, args=(
            gpu_id, samples_per_gpu[gpu_id], prompt_cn, prompt_en,
            str(output_file), progress_queue
        ))
        p.start()
        processes.append(p)

    with tqdm(total=len(pending), desc="GLM-4.6V 8-GPU") as pbar:
        done = 0
        while done < len(pending):
            try:
                progress_queue.get(timeout=600)
                done += 1
                pbar.update(1)
            except:
                if not any(p.is_alive() for p in processes):
                    break

    for p in processes:
        p.join()

    # Stats
    results = []
    with open(output_file, "r", encoding="utf-8") as f:
        for line in f:
            results.append(json.loads(line))
    success = len([r for r in results if "error" not in r])
    failed = len(results) - success
    avg_time = sum(r.get("inference_time", 0) for r in results if "error" not in r) / max(success, 1)

    stats = {
        "model": "GLM-4.6V-Flash", "num_gpus": args.num_gpus,
        "total": len(samples), "success": success, "failed": failed,
        "avg_time_per_sample": avg_time,
    }
    with open(output_dir / "glm46v_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    print(f"\nDone! Success: {success}/{len(samples)}, Avg: {avg_time:.1f}s/sample")


if __name__ == "__main__":
    main()
