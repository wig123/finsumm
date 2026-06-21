# Financial Chart Annotation System

A chart summarization annotation tool based on the FinChart-Bench dataset.

## Project Background

- **Dataset**: FinChart-Bench financial chart dataset (7020 charts)
- **Task**: Generate and review summary texts for each chart
- **Collaboration**: Multiple annotators synchronize work progress via Git

## Quick Start

```bash
# Clone the project
git clone <repository-url>
cd annotation-system

# Install dependencies
npm install

# Initialize database
npm run init

# Start the service
npm start

# Visit http://localhost:3000

# Export annotation data
npm run export
```

## Default Accounts

- Admin: `admin` / `admin123`
- Annotator: `annotator` / `anno123`

## Annotation Guidelines

### Summary Requirements
1. **Concise and Accurate**: 100-200 words
2. **Must Include**: Chart type, main trends, key data points
3. **Objective Description**: No subjective judgments or predictions

### Annotation Process
1. View the chart, read the AI-generated draft
2. Manually edit or use AI for optimization
3. Click 'Accept' after confirming accuracy
4. The system automatically navigates to the next chart

### Quality Standards
- ✅ Correctly identify chart types (bar charts, line charts, pie charts, etc.)
- ✅ Accurately describe data trends and key metrics
- ✅ Fluent sentences, no obvious errors
- ❌ Avoid redundancy and filler words
- ❌ Avoid subjective speculation

## Workflow

### Annotation
```bash
npm start                        # Start the service
# Log in via browser and annotate
```

### Synchronization
```bash
git pull                         # Pull latest data
# Continue annotation
git add database.db              # Stage annotation data
git commit -m "Annotation: John 50 charts"  # Commit
git push                         # Push
```

### Conflict Resolution
Conflicts may arise when multiple people annotate simultaneously. Solutions:
```bash
git pull                         # Conflict prompt when pulling
# Use merge strategy for database.db (explained later)
git add database.db
git commit -m "Merge annotations"
git push
```

## Project Structure

```
annotation-system/
├── src/                   # Source code
│   ├── server.js          # Express backend service
│   └── init-db.js         # Database initialization script
├── public/                # Frontend static files
│   ├── index.html         # Login page
│   ├── annotate.html      # Annotation page
│   ├── manage.html        # Management page
│   ├── api.js             # API wrapper layer
│   ├── annotate.js        # Annotation page logic
│   ├── manage.js          # Management page logic
│   └── styles.css         # Stylesheet
├── images/                # Chart data (7020 images)
├── database.db            # SQLite database
├── package.json           # Project configuration
└── README.md              # Documentation
```

## API Endpoints

```
POST   /api/auth/login              Login
GET    /api/images                  Get image list
GET    /api/annotations             Get annotation data
POST   /api/annotations             Save annotation
PUT    /api/annotations/:id         Update annotation
GET    /api/stats                   Statistics
POST   /api/ai/generate             AI generate summary
POST   /api/ai/modify               AI modify summary
```

## Data Export

Export all annotation data in JSON format:

```bash
npm run export
```

The exported file includes:
- All annotation data (summary, modification_note, status, annotator, etc.)
- Associated image information (filename, path)
- Annotation history (version of each modification)
- Statistical information (grouped by status, grouped by annotator)

Exported file naming format: `annotations_export_YYYY-MM-DDTHH-MM-SS.json`

## Important Notes

1. **Regular Commits**: Commit after completing every 50-100 annotations
2. **Timely Synchronization**: Before starting annotation, first `git pull`
3. **Data Backup**: Regularly back up `database.db` or use `npm run export` to export
4. **Images Read-Only**: Do not modify the `images/` directory
5. **Conflict Handling**: Communicate and resolve conflicts promptly

## Troubleshooting

**Port Occupied**
```bash
lsof -ti:3000 | xargs kill
```

**Database Corruption**
```bash
rm database.db
npm run init
```

**Image Loading Failure**
- Check if the `images/` directory is complete
- Confirm the image path is correct

## Tech Stack

- Frontend: HTML + CSS + Vanilla JS
- Backend: Node.js + Express
- Database: SQLite
- Authentication: JWT

## License

MIT
