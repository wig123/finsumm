# SQLite Database Query Guide

## Basic Commands

### Enter Database
```bash
sqlite3 database.db
```

### View All Tables
```sql
.tables
```

### View Table Structure
```sql
.schema images
.schema annotations
.schema users
```

### Set Display Mode (More Readable)
```sql
.mode column
.headers on
```

### Exit
```sql
.quit
```

---

## Common SQL Queries

### 1. Statistics
```sql
-- View data count for all tables
SELECT 'images' as table_name, COUNT(*) as count FROM images
UNION ALL
SELECT 'annotations', COUNT(*) FROM annotations
UNION ALL
SELECT 'users', COUNT(*) FROM users;

-- Count images by status
SELECT status, COUNT(*) as count FROM images GROUP BY status;
```

### 2. View User Information
```sql
SELECT id, username, role, datetime(created_at/1000, 'unixepoch', 'localtime') as created_at 
FROM users;
```

### 3. View Annotation Progress
```sql
-- View the latest 10 annotations
SELECT 
    a.image_id,
    i.filename,
    a.status,
    a.annotator,
    datetime(a.annotated_at/1000, 'unixepoch', 'localtime') as annotated_time,
    substr(a.summary, 1, 50) || '...' as summary_preview
FROM annotations a
LEFT JOIN images i ON a.image_id = i.id
ORDER BY a.annotated_at DESC
LIMIT 10;
```

### 4. View Images Pending Annotation
```sql
-- First 10 images pending annotation
SELECT id, filename, status 
FROM images 
WHERE status = 'pending' 
LIMIT 10;
```

### 5. View Workload for a Specific Annotator
```sql
SELECT 
    annotator,
    COUNT(*) as total,
    COUNT(CASE WHEN status = 'annotated' THEN 1 END) as completed
FROM annotations
GROUP BY annotator;
```

### 6. View Annotation History (Version Records)
```sql
SELECT 
    image_id,
    version,
    substr(summary, 1, 50) || '...' as summary_preview,
    datetime(created_at/1000, 'unixepoch', 'localtime') as created_time
FROM annotation_history
ORDER BY image_id, version;
```

### 7. View AI Prompt Configuration
```sql
SELECT * FROM config;
```

---

## One-Line Command Queries (Non-Interactive Mode)

### Get Statistics
```bash
sqlite3 database.db "SELECT status, COUNT(*) FROM images GROUP BY status;"
```

### Export to CSV
```bash
sqlite3 -header -csv database.db "SELECT * FROM annotations;" > annotations.csv
```

### Formatted Output
```bash
sqlite3 -column -header database.db "SELECT * FROM users;"
```

---

## Advanced Operations

### Backup Database
```bash
sqlite3 database.db ".backup backup_$(date +%Y%m%d).db"
```

### Export Entire Database as SQL
```bash
sqlite3 database.db .dump > database_backup.sql
```

### Restore Database
```bash
sqlite3 new_database.db < database_backup.sql
```

### Check Database Integrity
```bash
sqlite3 database.db "PRAGMA integrity_check;"
```

---

## Utility Scripts

### View Current Annotation Progress
```bash
sqlite3 database.db << EOF
.mode column
.headers on
SELECT 
    'Total Images' as metric, COUNT(*) as value FROM images
UNION ALL
SELECT 'Annotated', COUNT(*) FROM images WHERE status = 'annotated'
UNION ALL
SELECT 'Pending', COUNT(*) FROM images WHERE status = 'pending'
UNION ALL
SELECT 'Deleted', COUNT(*) FROM images WHERE status = 'deleted';
EOF
```
