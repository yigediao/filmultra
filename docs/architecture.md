# FilmUltra V1 架构说明

## 当前实现范围

本版实现对应 `photo_dam_dev_spec.md` 中的 V1 首期闭环：

- 扫描照片目录
- 按目录 + basename 归并 RAW / JPG 为一个逻辑照片
- 只展示逻辑照片，不重复展示物理文件
- 支持逻辑照片评分
- 评分同步到元数据层
- 提供照片详情页查看关联物理文件

## 模块划分

### Backend

`backend/app/main.py`

- FastAPI 入口
- 自动建表
- 注册资产、文件、任务 API

`backend/app/services/scanner.py`

- 扫描指定目录
- 识别 JPG / RAW
- 生成 `logical_assets` 与 `physical_files`
- 优先把 JPG 选为 `hero_file`

`backend/app/services/metadata.py`

- 评分写入数据库后同步元数据
- JPG 在检测到 `exiftool` 时直接写回文件
- RAW 默认写标准 `.xmp` sidecar
- 若 JPG 无 `exiftool`，退化为写 `*.jpg.xmp`

`backend/app/services/preview.py`

- JPG 生成缓存预览图
- RAW 优先提取内嵌缩略图，失败时退回 `rawpy` 解码
- 预览缓存按文件路径 + mtime + size 自动失效

`backend/app/services/faces.py`

- 基于 OpenCV Zoo 的 YuNet + SFace 做人脸检测和 embedding 提取
- 在 1600px 预览图上做检测，避免直接扫原图
- 先自动聚类，再把未命名 cluster 手工升级为 person
- 已命名人物会参与后续自动归类
- 支持手工把单张错脸移出人物、改归到其他人物，并在重聚类时保留人工修正

### Frontend

`frontend/app/page.tsx`

- 逻辑照片网格页
- 空库提示扫描入口

`frontend/app/assets/[id]/page.tsx`

- 照片详情页
- 查看 hero 预览、评分、物理文件列表

`frontend/app/people/page.tsx`

- 人物识别任务入口
- 已命名人物列表
- 未命名 cluster 命名入口

`frontend/app/people/[id]/page.tsx`

- 单个人物详情页
- 人脸样本与关联资产
- 人物合并与逐脸纠错入口

## 当前取舍

- 数据库默认走 SQLite，方便先本地起通；容器编排保留 PostgreSQL
- 扫描器目前不处理“已删除文件”回收
- RAW 预览已接入 `rawpy`，首次访问会生成缓存
- 人脸识别任务当前同步执行，后续建议迁移到 Redis + worker
- 人脸聚类目前采用余弦相似度阈值 + 运行中质心更新，属于 MVP 方案

## 下一步建议

1. 接入 Alembic，固定数据库迁移
2. 为扫描器补增量扫描与删除检测
3. 将 metadata sync / preview / face jobs 拆到独立 worker
4. 为人物页补“合并人物”和“拆分 cluster”界面
5. 加入更强的人脸模型与增量识别链路
