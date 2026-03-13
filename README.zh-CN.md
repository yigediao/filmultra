<p align="center">
  <img src="docs/branding/filmultra-readme-banner.png" alt="FilmUltra" width="860" />
</p>

# FilmUltra

[English](README.md) | [简体中文](README.zh-CN.md)

FilmUltra 是一个面向专业摄影师的本地优先照片管理器，目标是替代对专业工作流并不友好的 Synology Photos。

## 为什么做它

- 解决 Synology Photos 中 RAW + JPG 重复显示的问题，把同一张照片的多种文件格式合并成一个逻辑资产。
- 解决评分功能基本无用的问题，把评分变成真正可用的筛片工作流，而不是一个摆设筛选器。
- 以更快、更准、可纠错、可迭代学习的人脸流程替代 Synology Photos 原有人脸检测能力。
- 加入实验性的 SAM3D 单帧人体与物体三维重建能力，可自然衔接 3D 打印工作流。

## 技术栈

- 后端：FastAPI、SQLAlchemy、Pillow、rawpy、OpenCV
- 前端：Next.js 15、React 19、TypeScript
- 存储：默认 SQLite，也可切换到 PostgreSQL 方案
- 可选机器学习能力：通过 `third_party/` 子模块接入 SAM2、SAM 3D Body、SAM 3D Objects

## 项目状态

FilmUltra 当前处于 alpha 阶段。
核心图库、详情页、人物工作流与开发 smoke test 已可用。
3D 流水线仍属实验特性，并依赖本地安装的模型权重。

## 快速开始

### 1. 连同子模块一起克隆

```bash
git clone --recurse-submodules https://github.com/yigediao/filmultra.git
cd filmultra
```

如果你已经克隆过但没有带子模块：

```bash
git submodule update --init --recursive
```

### 2. 安装后端依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

### 4. 配置本地路径

```bash
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
```

编辑 `backend/.env`，将照片库挂载路径与本地运行目录改成你自己的环境。

### 5. 启动本地开发

```bash
make backend-dev
make frontend-dev
```

后端默认地址是 `http://127.0.0.1:8000`，前端默认地址是 `http://127.0.0.1:3000`。

## 常用命令

```bash
make help
make smoke-synology-gvfs
make latest-synology-run
make review-synology-gvfs
make stop-review-synology-gvfs
make migrate-workspace
make project-status
```

## 仓库结构

- `backend/`：FastAPI 应用与核心服务
- `frontend/`：Next.js 前端与 UI 组件
- `docs/`：架构说明、环境配置与开发治理文档
- `scripts/`：开发脚本与 smoke test 入口
- `third_party/`：外部模型与研究仓库子模块
- `var/`：运行时状态、日志、缓存与隔离测试产物

另见：

- `docs/architecture.md`
- `docs/development/README.md`
- `docs/development/REPO_LAYOUT.md`
- `docs/development/WORKLOG.md`
- `docs/sam3d_environment_setup.md`

## 哪些内容不会进入版本库

公开仓库 **不会** 包含：

- 本地照片库或 NAS 镜像目录
- SQLite 数据库与生成的预览缓存
- smoke test 日志与临时运行产物
- 大体积模型权重与 checkpoint
- 本地挂载会话状态与机器相关辅助输出

## Synology / NAS 工作流

FilmUltra 可以处理任何本地已挂载的照片目录。
如果你使用的是 Synology，依然支持 SMB/NFS 挂载工作流，但仓库本身已经做成通用形态：
你需要通过环境变量或脚本参数提供自己的主机、共享名与本地挂载点。

## 3D 工具链

3D 流水线需要额外环境配置与本地 checkpoint。
请查看 `docs/sam3d_environment_setup.md`，了解当前环境模型、预期路径与 smoke test 入口。

## 当前注意事项

- 人物聚类仍然属于 MVP 级流程，依然建议人工复核
- 任务执行目前仍在进程内完成，还没有独立 worker 队列
- 3D 重建能力依赖本地安装的研究环境与模型权重
- 当前 UI 文案仍然是中文优先

## 许可证

本项目采用 Apache License 2.0。详见 [LICENSE](LICENSE)。
