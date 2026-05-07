#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests


class FeishuBaseSync:
    def __init__(self, app_id: str, app_secret: str, app_token: str, table_id: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id
        self._tenant_access_token: Optional[str] = None
        self._token_expire_at = 0

    def _get_tenant_access_token(self) -> str:
        if self._tenant_access_token and time.time() < self._token_expire_at - 60:
            return self._tenant_access_token

        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=15,
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
        self._tenant_access_token = data["tenant_access_token"]
        self._token_expire_at = time.time() + int(data.get("expire", 7200))
        return self._tenant_access_token

    def _headers(self) -> Dict[str, str]:
        token = self._get_tenant_access_token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"}

    @staticmethod
    def _to_unix_ms(value: str) -> Optional[int]:
        if not value:
            return None
        raw = value
        if "T" not in raw:
            return None
        core = raw.rstrip("Z")
        fmt = "%Y%m%dT%H%M%S" if len(core) >= 15 else "%Y%m%dT%H%M"
        try:
            dt = datetime.strptime(core[: len(fmt.replace("%", "").replace("Y", "0000"))], fmt)
            return int(dt.timestamp() * 1000)
        except Exception:
            return None

    @staticmethod
    def _event_key(event: Dict[str, str]) -> str:
        seed = f"{event.get('source','')}|{event.get('uid','')}|{event.get('dtstart','')}"
        return hashlib.sha1(seed.encode("utf-8")).hexdigest()

    def _list_all_records(self) -> List[Dict]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        items = []
        page_token = None
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(url, headers=self._headers(), params=params, timeout=20)
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"查询记录失败: {data}")
            payload = data.get("data", {})
            items.extend(payload.get("items", []))
            if not payload.get("has_more"):
                break
            page_token = payload.get("page_token")
        return items

    def _build_existing_index(self) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for item in self._list_all_records():
            fields = item.get("fields", {})
            key = fields.get("event_key")
            if isinstance(key, list):
                key = key[0] if key else None
            if key:
                index[str(key)] = item["record_id"]
        return index

    def _build_fields(self, event: Dict[str, str]) -> Dict:
        start_ms = self._to_unix_ms(event.get("dtstart", ""))
        end_ms = self._to_unix_ms(event.get("dtend", ""))
        return {
            "event_key": self._event_key(event),
            "source": event.get("source", ""),
            "calendar_name": event.get("calendar_name", ""),
            "summary": event.get("summary", ""),
            "description": event.get("description", ""),
            "location": event.get("location", ""),
            "start_time": start_ms,
            "end_time": end_ms,
            "uid": event.get("uid", ""),
            "status": event.get("status", ""),
            "updated_at": int(time.time() * 1000),
        }

    def upsert_events(self, events: List[Dict[str, str]]) -> Dict[str, int]:
        existing = self._build_existing_index()
        create_count = 0
        update_count = 0
        create_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"

        for event in events:
            fields = self._build_fields(event)
            key = fields["event_key"]
            record_id = existing.get(key)
            if record_id:
                update_url = f"{create_url}/{record_id}"
                resp = requests.put(update_url, headers=self._headers(), json={"fields": fields}, timeout=20)
                data = resp.json()
                if data.get("code") == 0:
                    update_count += 1
            else:
                resp = requests.post(create_url, headers=self._headers(), json={"fields": fields}, timeout=20)
                data = resp.json()
                if data.get("code") == 0:
                    create_count += 1
        return {"created": create_count, "updated": update_count}
