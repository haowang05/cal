#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth

from config_manager import CalDAVAccount
from ics_merger import ICSMerger
from sync_common import caldav_request_with_retry, parse_event_xml, parse_ics_content, save_ics


class TencentCalDAVSync:
    def __init__(self, account: CalDAVAccount, config: dict = None):
        self.account = account
        self.base_url = account.get_formatted_url()
        self.username = account.username
        self.password = account.password
        self.output_dir = f"tencent_events_{self.username}"
        self.merger = ICSMerger()
        self.collected_events = []
        config = config or {}
        self.sync_days_past = int(config.get("TENCENT_SYNC_DAYS_PAST") or 90)
        self.sync_days_future = int(config.get("TENCENT_SYNC_DAYS_FUTURE") or 90)

    def discover_collections(self):
        body = """<?xml version="1.0" encoding="UTF-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:displayname/>
    <D:resourcetype/>
  </D:prop>
</D:propfind>"""
        response = caldav_request_with_retry(
            "PROPFIND",
            self.base_url,
            auth=HTTPBasicAuth(self.username, self.password),
            headers={"Content-Type": "application/xml; charset=UTF-8", "Depth": "1"},
            data=body,
            timeout=30,
        )
        if response.status_code != 207:
            return []
        temp_file = self.merger.get_temp_xml_path("tencent", self.username, "collections")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(response.text)
        return self.parse_collections(response.text)

    def parse_collections(self, xml_data):
        collections = []
        root = ET.fromstring(xml_data)
        ns = {"D": "DAV:", "C": "urn:ietf:params:xml:ns:caldav"}
        for response_elem in root.findall("D:response", ns):
            href_elem = response_elem.find("D:href", ns)
            if href_elem is None:
                continue
            resourcetype = response_elem.find(".//D:resourcetype", ns)
            if resourcetype is None or resourcetype.find("C:calendar", ns) is None:
                continue
            displayname_elem = response_elem.find(".//D:displayname", ns)
            displayname = displayname_elem.text if displayname_elem is not None else "未知日历"
            href = href_elem.text
            full_href = f"https://cal.meeting.tencent.com{href}" if href.startswith("/") else href
            collections.append({"name": displayname, "href": full_href})
        return collections

    def get_events_by_time_range(self, collection_href, display_name):
        now = datetime.utcnow()
        start = (now - timedelta(days=self.sync_days_past)).strftime("%Y%m%dT%H%M%SZ")
        end = (now + timedelta(days=self.sync_days_future)).strftime("%Y%m%dT%H%M%SZ")
        body = f"""<?xml version="1.0" encoding="UTF-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start}" end="{end}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""
        response = caldav_request_with_retry(
            "REPORT",
            collection_href,
            auth=HTTPBasicAuth(self.username, self.password),
            headers={"Content-Type": "application/xml; charset=UTF-8", "Depth": "1"},
            data=body,
            timeout=45,
        )
        if response.status_code != 207:
            return []
        safe_name = "".join(c for c in display_name if c.isalnum() or c in ("-", "_"))
        temp_file = self.merger.get_temp_xml_path("tencent", self.username, f"events_{safe_name}")
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(response.text)
        return self.parse_and_save_events(response.text, display_name)

    def parse_and_save_events(self, xml_data, display_name):
        events = []
        for i, ics_data in enumerate(parse_event_xml(xml_data), 1):
            event_info = parse_ics_content(ics_data)
            save_ics(self.output_dir, display_name, i, event_info.get("summary", "event"), ics_data)
            event_info["source"] = "tencent"
            event_info["calendar_name"] = display_name
            events.append(event_info)
        return events

    def sync(self):
        collections = self.discover_collections()
        if not collections:
            return False
        total_events = []
        for collection in collections:
            total_events.extend(self.get_events_by_time_range(collection["href"], collection["name"]))
        self.collected_events = total_events
        return len(total_events) > 0
