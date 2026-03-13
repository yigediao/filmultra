# 摄影资产管理 App 开发说明（群晖 + Ubuntu 4090）

## 1. 项目概述

本项目旨在开发一个面向专业摄影工作流的照片资产管理 App（Digital Asset Management, DAM），用于管理存储在群晖 NAS 中的大量摄影作品。

与普通家庭相册或通用图库不同，本系统重点面向摄影师场景，核心需求包括：

- 将同一张照片对应的 **RAW + JPG** 两个物理文件视为 **一个逻辑照片资产**。
- 在进行 **评分（rating）**、筛选、管理时，对两个文件进行统一映射。
- 在照片预览或网格浏览时，只显示一次，而不是 RAW 和 JPG 分别重复展示。
- 支持基于 AI 的 **人脸识别 / 人物管理** 功能。
- 将高负载 AI 识别任务放在本地 **Ubuntu 4090 工作站** 上完成，再将识别结果同步回主系统。

该系统不建议直接修改 Synology Photos 的内部逻辑，而是建议构建一个 **独立的 DAM 应用层**：

- **群晖 NAS**：负责原始照片存储、共享、备份。
- **自定义 DAM App**：负责逻辑资产管理、评分、检索、人物管理、预览。
- **Ubuntu 4090 节点**：负责人脸识别、特征提取、聚类、预览图生成等高性能计算任务。

---

## 2. 项目目标

### 2.1 核心目标

1. 建立一个摄影师友好的照片管理系统。
2. 在系统层面统一处理 RAW 与 JPG 的逻辑绑定关系。
3. 提供高效的浏览、评分、筛选和人物管理能力。
4. 使 AI 处理与文件存储解耦，便于后期升级与扩展。
5. 保持元数据尽可能兼容业界通用生态（如 XMP sidecar、Exif metadata）。

### 2.2 非目标

当前阶段不将以下内容视为第一优先级：

- 完整替代 Lightroom 的调色 / 开发能力。
- 直接依赖或深度改造 Synology Photos 的内部数据库。
- 移动端原生 App 首发版本。
- 在线多用户协同编辑的复杂权限体系。

---

## 3. 典型用户场景

### 3.1 摄影师日常审片

摄影师一次拍摄导入一批照片到群晖，每张照片通常包含：

- 一个 RAW 文件（例如 `.CR3` / `.NEF` / `.ARW`）
- 一个 JPG 文件（用于快速预览）

系统应自动将这两个文件识别为同一张逻辑照片：

- 浏览时只显示一次
- 打分时同步到逻辑资产
- 详情页可查看该逻辑照片下所有物理文件

### 3.2 人物管理

摄影师希望按人物管理照片：

- 自动识别同一个人出现的所有照片
- 支持给人物命名
- 支持合并错分的人物簇
- 后续新照片自动归类到已有人物

### 3.3 NAS + 本地 AI 协同

由于 NAS 不适合承担大规模深度学习识别任务：

- Ubuntu 4090 工作站挂载 NAS 目录
- 本地执行人脸检测、embedding 提取、聚类
- 结果写回主数据库和必要的 sidecar 元数据

---

## 4. 总体架构设计

### 4.1 架构原则

1. **文件存储与业务逻辑分离**：群晖仅负责存储，不承载核心业务逻辑。
2. **逻辑资产优先**：系统内部一切交互以“逻辑照片”为单位，而非物理文件。
3. **数据库为主，元数据文件为辅**：UI 交互优先读写数据库，同时尽量同步到标准元数据。
4. **重计算异步化**：AI、缩略图生成、索引更新通过后台任务完成。
5. **可增量扩展**：支持先做 MVP，后续逐步增加人物管理、相似照片、移动端等功能。

### 4.2 推荐系统组成

#### A. 存储层
- 群晖 NAS
- SMB / NFS 共享目录
- 原始照片目录
- sidecar 元数据目录（如需要）
- 缩略图缓存目录（可选）

#### B. 应用层
- Web 前端（React / Next.js）
- 后端 API（FastAPI）
- 数据库（PostgreSQL）
- 缓存 / 任务队列（Redis + Celery 或 RQ）

#### C. AI 处理层
- Ubuntu 4090 节点
- 人脸检测模型
- 人脸 embedding 提取模型
- 聚类与人物管理任务
- 缩略图 / 预览图生成任务

---

## 5. 数据模型设计

### 5.1 核心思想

系统不能以“一个文件就是一张照片”的方式建模，否则会天然导致：

- RAW 和 JPG 重复展示
- 评分难以同步
- 人物和标签管理混乱

因此必须采用两层模型：

