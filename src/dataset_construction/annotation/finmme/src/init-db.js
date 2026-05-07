const Database = require('better-sqlite3');
const bcrypt = require('bcryptjs');
const fs = require('fs');
const path = require('path');

console.log('初始化数据库...\n');

// 连接数据库
const db = new Database('database.db');

// 创建表
console.log('创建数据表...');

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
  );

  CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
  );

  CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id TEXT UNIQUE NOT NULL,
    summary TEXT,
    modification_note TEXT,
    status TEXT DEFAULT 'pending',
    annotator TEXT,
    annotated_at INTEGER,
    FOREIGN KEY (image_id) REFERENCES images(id)
  );

  CREATE TABLE IF NOT EXISTS annotation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id TEXT NOT NULL,
    summary TEXT,
    version INTEGER,
    created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000),
    FOREIGN KEY (image_id) REFERENCES images(id)
  );

  CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY,
    prompt_generate TEXT,
    prompt_modify TEXT
  );

  CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
  CREATE INDEX IF NOT EXISTS idx_annotations_image_id ON annotations(image_id);
  CREATE INDEX IF NOT EXISTS idx_history_image_id ON annotation_history(image_id);
`);

console.log('✓ 数据表创建完成\n');

// 创建默认用户
console.log('创建默认用户...');

const defaultUsers = [
  { username: 'admin', password: 'admin123', role: 'admin' },
  { username: 'annotator', password: 'anno123', role: 'annotator' }
];

const insertUser = db.prepare('INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)');

defaultUsers.forEach(user => {
  const hashedPassword = bcrypt.hashSync(user.password, 10);
  insertUser.run(user.username, hashedPassword, user.role);
  console.log(`✓ 用户创建: ${user.username} (${user.role})`);
});

console.log('');

// 导入图片
console.log('导入图片数据...');

const imagesDir = path.join(__dirname, '..', 'images');

if (!fs.existsSync(imagesDir)) {
  console.log('⚠ 图片目录不存在，跳过导入');
} else {
  const files = fs.readdirSync(imagesDir)
    .filter(file => /\.(jpg|jpeg|png|gif)$/i.test(file));

  if (files.length === 0) {
    console.log('⚠ 未找到图片文件');
  } else {
    const insertImage = db.prepare('INSERT OR IGNORE INTO images (id, filename, path, status) VALUES (?, ?, ?, ?)');
    const insertMany = db.transaction((files) => {
      files.forEach(file => {
        const id = path.parse(file).name;
        const relativePath = `/images/${file}`;
        insertImage.run(id, file, relativePath, 'pending');
      });
    });

    insertMany(files);
    console.log(`✓ 导入 ${files.length} 张图片`);
  }
}

console.log('');

// 创建默认 Prompt 配置
console.log('创建默认配置...');

const defaultPrompts = {
  prompt_generate: '请基于这张金融图表，生成一段简洁准确的总结，包括：\n1. 图表类型\n2. 主要数据趋势\n3. 关键发现\n4. 数据洞察\n\n要求：100-200字，客观描述，避免主观判断。',
  prompt_modify: '请基于原总结和用户的修改意见，优化总结内容。\n\n原总结：{summary}\n\n用户意见：{note}\n\n请给出改进后的总结（保持简洁，100-200字）：'
};

db.prepare('INSERT OR IGNORE INTO config (id, prompt_generate, prompt_modify) VALUES (1, ?, ?)')
  .run(defaultPrompts.prompt_generate, defaultPrompts.prompt_modify);

console.log('✓ 默认配置创建完成\n');

// 统计信息
const stats = {
  users: db.prepare('SELECT COUNT(*) as count FROM users').get().count,
  images: db.prepare('SELECT COUNT(*) as count FROM images').get().count,
  annotations: db.prepare('SELECT COUNT(*) as count FROM annotations').get().count
};

console.log('═══════════════════════════════════');
console.log('初始化完成！');
console.log('═══════════════════════════════════');
console.log(`用户数: ${stats.users}`);
console.log(`图片数: ${stats.images}`);
console.log(`标注数: ${stats.annotations}`);
console.log('═══════════════════════════════════\n');
console.log('运行 npm start 启动服务器');

db.close();
