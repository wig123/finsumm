# Financial Chart Annotation System

A chart summarization annotation tool based on the Finmme dataset. AI has generated initial drafts, which are to be manually reviewed and confirmed.

## 📌 Your Annotation Task

- **Annotation Account**: `annotator`
- **Assigned Range**: Images 1-1000
- **Corresponding Files**: `finmme_000000.png` ~ `finmme_001254.png`
- **Workload**: Total 1000 images

---

## Quick Start

### Prerequisites

- **Node.js** version >= 14.0
- **npm** (automatically installed with Node.js)

### Install Node.js

#### Windows Users

1. Visit [nodejs.org](https://nodejs.org/)
2. Download the **LTS version** (recommended) or Current version
3. Double-click the downloaded `.msi` file
4. Follow the installation wizard to complete the installation (just click "Next" all the way through)
5. Verify Installation:
   ```bash
   # Open Command Prompt (CMD) or PowerShell
   node --version
   npm --version
   ```

#### macOS Users

**Method 1: Official Website Download (Recommended for Beginners)**
1. Visit [nodejs.org](https://nodejs.org/)
2. Download the **LTS version** of the `.pkg` file
3. Double-click the installer package and follow the prompts to complete the installation
4. Verify Installation:
   ```bash
   # Open Terminal
   node --version
   npm --version
   ```

**Method 2: Using Homebrew (Recommended for Developers)**
```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Node.js
brew install node

# Verify installation
node --version
npm --version
```

### 1. Clone Project and Install

```bash
# Clone project
git clone <repository-url>
cd annotation-finmme

# Install dependencies
npm install

# Start service (database will be automatically initialized on first run)
npm start
```

### 2. Log in to the System

Visit **http://localhost:3000** and log in using your annotation account:

- **Account**: `annotator`
- **Password**: `anno123`

### 3. Start Annotating

- Find your assigned images (`finmme_000000.png` ~ `finmme_001254.png`) in the sidebar
- Click to enter the annotation page
- Follow the process below

---

## Annotation Process

### Summarization Guidelines

The AI-generated summary consists of two parts:
- **[Chart Composition]**: Basic information such as chart type, title, axes, legend, etc.
- **[Data Relationships]**: Key values, quantitative relationships, data comparisons (**primarily review this part**)

### 📖 Detailed Annotation Standards

**For complete annotation guidelines and examples, please refer to the Feishu document:**

👉 [Detailed Financial Chart Annotation Standards](https://jtafr5ebk9.feishu.cn/wiki/MDvCwZUsMiejtdksJlHcD0ebnve?wiki_all_space_view_source=space_sidebar&table=tblsavw6Bqc8FGFE&view=vewluJy8YA)

**Important Note**: Before starting annotation, please make sure to read the detailed standards and examples in the Feishu document!

### Operation Process

#### Scenario 1: No Modification Needed
1. Review the AI-generated summary, focusing on the numerical accuracy of the **[Data Relationships]** section
2. If confirmed correct, directly click the **"Accept"** button
3. The system will automatically jump to the next image

#### Scenario 2: Modification Required
1. Click the **"Edit"** button
2. Modify the summary content in the edit box (focus on correcting numerical errors)
3. Click the **"Save Changes"** button
4. After confirming the changes, click the **"Accept"** button

#### Scenario 3: Chart Issues
- Too many chart errors, overly complex, or issues with the image itself
- Directly click the **"Delete"** button

### Sidebar Quick Switching

The left sidebar displays a list of all images:
- **Green dot**: Annotated
- **Yellow dot**: Pending Annotation (AI generated, awaiting review)
- **Gray dot**: Not Annotated

Click any image in the sidebar to quickly navigate.

---

## Git Synchronization Process

### 📝 Workflow

#### 1. Before Each Annotation Session: Pull Latest Data

```bash
git pull
```

This will synchronize the annotation progress of others.

#### 2. Annotate Your Assigned Images

- **Only annotate**: `finmme_000000.png` ~ `finmme_001254.png`
- **Do not annotate**: images outside your range (to avoid conflicts)

#### 3. After Every 100 Images: Commit and Push

```bash
# Stage database file
git add database.db

# Commit (note progress)
git commit -m "Annotation: Completed 0-99, total 100 images"

# Push to remote
git push
```

### 💡 Important Tips

- ✅ **Before annotating, first `git pull`** to get the latest progress
- ✅ **Only annotate your assigned 1000 images** (`finmme_000000` ~ `finmme_001254`)
- ✅ **Push once every 100 images completed** to prevent data loss

---

## Frequently Asked Questions

### Port 3000 is Occupied

```bash
# Check process occupying port
lsof -i:3000

# Kill process (replace PID with actual process ID)
kill <PID>

# Or modify PORT in .env file to 3001
```

### Database Not Found on First Run

```bash
# Manually initialize database
npm run init
```

### Service Startup Failed

```bash
# 1. Check Node.js version
node --version  # Should be >= 14.0

# 2. Reinstall dependencies
rm -rf node_modules
npm install

# 3. Restart service
npm start
```

---

## Project Structure

```
annotation-finmme/
├── src/
│   ├── server.js          # Backend service
│   └── init-db.js         # Database initialization
├── public/                # Frontend pages
├── images/                # Chart data (2046 images)
├── database.db            # SQLite database (needs synchronization)
└── package.json
```
