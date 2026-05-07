#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import os
import re
import shutil
import time
from datetime import datetime
from typing import Dict, List


class ICSMerger:
    def __init__(self, temp_dir: str = "temp", public_dir: str = "public"):
        self.temp_dir = temp_dir
        self.public_dir = public_dir
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.public_dir, exist_ok=True)

    def parse_ics_file(self, filepath: str) -> Dict:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return {
                "vevents": re.findall(r"BEGIN:VEVENT.*?END:VEVENT", content, re.DOTALL),
                "vtimezones": re.findall(r"BEGIN:VTIMEZONE.*?END:VTIMEZONE", content, re.DOTALL),
                "filepath": filepath,
            }
        except Exception as e:
            print(f"解析ICS文件失败 {filepath}: {e}")
            return {"vevents": [], "vtimezones": [], "filepath": filepath}

    def collect_ics_files_by_type(self, account_type: str) -> List[str]:
        patterns = {
            "dingtalk": "dingtalk_events_*/*/*.ics",
            "tencent": "tencent_events_*/*/*.ics",
            "feishu": "feishu_events_*/*/*.ics",
        }
        pattern = patterns.get(account_type.lower())
        if not pattern:
            print(f"不支持的账号类型: {account_type}")
            return []
        files = glob.glob(pattern)
        print(f"找到 {len(files)} 个 {account_type} ICS 文件")
        return files

    def collect_all_ics_files(self) -> List[str]:
        dingtalk = glob.glob("dingtalk_events_*/*/*.ics")
        tencent = glob.glob("tencent_events_*/*/*.ics")
        feishu = glob.glob("feishu_events_*/*/*.ics")
        all_files = dingtalk + tencent + feishu
        print(f"总共找到 {len(all_files)} 个 ICS 文件")
        return all_files

    def generate_merged_ics(self, vtimezones: List[str], vevents: List[str], calendar_name: str) -> str:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//CalDAV Sync Tool//CalDAV Sync Tool v3//CN",
            f"X-WR-CALNAME:{calendar_name}",
            "X-WR-CALDESC:由 CalDAV 同步工具合并生成",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]
        lines.extend(vtimezones)
        lines.extend(vevents)
        lines.append("END:VCALENDAR")
        return "\n".join(lines)

    def merge_ics_files(self, ics_files: List[str], output_filename: str, calendar_name: str = "合并日历") -> str:
        if not ics_files:
            return ""
        all_vevents = []
        all_vtimezones = set()
        for path in ics_files:
            parsed = self.parse_ics_file(path)
            all_vevents.extend(parsed["vevents"])
            all_vtimezones.update(parsed["vtimezones"])

        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(self.generate_merged_ics(list(all_vtimezones), all_vevents, calendar_name))
        print(f"✅ 合并完成: {output_filename}")
        return output_filename

    def cleanup_public_files(self, pattern: str):
        for path in glob.glob(os.path.join(self.public_dir, pattern)):
            try:
                os.remove(path)
            except Exception as e:
                print(f"删除失败 {path}: {e}")

    def merge_by_account_type(self, account_type: str, custom_filename: str = None) -> str:
        files = self.collect_ics_files_by_type(account_type)
        if not files:
            return ""
        self.cleanup_public_files(f"{account_type}_*.ics")
        name = custom_filename or datetime.now().strftime("%Y%m%d_%H%M%S")
        output = os.path.join(self.public_dir, f"{account_type}_{name}.ics")
        return self.merge_ics_files(files, output, f"{account_type.upper()} 合并日历")

    def merge_all_accounts(self, custom_filename: str = None) -> str:
        files = self.collect_all_ics_files()
        if not files:
            return ""
        self.cleanup_public_files("all_calendars_*.ics")
        name = custom_filename or datetime.now().strftime("%Y%m%d_%H%M%S")
        output = os.path.join(self.public_dir, f"all_calendars_{name}.ics")
        return self.merge_ics_files(files, output, "所有日历合并")

    def get_temp_xml_path(self, service: str, username: str, file_type: str) -> str:
        return os.path.join(self.temp_dir, f"{service}_{file_type}_{username}.xml")

    def cleanup_temp_files(self, older_than_days: int = 7):
        cutoff = older_than_days * 24 * 3600
        now = time.time()
        for path in glob.glob(os.path.join(self.temp_dir, "*.xml")):
            if now - os.path.getmtime(path) > cutoff:
                try:
                    os.remove(path)
                except Exception:
                    pass

        for path in glob.glob("dingtalk_events_*") + glob.glob("tencent_events_*") + glob.glob("feishu_events_*"):
            if os.path.isdir(path) and now - os.path.getmtime(path) > cutoff:
                try:
                    shutil.rmtree(path)
                except Exception:
                    pass
