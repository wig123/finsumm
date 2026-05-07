const fs = require('fs');
const path = require('path');
const OpenAI = require('openai');
const sqlite3 = require('sqlite3').verbose();

// 配置 API 易
const API_KEY = '<YOUR_API_KEY>';
const BASE_URL = '<YOUR_LLM_PROXY>/v1';
const MODEL = 'gpt-5.1';

// 重试配置
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000; // 重试间隔 2 秒
const CONCURRENCY = 3; // 并发数

// 初始化客户端
const openai = new OpenAI({
  apiKey: API_KEY,
  baseURL: BASE_URL
});

// 数据库路径
const DB_PATH = path.join(__dirname, 'database.db');
const IMAGES_DIR = path.join(__dirname, 'images');

// 上次失败报告路径
const FAILED_REPORT_PATH = path.join(__dirname, 'output-pattern-insights-1764172216211/_summary_report.json');

// 结果保存
const results = [];
const errors = [];
const OUTPUT_DIR = `output-pattern-insights-retry-${Date.now()}`;

// 创建输出目录
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// 延迟函数
function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 保存单个结果到子文件夹
function saveResult(result) {
  const { image_id, filename, original_summary, pattern_insights, duration, imageSize, usage } = result;

  // 创建子文件夹
  const subDir = path.join(OUTPUT_DIR, image_id);
  if (!fs.existsSync(subDir)) {
    fs.mkdirSync(subDir, { recursive: true });
  }

  // 1. 复制图片
  const sourceImagePath = path.join(IMAGES_DIR, filename);
  const targetImagePath = path.join(subDir, filename);
  fs.copyFileSync(sourceImagePath, targetImagePath);

  // 2. 保存元数据
  const metadata = {
    image_id,
    filename,
    processed_at: new Date().toISOString(),
    duration_ms: duration,
    image_size_kb: imageSize,
    model: MODEL,
    api_usage: usage
  };
  fs.writeFileSync(path.join(subDir, 'metadata.json'), JSON.stringify(metadata, null, 2));

  // 3. 保存完整分析
  const fullAnalysis = original_summary + '\n\n' + pattern_insights;
  fs.writeFileSync(path.join(subDir, 'analysis.txt'), fullAnalysis, 'utf8');

  console.log(`   💾 已保存到子文件夹: ${subDir}`);
}

// 保存汇总报告
function saveSummaryReport() {
  const report = {
    config: {
      apiKey: API_KEY.substring(0, 20) + '...',
      baseURL: BASE_URL,
      model: MODEL,
      output_directory: OUTPUT_DIR,
      max_retries: MAX_RETRIES,
      concurrency: CONCURRENCY
    },
    summary: {
      total: results.length + errors.length,
      success: results.length,
      failed: errors.length,
      successRate: results.length > 0 ? ((results.length / (results.length + errors.length)) * 100).toFixed(2) + '%' : '0%',
      averageDuration: results.length > 0 ? (results.reduce((sum, r) => sum + r.duration, 0) / results.length).toFixed(2) + ' ms' : '0 ms',
      totalTokens: results.reduce((sum, r) => sum + (r.usage?.total_tokens || 0), 0)
    },
    successful_images: results.map(r => r.image_id),
    failed_images: errors.map(e => ({ image_id: e.image_id, error: e.error, retries: e.retries })),
    generated_at: new Date().toISOString()
  };

  fs.writeFileSync(path.join(OUTPUT_DIR, '_summary_report.json'), JSON.stringify(report, null, 2));
  console.log(`📊 汇总报告已保存: ${path.join(OUTPUT_DIR, '_summary_report.json')}`);
}

// 获取上次失败的图片ID列表
function getFailedImageIds() {
  const report = JSON.parse(fs.readFileSync(FAILED_REPORT_PATH, 'utf8'));
  return report.failed_images.map(item => item.image_id);
}

// 从数据库获取指定图片的标注数据
function getAnnotationsByImageIds(imageIds) {
  return new Promise((resolve, reject) => {
    const db = new sqlite3.Database(DB_PATH);

    const placeholders = imageIds.map(() => '?').join(',');
    const query = `
      SELECT
        a.image_id,
        a.summary,
        a.annotator,
        i.filename,
        i.path
      FROM annotations a
      JOIN images i ON a.image_id = i.id
      WHERE a.status = 'annotated'
        AND a.summary IS NOT NULL
        AND a.summary != ''
        AND a.image_id IN (${placeholders})
      ORDER BY a.image_id
    `;

    db.all(query, imageIds, (err, rows) => {
      db.close();
      if (err) {
        reject(err);
      } else {
        resolve(rows);
      }
    });
  });
}

