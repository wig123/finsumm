"""
传统指标评估器（BLEU、ROUGE、BERTScore 等）
用于与论文标准基准对比
"""

import re
from typing import Dict, List
import numpy as np


class TraditionalMetricsEvaluator:
    """传统指标评估器"""

    def __init__(self):
        """初始化评估器（延迟加载依赖）"""
        self._bleu_scorer = None
        self._rouge_scorer = None
        self._bertscore = None
        self._meteor = None
        self._cider = None

    def _get_bleu_scorer(self):
        """延迟加载 SacreBLEU"""
        if self._bleu_scorer is None:
            try:
                from sacrebleu.metrics import BLEU
                self._bleu_scorer = BLEU()
            except ImportError:
                raise ImportError("请安装 sacrebleu: pip install sacrebleu")
        return self._bleu_scorer

    def _get_rouge_scorer(self):
        """延迟加载 ROUGE"""
        if self._rouge_scorer is None:
            try:
                from rouge_score import rouge_scorer
                self._rouge_scorer = rouge_scorer.RougeScorer(
                    ['rouge1', 'rouge2', 'rougeL'],
                    use_stemmer=True
                )
            except ImportError:
                raise ImportError("请安装 rouge-score: pip install rouge-score")
        return self._rouge_scorer

    def _get_bertscore(self):
        """延迟加载 BERTScore"""
        if self._bertscore is None:
            try:
                import bert_score
                self._bertscore = bert_score
            except ImportError:
                raise ImportError("请安装 bert-score: pip install bert-score")
        return self._bertscore

    def _get_meteor(self):
        """延迟加载 METEOR (通过 nltk)"""
        if self._meteor is None:
            try:
                import nltk
                try:
                    nltk.data.find('corpora/wordnet')
                except LookupError:
                    nltk.download('wordnet', quiet=True)
                    nltk.download('punkt', quiet=True)
                    nltk.download('punkt_tab', quiet=True)
                from nltk.translate.meteor_score import meteor_score
                self._meteor = meteor_score
            except ImportError:
                raise ImportError("请安装 nltk: pip install nltk")
        return self._meteor

    def _get_cider(self):
        """延迟加载 CIDEr (通过 pycocoevalcap)"""
        if self._cider is None:
            try:
                from pycocoevalcap.cider.cider import Cider
                self._cider = Cider()
            except ImportError:
                raise ImportError("请安装 pycocoevalcap: pip install pycocoevalcap")

    def _extract_section(self, text: str, section_name: str) -> str:
        """
        从文本中提取特定章节

        Args:
            text: 完整文本
            section_name: 章节名称（如"数据关系"、"核心洞察"）

        Returns:
            提取的章节文本
        """
        # 匹配 【章节名】 或 **章节名**
        pattern = rf'[【\[].*?{section_name}.*?[】\]]\s*(.*?)(?=[【\[]|$)'
        match = re.search(pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()

        # 如果没找到，尝试匹配 **章节名**
        pattern2 = rf'\*\*.*?{section_name}.*?\*\*\s*(.*?)(?=\*\*|$)'
        match2 = re.search(pattern2, text, re.DOTALL)

        if match2:
            return match2.group(1).strip()

        return ""

    def calculate_bleu(
        self,
        predictions: List[str],
        references: List[str]
    ) -> Dict:
        """
        计算 BLEU 分数

        Args:
            predictions: 预测文本列表
            references: 参考文本列表

        Returns:
            BLEU 分数字典
        """
        bleu = self._get_bleu_scorer()

        # SacreBLEU 要求 references 是 List[List[str]]
        refs_wrapped = [[ref] for ref in references]

        result = bleu.corpus_score(predictions, refs_wrapped)

        return {
            "bleu": result.score / 100.0,  # 转换为 0-1 范围
            "bleu_1": result.precisions[0] / 100.0,
            "bleu_2": result.precisions[1] / 100.0,
            "bleu_3": result.precisions[2] / 100.0,
            "bleu_4": result.precisions[3] / 100.0,
            "brevity_penalty": result.bp
        }

    def calculate_rouge(
        self,
        predictions: List[str],
        references: List[str]
    ) -> Dict:
        """
        计算 ROUGE 分数

        Args:
            predictions: 预测文本列表
            references: 参考文本列表

        Returns:
            ROUGE 分数字典
        """
        rouge = self._get_rouge_scorer()

        all_scores = {
            'rouge1': [],
            'rouge2': [],
            'rougeL': []
        }

        for pred, ref in zip(predictions, references):
            scores = rouge.score(ref, pred)

            for metric in all_scores.keys():
                all_scores[metric].append(scores[metric].fmeasure)

        return {
            "rouge1": np.mean(all_scores['rouge1']),
            "rouge2": np.mean(all_scores['rouge2']),
            "rougeL": np.mean(all_scores['rougeL']),
            "rouge1_precision": np.mean([
                rouge.score(ref, pred)['rouge1'].precision
                for pred, ref in zip(predictions, references)
            ]),
            "rouge1_recall": np.mean([
                rouge.score(ref, pred)['rouge1'].recall
                for pred, ref in zip(predictions, references)
            ])
        }

    def calculate_bertscore(
        self,
        predictions: List[str],
        references: List[str],
        model_type: str = "microsoft/deberta-xlarge-mnli",
        device: str = "cuda"
    ) -> Dict:
        """
        计算 BERTScore

        Args:
            predictions: 预测文本列表
            references: 参考文本列表
            model_type: BERT 模型类型
            device: 设备（cuda 或 cpu）

        Returns:
            BERTScore 字典
        """
        bert_score = self._get_bertscore()

        P, R, F1 = bert_score.score(
            predictions,
            references,
            model_type=model_type,
            device=device,
            verbose=False
        )

        return {
            "bertscore_precision": P.mean().item(),
            "bertscore_recall": R.mean().item(),
            "bertscore_f1": F1.mean().item()
        }

    def calculate_meteor(
        self,
        predictions: List[str],
        references: List[str]
    ) -> Dict:
        """
        计算 METEOR 分数

        Args:
            predictions: 预测文本列表
            references: 参考文本列表

        Returns:
            METEOR 分数字典
        """
        meteor_score_fn = self._get_meteor()
        from nltk import word_tokenize

        scores = []
        for pred, ref in zip(predictions, references):
            try:
                # METEOR 需要分词
                pred_tokens = word_tokenize(pred)
                ref_tokens = word_tokenize(ref)
                score = meteor_score_fn([ref_tokens], pred_tokens)
                scores.append(score)
            except Exception:
                scores.append(0.0)

        return {
            "meteor": float(np.mean(scores)) if scores else 0.0
        }

    def calculate_cider(
        self,
        predictions: List[str],
        references: List[str]
    ) -> Dict:
        """
        计算 CIDEr 分数

        Args:
            predictions: 预测文本列表
            references: 参考文本列表

        Returns:
            CIDEr 分数字典
        """
        self._get_cider()
        from pycocoevalcap.cider.cider import Cider
        cider = Cider()

        # CIDEr 需要特定格式: {id: [text]}
        gts = {str(i): [ref] for i, ref in enumerate(references)}
        res = {str(i): [pred] for i, pred in enumerate(predictions)}

        try:
            score, _ = cider.compute_score(gts, res)
            return {"cider": float(score)}
        except Exception as e:
            print(f"⚠️  CIDEr 计算失败: {e}")
            return {"cider": 0.0}

    def evaluate_by_section(
        self,
        predictions: List[str],
        references: List[str],
        section_name: str
    ) -> Dict:
        """
        按章节评估（用于分段评估）

        Args:
            predictions: 预测文本列表
            references: 参考文本列表
            section_name: 章节名称

        Returns:
            该章节的评估结果
        """
        # 提取章节
        pred_sections = [self._extract_section(p, section_name) for p in predictions]
        ref_sections = [self._extract_section(r, section_name) for r in references]

        # 过滤空章节
        valid_pairs = [
            (pred, ref) for pred, ref in zip(pred_sections, ref_sections)
            if pred and ref
        ]

        if not valid_pairs:
            return {
                "error": f"未找到章节: {section_name}",
                "valid_samples": 0
            }

        pred_sections_valid, ref_sections_valid = zip(*valid_pairs)

        # 计算指标
        bleu_scores = self.calculate_bleu(
            list(pred_sections_valid),
            list(ref_sections_valid)
        )

        rouge_scores = self.calculate_rouge(
            list(pred_sections_valid),
            list(ref_sections_valid)
        )

        return {
            **bleu_scores,
            **rouge_scores,
            "section": section_name,
            "valid_samples": len(valid_pairs)
        }

    def evaluate(
        self,
        predictions: List[str],
        references: List[str],
        use_bertscore: bool = True,
        device: str = "cuda"
    ) -> Dict:
        """
        完整评估（全文 + 各章节）

        Args:
            predictions: 预测文本列表
            references: 参考文本列表
            use_bertscore: 是否计算 BERTScore（较慢）
            device: 设备

        Returns:
            完整评估结果
        """
        # 全文评估
        overall_bleu = self.calculate_bleu(predictions, references)
        overall_rouge = self.calculate_rouge(predictions, references)

        results = {
            "overall": {
                **overall_bleu,
                **overall_rouge
            }
        }

        # BERTScore（可选）
        if use_bertscore:
            try:
                overall_bert = self.calculate_bertscore(
                    predictions,
                    references,
                    device=device
                )
                results["overall"].update(overall_bert)
            except Exception as e:
                print(f"⚠️  BERTScore 计算失败: {e}")

        # METEOR
        try:
            meteor_scores = self.calculate_meteor(predictions, references)
            results["overall"].update(meteor_scores)
        except Exception as e:
            print(f"⚠️  METEOR 计算失败: {e}")

        # CIDEr
        try:
            cider_scores = self.calculate_cider(predictions, references)
            results["overall"].update(cider_scores)
        except Exception as e:
            print(f"⚠️  CIDEr 计算失败: {e}")

        # 分章节评估
        sections = ["图表构成", "数据关系", "模式特征", "核心洞察"]

        for section in sections:
            section_key = f"section_{section}"
            results[section_key] = self.evaluate_by_section(
                predictions,
                references,
                section
            )

        return results

    def evaluate_batch(
        self,
        predictions: List[str],
        references: List[str],
        **kwargs
    ) -> Dict:
        """
        批量评估（别名，保持接口一致）

        Args:
            predictions: 预测文本列表
            references: 参考文本列表
            **kwargs: 传递给 evaluate() 的参数

        Returns:
            评估结果
        """
        return self.evaluate(predictions, references, **kwargs)
