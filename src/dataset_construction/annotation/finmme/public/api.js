// API 封装层

const API_BASE = window.location.origin;

class API {
  constructor() {
    this.token = localStorage.getItem('auth_token');
  }

  // 设置 token
  setToken(token) {
    this.token = token;
    if (token) {
      localStorage.setItem('auth_token', token);
    } else {
      localStorage.removeItem('auth_token');
    }
  }

  // 通用请求方法
  async request(url, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_BASE}${url}`, {
      ...options,
      headers
    });

    if (response.status === 401 || response.status === 403) {
      this.setToken(null);
      window.location.href = '/index.html';
      throw new Error('未授权，请重新登录');
    }

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || '请求失败');
    }

    return response.json();
  }

  // 认证相关
  auth = {
    login: async (username, password) => {
      const data = await this.request('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password })
      });
      this.setToken(data.token);
      return data;
    },

    logout: () => {
      this.setToken(null);
    },

    isLoggedIn: () => {
      return !!this.token;
    },

    getCurrentUser: () => {
      if (!this.token) return null;
      try {
        const payload = JSON.parse(atob(this.token.split('.')[1]));
        return {
          id: payload.id,
          username: payload.username,
          role: payload.role
        };
      } catch {
        return null;
      }
    }
  };

  // 图片相关
  images = {
    list: async (params = {}) => {
      const query = new URLSearchParams(params).toString();
      return this.request(`/api/images${query ? '?' + query : ''}`);
    },

    get: async (id) => {
      return this.request(`/api/images/${id}`);
    }
  };

  // 标注相关
  annotations = {
    list: async () => {
      return this.request('/api/annotations');
    },

    get: async (imageId) => {
      return this.request(`/api/annotations/${imageId}`);
    },

    create: async (data) => {
      return this.request('/api/annotations', {
        method: 'POST',
        body: JSON.stringify(data)
      });
    },

    update: async (imageId, data) => {
      return this.request(`/api/annotations/${imageId}`, {
        method: 'PUT',
        body: JSON.stringify(data)
      });
    },

    delete: async (imageId) => {
      return this.request(`/api/annotations/${imageId}`, {
        method: 'DELETE'
      });
    }
  };

  // 统计相关
  stats = {
    get: async () => {
      return this.request('/api/stats');
    }
  };

  // AI 服务
  ai = {
    generate: async (imageUrl, prompt) => {
      return this.request('/api/ai/generate', {
        method: 'POST',
        body: JSON.stringify({ imageUrl, prompt })
      });
    },

    modify: async (summary, note, prompt, imageUrl = null) => {
      return this.request('/api/ai/modify', {
        method: 'POST',
        body: JSON.stringify({ summary, note, prompt, imageUrl })
      });
    }
  };

  // 配置相关
  config = {
    get: async () => {
      return this.request('/api/config');
    },

    update: async (data) => {
      return this.request('/api/config', {
        method: 'PUT',
        body: JSON.stringify(data)
      });
    }
  };
}

// 全局 API 实例
const api = new API();
