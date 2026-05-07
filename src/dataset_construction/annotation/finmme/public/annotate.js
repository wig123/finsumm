// 标注页面逻辑

// DOM 元素
const imageContainer = document.getElementById('imageContainer');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const progressText = document.getElementById('progressText');
const summaryDisplay = document.getElementById('summaryDisplay');
const summaryEditor = document.getElementById('summaryEditor');
const emptyState = document.getElementById('emptyState');
const editBtn = document.getElementById('editBtn');
const saveEditBtn = document.getElementById('saveEditBtn');
const generateFromEmpty = document.getElementById('generateFromEmpty');
const modifyBtn = document.getElementById('modifyBtn');
const acceptBtn = document.getElementById('acceptBtn');
const regenerateBtn = document.getElementById('regenerateBtn');
const deleteBtn = document.getElementById('deleteBtn');
const modificationPanel = document.getElementById('modificationPanel');
const modificationNote = document.getElementById('modificationNote');
const modifyBtnText = document.getElementById('modifyBtnText');
const historySection = document.getElementById('historySection');
const historyList = document.getElementById('historyList');
const historyCount = document.getElementById('historyCount');
const imageId = document.getElementById('imageId');
const statusBadge = document.getElementById('statusBadge');
const currentUser = document.getElementById('currentUser');
const logoutBtn = document.getElementById('logoutBtn');
const imageList = document.getElementById('imageList');
const filterTabs = document.querySelectorAll('.filter-tab');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarPanel = document.querySelector('.sidebar-panel');
const annotationContent = document.querySelector('.annotation-content');

// 状态变量
let images = [];
let allImages = [];  // 保存所有图片的副本
let currentIndex = 0;
let currentAnnotation = null;
let isEditMode = false;
let isModifyPanelOpen = false;
let isGenerating = false;
let currentFilter = 'all';  // 当前筛选状态
let isSidebarCollapsed = false;  // 侧边栏收起状态

// 检查登录状态
if (!api.auth.isLoggedIn()) {
  window.location.href = 'index.html';
}

// ========== 侧边栏功能 ==========

// 渲染图片列表到侧边栏
async function renderImageList() {
  if (!imageList) return;

  // 获取所有标注状态
  const annotations = await api.annotations.list();
  const annotationMap = {};
  annotations.forEach(ann => {
    annotationMap[ann.image_id] = ann.status;
  });

  // 生成列表 HTML
  imageList.innerHTML = images.map((img, index) => {
    const status = annotationMap[img.id] || 'unannotated';
    const statusText = status === 'annotated' ? '已标注' : status === 'pending' ? '待标注' : '未标注';
    const statusClass = status === 'annotated' ? 'annotated' : status === 'pending' ? 'pending' : 'unannotated';

    return `
      <div class="image-list-item" data-index="${index}" data-image-id="${img.id}">
        <div class="item-index">${index + 1}</div>
        <div class="item-info">
          <div class="item-filename" title="${img.filename}">${img.filename}</div>
          <div class="item-status">
            <span class="status-dot ${statusClass}"></span>
            <span style="color: #6b7280;">${statusText}</span>
          </div>
        </div>
      </div>
    `;
  }).join('');

  // 绑定点击事件
  document.querySelectorAll('.image-list-item').forEach(item => {
    item.addEventListener('click', () => {
      const index = parseInt(item.dataset.index);
      jumpToImage(index);
    });
  });

  // 更新当前选中状态
  updateSidebarActiveState();
}

