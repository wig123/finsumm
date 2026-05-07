#!/bin/bash
while true; do
    clear
    echo "=================================="
    echo "图表生成进度监控"
    echo "=================================="
    echo ""
    
    # 统计成功和失败
    success=$(grep -c "✓ task_" prog_1000_execution.log 2>/dev/null || echo 0)
    failed=$(grep -c "✗ task_" prog_1000_execution.log 2>/dev/null || echo 0)
    total=1000
    completed=$((success + failed))
    
    echo "✅ 成功: $success 张"
    echo "❌ 失败: $failed 张"
    echo "📊 总计: $completed / $total 张"
    echo "📈 进度: $(awk "BEGIN {printf \"%.1f\", $completed/$total*100}")%"
    
    if [ $completed -gt 0 ]; then
        success_rate=$(awk "BEGIN {printf \"%.1f\", $success/$completed*100}")
        echo "✓  成功率: $success_rate%"
    fi
    
    echo ""
    echo "最近完成的任务:"
    tail -10 prog_1000_execution.log | grep -E "(✓|✗) task_" | tail -5
    
    echo ""
    echo "按 Ctrl+C 退出监控"
    sleep 5
done
