# Audio2MusicScore

云端音频转乐谱系统 - 将音频文件自动转换为乐谱（MusicXML/PDF）。

## 功能特性

- 支持多种音频格式（MP3, WAV, FLAC, OGG, M4A）
- 支持从 YouTube 等平台下载音频
- 使用 Demucs 进行音源分离
- 使用 Basic-Pitch 进行音高检测
- 使用 Music21 + MuseScore 生成乐谱
- 异步任务处理（Celery + Redis）
- RESTful API 接口

## 目录结构

```
Audio2MusicScore/
├── app/                      # 应用主目录
│   ├── api/                  # API 路由模块
│   │   └── __init__.py
│   ├── core/                 # 核心模块
│   │   ├── __init__.py
│   │   ├── config.py         # 配置管理（Pydantic BaseSettings）
│   │   └── utils.py          # 工具函数
│   ├── services/             # 业务服务层
│   │   └── __init__.py
│   ├── tasks/                # Celery 异步任务
│   │   └── __init__.py
│   └── __init__.py
├── uploads/                  # 用户上传的原始音频文件
├── results/                  # 生成的乐谱文件（MusicXML, PDF）
├── temp/                     # 临时文件（处理中间产物）
├── tests/                    # 测试文件
│   └── __init__.py
├── .env                      # 环境变量配置（不提交到 Git）
├── requirements.txt          # Python 依赖
└── README.md                 # 项目说明
```

## 环境要求

- Ubuntu 22.04 (Headless)
- Python 3.10+
- Redis
- MuseScore 3/4（需配合 xvfb-run 使用）
- FFmpeg

## 快速开始

### 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y redis-server ffmpeg xvfb musescore3
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

创建 `.env` 文件：

```env
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=your-secret-key-here
DEBUG=false
```

### 4. 启动服务

```bash
# 启动 Redis
sudo systemctl start redis

# 启动 Celery Worker
celery -A app.tasks worker --loglevel=info

# 启动 FastAPI 服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 配置说明

所有配置项均可通过环境变量覆盖，详见 `app/core/config.py`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接地址 |
| `JWT_SECRET_KEY` | 随机生成 | JWT 签名密钥 |
| `MAX_UPLOAD_SIZE_MB` | `100` | 最大上传文件大小（MB） |
| `USE_XVFB` | `true` | 是否使用 xvfb-run 运行 MuseScore |

## 许可证

MIT License
