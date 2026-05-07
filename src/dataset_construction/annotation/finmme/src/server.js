const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const Database = require('better-sqlite3');
const jwt = require('jsonwebtoken');
const bcrypt = require('bcryptjs');
const OpenAI = require('openai');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;
const JWT_SECRET = process.env.JWT_SECRET || 'default_secret_change_in_production';
const OPENAI_MODEL = process.env.OPENAI_MODEL || 'gpt-5';  // AI 模型配置，默认使用 gpt-5

// 初始化 OpenAI 客户端（使用 FinChart-Bench 的配置）
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
  baseURL: process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1'
});

// 中间件
app.use(cors());
app.use(express.json({ limit: '50mb' }));
app.use(express.static(path.join(__dirname, '..', 'public')));
app.use('/images', express.static(path.join(__dirname, '..', 'images')));

// 数据库连接
const db = new Database(path.join(__dirname, '..', 'database.db'));
db.pragma('journal_mode = WAL');

// ========== 认证中间件 ==========
function authenticateToken(req, res, next) {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) {
    return res.status(401).json({ error: '未授权' });
  }

  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) return res.status(403).json({ error: '无效的令牌' });
    req.user = user;
    next();
  });
}

// ========== 认证路由 ==========
app.post('/api/auth/login', (req, res) => {
  try {
    const { username, password } = req.body;

    const user = db.prepare('SELECT * FROM users WHERE username = ?').get(username);

    if (!user || !bcrypt.compareSync(password, user.password)) {
      return res.status(401).json({ error: '用户名或密码错误' });
    }

    const token = jwt.sign(
      { id: user.id, username: user.username, role: user.role },
      JWT_SECRET,
      { expiresIn: '7d' }
    );

    res.json({
      token,
      user: {
        id: user.id,
        username: user.username,
        role: user.role
      }
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ========== 图片路由 ==========
app.get('/api/images', authenticateToken, (req, res) => {
  try {
    const { status, limit, offset } = req.query;

    let query = 'SELECT * FROM images';
    const params = [];

    if (status && status !== 'all') {
      query += ' WHERE status = ?';
      params.push(status);
    }

    query += ' ORDER BY id';

    if (limit) {
      query += ' LIMIT ?';
      params.push(parseInt(limit));
    }

    if (offset) {
      query += ' OFFSET ?';
      params.push(parseInt(offset));
    }

    const images = db.prepare(query).all(...params);
    res.json(images);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/images/:id', authenticateToken, (req, res) => {
  try {
    const image = db.prepare('SELECT * FROM images WHERE id = ?').get(req.params.id);

    if (!image) {
      return res.status(404).json({ error: '图片不存在' });
    }

    res.json(image);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ========== 标注路由 ==========
app.get('/api/annotations', authenticateToken, (req, res) => {
  try {
    const annotations = db.prepare(`
      SELECT a.*, i.path as image_path, i.filename
      FROM annotations a
      LEFT JOIN images i ON a.image_id = i.id
      ORDER BY a.annotated_at DESC
    `).all();

    res.json(annotations);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/annotations/:imageId', authenticateToken, (req, res) => {
  try {
    const annotation = db.prepare('SELECT * FROM annotations WHERE image_id = ?')
      .get(req.params.imageId);

    if (!annotation) {
      return res.json(null);
    }

    // 获取历史记录
    const history = db.prepare('SELECT * FROM annotation_history WHERE image_id = ? ORDER BY version')
      .all(req.params.imageId);

    res.json({ ...annotation, history });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.post('/api/annotations', authenticateToken, (req, res) => {
  try {
    const { image_id, summary, modification_note, status } = req.body;

    // 检查是否已存在
    const existing = db.prepare('SELECT * FROM annotations WHERE image_id = ?').get(image_id);

    if (existing) {
      // 保存历史版本
      if (existing.summary && existing.summary !== summary) {
        const maxVersion = db.prepare('SELECT MAX(version) as max FROM annotation_history WHERE image_id = ?')
          .get(image_id).max || 0;

        db.prepare(`
          INSERT INTO annotation_history (image_id, summary, version, created_at)
          VALUES (?, ?, ?, ?)
        `).run(image_id, existing.summary, maxVersion + 1, Date.now());
      }

      // 更新标注
      db.prepare(`
        UPDATE annotations
        SET summary = ?, modification_note = ?, status = ?, annotator = ?, annotated_at = ?
        WHERE image_id = ?
      `).run(summary, modification_note || '', status || 'pending', req.user.username, Date.now(), image_id);

      // 更新图片状态
      db.prepare('UPDATE images SET status = ? WHERE id = ?').run(status || 'pending', image_id);
    } else {
      // 创建新标注
      db.prepare(`
        INSERT INTO annotations (image_id, summary, modification_note, status, annotator, annotated_at)
        VALUES (?, ?, ?, ?, ?, ?)
      `).run(image_id, summary, modification_note || '', status || 'pending', req.user.username, Date.now());

      // 更新图片状态
      db.prepare('UPDATE images SET status = ? WHERE id = ?').run(status || 'pending', image_id);
    }

    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.put('/api/annotations/:imageId', authenticateToken, (req, res) => {
  try {
    const { summary, modification_note, status } = req.body;

    db.prepare(`
      UPDATE annotations
      SET summary = ?, modification_note = ?, status = ?, annotator = ?, annotated_at = ?
      WHERE image_id = ?
    `).run(summary, modification_note || '', status || 'pending', req.user.username, Date.now(), req.params.imageId);

    // 更新图片状态
    db.prepare('UPDATE images SET status = ? WHERE id = ?').run(status || 'pending', req.params.imageId);

    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.delete('/api/annotations/:imageId', authenticateToken, (req, res) => {
  try {
    db.prepare('UPDATE images SET status = ? WHERE id = ?').run('deleted', req.params.imageId);
    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ========== 统计路由 ==========
app.get('/api/stats', authenticateToken, (req, res) => {
  try {
    const total = db.prepare('SELECT COUNT(*) as count FROM images').get().count;
    const annotated = db.prepare('SELECT COUNT(*) as count FROM images WHERE status = ?').get('annotated').count;
    const pending = db.prepare('SELECT COUNT(*) as count FROM images WHERE status = ?').get('pending').count;
    const deleted = db.prepare('SELECT COUNT(*) as count FROM images WHERE status = ?').get('deleted').count;

    res.json({ total, annotated, pending, deleted });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ========== AI 服务路由（使用 Base64 编码，和 FinChart-Bench 一致）==========
app.post('/api/ai/generate', authenticateToken, async (req, res) => {
  try {
    const { imageUrl, prompt } = req.body;

    // 将图片路径转换为本地文件路径
    const imagePath = path.join(__dirname, '..', imageUrl.replace(/^\//, ''));
    
    console.log('[AI Generate] 读取图片:', imagePath);
    console.log('[AI Generate] Prompt 长度:', prompt ? prompt.length : 0, '字符');

    // 读取图片并转换为 Base64（和 FinChart-Bench 一样）
    const imageBuffer = fs.readFileSync(imagePath);
    const base64Image = imageBuffer.toString('base64');
    
    console.log('[AI Generate] 图片已转换为 Base64，大小:', Math.round(base64Image.length / 1024), 'KB');

    // 调用 OpenAI API（旧格式，和 FinChart-Bench 保持一致）
    const completion = await openai.chat.completions.create({
      model: OPENAI_MODEL,
      stream: false,
      messages: [
        {
          role: 'system',
          content: '你是一位专业的金融数据分析师'
        },
        {
          role: 'user',
          content: [
            {
              type: 'text',
              text: prompt || '请分析这张金融图表，包括数据趋势、关键发现和建议。'
            },
            {
              type: 'image_url',
              image_url: {
                url: `data:image/jpeg;base64,${base64Image}`,
                detail: 'high'
              }
            }
          ]
        }
      ],
      // temperature: 0.3,           // GPT-5 不支持自定义 temperature，只能使用默认值 1
      max_completion_tokens: 8192    // GPT-5 使用 max_completion_tokens 而不是 max_tokens
    });

    const summary = completion.choices[0].message.content;
    console.log('[AI Generate] 生成成功');

    res.json({ summary });
  } catch (error) {
    console.error('[AI Generate] 错误:', error.message);
    res.status(500).json({ error: `AI 生成失败: ${error.message}` });
  }
});

app.post('/api/ai/modify', authenticateToken, async (req, res) => {
  try {
    const { summary, note, prompt, imageUrl } = req.body;

    console.log('[AI Modify] 调用 GPT-5 修改总结');

    // 构建消息内容（旧格式）
    const userContent = [
      {
        type: 'text',
        text: `当前总结：\n${summary}\n\n修改意见：\n${note}\n\n${prompt || '请根据修改意见优化总结内容，保持专业性和准确性。'}`
      }
    ];

    // 如果提供了图片，添加图片分析（使用 Base64）
    if (imageUrl) {
      const imagePath = path.join(__dirname, '..', imageUrl.replace(/^\//, ''));
      const imageBuffer = fs.readFileSync(imagePath);
      const base64Image = imageBuffer.toString('base64');
      
      userContent.push({
        type: 'image_url',
        image_url: {
          url: `data:image/jpeg;base64,${base64Image}`,
          detail: 'high'
        }
      });
    }

    // 调用 OpenAI API（旧格式，和 FinChart-Bench 保持一致）
    const completion = await openai.chat.completions.create({
      model: OPENAI_MODEL,
      stream: false,
      messages: [
        {
          role: 'system',
          content: '你是一位专业的金融数据分析师。根据用户的修改意见，优化已有的总结内容，保持中文回复。'
        },
        {
          role: 'user',
          content: userContent
        }
      ],
      // temperature: 0.3,            // GPT-5 不支持自定义 temperature
      max_completion_tokens: 8192    // GPT-5 使用 max_completion_tokens
    });

    const modifiedSummary = completion.choices[0].message.content;
    console.log('[AI Modify] 修改成功');

    res.json({ summary: modifiedSummary });
  } catch (error) {
    console.error('[AI Modify] 错误:', error.message);
    res.status(500).json({ error: `AI 修改失败: ${error.message}` });
  }
});

// ========== Prompt 配置路由 ==========
app.get('/api/config', authenticateToken, (req, res) => {
  try {
    const config = db.prepare('SELECT * FROM config WHERE id = 1').get();
    res.json(config || { prompt_generate: '', prompt_modify: '' });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.put('/api/config', authenticateToken, (req, res) => {
  try {
    const { prompt_generate, prompt_modify } = req.body;

    const existing = db.prepare('SELECT * FROM config WHERE id = 1').get();

    if (existing) {
      db.prepare('UPDATE config SET prompt_generate = ?, prompt_modify = ? WHERE id = 1')
        .run(prompt_generate, prompt_modify);
    } else {
      db.prepare('INSERT INTO config (id, prompt_generate, prompt_modify) VALUES (1, ?, ?)')
        .run(prompt_generate, prompt_modify);
    }

    res.json({ success: true });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// ========== 根路由 ==========
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '..', 'public', 'index.html'));
});

// ========== 启动服务器 ==========
app.listen(PORT, () => {
  console.log(`
╔═══════════════════════════════════════╗
║   金融图表标注系统                     ║
║   服务已启动: http://localhost:${PORT}  ║
╚═══════════════════════════════════════╝
  `);
});
