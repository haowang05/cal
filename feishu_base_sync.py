#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import re
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

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
    def _sanitize_epoch_ms(value: Optional[int]) -> Optional[int]:
        if value is None:
            return None
        # 飞书显示 1970 通常意味着写入了 0 或异常小时间戳，这里直接拦截
        if value < 946684800000:  # 2000-01-01 00:00:00 UTC
            return None
        return value

    @staticmethod
    def _to_unix_ms(value: str, key: str = "") -> Optional[int]:
        if not value:
            return None
        raw = value.strip().replace("\r", "").strip("\"")
        key = (key or "").strip()

        tz_name = None
        tz_match = re.search(r"TZID=([^;:]+)", key)
        if tz_match:
            tz_name = tz_match.group(1)

        explicit_offset = None
        offset_match = re.search(r"([+-]\d{4})$", raw)
        if offset_match:
            explicit_offset = offset_match.group(1)

        try:
            # 支持 epoch 秒/毫秒
            if raw.isdigit():
                ts = int(raw)
                if ts > 10_000_000_000:  # ms
                    return FeishuBaseSync._sanitize_epoch_ms(ts)
                if ts > 1_000_000_000:  # s
                    return FeishuBaseSync._sanitize_epoch_ms(ts * 1000)
            if raw.endswith("Z"):
                dt = datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                return FeishuBaseSync._sanitize_epoch_ms(int(dt.timestamp() * 1000))
            if explicit_offset:
                dt = datetime.strptime(raw, "%Y%m%dT%H%M%S%z")
                return FeishuBaseSync._sanitize_epoch_ms(int(dt.timestamp() * 1000))
            # 支持 ISO-8601（例如 2026-05-08T09:00:00+08:00）
            if "-" in raw and "T" in raw:
                iso = raw.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=ZoneInfo(tz_name or "Asia/Shanghai"))
                return FeishuBaseSync._sanitize_epoch_ms(int(dt.timestamp() * 1000))
            if "T" in raw:
                if len(raw) == 15:
                    dt = datetime.strptime(raw, "%Y%m%dT%H%M%S")
                elif len(raw) == 13:
                    dt = datetime.strptime(raw, "%Y%m%dT%H%M")
                else:
                    return None
                dt = dt.replace(tzinfo=ZoneInfo(tz_name or "Asia/Shanghai"))
                return FeishuBaseSync._sanitize_epoch_ms(int(dt.timestamp() * 1000))
            if len(raw) == 8:
                dt = datetime.strptime(raw, "%Y%m%d")
                dt = dt.replace(tzinfo=ZoneInfo(tz_name or "Asia/Shanghai"))
                return FeishuBaseSync._sanitize_epoch_ms(int(dt.timestamp() * 1000))
        except Exception:
            pass

        # 兜底：从任意字符串中提取 YYYYMMDD + 可选 HHMMSS
        m = re.search(r"(\d{8})(?:T(\d{4,6}))?", raw)
        if not m:
            return None
        day = m.group(1)
        t = m.group(2)
        try:
            if not t:
                dt = datetime.strptime(day, "%Y%m%d")
            elif len(t) == 4:
                dt = datetime.strptime(f"{day}T{t}", "%Y%m%dT%H%M")
            elif len(t) == 6:
                dt = datetime.strptime(f"{day}T{t}", "%Y%m%dT%H%M%S")
            else:
                return None
            dt = dt.replace(tzinfo=ZoneInfo(tz_name or "Asia/Shanghai"))
            return FeishuBaseSync._sanitize_epoch_ms(int(dt.timestamp() * 1000))
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
        event_key_field = self._field_name("event_key")
        if not event_key_field:
            return index
        for item in self._list_all_records():
            fields = item.get("fields", {})
            key = fields.get(event_key_field)
            if isinstance(key, list):
                key = key[0] if key else None
            if key:
                index[str(key)] = item["record_id"]
        return index

    def _list_table_fields(self) -> List[Dict]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields"
        items = []
        page_token = None
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            resp = requests.get(url, headers=self._headers(), params=params, timeout=20)
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"查询字段失败: {data}")
            payload = data.get("data", {})
            items.extend(payload.get("items", []))
            if not payload.get("has_more"):
                break
            page_token = payload.get("page_token")
        return items

    def _field_aliases(self) -> Dict[str, List[str]]:
        return {
            "event_key": ["event_key", "事件唯一键", "唯一键"],
            "source": ["source", "来源", "日历来源"],
            "calendar_name": ["calendar_name", "日历名", "日历名称"],
            "summary": ["summary", "标题", "主题"],
            "description": ["description", "描述", "详情"],
            "location": ["location", "地点", "位置"],
            "start_time": ["start_time", "开始时间", "开始"],
            "end_time": ["end_time", "结束时间", "结束"],
            "uid": ["uid", "UID", "事件UID"],
            "status": ["status", "状态"],
            "updated_at": ["updated_at", "更新时间", "同步时间"],
        }

    def _build_field_map(self) -> Dict[str, str]:
        table_fields = self._list_table_fields()
        existing_names = {str(item.get("field_name", "")).strip() for item in table_fields if item.get("field_name")}
        mapping: Dict[str, str] = {}
        for canonical, aliases in self._field_aliases().items():
            for name in aliases:
                if name in existing_names:
                    mapping[canonical] = name
                    break
        return mapping

    def _field_name(self, canonical_name: str) -> Optional[str]:
        if not hasattr(self, "_resolved_field_map"):
            self._resolved_field_map = self._build_field_map()
        return self._resolved_field_map.get(canonical_name)

    def _build_fields(self, event: Dict[str, str]) -> Dict:
        start_ms = self._to_unix_ms(event.get("dtstart", ""), event.get("dtstart_key", ""))
        end_ms = self._to_unix_ms(event.get("dtend", ""), event.get("dtend_key", ""))
        canonical_values = {
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
        fields = {}
        for canonical, value in canonical_values.items():
            if canonical in ("start_time", "end_time") and value is None:
                continue
            actual = self._field_name(canonical)
            if actual:
                fields[actual] = value
        return fields

    def upsert_events(self, events: List[Dict[str, str]]) -> Dict[str, int]:
        existing = self._build_existing_index()
        create_count = 0
        update_count = 0
        failed_count = 0
        first_error = None
        missing_start_count = 0
        missing_start_samples = []
        create_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"

        for event in events:
            if event.get("dtstart") and self._to_unix_ms(event.get("dtstart", ""), event.get("dtstart_key", "")) is None:
                missing_start_count += 1
                if len(missing_start_samples) < 5:
                    sample = f"{event.get('dtstart_key','DTSTART')}:{event.get('dtstart','')}"
                    if sample not in missing_start_samples:
                        missing_start_samples.append(sample)
            fields = self._build_fields(event)
            key = self._event_key(event)
            if not fields:
                failed_count += 1
                if first_error is None:
                    first_error = "写入失败：目标多维表未匹配到任何可用字段"
                continue
            record_id = existing.get(key)
            if record_id:
                update_url = f"{create_url}/{record_id}"
                resp = requests.put(update_url, headers=self._headers(), json={"fields": fields}, timeout=20)
                data = resp.json()
                if data.get("code") == 0:
                    update_count += 1
                else:
                    failed_count += 1
                    if first_error is None:
                        first_error = f"更新失败 code={data.get('code')} msg={data.get('msg')} event_key={key}"
            else:
                resp = requests.post(create_url, headers=self._headers(), json={"fields": fields}, timeout=20)
                data = resp.json()
                if data.get("code") == 0:
                    create_count += 1
                else:
                    failed_count += 1
                    if first_error is None:
                        first_error = f"创建失败 code={data.get('code')} msg={data.get('msg')} event_key={key}"
        return {
            "created": create_count,
            "updated": update_count,
            "failed": failed_count,
            "first_error": first_error,
            "missing_start_count": missing_start_count,
            "missing_start_samples": missing_start_samples,
        }
