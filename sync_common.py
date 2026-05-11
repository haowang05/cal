#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List

import requests


def parse_ics_content(ics_data: str) -> Dict[str, str]:
    event_info: Dict[str, str] = {}

    # 先做 ICS unfold：以空格/Tab 开头的行是上一行的续行
    unfolded_lines = []
    for raw in ics_data.splitlines():
        if (raw.startswith(" ") or raw.startswith("\t")) and unfolded_lines:
            unfolded_lines[-1] += raw[1:]
        else:
            unfolded_lines.append(raw)

    in_vevent = False
    for raw_line in unfolded_lines:
        line = raw_line.strip()
        if line == "BEGIN:VEVENT":
            in_vevent = True
            continue
        if line == "END:VEVENT":
            break
        if not in_vevent:
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key == "SUMMARY":
            event_info["summary"] = value
        elif key.startswith("DTSTART"):
            event_info["dtstart"] = value
            event_info["dtstart_key"] = key
        elif key.startswith("DTEND"):
            event_info["dtend"] = value
            event_info["dtend_key"] = key
        elif key == "LOCATION":
            event_info["location"] = value
        elif key == "DESCRIPTION":
            event_info["description"] = value
        elif key == "UID":
            event_info["uid"] = value
        elif key == "STATUS":
            event_info["status"] = value
    return event_info


def parse_event_xml(xml_data: str) -> List[str]:
    root = ET.fromstring(xml_data)
    namespaces = {"D": "DAV:", "C": "urn:ietf:params:xml:ns:caldav"}
    result: List[str] = []
    for response_elem in root.findall("D:response", namespaces):
        calendar_data_elem = response_elem.find(".//C:calendar-data", namespaces)
        if calendar_data_elem is not None and calendar_data_elem.text:
            result.append(calendar_data_elem.text.strip())
    return result


def save_ics(output_root: str, calendar_name: str, index: int, summary: str, ics_data: str) -> str:
    output_dir = os.path.join(output_root, calendar_name)
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_summary = "".join(c for c in summary if c.isalnum() or c in ("-", "_"))[:50] or "event"
    filename = f"{timestamp}_{index}_{safe_summary}.ics"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(ics_data)
    return filepath


def caldav_request_with_retry(
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff_seconds: float = 1.5,
    timeout: int = 30,
    **kwargs,
):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return requests.request(method, url, timeout=timeout, **kwargs)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            if attempt == retries:
                raise
            sleep_for = backoff_seconds * (2 ** (attempt - 1))
            print(f"[WARN] {method} {url} 第 {attempt}/{retries} 次请求失败: {exc}; {sleep_for:.1f}s 后重试")
            time.sleep(sleep_for)
    if last_exc:
        raise last_exc
