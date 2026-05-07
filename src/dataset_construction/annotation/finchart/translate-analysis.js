const fs = require('fs');
const path = require('path');
const OpenAI = require('openai');

// 配置 API 易 - Gemini 2.5 Flash
const API_KEY = '<YOUR_API_KEY>';
const BASE_URL = '<YOUR_LLM_PROXY>/v1';
const MODEL = 'gemini-2.5-flash-preview-09-2025';

// 初始化客户端
const client = new OpenAI({
  apiKey: API_KEY,
  baseURL: BASE_URL
});

// 输入目录
const INPUT_DIR = 'output-full-analysis-continue-1764221988787';

// 结果统计
const results = {
  success: [],
  failed: [],
  skipped: []
};

// 翻译单个文件
async function translateFile(subDir, index, total) {
  const analysisPath = path.join(INPUT_DIR, subDir, 'analysis.txt');
  const outputPath = path.join(INPUT_DIR, subDir, 'analysis_en.txt');

  try {
    // 检查 analysis.txt 是否存在
    if (!fs.existsSync(analysisPath)) {
      console.log(`⏭️  [${index + 1}/${total}] 跳过: ${subDir} (analysis.txt 不存在)`);
      results.skipped.push(subDir);
      return;
    }

    // 检查 analysis_en.txt 是否已存在
    if (fs.existsSync(outputPath)) {
      console.log(`⏭️  [${index + 1}/${total}] 跳过: ${subDir} (已翻译)`);
      results.skipped.push(subDir);
      return;
    }

    console.log(`🔄 [${index + 1}/${total}] 翻译中: ${subDir}`);

    // 读取原文
    const chineseText = fs.readFileSync(analysisPath, 'utf8');
    console.log(`   📝 原文长度: ${chineseText.length} 字符`);

    const startTime = Date.now();

    // 调用 API 翻译
    const completion = await client.chat.completions.create({
      model: MODEL,
      messages: [
        {
          role: 'system',
          content: `You are a professional financial document translator. Translate the following Chinese financial chart analysis into English.

**Translation Requirements:**
1. **REPLACE Chinese section headers with English equivalents:**
   - 【图表构成】 → [Chart Components]
   - 【数据关系】 → [Data Relationships]
   - 【模式特征】 → [Pattern Characteristics]
   - 【核心洞察】 → [Core Insights]
2. Keep all numerical values, percentages, and data points unchanged
3. Use professional financial terminology
4. Preserve the original formatting (bullet points, line breaks, etc.)
5. Keep technical terms accurate (e.g., 同比 = YoY, 环比 = MoM, 占比 = proportion)
6. Do not add any explanations or comments - only provide the translation
7. The entire output must be in English, including all section headers`
        },
        {
          role: 'user',
          content: chineseText
        }
      ],
      temperature: 0.3,
      max_completion_tokens: 4096
    });

    const duration = Date.now() - startTime;
    const englishText = completion.choices?.[0]?.message?.content || '';

    if (!englishText) {
      throw new Error('API 返回了空内容');
    }

    // 保存翻译结果
    fs.writeFileSync(outputPath, englishText, 'utf8');

    console.log(`✅ [${index + 1}/${total}] 成功: ${subDir} (耗时: ${duration}ms)`);
    console.log(`   📊 译文长度: ${englishText.length} 字符`);
    console.log(`   💾 已保存: analysis_en.txt\n`);

    results.success.push({
      subDir,
      duration,
      originalLength: chineseText.length,
      translatedLength: englishText.length,
      usage: completion.usage
    });

  } catch (error) {
    console.error(`❌ [${index + 1}/${total}] 失败: ${subDir}`);
    console.error(`   错误: ${error.message}\n`);

    results.failed.push({
      subDir,
      error: error.message
    });
  }
}

// 并发控制函数
async function processConcurrently(tasks, concurrency) {
  const executing = [];

  for (const task of tasks) {
    const promise = task().then(result => {
      executing.splice(executing.indexOf(promise), 1);
      return result;
    });

    executing.push(promise);

    if (executing.length >= concurrency) {
      await Promise.race(executing);
    }
  }

  await Promise.all(executing);
}

