#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List


def parse_ics_content(ics_data: str) -> Dict[str, str]:
    event_info: Dict[str, str] = {}
    for raw_line in ics_data.split("\n"):
        line = raw_line.strip()
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