// 筛选图片
async function filterImages(filter) {
  currentFilter = filter;

  // 更新筛选按钮状态
  filterTabs.forEach(tab => {
    if (tab.dataset.filter === filter) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  // 根据筛选条件过滤图片
  if (filter === 'all') {
    images = [...allImages];
  } else {
    // 获取标注状态
    const annotations = await api.annotations.list();
    const annotationMap = {};
    annotations.forEach(ann => {
      annotationMap[ann.image_id] = ann.status;
    });

    if (filter === 'annotated') {
      images = allImages.filter(img => annotationMap[img.id] === 'annotated');
    } else if (filter === 'unannotated') {
      images = allImages.filter(img => !annotationMap[img.id] || annotationMap[img.id] !== 'annotated');
    }
  }

  // 重新渲染列表
  await renderImageList();

  // 加载第一张图片（如果有）
  if (images.length > 0) {
    await loadImage(0);
  } else {
    imageContainer.innerHTML = '<div style="text-align: center; color: #9ca3af;"><i class="fas fa-info-circle" style="font-size: 3rem; margin-bottom: 1rem; opacity: 0.3;"></i><p>没有符合条件的图片</p></div>';
  }
}

// 更新侧边栏的选中状态
function updateSidebarActiveState() {
  document.querySelectorAll('.image-list-item').forEach(item => {
    const index = parseInt(item.dataset.index);
    if (index === currentIndex) {
      item.classList.add('active');
      // 滚动到可见区域
      item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
      item.classList.remove('active');
    }
  });
}

// 跳转到指定图片
async function jumpToImage(index) {
  if (index < 0 || index >= images.length) return;
  if (index === currentIndex) return;

  // 退出编辑模式
  if (isEditMode) toggleEditMode();
  if (isModifyPanelOpen) toggleModifyPanel();

  // 加载图片
  await loadImage(index);
}

// 收起/展开侧边栏
function toggleSidebar() {
  isSidebarCollapsed = !isSidebarCollapsed;

  if (isSidebarCollapsed) {
    sidebarPanel.classList.add('collapsed');
    annotationContent.classList.add('sidebar-collapsed');
    sidebarToggle.classList.add('collapsed');
  } else {
    sidebarPanel.classList.remove('collapsed');
    annotationContent.classList.remove('sidebar-collapsed');
    sidebarToggle.classList.remove('collapsed');
  }

  // 添加动画效果
  anime({
    targets: [sidebarPanel, annotationContent],
    duration: 300,
    easing: 'easeOutQuad'
  });
}

// ========== 初始化 ==========

// 初始化
async function init() {
  try {
    // 显示当前用户
    const user = api.auth.getCurrentUser();
    if (user) {
      currentUser.textContent = user.username;
    }

    // 加载图片列表
    images = await api.images.list({ status: 'all' });
    allImages = [...images];  // 保存所有图片的副本

    if (images.length === 0) {
      alert('没有可标注的图片');
      return;
    }

    // 渲染侧边栏图片列表
    await renderImageList();

    // 检查 URL 参数，是否指定了要查看的图片
    const urlParams = new URLSearchParams(window.location.search);
    const imageId = urlParams.get('id');

    let startIndex = 0;
    if (imageId) {
      // 查找指定图片的索引
      const foundIndex = images.findIndex(img => img.id === imageId);
      if (foundIndex !== -1) {
        startIndex = foundIndex;
        console.log(`从 URL 参数定位到图片: ${imageId}, 索引: ${startIndex}`);
      }
    }

    // 加载指定的图片（或第一张）
    await loadImage(startIndex);

    // 绑定事件
    bindEvents();

    // 入场动画
    anime({
      targets: '.annotation-content',
      opacity: [0, 1],
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
  prevBtn.addEventListener('click', () => navigate(-1));
  nextBtn.addEventListener('click', () => navigate(1));
  editBtn.addEventListener('click', toggleEditMode);
  saveEditBtn.addEventListener('click', saveManualEdit);
  generateFromEmpty.addEventListener('click', generateSummary);
  modifyBtn.addEventListener('click', toggleModifyPanel);
  acceptBtn.addEventListener('click', acceptAnnotation);
  regenerateBtn.addEventListener('click', regenerateSummary);
  deleteBtn.addEventListener('click', deleteAnnotation);
  logoutBtn.addEventListener('click', logout);

  // 侧边栏筛选器
  filterTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const filter = tab.dataset.filter;
      filterImages(filter);
    });
  });

  // 侧边栏收起/展开
  sidebarToggle.addEventListener('click', toggleSidebar);

  // 键盘快捷键
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') navigate(-1);
    if (e.key === 'ArrowRight') navigate(1);
    if (e.key === 'Escape') {
      if (isEditMode) toggleEditMode();
      if (isModifyPanelOpen) toggleModifyPanel();
    }
  });
}