// 保存汇总报告
function saveSummaryReport() {
  const report = {
    config: {
      apiKey: API_KEY.substring(0, 20) + '...',
      baseURL: BASE_URL,
      model: MODEL,
      inputDirectory: INPUT_DIR
    },
    summary: {
      total: results.success.length + results.failed.length + results.skipped.length,
      success: results.success.length,
      failed: results.failed.length,
      skipped: results.skipped.length,
      successRate: results.success.length > 0
        ? ((results.success.length / (results.success.length + results.failed.length)) * 100).toFixed(2) + '%'
        : '0%',
      averageDuration: results.success.length > 0
        ? (results.success.reduce((sum, r) => sum + r.duration, 0) / results.success.length).toFixed(2) + ' ms'
        : '0 ms',
      totalTokens: results.success.reduce((sum, r) => sum + (r.usage?.total_tokens || 0), 0)
    },
    successful_translations: results.success.map(r => r.subDir),
    failed_translations: results.failed,
    skipped_translations: results.skipped,
    generated_at: new Date().toISOString()
  };

  const reportPath = path.join(INPUT_DIR, '_translation_report.json');
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`📊 翻译报告已保存: ${reportPath}`);
}

// 主函数
async function main() {
  console.log('╔════════════════════════════════════════════════╗');
  console.log('║      批量翻译金融图表分析 (中文 → 英文)       ║');
  console.log('║         Gemini 2.5 Flash (云雾 AI)             ║');
  console.log('╚════════════════════════════════════════════════╝');
  console.log(`🔑 API Key: ${API_KEY.substring(0, 20)}...`);
  console.log(`🌐 Base URL: ${BASE_URL}`);
  console.log(`🤖 模型: ${MODEL}`);
  console.log(`📁 输入目录: ${INPUT_DIR}`);
  console.log(`⏱️  开始时间: ${new Date().toLocaleString()}\n`);

  // 检查输入目录是否存在
  if (!fs.existsSync(INPUT_DIR)) {
    console.error(`❌ 错误: 输入目录不存在: ${INPUT_DIR}`);
    process.exit(1);
  }

  // 获取所有子文件夹
  const allItems = fs.readdirSync(INPUT_DIR);
  const subDirs = allItems.filter(item => {
    const fullPath = path.join(INPUT_DIR, item);
    return fs.statSync(fullPath).isDirectory();
  });

  console.log(`📊 找到 ${subDirs.length} 个子文件夹\n`);

  if (subDirs.length === 0) {
    console.log('❌ 没有找到子文件夹，程序退出。');
    return;
  }

  const totalStartTime = Date.now();

  // 创建任务列表
  const tasks = subDirs.map((subDir, index) => {
    return () => translateFile(subDir, index, subDirs.length);
  });

  // 并发处理（并发数为 5）
  await processConcurrently(tasks, 5);

  const totalDuration = Date.now() - totalStartTime;

  // 统计结果
  console.log('\n╔════════════════════════════════════════════════╗');
  console.log('║                  翻译完成                       ║');
  console.log('╚════════════════════════════════════════════════╝');
  console.log(`⏱️  总耗时: ${(totalDuration / 1000).toFixed(2)} 秒`);
  console.log(`✅ 成功: ${results.success.length} 个`);
  console.log(`❌ 失败: ${results.failed.length} 个`);
  console.log(`⏭️  跳过: ${results.skipped.length} 个`);

  if (results.success.length > 0) {
    const avgDuration = results.success.reduce((sum, r) => sum + r.duration, 0) / results.success.length;
    console.log(`⏱️  平均响应时间: ${(avgDuration / 1000).toFixed(2)} 秒`);

    const totalTokens = results.success.reduce((sum, r) => sum + (r.usage?.total_tokens || 0), 0);
    console.log(`🔢 总消耗 Token: ${totalTokens}`);
  }

  // 保存汇总报告
  saveSummaryReport();

  if (results.failed.length > 0) {
    console.log('\n❌ 失败列表:');
    results.failed.forEach(item => {
      console.log(`   - ${item.subDir}: ${item.error}`);
    });
  }
}

// 运行
main().catch(console.error);