1. **Logical Asset（逻辑照片资产）**
2. **Physical File（物理文件）**

---

### 5.2 主要数据表

## 5.2.1 logical_assets

表示用户视角中的“一张照片”。

建议字段：

- `id`
- `capture_key`
- `display_name`
- `hero_file_id`
- `capture_time`
- `camera_model`
- `lens_model`
- `rating`
- `pick_flag`
- `reject_flag`
- `color_label`
- `width`
- `height`
- `created_at`
- `updated_at`

说明：

- `capture_key` 用于标识同一逻辑照片，可由 basename、拍摄时间、相机序列号等组合生成。
- `hero_file_id` 指向预览时默认展示的物理文件，一般优先选择 JPG。
- 所有 UI 层面的评分、标签、人物关联原则上都挂在 `logical_assets` 上。

## 5.2.2 physical_files

表示真实存在于文件系统中的文件。

建议字段：

- `id`
- `logical_asset_id`
- `file_path`
- `directory_path`
- `basename`
- `extension`
- `file_type`（RAW / JPG / XMP / VIDEO / OTHER）
- `file_size`
- `checksum`
- `capture_time`
- `width`
- `height`
- `is_hero`
- `metadata_json`
- `created_at`
- `updated_at`

说明：

- 一个 `logical_asset` 下可挂多个 `physical_file`。
- 常见情况是：一个 RAW + 一个 JPG。
- 后续也可以支持一个 RAW 对应多个导出版本。

## 5.2.3 people

存储已命名人物。

建议字段：

- `id`
- `name`
- `alias`
- `cover_face_id`
- `notes`
- `created_at`
- `updated_at`

## 5.2.4 faces

存储检测到的人脸实例。

建议字段：

- `id`
- `logical_asset_id`
- `physical_file_id`
- `bbox_x1`
- `bbox_y1`
- `bbox_x2`
- `bbox_y2`
- `confidence`
- `embedding_vector`
- `cluster_id`
- `person_id`
- `preview_path`
- `created_at`

说明：

- `embedding_vector` 可使用 pgvector 存储，或单独存储到向量库。
- 初始聚类阶段可先只写 `cluster_id`，待人工命名后再关联 `person_id`。

## 5.2.5 tags

可选表，用于关键词标签。

## 5.2.6 logical_asset_people

人物与照片的多对多关系。

建议字段：

- `logical_asset_id`
- `person_id`
- `face_count`

## 5.2.7 jobs

后台任务表。

建议字段：

