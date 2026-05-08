#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
from typing import List

from config_manager import CalDAVAccount, ConfigManager
from feishu_base_sync import FeishuBaseSync
from ics_merger import ICSMerger
from sync_dingtalk import DingTalkCalDAVSync
from sync_feishu import FeishuCalDAVSync
from sync_tencent import TencentCalDAVSync


class CalDAVSyncManager:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.sync_handlers = {
            "dingtalk": DingTalkCalDAVSync,
            "tencent": TencentCalDAVSync,
            "feishu": FeishuCalDAVSync,
        }
        self.merger = ICSMerger()

    def list_accounts(self):
        self.config_manager.list_accounts()

    def _handler_config(self, account_type: str) -> dict:
        cfg = {}
        if account_type == "dingtalk":
            cfg["DINGTALK_SYNC_DAYS_PAST"] = self.config_manager.get_global_config("DINGTALK_SYNC_DAYS_PAST")
            cfg["DINGTALK_SYNC_DAYS_FUTURE"] = self.config_manager.get_global_config("DINGTALK_SYNC_DAYS_FUTURE")
        elif account_type == "tencent":
            cfg["TENCENT_SYNC_DAYS_PAST"] = self.config_manager.get_global_config("TENCENT_SYNC_DAYS_PAST")
            cfg["TENCENT_SYNC_DAYS_FUTURE"] = self.config_manager.get_global_config("TENCENT_SYNC_DAYS_FUTURE")
        elif account_type == "feishu":
            cfg["FEISHU_SYNC_DAYS_PAST"] = self.config_manager.get_global_config("FEISHU_SYNC_DAYS_PAST")
            cfg["FEISHU_SYNC_DAYS_FUTURE"] = self.config_manager.get_global_config("FEISHU_SYNC_DAYS_FUTURE")
        return cfg

    def sync_account(self, account: CalDAVAccount):
        handler_class = self.sync_handlers.get(account.account_type)
        if not handler_class:
            return False, []
        handler = handler_class(account, config=self._handler_config(account.account_type))
        success = handler.sync()
        return success, getattr(handler, "collected_events", [])

    def sync_all_accounts(self):
        accounts = self.config_manager.get_accounts()
        success_count = 0
        all_events: List[dict] = []
        for account in accounts:
            success, events = self.sync_account(account)
            if success:
                success_count += 1
            all_events.extend(events)
        return success_count, all_events

    def sync_by_type(self, account_type: str):
        account = self.config_manager.get_account_by_type(account_type)
        if not account:
            return False, []
        return self.sync_account(account)

    def sync_by_name(self, account_name: str):
        account = self.config_manager.get_account_by_name(account_name)
        if not account:
            return False, []
        return self.sync_account(account)

    def merge_by_type(self, account_type: str) -> bool:
        custom_filename = self.config_manager.get_global_config("ICS_FILE_NAME")
        return bool(self.merger.merge_by_account_type(account_type, custom_filename))

    def merge_all(self) -> bool:
        custom_filename = self.config_manager.get_global_config("ICS_FILE_NAME")
        return bool(self.merger.merge_all_accounts(custom_filename))

    def cleanup_temp_files(self, days: int = 7) -> bool:
        self.merger.cleanup_temp_files(days)
        return True

    def sync_to_feishu_base(self, events: List[dict]) -> bool:
        app_id = self.config_manager.get_global_config("APP_ID")
        app_secret = self.config_manager.get_global_config("APP_SECRET")
        app_token = self.config_manager.get_global_config("APP_TOKEN")
        table_id = self.config_manager.get_global_config("TABLE_ID")
        if not all([app_id, app_secret, app_token, table_id]):
            print("未配置飞书 Base 所需 APP_ID/APP_SECRET/APP_TOKEN/TABLE_ID，跳过写入。")
            return False
        skip_holiday = str(self.config_manager.get_global_config("SKIP_HOLIDAY_CALENDAR", "true")).lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        def should_skip(event: dict) -> bool:
            if not skip_holiday:
                return False
            name = str(event.get("calendar_name", "")).strip()
            return ("国务院假期及传统节日" in name) or ("节假日" in name and "国务院" in name)

        filtered_events = [e for e in events if not should_skip(e)]
        skipped = len(events) - len(filtered_events)
        print(f"写入前事件统计: 原始 {len(events)}，过滤后 {len(filtered_events)}")
        if skipped:
            print(f"已过滤 {skipped} 条节假日日历事件（2026国务院假期及传统节日）")
        if not filtered_events:
            print("过滤后无可写入事件，请检查过滤规则或同步时间窗口。")
        client = FeishuBaseSync(app_id, app_secret, app_token, table_id)
        result = client.upsert_events(filtered_events)
        print(
            f"飞书 Base 同步完成: 新增 {result['created']}，更新 {result['updated']}，失败 {result.get('failed', 0)}"
        )
        if result.get("missing_start_count"):
            print(f"开始时间解析失败 {result['missing_start_count']} 条（未写入 start_time，避免出现 1970）")
            samples = result.get("missing_start_samples") or []
            if samples:
                print("开始时间失败样本:")
                for s in samples:
                    print(f"- {s}")
        if result.get("first_error"):
            print(f"飞书 Base 首条失败原因: {result['first_error']}")
        return True

    def run_full_workflow(self, cleanup_days: int = 7) -> bool:
        success_count, events = self.sync_all_accounts()
        if success_count == 0:
            return False
        for account_type in {a.account_type for a in self.config_manager.get_accounts()}:
            self.merge_by_type(account_type)
        self.merge_all()
        self.sync_to_feishu_base(events)
        self.cleanup_temp_files(cleanup_days)
        return True


def create_parser():
    parser = argparse.ArgumentParser(description="CalDAV 同步工具")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--sync-all", action="store_true")
    group.add_argument("--sync-type", metavar="TYPE")
    group.add_argument("--sync-name", metavar="NAME")
    group.add_argument("--merge-type", metavar="TYPE")
    group.add_argument("--merge-all", action="store_true")
    group.add_argument("--cleanup", type=int, nargs="?", const=7, metavar="DAYS")
    group.add_argument("--workflow", type=int, nargs="?", const=7, metavar="DAYS")
    group.add_argument("--sync-feishu-base", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    manager = CalDAVSyncManager()
    try:
        if args.list:
            manager.list_accounts()
            sys.exit(0)
        if args.sync_all:
            success_count, _ = manager.sync_all_accounts()
            sys.exit(0 if success_count > 0 else 1)
        if args.sync_type:
            ok, _ = manager.sync_by_type(args.sync_type)
            sys.exit(0 if ok else 1)
        if args.sync_name:
            ok, _ = manager.sync_by_name(args.sync_name)
            sys.exit(0 if ok else 1)
        if args.merge_type:
            sys.exit(0 if manager.merge_by_type(args.merge_type) else 1)
        if args.merge_all:
            sys.exit(0 if manager.merge_all() else 1)
        if args.cleanup is not None:
            sys.exit(0 if manager.cleanup_temp_files(args.cleanup) else 1)
        if args.sync_feishu_base:
            _, events = manager.sync_all_accounts()
            sys.exit(0 if manager.sync_to_feishu_base(events) else 1)
        if args.workflow is not None:
            sys.exit(0 if manager.run_full_workflow(args.workflow) else 1)
    except Exception as e:
        print(f"程序执行出错: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
