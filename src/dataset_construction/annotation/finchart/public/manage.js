// 管理页面逻辑

// DOM 元素
const currentUser = document.getElementById('currentUser');
const logoutBtn = document.getElementById('logoutBtn');
const statTotal = document.getElementById('statTotal');
const statAnnotated = document.getElementById('statAnnotated');
const statPending = document.getElementById('statPending');
const statDeleted = document.getElementById('statDeleted');
const progressAnnotated = document.getElementById('progressAnnotated');
const progressPending = document.getElementById('progressPending');
const progressDeleted = document.getElementById('progressDeleted');
const promptGenerate = document.getElementById('promptGenerate');
const promptModify = document.getElementById('promptModify');
const savePromptGenerate = document.getElementById('savePromptGenerate');
const savePromptModify = document.getElementById('savePromptModify');
const fileUploadArea = document.getElementById('fileUploadArea');
const fileInput = document.getElementById('fileInput');
const uploadPreview = document.getElementById('uploadPreview');
const uploadCount = document.getElementById('uploadCount');
const previewGrid = document.getElementById('previewGrid');
const clearUpload = document.getElementById('clearUpload');
const confirmUpload = document.getElementById('confirmUpload');
const selectAllBtn = document.getElementById('selectAllBtn');
const batchGenerateBtn = document.getElementById('batchGenerateBtn');
const exportBtn = document.getElementById('exportBtn');
const selectedCount = document.getElementById('selectedCount');
const filterBtns = document.querySelectorAll('.filter-btn');
const imageGrid = document.getElementById('imageGrid');
const pagination = document.getElementById('pagination');

// 状态变量
let images = [];
let selectedImages = new Set();
let currentFilter = 'all';
let currentPage = 1;
const pageSize = 24;
let filesToUpload = [];

// 检查登录状态
if (!api.auth.isLoggedIn()) {
  window.location.href = 'index.html';
}

// 初始化
async function init() {
  try {
    // 显示当前用户
    const user = api.auth.getCurrentUser();
    if (user) {
      currentUser.textContent = user.username;
    }

    // 加载统计数据
    await loadStats();

    // 加载配置
    await loadConfig();

    // 加载图片列表
    await loadImages();

    // 绑定事件
    bindEvents();

    // 入场动画
    anime({
      targets: '.fade-in',
      opacity: [0, 1],
      translateY: [20, 0],
      duration: 600,
      easing: 'easeOutQuad'
    });
  } catch (error) {
    console.error('初始化失败:', error);
    alert('初始化失败: ' + error.message);
  }
}

// 绑定事件
function bindEvents() {
  logoutBtn.addEventListener('click', logout);
  savePromptGenerate.addEventListener('click', () => savePrompt('generate'));
  savePromptModify.addEventListener('click', () => savePrompt('modify'));

  // 文件上传
  fileUploadArea.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', handleFileSelect);
  fileUploadArea.addEventListener('dragover', handleDragOver);
  fileUploadArea.addEventListener('dragleave', handleDragLeave);
  fileUploadArea.addEventListener('drop', handleDrop);
  clearUpload.addEventListener('click', clearFileUpload);
  confirmUpload.addEventListener('click', uploadFiles);

  // 批量操作
  selectAllBtn.addEventListener('click', toggleSelectAll);
  batchGenerateBtn.addEventListener('click', batchGenerate);
  exportBtn.addEventListener('click', exportData);

  // 筛选
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      currentFilter = btn.dataset.filter;
      currentPage = 1;
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadImages();
    });
  });

  // 默认激活"全部"
  filterBtns[0].classList.add('active');
}

// 加载统计数据
async function loadStats() {
  try {
    const stats = await api.stats.get();

    statTotal.textContent = stats.total;
    statAnnotated.textContent = stats.annotated;
    statPending.textContent = stats.pending;
    statDeleted.textContent = stats.deleted;

    const total = stats.total || 1;
    progressAnnotated.style.width = `${(stats.annotated / total) * 100}%`;
    progressPending.style.width = `${(stats.pending / total) * 100}%`;
    progressDeleted.style.width = `${(stats.deleted / total) * 100}%`;
  } catch (error) {
    console.error('加载统计失败:', error);
  }
}

// 加载配置
async function loadConfig() {
  try {
    const config = await api.config.get();
    promptGenerate.value = config.prompt_generate || '';
    promptModify.value = config.prompt_modify || '';
  } catch (error) {
    console.error('加载配置失败:', error);
  }
}

