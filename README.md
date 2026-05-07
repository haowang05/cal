# CalDAV Sync -> Feishu Base

基于 `sync-caldav-v3` 的同步流程改造，保留原有 CalDAV 拉取与 ICS 落盘逻辑，并新增：

- 支持飞书 CalDAV 作为同步源（`FEISHU_*`）
- 将同步事件 Upsert 到飞书多维表（Base）
- GitHub Actions 每 2 小时自动执行一次（`.github/workflows/sync.yml`）

## 使用

1. 复制 `.env.example` 为 `.env` 并填写。
2. 安装依赖：`pip install -r requirements.txt`
3. 列配置账号：`python main.py --list`
4. 执行全流程：`python main.py --workflow`

## 关键命令

- `python main.py --sync-all`
- `python main.py --sync-type dingtalk|tencent|feishu`
- `python main.py --sync-feishu-base`
- `python main.py --workflow`
