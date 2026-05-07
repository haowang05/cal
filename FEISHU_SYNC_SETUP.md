# CalDAV -> 飞书多维表 同步配置单

请把以下内容补全后发我（敏感信息可打码后再私发完整值）。

## 1) 飞书开放平台应用信息（用于写入多维表）

- `APP_ID`:cli_a96cb03119f95bdb
- `APP_SECRET`:HkKwEFGxsXosu0lT0NWK7ekRYUDqbMW8

应用权限建议至少包含（名称可能随版本略有差异）：
- 多维表格读写相关权限（record/table/app 读写）
- 获取 tenant_access_token 所需基础权限

## 2) 目标多维表信息

- `APP_TOKEN`（你的 Base ID）: `JjCzbvTNoaYvDusyeVocvIHfnAO`
- `TABLE_ID`: `tblwqOBPV8O7CoUE`
- `VIEW_ID`（可选，仅用于校验或展示）: `vewg390Egs`

## 3) 表结构（字段映射）

请确认是否使用下面这套标准字段（推荐）：

- `event_key`（文本，唯一键，建议由 `source + uid + start` 组成）
- `source`（文本，如 dingtalk/tencent/feishu）
- `calendar_name`（文本）
- `summary`（文本）
- `description`（多行文本）
- `location`（文本）
- `start_time`（日期时间）
- `end_time`（日期时间）
- `uid`（文本）
- `status`（文本）
- `updated_at`（日期时间）
- `raw_ics_url`（文本，可选）

如你已有固定字段，请按“字段名 -> 类型 -> 说明”列出来：

```text
示例：
标题 -> 文本 -> 对应 summary
开始时间 -> 日期时间 -> 对应 start_time
...
```

## 4) 飞书 CalDAV 账号（作为同步源）

- `FEISHU_CALDAV_URL`:https://caldav.feishu.cn
- `FEISHU_CALDAV_USERNAME`:u_vpvp9493
- `FEISHU_CALDAV_PASSWORD`（或专用密码）:mK4Gsy2KjY

补充说明（如果有）：
- 是否需要特定路径（如个人主日历路径）
- 是否有公司网络 / IP 白名单限制

## 5) 钉钉 / 腾讯 CalDAV 账号（作为同步源）

如果你希望同时同步钉钉和腾讯，也请补全：

### 钉钉
- `DINGTALK_CALDAV_URL`:https://calendar.dingtalk.com/dav/{username}/
- `DINGTALK_CALDAV_USERNAME`:u_5k2tohbv
- `DINGTALK_CALDAV_PASSWORD`（或专用密码）:m9uyzgjh

### 腾讯会议
- `TENCENT_CALDAV_URL`:https://cal.meeting.tencent.com/caldav/{username}/calendar/
- `TENCENT_CALDAV_USERNAME`:Cal_2njutof6tc@cal.meeting.tencent.com
- `TENCENT_CALDAV_PASSWORD`（或专用密码）:I539w1MOsY

补充说明（如果有）：
- 是否某个源只同步特定日历
- 哪个源优先级更高（同一事件冲突时）

## 6) 同步策略（业务规则）

- 同步时间窗口（如：过去 30 天 + 未来 180 天）:过去14天+未来90天
- 删除策略（源端删除后，目标是否删除/标记取消）:源端删除标记取消
- 冲突策略（同一事件更新时，以哪个源为准）:钉钉大于飞书大于腾讯
- 时区（默认 `Asia/Shanghai` 是否可用）:可用
- 是否保留本地 `ics` 文件输出（是/否）:不用保存 ics

---

# GitHub Actions（每 2 小时执行）配置

下面是工作流核心片段（我后续会按你的仓库结构放到 `.github/workflows/sync.yml`）：

```yaml
name: Sync CalDAV to Feishu Base

on:
  schedule:
    - cron: '0 */2 * * *' # every 2 hours (UTC)
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run sync
        env:
          APP_ID: ${{ secrets.APP_ID }}
          APP_SECRET: ${{ secrets.APP_SECRET }}
          APP_TOKEN: ${{ secrets.APP_TOKEN }}
          TABLE_ID: ${{ secrets.TABLE_ID }}
          DINGTALK_CALDAV_URL: ${{ secrets.DINGTALK_CALDAV_URL }}
          DINGTALK_CALDAV_USERNAME: ${{ secrets.DINGTALK_CALDAV_USERNAME }}
          DINGTALK_CALDAV_PASSWORD: ${{ secrets.DINGTALK_CALDAV_PASSWORD }}
          TENCENT_CALDAV_URL: ${{ secrets.TENCENT_CALDAV_URL }}
          TENCENT_CALDAV_USERNAME: ${{ secrets.TENCENT_CALDAV_USERNAME }}
          TENCENT_CALDAV_PASSWORD: ${{ secrets.TENCENT_CALDAV_PASSWORD }}
          FEISHU_CALDAV_URL: ${{ secrets.FEISHU_CALDAV_URL }}
          FEISHU_CALDAV_USERNAME: ${{ secrets.FEISHU_CALDAV_USERNAME }}
          FEISHU_CALDAV_PASSWORD: ${{ secrets.FEISHU_CALDAV_PASSWORD }}
        run: |
          python main.py --workflow
```

注意：
- GitHub Actions 的 `cron` 使用 UTC；`0 */2 * * *` 表示每 2 小时整点执行一次。
- 所有敏感信息放到仓库 `Settings -> Secrets and variables -> Actions`，不要写进代码仓库。