// 带重试的 API 调用
async function callApiWithRetry(systemPrompt, userPrompt, base64Image, retryCount = 0) {
  try {
    const completion = await openai.chat.completions.create({
      model: MODEL,
      stream: false,
      messages: [
        {
          role: 'system',
          content: systemPrompt
        },
        {
          role: 'user',
          content: [
            {
              type: 'text',
              text: userPrompt
            },
            {
              type: 'image_url',
              image_url: {
                url: `data:image/png;base64,${base64Image}`,
                detail: 'high'
              }
            }
          ]
        }
      ],
      max_completion_tokens: 8196
    });

    return completion;
  } catch (error) {
    if (retryCount < MAX_RETRIES) {
      const waitTime = RETRY_DELAY_MS * (retryCount + 1); // 递增等待时间
      console.log(`   ⚠️ 请求失败，${waitTime/1000}秒后进行第 ${retryCount + 1} 次重试...`);
      await delay(waitTime);
      return callApiWithRetry(systemPrompt, userPrompt, base64Image, retryCount + 1);
    }
    throw error;
  }
}

// 生成【模式特征】和【核心洞察】
async function generatePatternAndInsights(annotation, index, total) {
  const { image_id, summary, filename } = annotation;
  const imagePath = path.join(IMAGES_DIR, filename);

  let retryCount = 0;

  try {
    console.log(`🔄 [${index + 1}/${total}] 处理中: ${image_id} (${filename})`);

    // 检查图片是否存在
    if (!fs.existsSync(imagePath)) {
      throw new Error(`图片文件不存在: ${imagePath}`);
    }

    // 读取图片并转换为 Base64
    const imageBuffer = fs.readFileSync(imagePath);
    const base64Image = imageBuffer.toString('base64');
    const imageSize = Math.round(base64Image.length / 1024);

    console.log(`   📷 图片大小: ${imageSize} KB`);
    console.log(`   📝 已有标注长度: ${summary.length} 字符`);

    const startTime = Date.now();

    // 构建提示词
    const systemPrompt = `你是一位严谨的、专注于金融领域的图表分析专家。

**背景说明:**
用户已经为一张金融图表完成了前两部分的标注：
1. 【图表构成】- 图表的基础元素描述
2. 【数据关系】- 关键数值和量化关系

**你的任务:**
基于用户提供的【图表构成】和【数据关系】，以及原始图表，生成剩余的两个部分：
3. 【模式特征】- 数据的形态特征
4. 【核心洞察】- 业务层面的解读和影响

**核心规则:**
1. **严格遵循结构:** 你的报告必须包含【模式特征】、【核心洞察】这两个部分的标题。
2. **信息封闭原则:** 所有分析必须完全且仅来源于图表本身和用户提供的【图表构成】【数据关系】，严禁引入图表之外的信息。
3. **纯净输出:** 直接从【模式特征】开始，报告结束后不添加任何附言。

---

**【模式特征】**
- **任务:** 用2-3句话纯粹描述数据的形态特征，不做任何业务解读。
- **内容:**
  - 整体形态（如时序图：趋势方向、波动幅度、周期性；如分布图：集中度、对称性、聚类特征；如关系图：相关性分布、线性程度）
  - 结构特点（如：均衡/失衡、连续/跳跃、单一主导/多元分散）
  - 明显的异常、拐点或例外（如有）
- **要求:**
  - 这是纯粹的"形态层"，只描述数据的视觉模式
  - 避免重复【数据关系】中的具体数值
  - 严禁使用业务解读词汇（如"健康""疲软""风险""优势"等）
  - 用中性的形态词汇描述"看到的模式是什么"，而非"这意味着什么"

**【核心洞察】**
- **任务:** 基于前面的形态特征，提炼业务层面的结论和影响。这是"业务解读层"，而非"形态描述层"。
- **内容结构（严格遵循）:**
  \`\`\`
  核心结论：（最重要的业务判断，≤30字）

  业务含义：
  - 含义1（这个模式说明什么业务状况/问题/优势？≤20字）
  - 含义2（对哪个环节/指标/能力有什么影响？≤20字）
  - 含义3（如有，进一步的业务推论，≤20字）

  风险关注：
  - 风险点1（具体阈值+可能后果，≤25字）
  - 风险点2（如有，具体阈值+可能后果，≤25字）
  \`\`\`
- **要求:**
  - 总字数控制在150字左右，使用直白的商业语言
  - **严禁重复【模式特征】中的形态描述**（如"上升""背离""波动"等形态词汇）
  - **"业务含义"必须是业务层面的解读**，回答以下问题之一：
    - 这个模式说明了什么状况？（如：盈利能力、市场情绪、风险水平、配置效率、相关性强度）
    - 对什么有什么影响？（如：对决策的影响、对风险敞口的影响、对资产配置的含义、对流动性的影响）
    - 反映了什么特征？（如：稳定性、依赖性、集中度、敏感性、对称性、周期性）
  - **"风险关注"必须包含具体信息：**
    - 明确的数字阈值或临界点
    - 直白的可能后果或影响
    - 避免抽象或模糊的表述
  - 严禁引用任何未在图表中出现的信息`;

    const userPrompt = `以下是已标注的【图表构成】和【数据关系】：

${summary}

---

请基于上述标注和原始图表，生成【模式特征】和【核心洞察】两个部分。`;

    // 调用 API（带重试）
    const completion = await callApiWithRetry(systemPrompt, userPrompt, base64Image);

    const duration = Date.now() - startTime;
    const patternInsights = completion.choices?.[0]?.message?.content || '';

    if (!patternInsights) {
      throw new Error('API 返回了空内容');
    }

    console.log(`✅ [${index + 1}/${total}] 成功: ${image_id} (耗时: ${duration}ms)`);
    console.log(`   📊 生成内容长度: ${patternInsights.length} 字符`);

    const result = {
      image_id,
      filename,
      original_summary: summary,
      pattern_insights: patternInsights,
      duration,
      imageSize,
      timestamp: new Date().toISOString(),
      usage: completion.usage
    };

    results.push(result);

    // 立即保存到子文件夹
    saveResult(result);

  } catch (error) {
    console.error(`❌ [${index + 1}/${total}] 失败: ${image_id} (重试 ${MAX_RETRIES} 次后)`);
    console.error(`   错误: ${error.message}`);

    errors.push({
      image_id,
      filename,
      error: error.message,
      retries: MAX_RETRIES,
      timestamp: new Date().toISOString()
    });
  }
}

