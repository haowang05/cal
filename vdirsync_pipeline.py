#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import tempfile
from typing import Dict, List, Tuple

from sync_common import parse_ics_content


def _build_source_profiles(config: Dict[str, str]) -> List[Dict[str, str]]:
    profiles = []
    tencent_enabled = str(config.get("ENABLE_TENCENT_SYNC", "false")).lower() in ("1", "true", "yes", "on")
    for source in ("tencent", "feishu"):
        if source == "tencent" and not tencent_enabled:
            continue
        p = source.upper()
        username = config.get(f"{p}_USERNAME") or config.get(f"{p}_CALDAV_USERNAME")
        password = config.get(f"{p}_PASSWORD") or config.get(f"{p}_CALDAV_PASSWORD")
        url = config.get(f"{p}_URL") or config.get(f"{p}_CALDAV_URL")
        if username and password and url:
            profiles.append({"source": source, "username": username, "password": password, "url": url})
    return profiles


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def run_vdirsync(config: Dict[str, str], workspace_root: str) -> Tuple[bool, str, List[str]]:
    profiles = _build_source_profiles(config)
    if not profiles:
        return False, "", []

    data_root = os.path.join(workspace_root, "vdir_data")
    os.makedirs(data_root, exist_ok=True)
    enabled_sources = []
    with tempfile.TemporaryDirectory(prefix="vdirsync_", dir=workspace_root) as tmpdir:
        status_path = os.path.join(tmpdir, "status")
        os.makedirs(status_path, exist_ok=True)
        config_path = os.path.join(tmpdir, "vdirsyncer.ini")
        lines = [
            "[general]",
            f'status_path = "{_escape(status_path)}"',
            "",
        ]

        for profile in profiles:
            source = profile["source"]
            enabled_sources.append(source)
            pair = f"{source}_pair"
            remote = f"{source}_remote"
            local = f"{source}_local"
            local_path = os.path.join(data_root, source)
            os.makedirs(local_path, exist_ok=True)

            lines.extend(
                [
                    f"[pair {pair}]",
                    f'a = "{remote}"',
                    f'b = "{local}"',
                    'collections = ["from a"]',
                    'conflict_resolution = "a wins"',
                    "",
                    f"[storage {remote}]",
                    'type = "caldav"',
                    f'url = "{_escape(profile["url"])}"',
                    f'username = "{_escape(profile["username"])}"',
                    f'password = "{_escape(profile["password"])}"',
                    "",
                    f"[storage {local}]",
                    'type = "filesystem"',
                    f'path = "{_escape(local_path)}"',
                    'fileext = ".ics"',
                    "",
                ]
            )

        with open(config_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"[vdirsyncer] 使用临时配置: {config_path}")

        for source in enabled_sources:
            pair = f"{source}_pair"
            print(f"[vdirsyncer] discover {pair}")
            subprocess.run(
                ["vdirsyncer", "-c", config_path, "discover", pair],
                check=False,
                input="y\n",
                text=True,
            )
            print(f"[vdirsyncer] sync {pair}")
            proc = subprocess.run(
                ["vdirsyncer", "-c", config_path, "sync", pair],
                check=False,
                input="y\n",
                text=True,
            )
            if proc.returncode != 0:
                print(f"[vdirsyncer] {pair} 同步失败，退出码 {proc.returncode}")

    return True, data_root, enabled_sources


def _extract_vevent_blocks(ics_text: str) -> List[str]:
    unfolded = []
    for line in ics_text.splitlines():
        if (line.startswith(" ") or line.startswith("\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)

    blocks = []
    in_event = False
    buff: List[str] = []
    for line in unfolded:
        if line.strip() == "BEGIN:VEVENT":
            in_event = True
            buff = [line]
            continue
        if in_event:
            buff.append(line)
            if line.strip() == "END:VEVENT":
                blocks.append("\n".join(buff))
                in_event = False
                buff = []
    return blocks


def collect_events_from_vdir(data_root: str, enabled_sources: List[str]) -> List[Dict[str, str]]:
    events: List[Dict[str, str]] = []
    for source in enabled_sources:
        source_root = os.path.join(data_root, source)
        source_count = 0
        file_count = 0
        empty_event_files = 0
        if not os.path.isdir(source_root):
            print(f"[vdirsyncer] 源目录不存在: {source_root}")
            continue
        for root, _, files in os.walk(source_root):
            for filename in files:
                if not filename.endswith(".ics"):
                    continue
                file_count += 1
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        text = f.read()
                except UnicodeDecodeError:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()

                blocks = _extract_vevent_blocks(text)
                calendar_name = os.path.basename(root) or source
                parsed_in_file = 0
                for block in blocks:
                    event = parse_ics_content(block)
                    if not event:
                        continue
                    event["source"] = source
                    event["calendar_name"] = calendar_name
                    events.append(event)
                    source_count += 1
                    parsed_in_file += 1
                if parsed_in_file == 0:
                    empty_event_files += 1
        print(f"[vdirsyncer] 源 {source} 读取 ICS 文件 {file_count} 个")
        if empty_event_files:
            print(f"[vdirsyncer] 源 {source} 有 {empty_event_files} 个 ICS 文件未解析出 VEVENT")
        print(f"[vdirsyncer] 源 {source} 收集事件 {source_count} 条")
    return events
