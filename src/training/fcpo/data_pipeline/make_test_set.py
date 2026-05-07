#!/usr/bin/env python3
"""创建 8 条测试集用于快速验证"""
import json

with open("/home1/ww/finmme-official/finmme_1000_samples.json") as f:
    samples = json.load(f)[:8]

with open("/home1/ww/finmme-official/finmme_test_8.json", "w") as f:
    json.dump(samples, f, ensure_ascii=False, indent=2)

print(f"Created test set: 8 samples")
for s in samples:
    print(f"  id={s['id']} type={s['question_type']} answer={s['answer'][:50]}")