// 并发控制函数
async function processConcurrently(tasks, concurrency) {
  const results = [];
  const executing = [];

  for (const task of tasks) {
    const promise = task().then(result => {
      executing.splice(executing.indexOf(promise), 1);
      return result;
    });

    results.push(promise);
    executing.push(promise);

    if (executing.length >= concurrency) {
      await Promise.race(executing);
    }
  }

  await Promise.all(results);
}

// 主函数
async function main() {
  console.log('╔════════════════════════════════════════════════╗');
  console.log('║   重试失败任务 - 生成【模式特征】和【核心洞察】 ║');
  console.log('║           云雾 AI (<YOUR_LLM_PROXY>)                   ║');
  console.log('╚════════════════════════════════════════════════╝');
  console.log(`🔑 API Key: ${API_KEY.substring(0, 20)}...`);
  console.log(`🌐 Base URL: ${BASE_URL}`);
  console.log(`🤖 模型: ${MODEL}`);
  console.log(`🔄 最大重试次数: ${MAX_RETRIES}`);
  console.log(`⚡ 并发数: ${CONCURRENCY}`);
  console.log(`📁 输出目录: ${OUTPUT_DIR}`);
  console.log(`⏱️  开始时间: ${new Date().toLocaleString()}\n`);

  // 获取上次失败的图片ID
  console.log('📋 正在读取上次失败的任务列表...');
  const failedImageIds = getFailedImageIds();
  console.log(`✅ 共有 ${failedImageIds.length} 个失败任务需要重试\n`);

  if (failedImageIds.length === 0) {
    console.log('🎉 没有失败的任务，程序退出。');
    return;
  }

  // 从数据库获取这些图片的标注数据
  console.log('📊 正在从数据库读取标注数据...');
  const annotations = await getAnnotationsByImageIds(failedImageIds);
  console.log(`✅ 获取到 ${annotations.length} 条标注数据\n`);

  if (annotations.length === 0) {
    console.log('❌ 没有找到对应的标注数据，程序退出。');
    return;
  }

  const totalStartTime = Date.now();

  // 创建任务列表
  const tasks = annotations.map((annotation, index) => {
    return () => generatePatternAndInsights(annotation, index, annotations.length);
  });

  // 并发处理
  await processConcurrently(tasks, CONCURRENCY);

  const totalDuration = Date.now() - totalStartTime;

  // 统计结果
  console.log('\n╔════════════════════════════════════════════════╗');
  console.log('║                  处理完成                       ║');
  console.log('╚════════════════════════════════════════════════╝');
  console.log(`⏱️  总耗时: ${(totalDuration / 1000).toFixed(2)} 秒`);
  console.log(`✅ 成功: ${results.length} 条`);
  console.log(`❌ 失败: ${errors.length} 条`);
  console.log(`📈 成功率: ${((results.length / annotations.length) * 100).toFixed(2)}%`);

  if (results.length > 0) {
    const avgDuration = results.reduce((sum, r) => sum + r.duration, 0) / results.length;
    console.log(`⏱️  平均响应时间: ${(avgDuration / 1000).toFixed(2)} 秒`);

    const totalTokens = results.reduce((sum, r) => sum + (r.usage?.total_tokens || 0), 0);
    console.log(`🔢 总消耗 Token: ${totalTokens}`);
  }

  // 保存汇总报告
  saveSummaryReport();
  console.log(`\n📁 所有结果已保存到目录: ${OUTPUT_DIR}`);

  if (errors.length > 0) {
    console.log('\n❌ 仍然失败的任务:');
    errors.slice(0, 20).forEach(e => {
      console.log(`   - ${e.image_id}: ${e.error}`);
    });
    if (errors.length > 20) {
      console.log(`   ... 还有 ${errors.length - 20} 个失败任务`);
    }
  }
}

// 运行
main().catch(console.error);