// 保存 Prompt
async function savePrompt(type) {
  try {
    const btn = type === 'generate' ? savePromptGenerate : savePromptModify;
    btn.disabled = true;
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<div class="spinner"></div> 保存中...';

    const config = await api.config.get();
    const newConfig = {
      prompt_generate: type === 'generate' ? promptGenerate.value : config.prompt_generate,
      prompt_modify: type === 'modify' ? promptModify.value : config.prompt_modify
    };

    await api.config.update(newConfig);

    anime({
      targets: btn,
      scale: [0.95, 1],
      duration: 300,
      easing: 'easeOutQuad'
    });

    alert('保存成功');
  } catch (error) {
    console.error('保存失败:', error);
    alert('保存失败: ' + error.message);
  } finally {
    const btn = type === 'generate' ? savePromptGenerate : savePromptModify;
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-save"></i> 保存';
  }
}

// 加载图片列表
async function loadImages() {
  try {
    const params = currentFilter !== 'all' ? { status: currentFilter } : {};
    images = await api.images.list(params);

    renderImages();
    renderPagination();
  } catch (error) {
    console.error('加载图片失败:', error);
    imageGrid.innerHTML = '<div class="text-center text-gray-500 p-8">加载失败</div>';
  }
}

// 渲染图片网格
function renderImages() {
  const start = (currentPage - 1) * pageSize;
  const end = start + pageSize;
  const pageImages = images.slice(start, end);

  if (pageImages.length === 0) {
    imageGrid.innerHTML = '<div class="text-center text-gray-500 p-8">暂无图片</div>';
    return;
  }

  imageGrid.innerHTML = pageImages.map(img => {
    const isSelected = selectedImages.has(img.id);
    const statusColor = img.status === 'annotated' ? '#10b981' :
                       img.status === 'pending' ? '#f59e0b' : '#ef4444';
    const statusText = img.status === 'annotated' ? '已标注' :
                      img.status === 'pending' ? '待标注' : '已删除';

    return `
      <div class="image-card" data-id="${img.id}">
        <input
          type="checkbox"
          class="image-card-checkbox"
          data-id="${img.id}"
          ${isSelected ? 'checked' : ''}
        >
        <img src="${img.path}" alt="${img.filename}" loading="lazy">
        <div class="image-card-content">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-semibold" style="color: #6b7280;">ID: ${img.id}</span>
            <span class="badge" style="background: ${statusColor}; color: white; font-size: 0.7rem; padding: 0.2rem 0.5rem;">
              ${statusText}
            </span>
          </div>
          <div class="text-xs text-gray-600">${img.filename}</div>
        </div>
      </div>
    `;
  }).join('');

  // 绑定事件
  document.querySelectorAll('.image-card-checkbox').forEach(checkbox => {
    checkbox.addEventListener('change', handleCheckboxChange);
  });

  document.querySelectorAll('.image-card').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.classList.contains('image-card-checkbox')) return;
      const id = card.dataset.id;
      window.location.href = `annotate.html?id=${id}`;
    });
  });

  updateSelectedCount();
}

// 渲染分页
function renderPagination() {
  const totalPages = Math.ceil(images.length / pageSize);

  if (totalPages <= 1) {
    pagination.innerHTML = '';
    return;
  }

  let pages = '';

  pages += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="changePage(${currentPage - 1})">
    <i class="fas fa-chevron-left"></i>
  </button>`;

  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
      pages += `<button class="${i === currentPage ? 'active' : ''}" onclick="changePage(${i})">${i}</button>`;
    } else if (i === currentPage - 3 || i === currentPage + 3) {
      pages += `<span>...</span>`;
    }
  }

  pages += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="changePage(${currentPage + 1})">
    <i class="fas fa-chevron-right"></i>
  </button>`;

  pagination.innerHTML = pages;
}

