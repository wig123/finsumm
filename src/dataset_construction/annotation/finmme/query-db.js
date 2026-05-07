#!/usr/bin/env node
/**
 * 脚本路径: $HOME/Documents/githublearning/annotation-system/query-db.js
 * 功能: 交互式查询 SQLite 数据库，提供友好的数据展示
 */

const Database = require('better-sqlite3');
const path = require('path');

// 连接数据库
const dbPath = path.join(__dirname, 'database.db');
const db = new Database(dbPath, { readonly: true });

console.log('\n╔═══════════════════════════════════════════════════════╗');
console.log('║           金融图表标注系统 - 数据库查询工具              ║');
console.log('╚═══════════════════════════════════════════════════════╝\n');

// 1. 基本统计
console.log('📊 数据库统计\n' + '─'.repeat(60));
const stats = {
  users: db.prepare('SELECT COUNT(*) as count FROM users').get().count,
  images: db.prepare('SELECT COUNT(*) as count FROM images').get().count,
  annotations: db.prepare('SELECT COUNT(*) as count FROM annotations').get().count,
  history: db.prepare('SELECT COUNT(*) as count FROM annotation_history').get().count
};

console.log(`👥 用户数量: ${stats.users}`);
console.log(`📷 图片总数: ${stats.images}`);
console.log(`✅ 标注总数: ${stats.annotations}`);
console.log(`📜 历史版本: ${stats.history}`);

// 2. 图片状态分布
console.log('\n📷 图片状态分布\n' + '─'.repeat(60));
const statusStats = db.prepare(`
  SELECT status, COUNT(*) as count 
  FROM images 
  GROUP BY status
`).all();

statusStats.forEach(({ status, count }) => {
  const emoji = {
    'pending': '⏳',
    'annotated': '✅',
    'deleted': '🗑️'
  }[status] || '❓';
  const percentage = ((count / stats.images) * 100).toFixed(1);
  console.log(`${emoji} ${status.padEnd(12)}: ${count.toString().padStart(4)} (${percentage}%)`);
});

// 3. 用户信息
console.log('\n👥 系统用户\n' + '─'.repeat(60));
const users = db.prepare('SELECT id, username, role FROM users').all();
console.table(users);

// 4. 标注员工作量
console.log('📝 标注员工作统计\n' + '─'.repeat(60));
const annotatorStats = db.prepare(`
  SELECT 
    annotator,
    COUNT(*) as total,
    COUNT(CASE WHEN status = 'annotated' THEN 1 END) as completed,
    COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending
  FROM annotations
  WHERE annotator IS NOT NULL
  GROUP BY annotator
`).all();

if (annotatorStats.length > 0) {
  console.table(annotatorStats);
} else {
  console.log('暂无标注记录');
}

// 5. 最近标注记录
console.log('🕐 最新标注记录（前5条）\n' + '─'.repeat(60));
const recentAnnotations = db.prepare(`
  SELECT 
    a.image_id,
    i.filename,
    a.status,
    a.annotator,
    datetime(a.annotated_at/1000, 'unixepoch', 'localtime') as time
  FROM annotations a
  LEFT JOIN images i ON a.image_id = i.id
  WHERE a.annotated_at IS NOT NULL
  ORDER BY a.annotated_at DESC
  LIMIT 5
`).all();

if (recentAnnotations.length > 0) {
  console.table(recentAnnotations);
} else {
  console.log('暂无标注记录');
}

// 6. Prompt 配置
console.log('⚙️  AI Prompt 配置\n' + '─'.repeat(60));
const config = db.prepare('SELECT * FROM config WHERE id = 1').get();
if (config) {
  console.log('生成 Prompt:');
  console.log(config.prompt_generate.substring(0, 100) + '...\n');
  console.log('修改 Prompt:');
  console.log(config.prompt_modify.substring(0, 100) + '...\n');
} else {
  console.log('未找到配置');
}

// 7. 数据库文件信息
const fs = require('fs');
const stats_file = fs.statSync(dbPath);
const sizeInMB = (stats_file.size / (1024 * 1024)).toFixed(2);
console.log('💾 数据库文件信息\n' + '─'.repeat(60));
console.log(`文件路径: ${dbPath}`);
console.log(`文件大小: ${sizeInMB} MB`);
console.log(`最后修改: ${stats_file.mtime.toLocaleString('zh-CN')}`);

// 关闭数据库
db.close();

console.log('\n' + '═'.repeat(60));
console.log('查询完成！\n');

