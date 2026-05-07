# 金融图表标注系统

基于 FinChart-Bench 数据集的图表总结标注工具。

## 项目背景

- **数据集**: FinChart-Bench 金融图表数据集（7020 张）
- **任务**: 为每张图表生成和审核总结文本
- **协作**: 多标注员通过 Git 同步工作进度

## 快速开始

```bash
# 克隆项目
git clone <repository-url>
cd annotation-system

# 安装依赖
npm install

# 初始化数据库
npm run init

# 启动服务
npm start

# 访问 http://localhost:3000

# 导出标注数据
npm run export
```

## 默认账号

- 管理员: `admin` / `admin123`
- 标注员: `annotator` / `anno123`

## 标注规范

### 总结要求
1. **简洁准确**: 100-200 字
2. **必须包含**: 图表类型、主要趋势、关键数据点
3. **客观描述**: 不做主观判断和预测

### 标注流程
1. 查看图表，阅读 AI 生成的初稿
2. 手动编辑或使用 AI 优化
3. 确认无误后点击「接受」
4. 系统自动跳转到下一张

### 质量标准
- ✅ 正确识别图表类型（柱状图、折线图、饼图等）
- ✅ 准确描述数据趋势和关键指标
- ✅ 语句通顺，无明显错误
- ❌ 避免冗余和废话
- ❌ 避免主观臆测

## 工作流程

### 标注
```bash
npm start                        # 启动服务
# 浏览器登录并标注
```

### 同步
```bash
git pull                         # 拉取最新数据
# 继续标注
git add database.db              # 暂存标注数据
git commit -m "标注: 张三 50张"  # 提交
git push                         # 推送
```

### 冲突解决
多人同时标注可能产生冲突，解决方法：
```bash
git pull                         # 拉取时提示冲突
# 使用 database.db 的 merge 策略（稍后说明）
git add database.db
git commit -m "合并标注"
git push
```

## 项目结构

```
annotation-system/
├── src/                   # 源代码
│   ├── server.js          # Express 后端服务
│   └── init-db.js         # 数据库初始化脚本
├── public/                # 前端静态文件
│   ├── index.html         # 登录页
│   ├── annotate.html      # 标注页
│   ├── manage.html        # 管理页
│   ├── api.js             # API 封装层
│   ├── annotate.js        # 标注页逻辑
│   ├── manage.js          # 管理页逻辑
│   └── styles.css         # 样式文件
├── images/                # 图表数据（7020 张）
├── database.db            # SQLite 数据库
├── package.json           # 项目配置
└── README.md              # 说明文档
```

## API 接口

```
POST   /api/auth/login              登录
GET    /api/images                  获取图片列表
GET    /api/annotations             获取标注数据
POST   /api/annotations             保存标注
PUT    /api/annotations/:id         更新标注
GET    /api/stats                   统计信息
POST   /api/ai/generate             AI 生成总结
POST   /api/ai/modify               AI 修改总结
```

## 数据导出

导出所有标注数据为 JSON 格式：

```bash
npm run export
```

导出文件包含：
- 所有标注数据（summary、modification_note、status、annotator 等）
- 关联的图片信息（filename、path）
- 标注历史记录（每次修改的版本）
- 统计信息（按状态、按标注员分组）

导出文件命名格式：`annotations_export_YYYY-MM-DDTHH-MM-SS.json`

## 注意事项

1. **定期提交**: 每完成 50-100 张标注后提交一次
2. **及时同步**: 每次开始标注前先 `git pull`
3. **数据备份**: 定期备份 `database.db` 或使用 `npm run export` 导出
4. **图片只读**: 不要修改 `images/` 目录
5. **冲突处理**: 遇到冲突及时沟通解决

## 故障排查

**端口占用**
```bash
lsof -ti:3000 | xargs kill
```

**数据库损坏**
```bash
rm database.db
npm run init
```

**图片加载失败**
- 检查 `images/` 目录是否完整
- 确认图片路径正确

## 技术栈

- 前端: HTML + CSS + Vanilla JS
- 后端: Node.js + Express
- 数据库: SQLite
- 认证: JWT

## License

MIT