- `id`
- `job_type`
- `status`
- `payload_json`
- `result_json`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`

---

## 6. RAW + JPG 配对逻辑

### 6.1 配对目标

系统需要自动识别两个物理文件属于同一张逻辑照片。

### 6.2 建议规则

按照以下优先级配对：

1. 同目录
2. basename 相同
3. 扩展名组合符合 RAW/JPG 模式
4. 拍摄时间极接近
5. 相机型号 / 序列号一致
6. 图像尺寸和 EXIF 信息辅助确认

### 6.3 支持的常见 RAW 扩展名

- `.cr2`
- `.cr3`
- `.nef`
- `.arw`
- `.raf`
- `.orf`
- `.rw2`
- `.dng`

### 6.4 示例

```text
IMG_1234.CR3
IMG_1234.JPG
```

应归并为一个 `logical_asset`。

### 6.5 异常情况处理

#### 情况 A：只有 JPG，没有 RAW
建立单文件逻辑资产。

#### 情况 B：只有 RAW，没有 JPG
建立单文件逻辑资产，但预览时需要动态生成缩略图。

#### 情况 C：一个 RAW 对应多个 JPG
应允许主 JPG 作为 `hero_file`，其余 JPG 记为衍生文件，后续可扩展版本管理逻辑。

---

## 7. 评分（Rating）设计

### 7.1 业务需求

用户给某张照片打分时，系统应将其视为对该逻辑照片打分，而不是只对某个具体文件打分。

例如：

- 逻辑照片 `A001` 包含 `IMG_1234.CR3` 和 `IMG_1234.JPG`
- 用户给该照片打 4 星
- 系统内部应记录该逻辑资产的评分为 4
- 同时尽可能同步到实际文件元数据

### 7.2 推荐实现

#### 主记录位置：数据库

数据库中的 `logical_assets.rating` 作为系统真相源。

#### 文件同步位置：XMP / Exif

- JPG：可直接写入 XMP / Exif rating
- RAW：优先写入 `.xmp sidecar`
- 不建议直接修改 RAW 原始文件

### 7.3 同步策略

当用户修改评分时：

1. 更新 `logical_assets.rating`
2. 生成元数据同步任务
3. 对对应 JPG 写入 rating
4. 对 RAW 对应 sidecar 写入 rating
5. 记录同步状态与错误日志

### 7.4 冲突处理

若文件系统中的 XMP rating 与数据库 rating 不一致：

- 默认以数据库为准
- 可在“重新导入元数据”模式中支持反向同步

---

## 8. 预览与浏览设计

### 8.1 核心原则

用户在照片墙 / 网格浏览 / 时间线中，应看到的是“逻辑照片”，而不是“物理文件列表”。

### 8.2 展示逻辑

默认展示 `logical_asset.hero_file_id` 对应的图片：

- 优先 JPG
- 若无 JPG，则使用 RAW 解码生成预览

### 8.3 详情页显示内容

对于每个逻辑照片，详情页中可以展示：

- 主预览图
- 评分、标签、人物
- 关联物理文件列表
  - RAW 文件路径
  - JPG 文件路径
  - sidecar 文件路径
- EXIF 信息
- AI 分析结果

### 8.4 性能要求

大图库浏览必须依赖预生成缩略图与分页加载，不能实时全量解码 RAW。

---

## 9. 人脸识别与人物管理设计

### 9.1 目标

实现以下能力：

1. 自动检测照片中的人脸
2. 为每张脸提取 embedding
3. 对 embedding 聚类，生成候选人物簇
4. 支持人工命名与合并
5. 后续新照片自动归类

### 9.2 计算位置

所有重计算任务在 Ubuntu 4090 上完成，不在群晖 NAS 上执行。

### 9.3 推荐流程

#### 第一步：检测人脸
输入照片预览图或原始 JPG
输出人脸框（bbox）

#### 第二步：提取 embedding
对每张检测到的人脸生成高维特征向量

#### 第三步：聚类
将 embedding 聚类，形成若干 cluster

#### 第四步：人工确认
Web UI 中展示“未命名人物”
用户可：

- 命名人物
- 合并两个 cluster
- 拆分错误归类

#### 第五步：增量识别
后续新照片到来时：

- 只处理新资产
- embedding 与已有人物模板进行匹配
- 自动归类或标记为待确认

### 9.4 数据回传

AI 节点将以下内容写回数据库：

- faces 表
- logical_asset_people 表
- people 表（仅在人工命名后更新）

---

## 10. Ubuntu 4090 AI 节点设计

### 10.1 职责

Ubuntu 节点负责所有高性能任务：

- 新文件扫描
- EXIF 抽取
- 逻辑资产配对
- 缩略图生成
- RAW 预览图生成
- 人脸检测
- embedding 提取
- 聚类
- 相似照片分析（后续可扩展）

### 10.2 访问 NAS 的方式

推荐通过 SMB 或 NFS 将群晖目录挂载到 Ubuntu：

```bash
/mnt/photo_library
```

AI 节点直接读取群晖中的原始文件，而非复制整库到本地。

### 10.3 任务执行机制

建议采用后台队列：

- 扫描任务
- 缩略图任务
- metadata 写回任务
- 人脸识别任务
- 聚类任务

### 10.4 增量更新原则

必须支持增量更新，避免每次全库重跑：

- 基于文件修改时间
- 基于 checksum
- 基于数据库扫描状态

---

## 11. 技术栈建议

## 11.1 后端

推荐：

- Python 3.11+
- FastAPI
- SQLAlchemy
- PostgreSQL
- Redis
- Celery / RQ
- ExifTool
- rawpy / libraw
- Pillow
- OpenCV

### 11.2 前端

推荐：

- Next.js
- React
- TypeScript
- Tailwind CSS
- TanStack Query
- Zustand 或 Redux Toolkit

### 11.3 AI / 向量相关

推荐：

- PyTorch
- InsightFace / ArcFace
- RetinaFace 或等价人脸检测器
- pgvector 或 Qdrant
- HDBSCAN / DBSCAN

### 11.4 部署建议

#### 推荐部署模式

**模式 A：主服务放 Ubuntu，NAS 只做存储**

优点：
- 性能更强
- 便于接 AI 与数据库
- 维护更方便

**模式 B：轻量服务放群晖，AI 放 Ubuntu**

适合后期优化，但第一版不建议增加复杂度。

---

## 12. 模块拆分

### 12.1 资产扫描器（Asset Scanner）

功能：

- 扫描 NAS 目录
- 识别新增文件
- 提取 EXIF
- 建立 logical_asset / physical_file
- 执行 RAW + JPG 配对

### 12.2 缩略图与预览服务（Preview Service）

功能：

- 生成网格缩略图
- 生成详情预览图
- 为没有 JPG 的 RAW 动态生成预览

### 12.3 元数据服务（Metadata Service）

功能：

- 处理 rating / label / tag 写入
- 同步到 JPG metadata
- 同步到 RAW sidecar
- 导入外部 XMP 变化

### 12.4 人物识别服务（Face Service）

功能：

- 人脸检测
- embedding 提取
- 聚类
- 人脸预览裁剪
- 人物归类

### 12.5 搜索与筛选服务（Search Service）

功能：

- 按日期筛选
- 按评分筛选
- 按人物筛选
- 按相机 / 镜头筛选
- 后续可支持语义搜索

### 12.6 Web UI

主要页面：

- 登录页
- 照片网格页
- 照片详情页
- 人物页
- 单个人物相册页
- 任务监控页
- 系统设置页

---

## 13. API 草案

### 13.1 资产相关

- `GET /api/assets`
- `GET /api/assets/{id}`
- `PATCH /api/assets/{id}/rating`
- `PATCH /api/assets/{id}/flags`
- `PATCH /api/assets/{id}/label`

### 13.2 文件相关

- `GET /api/files/{id}`
- `GET /api/files/{id}/preview`
- `GET /api/files/{id}/metadata`

### 13.3 人物相关

- `GET /api/people`
- `POST /api/people`
- `PATCH /api/people/{id}`
- `POST /api/people/merge`
- `GET /api/people/{id}/assets`

### 13.4 后台任务相关

- `POST /api/jobs/scan`
- `POST /api/jobs/face-detect`
- `POST /api/jobs/recluster`
- `GET /api/jobs`
- `GET /api/jobs/{id}`

---

## 14. MVP 开发路线

### 14.1 V1 目标（第一阶段）

第一阶段只做最关键闭环：

1. 扫描群晖目录
2. 自动建立 RAW + JPG 逻辑照片
3. 网格浏览时不重复显示
4. 支持 rating
5. rating 可同步到两个文件的元数据层
6. 支持基本照片详情页

### 14.2 V2 目标（第二阶段）

1. 加入人物识别
2. 人物候选聚类
3. 人物命名
4. 按人物筛选照片
5. 基本任务监控界面

### 14.3 V3 目标（第三阶段）

1. Pick / Reject / Color Label
2. 相似照片聚类
3. 更高级检索
4. 手机端审片
5. 客户交付相册能力

---

## 15. 关键风险与注意事项

### 15.1 不要依赖群晖内部私有逻辑

不要把核心业务建立在 Synology Photos 内部数据库之上，否则：

- 升级风险高
- 可迁移性差
- 调试困难

### 15.2 不要直接修改 RAW 原文件

对于 RAW 元数据写入，优先使用 XMP sidecar。

### 15.3 必须做增量扫描

如果每次都全库扫描、全库重做人脸识别，性能将无法接受。

### 15.4 必须建立缓存体系

RAW 解码成本高，大图库浏览必须依赖缓存缩略图与分页。

### 15.5 UI 逻辑必须围绕 logical_asset

这是整个系统最关键的数据建模原则。

---

## 16. 推荐的首期目录结构

```text
filmultra/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── workers/
│   │   └── main.py
│   ├── alembic/
│   └── requirements.txt
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── package.json
├── worker/
│   ├── face/
│   ├── preview/
│   ├── metadata/
│   └── scanner/
├── docs/
│   └── architecture.md
└── docker-compose.yml
```

---

## 17. 推荐实施顺序

### Step 1
先完成文件扫描与逻辑照片建模：

- 扫目录
- 读取 EXIF
- 建立 `logical_assets`
- 建立 `physical_files`
- 前端网格页只展示逻辑照片

### Step 2
完成评分闭环：

- UI 打分
- DB 更新
- JPG metadata 写入
- RAW sidecar 写入

### Step 3
完成人物识别基础版：

- 人脸检测
- embedding 提取
- cluster 生成
- 人物页展示

### Step 4
补充人物管理和高级筛选。

---

## 18. 最终结论

本项目的正确方向不是去“修改群晖照片应用本身”，而是：

**在群晖文件存储之上，建立一层真正面向摄影师工作流的 DAM 系统。**

该系统的核心原则如下：

1. **逻辑照片优先**：RAW + JPG = 一个资产
2. **评分统一管理**：数据库为主，XMP / Exif 为辅
3. **预览不重复**：默认只展示 hero file
4. **AI 外置计算**：4090 Ubuntu 负责人脸识别与索引
5. **群晖负责存储**：不承担核心业务逻辑

如果后续进入正式开发阶段，下一份文档建议继续拆分为：

- 数据库 ER 图
- API 详细定义
- worker 任务流设计
- 前端页面原型说明
- Docker 部署方案

