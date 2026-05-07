"""
patch_fcpo.py — 对 LLaMA-Factory 0.9.x 打 FCPO 补丁 (4 处修改)

实现 FCPO 乘法 margin: L_i = -log σ(β × margin_i × Δlogits_i)
margin=0 的样本梯度为零，不参与训练。

修改文件:
  1. data/converter.py       — align_dataset() 保留 margin 列
  2. data/processor/pairwise.py — preprocess_dataset() 传递 margin
  3. data/collator.py         — PairwiseDataCollatorWithPadding 传 margin 到 batch
  4. train/dpo/trainer.py     — compute_preference_loss 实现 FCPO

用法:
  python patch_fcpo.py $LLAMAFACTORY_PATH    # 指定安装路径
  python patch_fcpo.py                       # 自动查找
  python patch_fcpo.py --verify              # 只检查，不修改
"""

import sys
import os

VERIFY_ONLY = "--verify" in sys.argv


def find_src():
    """查找 LLaMA-Factory src/llamafactory 路径"""
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            continue
        p = os.path.join(arg, "src", "llamafactory")
        if os.path.isdir(p):
            return p

    for p in ["$LLAMAFACTORY_PATH/src/llamafactory", "/tmp/LLaMA-Factory/src/llamafactory"]:
        if os.path.isdir(p):
            return p

    try:
        import llamafactory
        return os.path.dirname(llamafactory.__file__)
    except ImportError:
        pass

    raise FileNotFoundError("找不到 LLaMA-Factory")


