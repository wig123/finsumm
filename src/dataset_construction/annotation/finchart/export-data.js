// 脚本路径: $HOME/Documents/githublearning/annotation-system/export-data.js
// 功能: 从 SQLite 数据库导出所有标注数据为 JSON 格式

const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

console.log('开始导出标注数据...\n');

// 连接数据库
const db = new Database('database.db', { readonly: true });

try {
  // 查询所有标注数据（关联图片信息）
  const annotations = db.prepare(`
    SELECT 
      a.id,
      a.image_id,
      a.summary,
      a.modification_note,
      a.status,
      a.annotator,
      a.annotated_at,
      i.filename,
      i.path as image_path,
      i.created_at as image_created_at
    FROM annotations a
    LEFT JOIN images i ON a.image_id = i.id
    ORDER BY a.id
  `).all();

  // 查询标注历史记录
  const history = db.prepare(`
    SELECT 
      h.id,
      h.image_id,
      h.summary,
      h.version,
      h.created_at
    FROM annotation_history h
    ORDER BY h.image_id, h.version
  `).all();

  // 组织数据：将历史记录按 image_id 分组
  const historyByImage = {};
  history.forEach(h => {
    if (!historyByImage[h.image_id]) {
      historyByImage[h.image_id] = [];
    }
    historyByImage[h.image_id].push({
      version: h.version,
      summary: h.summary,
      created_at: h.created_at
    });
  });

  // 将历史记录附加到对应的标注数据
  const annotationsWithHistory = annotations.map(a => ({
    ...a,
    history: historyByImage[a.image_id] || []
  }));

  // 统计信息
  const stats = {
    total: annotations.length,
    by_status: {
      pending: annotations.filter(a => a.status === 'pending').length,
      annotated: annotations.filter(a => a.status === 'annotated').length,
      deleted: annotations.filter(a => a.status === 'deleted').length
    },
    by_annotator: {}
  };

  // 统计各标注员的工作量
  annotations.forEach(a => {
    if (a.annotator) {
      stats.by_annotator[a.annotator] = (stats.by_annotator[a.annotator] || 0) + 1;
    }
  });

  // 准备导出数据
  const exportData = {
    export_time: new Date().toISOString(),
    export_timestamp: Date.now(),
    statistics: stats,
    annotations: annotationsWithHistory
  };

  // 生成文件名（带时间戳）
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
  const filename = `annotations_export_${timestamp}.json`;
  const filepath = path.join(__dirname, filename);

  // 写入文件
  fs.writeFileSync(filepath, JSON.stringify(exportData, null, 2), 'utf8');

  console.log('✅ 导出成功！\n');
  console.log('═══════════════════════════════════');
  console.log(`文件名: ${filename}`);
  console.log(`路径: ${filepath}`);
  console.log(`文件大小: ${(fs.statSync(filepath).size / 1024).toFixed(2)} KB`);
  console.log('═══════════════════════════════════');
  console.log(`总标注数: ${stats.total}`);
  console.log(`  - 待处理: ${stats.by_status.pending}`);
  console.log(`  - 已完成: ${stats.by_status.annotated}`);
  console.log(`  - 已删除: ${stats.by_status.deleted}`);
  console.log('───────────────────────────────────');
  console.log('标注员工作量:');
  Object.entries(stats.by_annotator).forEach(([annotator, count]) => {
    console.log(`  - ${annotator}: ${count} 条`);
  });
  console.log('═══════════════════════════════════\n');

} catch (error) {
  console.error('❌ 导出失败:', error.message);
  process.exit(1);
} finally {
  db.close();
}