// 切换页面
function changePage(page) {
  currentPage = page;
  renderImages();
  renderPagination();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// 全局暴露 changePage
window.changePage = changePage;

// 处理复选框变化
function handleCheckboxChange(e) {
  const id = e.target.dataset.id;
  if (e.target.checked) {
    selectedImages.add(id);
  } else {
    selectedImages.delete(id);
  }
  updateSelectedCount();
}

// 更新选中计数
function updateSelectedCount() {
  selectedCount.textContent = selectedImages.size;
  batchGenerateBtn.disabled = selectedImages.size === 0;
}

// 全选/取消全选
function toggleSelectAll() {
  const start = (currentPage - 1) * pageSize;
  const end = start + pageSize;
  const pageImages = images.slice(start, end);

  const allSelected = pageImages.every(img => selectedImages.has(img.id));

  if (allSelected) {
    pageImages.forEach(img => selectedImages.delete(img.id));
    selectAllBtn.innerHTML = '<i class="fas fa-check-square"></i> 全选';
  } else {
    pageImages.forEach(img => selectedImages.add(img.id));
    selectAllBtn.innerHTML = '<i class="fas fa-square"></i> 取消全选';
  }

  renderImages();
}

// 批量生成（并发控制版本）
async function batchGenerate() {
  if (selectedImages.size === 0) return;

  const confirmed = confirm(`确定要为选中的 ${selectedImages.size} 张图片生成总结吗？\n\n将使用 5 个并发请求同时处理，预计耗时更短。`);
  if (!confirmed) return;

  try {
    batchGenerateBtn.disabled = true;
    const originalHTML = batchGenerateBtn.innerHTML;

    const config = await api.config.get();
    const prompt = config.prompt_generate || '请生成图表总结';

    // 使用并发控制批量生成
    const result = await batchGenerateWithConcurrency(
      Array.from(selectedImages),
      prompt,
      5  // 并发数：5
    );

    // 显示结果
    const message = `
批量生成完成！

✅ 成功: ${result.completed} 张
${result.failed > 0 ? `❌ 失败: ${result.failed} 张` : ''}
📊 总计: ${result.total} 张

${result.failed > 0 ? '\n失败的图片已在控制台输出详情。' : ''}
    `.trim();

    alert(message);
    
    selectedImages.clear();
    await loadStats();
    await loadImages();
  } catch (error) {
    console.error('批量生成失败:', error);
    alert('批量生成失败: ' + error.message);
  } finally {
    batchGenerateBtn.disabled = false;
    batchGenerateBtn.innerHTML = '<i class="fas fa-magic"></i> 批量生成 (<span id="selectedCount">0</span>)';
  }
}

// 并发控制的批量生成函数
async function batchGenerateWithConcurrency(imageIds, prompt, concurrency = 5) {
  const results = [];
  const queue = [...imageIds];
  let completed = 0;
  let failed = 0;
  const total = imageIds.length;
  const failedItems = []; // 记录失败的详情

  console.log(`[批量生成] 开始处理 ${total} 张图片，并发数: ${concurrency}`);

  // 单个工作线程
  async function worker(workerId) {
    while (queue.length > 0) {
      const imageId = queue.shift();
      if (!imageId) break;

      console.log(`[Worker ${workerId}] 处理图片: ${imageId} (剩余: ${queue.length})`);

      try {
        const image = images.find(img => img.id === imageId);
        if (!image) {
          console.warn(`[Worker ${workerId}] 图片不存在: ${imageId}`);
          failed++;
          failedItems.push({ imageId, error: '图片不存在' });
          continue;
        }

        // 调用 AI 生成
        console.log(`[Worker ${workerId}] 调用 AI 生成...`);
        const result = await api.ai.generate(image.path, prompt);

        // 保存标注（状态设为 pending，等用户确认后再变 annotated）
        await api.annotations.create({
          image_id: imageId,
          summary: result.summary,
          modification_note: '',
          status: 'pending'  // 生成后需要用户审核确认
        });

        completed++;
        results.push({ imageId, success: true });
        console.log(`[Worker ${workerId}] ✅ 完成: ${imageId}`);

      } catch (error) {
        console.error(`[Worker ${workerId}] ❌ 失败 (${imageId}):`, error.message);
        failed++;
        failedItems.push({ imageId, error: error.message });
        results.push({ imageId, success: false, error: error.message });

        // 如果是 429 限流错误，等待后重新加入队列（最多重试1次）
        if (error.message.includes('429') && !error._retried) {
          console.log(`[Worker ${workerId}] 遇到速率限制，5秒后重试: ${imageId}`);
          await new Promise(resolve => setTimeout(resolve, 5000));
          
          // 标记已重试，避免无限重试
          const retryError = new Error(error.message);
          retryError._retried = true;
          queue.push(imageId);
          failed--; // 回退计数，因为会重试
        }
      }

      // 更新进度显示
      const progress = completed + failed;
      const percentage = Math.round((progress / total) * 100);
      batchGenerateBtn.innerHTML = `
        <div class="spinner"></div> 
        ${progress}/${total} (${percentage}%)
        ${failed > 0 ? `<span style="color: #ef4444;">失败: ${failed}</span>` : ''}
      `;
    }

    console.log(`[Worker ${workerId}] 工作完成`);
  }

  // 创建并发工作池
  const workers = Array(concurrency)
    .fill(null)
    .map((_, index) => worker(index + 1));

  // 等待所有工作线程完成
  await Promise.all(workers);

  console.log(`[批量生成] 全部完成 - 成功: ${completed}, 失败: ${failed}`);
  
  // 输出失败详情
  if (failedItems.length > 0) {
    console.group('❌ 失败的图片详情');
    failedItems.forEach(item => {
      console.log(`${item.imageId}: ${item.error}`);
    });
    console.groupEnd();
  }

  return {
    completed,
    failed,
    total,
    results,
    failedItems
  };
}

// 导出数据
async function exportData() {
  try {
    exportBtn.disabled = true;
    exportBtn.innerHTML = '<div class="spinner"></div> 导出中...';

    const annotations = await api.annotations.list();

    const data = annotations.map(anno => ({
      image_id: anno.image_id,
      filename: anno.filename,
      summary: anno.summary,
      modification_note: anno.modification_note,
      status: anno.status,
      annotator: anno.annotator,
      annotated_at: anno.annotated_at ? new Date(anno.annotated_at).toLocaleString('zh-CN') : ''
    }));

    // 导出为 JSON
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `annotations_${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);

    alert('导出成功');
  } catch (error) {
    console.error('导出失败:', error);
    alert('导出失败: ' + error.message);
  } finally {
    exportBtn.disabled = false;
    exportBtn.innerHTML = '<i class="fas fa-download"></i> 导出数据';
  }
}

// 文件上传相关
function handleFileSelect(e) {
  const files = Array.from(e.target.files);
  addFilesToUpload(files);
}

function handleDragOver(e) {
  e.preventDefault();
  fileUploadArea.classList.add('drag-over');
}

function handleDragLeave(e) {
  e.preventDefault();
  fileUploadArea.classList.remove('drag-over');
}

function handleDrop(e) {
  e.preventDefault();
  fileUploadArea.classList.remove('drag-over');
  const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
  addFilesToUpload(files);
}

function addFilesToUpload(files) {
  filesToUpload = [...filesToUpload, ...files];
  updateUploadPreview();
}

function updateUploadPreview() {
  if (filesToUpload.length === 0) {
    uploadPreview.style.display = 'none';
    return;
  }

  uploadPreview.style.display = 'block';
  uploadCount.textContent = filesToUpload.length;

  previewGrid.innerHTML = filesToUpload.map((file, index) => {
    const url = URL.createObjectURL(file);
    return `
      <div style="position: relative;">
        <img src="${url}" style="width: 100%; height: 100px; object-fit: cover; border-radius: 0.375rem;">
        <button
          class="btn btn-danger"
          style="position: absolute; top: 0.25rem; right: 0.25rem; padding: 0.25rem 0.5rem; font-size: 0.75rem;"
          onclick="removeUploadFile(${index})"
        >
          <i class="fas fa-times"></i>
        </button>
      </div>
    `;
  }).join('');
}

// 全局暴露移除文件函数
window.removeUploadFile = function(index) {
  filesToUpload.splice(index, 1);
  updateUploadPreview();
};

function clearFileUpload() {
  filesToUpload = [];
  fileInput.value = '';
  updateUploadPreview();
}

async function uploadFiles() {
  if (filesToUpload.length === 0) return;

  alert('注意：图片上传功能需要后端支持文件上传接口。当前系统使用本地images目录的图片。\n\n建议直接将图片复制到 images/ 目录，然后运行 npm run init 重新初始化数据库。');

  // 这里可以添加真实的上传逻辑
  // const formData = new FormData();
  // filesToUpload.forEach(file => formData.append('images', file));
  // await api.images.upload(formData);

  clearFileUpload();
}

// 退出登录
function logout() {
  const confirmed = confirm('确定要退出登录吗？');
  if (!confirmed) return;

  api.auth.logout();
  window.location.href = 'index.html';
}

// 启动应用
init();
