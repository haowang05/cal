# CalDAV Sync -> Feishu Base

将 CalDAV 日历（腾讯 / 飞书）同步到飞书多维表（Base）。

## 功能说明

- 拉取 CalDAV 事件并生成 ICS 文件
- 合并输出 `public/all_calendars_latest.ics`
- Upsert 写入飞书多维表（同一事件不会重复新增）
- 支持 GitHub Actions 定时运行

## 字段与主键规则

当前脚本支持以下策略：

- 使用 `eventID` 作为主键（优先）
  - 值为稳定生成的 10 位字符串（基于 `source + uid + dtstart` 的哈希前 10 位）
  - 同一事件多次同步时保持一致，用于更新而不是重复新增
- 若表里没有 `eventID`，自动回退到 `event_key`（兼容旧结构）
- `标题` 字段只作为普通内容字段，不作为 key
- 表中新增其他无关列不会影响同步（脚本只写匹配到的字段）

支持自动识别的常见字段名（中英文）：

- `eventID` / `event_id` / `事件ID`
- `event_key` / `事件唯一键`
- `source` / `来源`
- `calendar_name` / `日历名称`
- `summary` / `标题`
- `description` / `描述`
- `location` / `地点`
- `start_time` / `开始时间`
- `end_time` / `结束时间`
- `uid` / `UID`
- `status` / `状态`
- `updated_at` / `更新时间`

## 本地运行

### 1) 安装依赖

```bash
pip install -r requirements.txt
```

### 2) 配置环境变量

复制模板：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

- 飞书 Base:
  - `APP_ID`
  - `APP_SECRET`
  - `APP_TOKEN`
  - `TABLE_ID`
- 至少一个 CalDAV 账号（腾讯或飞书）：
  - `TENCENT_*` 或 `FEISHU_*`
- 如果飞书 discover 失败（常见 400/404），请额外配置：
  - `FEISHU_CALENDAR_URL`（必须是可 `REPORT` 的具体日历路径，不是根域名）
- 如果腾讯 discover 失败或事件为 0，可配置：
  - `TENCENT_CALENDAR_URL`

### 3) 常用命令

```bash
# 查看已识别账号
python main.py --list

# 只拉取并落地 ICS
python main.py --sync-all

# 只同步某个类型
python main.py --sync-type tencent

# 只执行写入飞书 Base（会先拉取各账号事件）
python main.py --sync-feishu-base -v

# 全流程（GitHub Actions 同款：vdirsyncer 拉取 + 写入飞书 Base）
python main.py --workflow-vdir -v
```

## GitHub Actions 使用（重点：Secrets）

仓库内工作流文件：`.github/workflows/sync.yml`

当前触发时间：

- 工作日（周一至周五）
- 上海时间 `12:08` / `15:08` / `18:08`
- 对应 UTC cron: `8 4,7,10 * * 1-5`

### 推荐方式：只配一个 Secret（`SYNC_ENV`）

本项目工作流会把 `secrets.SYNC_ENV` 直接写入 `.env`，并使用 `vdirsyncer` 同步 CalDAV 数据，所以你只要配一个多行 Secret。

路径：GitHub 仓库 -> `Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

- Name: `SYNC_ENV`
- Value: 填写完整 `.env` 内容（多行）

可直接使用下面模板（按需删减账号）：

```dotenv
# 全局
ICS_FILE_NAME=latest
SKIP_HOLIDAY_CALENDAR=true
ENABLE_TENCENT_SYNC=false

# 飞书 Base
APP_ID=cli_xxx
APP_SECRET=xxx
APP_TOKEN=xxx
TABLE_ID=xxx

# 腾讯 CalDAV（可选，vdirsyncer 用）
TENCENT_ACCOUNT_NAME=腾讯会议日历
TENCENT_USERNAME=
TENCENT_PASSWORD=
TENCENT_URL=https://cal.meeting.tencent.com/caldav/{username}/calendar/
TENCENT_SYNC_DAYS_PAST=90
TENCENT_SYNC_DAYS_FUTURE=90

# 飞书 CalDAV（可选，vdirsyncer 用）
FEISHU_ACCOUNT_NAME=飞书日历
FEISHU_USERNAME=
FEISHU_PASSWORD=
FEISHU_URL=https://caldav.feishu.cn
FEISHU_CALENDAR_URL=
FEISHU_SYNC_DAYS_PAST=90
FEISHU_SYNC_DAYS_FUTURE=90

# 腾讯可选：指定固定可查询日历 URL
TENCENT_CALENDAR_URL=
```

说明：

- 默认只同步飞书源（`ENABLE_TENCENT_SYNC=false`）
- 如需恢复腾讯同步，改为 `ENABLE_TENCENT_SYNC=true`

### 手动触发

在 `Actions` 页面打开该 workflow，点击 `Run workflow` 可立即执行一次。

## 常见问题

- 写入报 `FieldNameNotFound`
  - 表字段名与脚本映射不一致。建议保留上述字段之一（中英文都可）。
- 时间显示 `1970-01-01`
  - 通常是源事件时间异常，脚本已对异常时间戳做拦截并跳过无效时间写入。
- 只想新增列但不参与同步
  - 可以直接在飞书表里新增，脚本不会写入未映射列，也不会受影响。
- 不再同步钉钉但想保留历史
  - 本项目不会执行删除逻辑；停用钉钉后，只是不再写入新的钉钉事件，历史数据会保留在飞书 Base 中。
