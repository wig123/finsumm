# Qwen3-VL-8B SFT 环境
# 基于 PyTorch 2.6.0 + CUDA 12.4（驱动 550.x）
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel

# 设置镜像源加速
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV DEBIAN_FRONTEND=noninteractive

# 配置国内 apt 镜像源 (Ubuntu 22.04)
RUN sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list

# 1. 系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git vim wget curl ca-certificates \
    ffmpeg libsm6 libxext6 libxrender-dev \
    libgl1 libglib2.0-0 libjpeg-dev libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. 升级 pip
RUN pip install --no-cache-dir -U pip setuptools wheel

# 3. 复制并安装 LLaMA-Factory (GitHub 最新版，支持 qwen3_vl 模板)
COPY llama-factory-latest.tar.gz /tmp/
RUN cd /tmp && tar -xzf llama-factory-latest.tar.gz && \
    pip install --no-cache-dir -e "/tmp/LLaMA-Factory[torch,metrics]"

# 4. 安装 Flash Attention 2 (RTX 4090 支持)
# 需要 CUDA 编译环境，安装时间较长 (~30min)
RUN pip install --no-cache-dir ninja packaging && \
    pip install --no-cache-dir flash-attn --no-build-isolation

# 5. 安装额外依赖
RUN pip install --no-cache-dir \
    "transformers>=4.51.0" \
    "qwen-vl-utils[decord]>=0.0.14" \
    "bitsandbytes>=0.43.0" \
    "modelscope" \
    "wandb" \
    "tensorboard" \
    "deepspeed" \
    "omegaconf"

# 6. 环境变量配置（适配 8×RTX 4090）
ENV DISABLE_VERSION_CHECK=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1 \
    NCCL_P2P_DISABLE=1 \
    NCCL_IB_DISABLE=1 \
    CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 \
    TORCH_DISTRIBUTED_DEFAULT_PORT=29501

WORKDIR /app
CMD ["bash"]
