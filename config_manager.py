#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CalDAVAccount:
    account_type: str
    account_name: str
    username: str
    password: str
    url: str

    def get_formatted_url(self) -> str:
        return self.url.format(username=self.username)


class ConfigManager:
    def __init__(self, env_file: str = ".env"):
        self.env_file = env_file
        self.config = {}
        self.accounts: List[CalDAVAccount] = []
        self.load_config()

    def load_config(self):
        if os.path.exists(self.env_file):
            with open(self.env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        self.config[key.strip()] = value.strip()

        # 允许通过系统环境变量覆盖 .env，兼容 GitHub Actions secrets 场景
        for key, value in os.environ.items():
            if value is None:
                continue
            if key in self.config or key.startswith(("APP_", "TABLE_", "DINGTALK_", "TENCENT_", "FEISHU_", "ICS_")):
                self.config[key] = value

        if not self.config:
            raise FileNotFoundError(f"配置文件 {self.env_file} 不存在，且未检测到可用环境变量")

        self._parse_accounts()

    def _parse_accounts(self):
        account_types = ["DINGTALK", "TENCENT", "FEISHU"]

        for account_type in account_types:
            account_name = self.config.get(f"{account_type}_ACCOUNT_NAME")
            username = self.config.get(f"{account_type}_USERNAME") or self.config.get(f"{account_type}_CALDAV_USERNAME")
            password = self.config.get(f"{account_type}_PASSWORD") or self.config.get(f"{account_type}_CALDAV_PASSWORD")
            url = self.config.get(f"{account_type}_URL") or self.config.get(f"{account_type}_CALDAV_URL")

            if all([account_name, username, password, url]):
                self.accounts.append(
                    CalDAVAccount(
                        account_type=account_type.lower(),
                        account_name=account_name,
                        username=username,
                        password=password,
                        url=url,
                    )
                )

    def get_accounts(self) -> List[CalDAVAccount]:
        return self.accounts

    def get_account_by_type(self, account_type: str) -> Optional[CalDAVAccount]:
        for account in self.accounts:
            if account.account_type == account_type.lower():
                return account
        return None

    def get_account_by_name(self, account_name: str) -> Optional[CalDAVAccount]:
        for account in self.accounts:
            if account.account_name == account_name:
                return account
        return None

    def get_global_config(self, key: str, default=None):
        return self.config.get(key, default)

    def list_accounts(self):
        print("=== 已配置的 CalDAV 账号 ===")
        if not self.accounts:
            print("未找到任何配置的账号")
            return

        for i, account in enumerate(self.accounts, 1):
            print(f"{i}. {account.account_name}")
            print(f" 类型: {account.account_type.upper()}")
            print(f" 用户名: {account.username}")
            print(f" URL: {account.get_formatted_url()}")
            print()