// 加载图片
async function loadImage(index) {
  if (index < 0 || index >= images.length) return;

  currentIndex = index;
  const image = images[currentIndex];

  // 显示图片
  imageContainer.innerHTML = `<img id="imageDisplay" src="${image.path}" alt="${image.filename}">`;
  imageId.textContent = image.id;

  // 加载标注
  try {
    currentAnnotation = await api.annotations.get(image.id);

    if (currentAnnotation && currentAnnotation.summary) {
      // 有标注内容
      summaryDisplay.textContent = currentAnnotation.summary;
      summaryDisplay.style.display = 'block';
      summaryEditor.value = currentAnnotation.summary;
      summaryEditor.style.display = 'none';
      emptyState.style.display = 'none';

      // 显示历史记录
      if (currentAnnotation.history && currentAnnotation.history.length > 0) {
        historySection.style.display = 'block';
        historyCount.textContent = currentAnnotation.history.length;
        displayHistory(currentAnnotation.history);
      } else {
        historySection.style.display = 'none';
      }

      // 显示状态
      statusBadge.textContent = currentAnnotation.status === 'annotated' ? '已标注' : '待标注';
      statusBadge.className = 'badge badge-' + (currentAnnotation.status === 'annotated' ? 'success' : 'warning');

      // 更新按钮状态
      editBtn.style.display = 'inline-flex';
      editBtn.disabled = false;
      modifyBtn.disabled = false;
      acceptBtn.disabled = false;
      regenerateBtn.disabled = false;
      deleteBtn.disabled = false;
    } else {
      // 无标注内容
      summaryDisplay.style.display = 'none';
      summaryEditor.style.display = 'none';
      emptyState.style.display = 'block';
      historySection.style.display = 'none';

      statusBadge.textContent = '未标注';
      statusBadge.className = 'badge badge-secondary';

      editBtn.style.display = 'none';
      modifyBtn.disabled = true;
      acceptBtn.disabled = true;
      regenerateBtn.disabled = true;
      deleteBtn.disabled = false;
    }
  } catch (error) {
    console.error('加载标注失败:', error);
    summaryDisplay.textContent = '加载失败: ' + error.message;
    summaryDisplay.style.display = 'block';
  }

  // 更新进度
  await updateProgress();

  // 更新导航按钮
  prevBtn.disabled = currentIndex === 0;
  nextBtn.disabled = currentIndex === images.length - 1;

  // 更新 URL，保存当前位置（刷新后可恢复）
  const newUrl = new URL(window.location);
  newUrl.searchParams.set('id', image.id);
  window.history.replaceState({}, '', newUrl);

  // 更新侧边栏高亮状态
  updateSidebarActiveState();
}

// 导航
function navigate(direction) {
  const newIndex = currentIndex + direction;
  if (newIndex >= 0 && newIndex < images.length) {
    // 退出编辑模式
    if (isEditMode) toggleEditMode();
    if (isModifyPanelOpen) toggleModifyPanel();

    // 动画切换
    anime({
      targets: '.summary-panel',
      opacity: [1, 0],
      translateX: direction > 0 ? [-20, 0] : [20, 0],
      duration: 300,
      easing: 'easeOutQuad',
      complete: async () => {
        await loadImage(newIndex);
        anime({
          targets: '.summary-panel',
          opacity: [0, 1],
          duration: 300,
          easing: 'easeOutQuad'
        });
      }
    });
  }
}

// 更新进度
async function updateProgress() {
  try {
    const stats = await api.stats.get();
    const total = stats.total - stats.deleted;
    progressText.textContent = `${currentIndex + 1}/${images.length} (已标注: ${stats.annotated}/${total})`;
  } catch (error) {
    console.error('获取统计失败:', error);
    progressText.textContent = `${currentIndex + 1}/${images.length}`;
  }
}

// 切换编辑模式
function toggleEditMode() {
  isEditMode = !isEditMode;

  if (isEditMode) {
    summaryDisplay.style.display = 'none';
    summaryEditor.style.display = 'block';
    editBtn.style.display = 'none';
    saveEditBtn.style.display = 'inline-flex';
    summaryEditor.focus();
  } else {
    summaryDisplay.style.display = 'block';
    summaryEditor.style.display = 'none';
    editBtn.style.display = 'inline-flex';
    saveEditBtn.style.display = 'none';
    // 恢复原值
    summaryEditor.value = currentAnnotation?.summary || '';
  }
}