def patch(filepath, old, new, desc):
    """精确字符串替换"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if "FCPO" in content and old not in content:
        print(f"  [跳过] {desc} — 已 patch")
        return True

    if old not in content:
        print(f"  [失败] {desc}")
        print(f"         未找到匹配: {repr(old[:100])}...")
        return False

    if VERIFY_ONLY:
        print(f"  [待改] {desc}")
        return True

    content = content.replace(old, new, 1)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [成功] {desc}")
    return True


def main():
    src = find_src()
    print(f"源码路径: {src}")
    ok = []

    # ============================================================
    # 1. converter.py — 保留 margin 列
    # ============================================================
    f1 = os.path.join(src, "data", "converter.py")
    print(f"\n[1/4] {f1}")
    ok.append(patch(f1,
        # --- old ---
        '    dataset_converter = get_dataset_converter(dataset_attr.formatting, dataset_attr, data_args)\n'
        '    return dataset.map(\n'
        '        dataset_converter,\n'
        '        batched=False,\n'
        '        remove_columns=column_names,\n'
        '        **kwargs,\n'
        '    )',
        # --- new ---
        '    dataset_converter = get_dataset_converter(dataset_attr.formatting, dataset_attr, data_args)\n'
        '\n'
        '    # FCPO: save margin before column removal\n'
        '    _fcpo_has_margin = "margin" in column_names\n'
        '    _fcpo_margins = list(dataset["margin"]) if _fcpo_has_margin else None\n'
        '\n'
        '    _fcpo_result = dataset.map(\n'
        '        dataset_converter,\n'
        '        batched=False,\n'
        '        remove_columns=column_names,\n'
        '        **kwargs,\n'
        '    )\n'
        '\n'
        '    # FCPO: restore margin column\n'
        '    if _fcpo_margins is not None and len(_fcpo_margins) == len(_fcpo_result):\n'
        '        _fcpo_result = _fcpo_result.add_column("margin", _fcpo_margins)\n'
        '\n'
        '    return _fcpo_result',
        "保留 margin 列"
    ))

    # ============================================================
    # 2. pairwise.py — preprocess_dataset 传递 margin
    # ============================================================
    f2 = os.path.join(src, "data", "processor", "pairwise.py")
    print(f"\n[2/4] {f2}")
    ok.append(patch(f2,
        # --- old ---
        '            model_inputs["images"].append(examples["_images"][i])\n'
        '            model_inputs["videos"].append(examples["_videos"][i])\n'
        '            model_inputs["audios"].append(examples["_audios"][i])\n'
        '\n'
        '        return model_inputs',
        # --- new ---
        '            model_inputs["images"].append(examples["_images"][i])\n'
        '            model_inputs["videos"].append(examples["_videos"][i])\n'
        '            model_inputs["audios"].append(examples["_audios"][i])\n'
        '            # FCPO: pass margin through preprocessing\n'
        '            if "margin" in examples:\n'
        '                model_inputs["margin"].append(examples["margin"][i])\n'
        '\n'
        '        return model_inputs',
        "传递 margin"
    ))

    # ============================================================
    # 3. collator.py — margin 传入 batch
    # ============================================================
    f3 = os.path.join(src, "data", "collator.py")
    print(f"\n[3/4] {f3}")
    ok.append(patch(f3,
        # --- old ---
        '        return super().__call__(concatenated_features)',
        # --- new ---
        '        # FCPO: extract per-pair margin before concatenation\n'
        '        _fcpo_margin = None\n'
        '        if features and "margin" in features[0]:\n'
        '            import torch as _torch\n'
        '            _fcpo_margin = _torch.tensor([f["margin"] for f in features], dtype=_torch.float32)\n'
        '\n'
        '        _batch = super().__call__(concatenated_features)\n'
        '\n'
        '        if _fcpo_margin is not None:\n'
        '            _batch["margin"] = _fcpo_margin\n'
        '\n'
        '        return _batch',
        "margin 传入 batch"
    ))

    # ============================================================
    # 4. trainer.py — FCPO 乘法 margin
    # ============================================================
    f4 = os.path.join(src, "train", "dpo", "trainer.py")
    print(f"\n[4/4] {f4}")

    # 4a: compute_preference_loss 加 margin 参数
    ok.append(patch(f4,
        '    def compute_preference_loss(\n'
        '        self,\n'
        '        policy_chosen_logps: "torch.Tensor",\n'
        '        policy_rejected_logps: "torch.Tensor",\n'
        '        reference_chosen_logps: Optional["torch.Tensor"],\n'
        '        reference_rejected_logps: Optional["torch.Tensor"],\n'
        '    ) -> tuple["torch.Tensor", "torch.Tensor", "torch.Tensor"]:\n'
        '        r"""Compute loss for preference learning."""\n'
        '        if not self.finetuning_args.use_ref_model:',
        # --- new ---
        '    def compute_preference_loss(\n'
        '        self,\n'
        '        policy_chosen_logps: "torch.Tensor",\n'
        '        policy_rejected_logps: "torch.Tensor",\n'
        '        reference_chosen_logps: Optional["torch.Tensor"],\n'
        '        reference_rejected_logps: Optional["torch.Tensor"],\n'
        '        fcpo_margin: Optional["torch.Tensor"] = None,\n'
        '    ) -> tuple["torch.Tensor", "torch.Tensor", "torch.Tensor"]:\n'
        '        r"""Compute loss for preference learning. FCPO: supports multiplicative margin."""\n'
        '        if not self.finetuning_args.use_ref_model:',
        "compute_preference_loss 签名"
    ))

    # 4b: DPO 分支中实现 FCPO
    ok.append(patch(f4,
        '            losses, chosen_rewards, rejected_rewards = self.dpo_loss(\n'
        '                policy_chosen_logps, policy_rejected_logps, reference_chosen_logps, reference_rejected_logps\n'
        '            )',
        # --- new ---
        '            # FCPO: multiplicative margin L_i = -log σ(β * margin_i * Δlogits_i)\n'
        '            if fcpo_margin is not None and fcpo_margin.abs().sum().item() > 1e-6:\n'
        '                import torch.nn.functional as _F\n'
        '                _dev = self.accelerator.device\n'
        '                _c = policy_chosen_logps.to(_dev) - reference_chosen_logps.to(_dev)\n'
        '                _r = policy_rejected_logps.to(_dev) - reference_rejected_logps.to(_dev)\n'
        '                _logits = _c - _r\n'
        '                losses = -_F.logsigmoid(self.beta * fcpo_margin.to(_dev) * _logits)\n'
        '                chosen_rewards = self.beta * _c.detach()\n'
        '                rejected_rewards = self.beta * _r.detach()\n'
        '            else:\n'
        '                losses, chosen_rewards, rejected_rewards = self.dpo_loss(\n'
        '                    policy_chosen_logps, policy_rejected_logps, reference_chosen_logps, reference_rejected_logps\n'
        '                )',
        "FCPO 乘法 margin 实现"
    ))

    # 4c: get_batch_loss_metrics 传递 margin
    ok.append(patch(f4,
        '        losses, chosen_rewards, rejected_rewards = self.compute_preference_loss(\n'
        '            policy_chosen_logps,\n'
        '            policy_rejected_logps,\n'
        '            reference_chosen_logps,\n'
        '            reference_rejected_logps,\n'
        '        )',
        # --- new ---
        '        # FCPO: extract per-pair margin from batch\n'
        '        _fcpo_margin = batch.get("margin", None)\n'
        '        losses, chosen_rewards, rejected_rewards = self.compute_preference_loss(\n'
        '            policy_chosen_logps,\n'
        '            policy_rejected_logps,\n'
        '            reference_chosen_logps,\n'
        '            reference_rejected_logps,\n'
        '            fcpo_margin=_fcpo_margin,\n'
        '        )',
        "get_batch_loss_metrics 传递 margin"
    ))

    # ============================================================
    # 总结
    # ============================================================
    print("\n" + "=" * 50)
    n_ok = sum(ok)
    n_total = len(ok)
    print(f"FCPO Patch: {n_ok}/{n_total} 成功")

    if all(ok):
        print("所有补丁已就绪！")
    else:
        print("部分补丁失败，请检查 LLaMA-Factory 版本。")

    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
