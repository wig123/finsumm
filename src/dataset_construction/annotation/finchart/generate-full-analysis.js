const fs = require('fs');
const path = require('path');
const OpenAI = require('openai');
// 配置云雾 API
const API_KEY = '<YOUR_API_KEY>';
const BASE_URL = '<YOUR_LLM_PROXY>/v1';
const MODEL = 'gemini-3-pro-preview';

// 初始化客户端
const openai = new OpenAI({
  apiKey: API_KEY,
  baseURL: BASE_URL
});

// 路径配置
const IMAGES_DIR = path.join(__dirname, 'images');
const OUTPUT_DIR = path.join(__dirname, `output-full-analysis-${Date.now()}`);

// 创建输出目录
if (!fs.existsSync(OUTPUT_DIR)) {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });
}

// 结果保存
const results = [];
const errors = [];

// 读取完整提示词
const PROMPT_FILE = path.join(__dirname, 'generate_prompt copy.txt');
const FULL_PROMPT = fs.readFileSync(PROMPT_FILE, 'utf8');

// 保存单个结果到子文件夹
function saveResult(result) {
  const { image_id, filename, analysis, duration, imageSize, usage } = result;

  // 创建子文件夹（使用图片名称去掉扩展名）
  const imageBasename = path.basename(filename, path.extname(filename));
  const subDir = path.join(OUTPUT_DIR, imageBasename);
  if (!fs.existsSync(subDir)) {
    fs.mkdirSync(subDir, { recursive: true });
  }

  // 1. 复制图片
  const sourceImagePath = path.join(IMAGES_DIR, filename);
  const targetImagePath = path.join(subDir, filename);
  fs.copyFileSync(sourceImagePath, targetImagePath);

  // 2. 保存元数据
  const metadata = {
    image_id: imageBasename,
    filename,
    processed_at: new Date().toISOString(),
    duration_ms: duration,
    image_size_kb: imageSize,
    model: MODEL,
    api_usage: usage
  };
  fs.writeFileSync(path.join(subDir, 'metadata.json'), JSON.stringify(metadata, null, 2));

  // 3. 保存完整分析
  fs.writeFileSync(path.join(subDir, 'analysis.txt'), analysis, 'utf8');

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
      images_directory: IMAGES_DIR
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
    failed_images: errors.map(e => ({ image_id: e.image_id, error: e.error })),
    generated_at: new Date().toISOString()
  };

  fs.writeFileSync(path.join(OUTPUT_DIR, '_summary_report.json'), JSON.stringify(report, null, 2));
  console.log(`📊 汇总报告已保存: ${path.join(OUTPUT_DIR, '_summary_report.json')}`);
}

// 生成完整分析
async function generateFullAnalysis(filename, index, total) {
  const imagePath = path.join(IMAGES_DIR, filename);
  const imageBasename = path.basename(filename, path.extname(filename));

  try {
    console.log(`🔄 [${index + 1}/${total}] 处理中: ${imageBasename} (${filename})`);

    // 检查图片是否存在
    if (!fs.existsSync(imagePath)) {
      throw new Error(`图片文件不存在: ${imagePath}`);
    }

    // 读取图片并转换为 Base64
    const imageBuffer = fs.readFileSync(imagePath);
    const base64Image = imageBuffer.toString('base64');
    const imageSize = Math.round(base64Image.length / 1024);

    console.log(`   📷 图片大小: ${imageSize} KB`);

    const startTime = Date.now();

    // 调用 API
    const completion = await openai.chat.completions.create({
      model: MODEL,
      stream: false,
      messages: [
        {
          role: 'system',
          content: FULL_PROMPT
        },
        {
          role: 'user',
          content: [
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

    const duration = Date.now() - startTime;
    const analysis = completion.choices?.[0]?.message?.content || '';

    if (!analysis) {
      throw new Error('API 返回了空内容');
    }

    console.log(`✅ [${index + 1}/${total}] 成功: ${imageBasename} (耗时: ${duration}ms)`);
    console.log(`   📊 分析内容长度: ${analysis.length} 字符`);
    console.log(`\n--- 分析内容预览 ---\n${analysis.substring(0, 200)}...\n--- 预览结束 ---\n`);

    const result = {
      image_id: imageBasename,
      filename,
      analysis,
      duration,
      imageSize,
      timestamp: new Date().toISOString(),
      usage: completion.usage
    };

    results.push(result);

    // 立即保存到子文件夹
    saveResult(result);

  } catch (error) {
    console.error(`❌ [${index + 1}/${total}] 失败: ${imageBasename}`);
    console.error(`   错误: ${error.message}`);

    errors.push({
      image_id: imageBasename,
      filename,
      error: error.message,
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
  console.log('║   生成完整图表分析（四部分）                   ║');
  console.log('║           云雾 AI (<YOUR_LLM_PROXY>)                   ║');
  console.log('╚════════════════════════════════════════════════╝');
  console.log(`🔑 API Key: ${API_KEY.substring(0, 20)}...`);
  console.log(`🌐 Base URL: ${BASE_URL}`);
  console.log(`🤖 模型: ${MODEL}`);
  console.log(`📁 图片目录: ${IMAGES_DIR}`);
  console.log(`📁 输出目录: ${OUTPUT_DIR}`);
  console.log(`⏱️  开始时间: ${new Date().toLocaleString()}\n`);

  // 读取图片列表
  console.log('📊 正在扫描图片目录...');
  const allFiles = fs.readdirSync(IMAGES_DIR)
    .filter(file => /\.(png|jpg|jpeg)$/i.test(file))
    .sort();

  console.log(`✅ 找到 ${allFiles.length} 张图片\n`);

  if (allFiles.length === 0) {
    console.log('❌ 没有找到图片，程序退出。');
    return;
  }

  // 询问用户要处理多少张
  const PROCESS_COUNT = process.env.PROCESS_COUNT ? parseInt(process.env.PROCESS_COUNT) : 100;
  const START_INDEX = process.env.START_INDEX ? parseInt(process.env.START_INDEX) : 0;
  const imagesToProcess = allFiles.slice(START_INDEX, START_INDEX + PROCESS_COUNT);
  console.log(`📌 本次将处理第 ${START_INDEX + 1} 到第 ${START_INDEX + imagesToProcess.length} 张图片 (共 ${imagesToProcess.length} 张)\n`);

  const totalStartTime = Date.now();

  // 创建任务列表
  const tasks = imagesToProcess.map((filename, index) => {
    return () => generateFullAnalysis(filename, index, imagesToProcess.length);
  });

  // 并发处理（并发数为 3）
  await processConcurrently(tasks, 3);

  const totalDuration = Date.now() - totalStartTime;

  // 统计结果
  console.log('\n╔════════════════════════════════════════════════╗');
  console.log('║                  处理完成                       ║');
  console.log('╚════════════════════════════════════════════════╝');
  console.log(`⏱️  总耗时: ${(totalDuration / 1000).toFixed(2)} 秒`);
  console.log(`✅ 成功: ${results.length} 张`);
  console.log(`❌ 失败: ${errors.length} 张`);
  console.log(`📈 成功率: ${((results.length / imagesToProcess.length) * 100).toFixed(2)}%`);

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
    console.log('\n❌ 失败列表:');
    errors.forEach(e => {
      console.log(`   - ${e.image_id} (${e.filename}): ${e.error}`);
    });
  }
}

// 运行
main().catch(console.error);