// 保存手动编辑
async function saveManualEdit() {
  const newSummary = summaryEditor.value.trim();

  if (!newSummary) {
    alert('总结不能为空');
    return;
  }

  try {
    saveEditBtn.disabled = true;

    const imgId = images[currentIndex].id;

    if (currentAnnotation) {
      // 更新现有标注（保持原状态，不改为已标注）
      await api.annotations.update(imgId, {
        summary: newSummary,
        modification_note: currentAnnotation.modification_note || '',
        status: currentAnnotation.status || 'pending'
      });
    } else {
      // 创建新标注（状态为待标注）
      await api.annotations.create({
        image_id: imgId,
        summary: newSummary,
        modification_note: '',
        status: 'pending'
      });
    }

    // 重新加载标注
    await loadImage(currentIndex);

    // 更新侧边栏
    await renderImageList();

    // 退出编辑模式
    isEditMode = false;

    // 成功动画
    anime({
      targets: '.summary-panel',
      scale: [0.98, 1],
      duration: 300,
      easing: 'easeOutQuad'
    });
  } catch (error) {
    console.error('保存失败:', error);
    alert('保存失败: ' + error.message);
  } finally {
    saveEditBtn.disabled = false;
  }
}

// 生成总结
async function generateSummary(triggerButton = null) {
  if (isGenerating) return;

  const btn = triggerButton || generateFromEmpty;
  const originalHTML = btn.innerHTML;

  try {
    isGenerating = true;
    
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner"></div> 生成中...';

    const imgId = images[currentIndex].id;
    const imagePath = images[currentIndex].path;

    // 获取生成 prompt
    const config = await api.config.get();
    const prompt = config.prompt_generate || '请生成图表总结';

    console.log(`[生成总结] 图片ID: ${imgId}`);

    // 调用 AI 生成
    const result = await api.ai.generate(imagePath, prompt);

    // 保存标注（状态为待标注）
    await api.annotations.create({
      image_id: imgId,
      summary: result.summary,
      modification_note: '',
      status: 'pending'
    });

    console.log(`[生成总结] 成功保存`);

    // 重新加载（会自动恢复按钮状态）
    await loadImage(currentIndex);

    // 更新侧边栏
    await renderImageList();

    // 成功动画
    anime({
      targets: '.summary-panel',
      backgroundColor: ['#f0fdf4', '#ffffff'],
      duration: 1000,
      easing: 'easeOutQuad'
    });
  } catch (error) {
    console.error('[生成总结] 失败:', error);
    alert('生成失败: ' + error.message);
  } finally {
    isGenerating = false;
    
    // 确保按钮恢复（防止卡住）
    if (btn.innerHTML.includes('生成中')) {
      btn.disabled = false;
      if (btn === regenerateBtn) {
        btn.innerHTML = '<i class="fas fa-sync"></i> 重新生成';
      } else {
        btn.innerHTML = '<i class="fas fa-magic"></i> 生成总结';
      }
    }
  }
}

// 切换修改面板
function toggleModifyPanel() {
  isModifyPanelOpen = !isModifyPanelOpen;

  if (isModifyPanelOpen) {
    modificationPanel.classList.add('expanded');
    modificationNote.value = '';
    modificationNote.focus();
    modifyBtnText.textContent = '提交修改';

    anime({
      targets: modificationPanel,
      opacity: [0, 1],
      duration: 300,
      easing: 'easeOutQuad'
    });
  } else {
    modificationPanel.classList.remove('expanded');
    modifyBtnText.textContent = 'AI修改';

    anime({
      targets: modificationPanel,
      opacity: [1, 0],
      duration: 300,
      easing: 'easeOutQuad'
    });
  }

  // 如果面板打开，按钮变成提交按钮
  if (isModifyPanelOpen) {
    modifyBtn.onclick = submitModification;
  } else {
    modifyBtn.onclick = toggleModifyPanel;
  }
}

