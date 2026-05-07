# 金融图表标注系统

基于 Finmme 数据集的图表总结标注工具。AI 已生成初稿，人工审核并确认。

## 📌 你的标注任务

- **标注账号**: `annotator`
- **负责范围**: 第 1-1000 张图片
- **对应文件**: `finmme_000000.png` ~ `finmme_001254.png`
- **工作量**: 共 1000 张图片


---

## 快速开始

### 前置要求

- **Node.js** 版本 >= 14.0
- **npm** (随 Node.js 自动安装)

### 安装 Node.js

#### Windows 用户

1. 访问 [nodejs.org](https://nodejs.org/)
2. 下载 **LTS 版本**（推荐）或 Current 版本
3. 双击下载的 `.msi` 文件
4. 按照安装向导完成安装（一路"下一步"即可）
5. 验证安装：
   ```bash
   # 打开命令提示符（CMD）或 PowerShell
   node --version
   npm --version
   ```

#### macOS 用户

**方法一：官网下载（推荐新手）**
1. 访问 [nodejs.org](https://nodejs.org/)
2. 下载 **LTS 版本** 的 `.pkg` 文件
3. 双击安装包，按照提示完成安装
4. 验证安装：
   ```bash
   # 打开终端（Terminal）
   node --version
   npm --version
   ```

**方法二：使用 Homebrew（推荐开发者）**
```bash
# 安装 Homebrew（如果未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Node.js
brew install node

# 验证安装
node --version
npm --version
```



### 1. 克隆项目并安装

```bash
# 克隆项目
git clone <repository-url>
cd annotation-finmme

# 安装依赖
npm install

# 启动服务（首次启动会自动初始化数据库）
npm start
```

### 2. 登录系统

访问 **http://localhost:3000**，使用你的标注账号登录：

- **账号**: `annotator`
- **密码**: `anno123`

### 3. 开始标注

- 在侧边栏中找到你负责的图片（`finmme_000000.png` ~ `finmme_001254.png`）
- 点击进入标注页面
- 按照下方流程操作

---

## 标注流程

### 总结规范

AI 生成的总结包含两个部分：
- **【图表构成】**: 图表类型、标题、坐标轴、图例等基础信息
- **【数据关系】**: 关键数值、量化关系、数据对比（**主要审核这部分**）

### 📖 详细标注标准

**完整的标注规范和示例请查看飞书文档：**

👉 [金融图表标注详细标准](https://jtafr5ebk9.feishu.cn/wiki/MDvCwZUsMiejtdksJlHcD0ebnve?wiki_all_space_view_source=space_sidebar&table=tblsavw6Bqc8FGFE&view=vewluJy8YA)

**重要提示**：开始标注前，请务必先阅读飞书文档中的详细标准和示例！

### 操作流程

#### 情况一：无需修改
1. 查看 AI 生成的总结，重点检查 **【数据关系】** 部分的数值准确性
2. 确认无误后，直接点击 **「接受」** 按钮
3. 系统自动跳转到下一张图片

#### 情况二：需要修改
1. 点击 **「编辑」** 按钮
2. 在编辑框中修改总结内容（重点修正数值错误）
3. 点击 **「保存修改」** 按钮
4. 确认修改后，点击 **「接受」** 按钮

#### 情况三：图表有问题
- 图表错误过多、太复杂、或图片本身有问题
- 直接点击 **「删除」** 按钮

### 侧边栏快速切换

左侧边栏显示所有图片列表：
- **绿色点**: 已标注
- **黄色点**: 待标注（AI 已生成，待审核）
- **灰色点**: 未标注

点击侧边栏任意图片可快速跳转。

---

## Git 同步流程

### 📝 工作流程

#### 1. 每次标注前：拉取最新数据

```bash
git pull
```

这会同步其他人的标注进度。

#### 2. 标注你负责的图片

- **只标注**: `finmme_000000.png` ~ `finmme_001254.png`
- **不要标注**: 其他范围的图片（避免冲突）

#### 3. 每完成 100 张：提交并推送

```bash
# 暂存数据库文件
git add database.db

# 提交（注明进度）
git commit -m "标注: 已完成 0-99 共100张"

# 推送到远程
git push
```

### 💡 重要提示

- ✅ **标注前先 `git pull`**，获取最新进度
- ✅ **只标注你负责的 1000 张图片**（`finmme_000000` ~ `finmme_001254`）
- ✅ **每完成 100 张推送一次**，避免数据丢失

---

## 常见问题

### 端口 3000 被占用

```bash
# 查看占用进程
lsof -i:3000

# 杀死进程（替换 PID 为实际进程 ID）
kill <PID>

# 或修改 .env 文件中的 PORT 为 3001
```

### 首次运行提示数据库不存在

```bash
# 手动初始化数据库
npm run init
```

### 服务启动失败

```bash
# 1. 检查 Node.js 版本
node --version  # 应该 >= 14.0

# 2. 重新安装依赖
rm -rf node_modules
npm install

# 3. 重启服务
npm start
```

---

## 项目结构

```
annotation-finmme/
├── src/
│   ├── server.js          # 后端服务
│   └── init-db.js         # 数据库初始化
├── public/                # 前端页面
├── images/                # 图表数据（2046 张）
├── database.db            # SQLite 数据库（需同步）
└── package.json
```