// 提交修改
async function submitModification() {
  const note = modificationNote.value.trim();

  if (!note) {
    alert('请输入修改意见');
    return;
  }

  try {
    modifyBtn.disabled = true;
    const originalText = modifyBtnText.textContent;
    modifyBtnText.textContent = '修改中...';

    // 获取修改 prompt
    const config = await api.config.get();
    const prompt = config.prompt_modify || '请根据意见修改总结';

    // 获取当前图片路径
    const imagePath = images[currentIndex].path;

    // 调用 AI 修改（传递图片 URL 以便进行多模态分析）
    const result = await api.ai.modify(currentAnnotation.summary, note, prompt, imagePath);

    // 更新标注（保持待标注状态）
    const imgId = images[currentIndex].id;
    await api.annotations.update(imgId, {
      summary: result.summary,
      modification_note: note,
      status: 'pending'
    });

    // 重新加载
    await loadImage(currentIndex);

    // 更新侧边栏
    await renderImageList();

    // 关闭面板
    isModifyPanelOpen = false;
    modificationPanel.classList.remove('expanded');

    // 成功动画
    anime({
      targets: '.summary-panel',
      backgroundColor: ['#f0f9ff', '#ffffff'],
      duration: 1000,
      easing: 'easeOutQuad'
    });
  } catch (error) {
    console.error('修改失败:', error);
    alert('修改失败: ' + error.message);
  } finally {
    modifyBtn.disabled = false;
    modifyBtnText.textContent = 'AI修改';
    modifyBtn.onclick = toggleModifyPanel;
  }
}

// 接受标注
async function acceptAnnotation() {
  if (!currentAnnotation) return;

  try {
    acceptBtn.disabled = true;

    const imgId = images[currentIndex].id;
    await api.annotations.update(imgId, {
      summary: currentAnnotation.summary,
      modification_note: currentAnnotation.modification_note || '',
      status: 'annotated'
    });

    // 立即更新侧边栏
    await renderImageList();

    // 成功提示
    anime({
      targets: '.summary-panel',
      backgroundColor: ['#f0fdf4', '#ffffff'],
      duration: 1000,
      easing: 'easeOutQuad'
    });

    // 自动跳转到下一张
    setTimeout(() => {
      navigate(1);
    }, 500);
  } catch (error) {
    console.error('接受失败:', error);
    alert('接受失败: ' + error.message);
  } finally {
    acceptBtn.disabled = false;
  }
}

// 重新生成
async function regenerateSummary() {
  const confirmed = confirm('确定要重新生成总结吗？当前总结将被覆盖。');
  if (!confirmed) return;

  // 传入 regenerateBtn 按钮，让它显示加载状态
  await generateSummary(regenerateBtn);
}

// 删除标注
async function deleteAnnotation() {
  const confirmed = confirm('确定要删除这张图片的标注吗？');
  if (!confirmed) return;

  try {
    deleteBtn.disabled = true;

    const imgId = images[currentIndex].id;
    await api.annotations.delete(imgId);

    // 从列表中移除
    images.splice(currentIndex, 1);
    // 同时从 allImages 中移除
    const deletedImageIndex = allImages.findIndex(img => img.id === imgId);
    if (deletedImageIndex !== -1) {
      allImages.splice(deletedImageIndex, 1);
    }

    if (images.length === 0) {
      alert('所有图片已标注完成');
      window.location.href = 'manage.html';
      return;
    }

    // 加载下一张（如果是最后一张，则加载前一张）
    const nextIndex = currentIndex >= images.length ? images.length - 1 : currentIndex;
    await loadImage(nextIndex);

    // 更新侧边栏
    await renderImageList();
  } catch (error) {
    console.error('删除失败:', error);
    alert('删除失败: ' + error.message);
  } finally {
    deleteBtn.disabled = false;
  }
}

// 显示历史记录
function displayHistory(history) {
  if (!history || history.length === 0) {
    historyList.innerHTML = '<div class="text-gray-500 text-sm">暂无历史记录</div>';
    return;
  }

  historyList.innerHTML = history.map((item) => `
    <div class="history-item" style="padding: 0.75rem; background: #f9fafb; border-radius: 0.5rem; margin-bottom: 0.5rem;">
      <div class="text-xs text-gray-500 mb-1">
        版本 ${item.version} - ${new Date(item.created_at).toLocaleString('zh-CN')}
      </div>
      <div class="text-sm">${item.summary}</div>
    </div>
  `).join('');
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
