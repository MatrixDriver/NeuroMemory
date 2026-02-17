"""Temporal extraction service - pure Python rule engine for time parsing."""

from __future__ import annotations

import re
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class TemporalExtractor:
    """Extract timestamps from text using regex-based rules.

    Design principle: return None rather than guess wrong.
    """

    # ISO 8601 patterns
    _ISO_FULL = re.compile(
        r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)"
    )
    _ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")

    # English absolute: May 7, 2023 / 7 May 2023 / May 7 2023
    _EN_MONTH_MAP = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
        "oct": 10, "nov": 11, "dec": 12,
    }
    _EN_ABS_MDY = re.compile(
        r"(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|"
        r"oct|nov|dec)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})",
        re.IGNORECASE,
    )
    _EN_ABS_DMY = re.compile(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?"
        r"(january|february|march|april|may|june|july|august|september|"
        r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|"
        r"oct|nov|dec)\.?,?\s*(\d{4})",
        re.IGNORECASE,
    )

    # Chinese absolute: 2023年5月7日 or 5月7日
    _ZH_FULL = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
    _ZH_PARTIAL = re.compile(r"(\d{1,2})月(\d{1,2})日")

    # English relative
    _EN_REL_AGO = re.compile(
        r"(\d+)\s+(day|week|month|year)s?\s+ago", re.IGNORECASE
    )
    _EN_REL_LAST = re.compile(
        r"last\s+(week|month|year|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        re.IGNORECASE,
    )
    _EN_REL_WORDS = {
        "yesterday": lambda ref: ref - timedelta(days=1),
        "today": lambda ref: ref,
        "the day before yesterday": lambda ref: ref - timedelta(days=2),
    }

    # Chinese relative
    _ZH_REL_AGO = re.compile(r"(\d+)\s*(?:天|日)前")
    _ZH_REL_WEEK_AGO = re.compile(r"(\d+)\s*(?:周|个?星期)前")
    _ZH_REL_MONTH_AGO = re.compile(r"(\d+)\s*个?月前")
    _ZH_REL_YEAR_AGO = re.compile(r"(\d+)\s*年前")
    _ZH_REL_WORDS = {
        "昨天": lambda ref: ref - timedelta(days=1),
        "前天": lambda ref: ref - timedelta(days=2),
        "今天": lambda ref: ref,
        "大前天": lambda ref: ref - timedelta(days=3),
    }
    _ZH_REL_LAST_WEEK = re.compile(r"上(?:个?星期|周)")
    _ZH_REL_LAST_MONTH = re.compile(r"上个?月")
    _ZH_REL_LAST_YEAR = re.compile(r"去年")

    _WEEKDAY_MAP = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }

    def extract(self, text: str, reference_time: datetime | None = None) -> datetime | None:
        """Extract a timestamp from text.

        Args:
            text: Input text (can be a raw time expression or full sentence)
            reference_time: Reference time for relative expressions.
                           Uses UTC now if not provided.

        Returns:
            datetime with timezone or None if no time found.
        """
        if not text:
            return None

        ref = reference_time or datetime.now(timezone.utc)
        # Ensure ref is timezone-aware
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)

        # Try each pattern in priority order
        for extractor in [
            self._try_iso_full,
            self._try_iso_date,
            self._try_en_absolute,
            self._try_zh_full,
            self._try_zh_partial,
            self._try_en_relative,
            self._try_zh_relative,
        ]:
            result = extractor(text, ref)
            if result is not None:
                return result

        return None

    def _try_iso_full(self, text: str, ref: datetime) -> datetime | None:
        m = self._ISO_FULL.search(text)
        if m:
            try:
                dt = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
                return dt.replace(tzinfo=ref.tzinfo)
            except ValueError:
                return None
        return None

    def _try_iso_date(self, text: str, ref: datetime) -> datetime | None:
        m = self._ISO_DATE.search(text)
        if m:
            try:
                dt = datetime.fromisoformat(m.group(1))
                return dt.replace(tzinfo=ref.tzinfo)
            except ValueError:
                return None
        return None

    def _try_en_absolute(self, text: str, ref: datetime) -> datetime | None:
        # Try "May 7, 2023" pattern
        m = self._EN_ABS_MDY.search(text)
        if m:
            month_str = m.group(0).split()[0].rstrip('.').lower()
            month = self._EN_MONTH_MAP.get(month_str)
            if month:
                try:
                    day = int(m.group(1))
                    year = int(m.group(2))
                    return datetime(year, month, day, tzinfo=ref.tzinfo)
                except ValueError:
                    pass

        # Try "7 May 2023" pattern
        m = self._EN_ABS_DMY.search(text)
        if m:
            month = self._EN_MONTH_MAP.get(m.group(2).lower())
            if month:
                try:
                    day = int(m.group(1))
                    year = int(m.group(3))
                    return datetime(year, month, day, tzinfo=ref.tzinfo)
                except ValueError:
                    pass

        return None

    def _try_zh_full(self, text: str, ref: datetime) -> datetime | None:
        m = self._ZH_FULL.search(text)
        if m:
            try:
                return datetime(
                    int(m.group(1)), int(m.group(2)), int(m.group(3)),
                    tzinfo=ref.tzinfo,
                )
            except ValueError:
                return None
        return None

    def _try_zh_partial(self, text: str, ref: datetime) -> datetime | None:
        m = self._ZH_PARTIAL.search(text)
        if m:
            try:
                return datetime(
                    ref.year, int(m.group(1)), int(m.group(2)),
                    tzinfo=ref.tzinfo,
                )
            except ValueError:
                return None
        return None

    def _try_en_relative(self, text: str, ref: datetime) -> datetime | None:
        text_lower = text.lower().strip()

        # Check word-based relative
        for word, func in self._EN_REL_WORDS.items():
            if word in text_lower:
                return func(ref).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

        # X days/weeks/months/years ago
        m = self._EN_REL_AGO.search(text_lower)
        if m:
            n = int(m.group(1))
            unit = m.group(2).lower()
            return self._subtract_unit(ref, n, unit)

        # last week/month/year/monday...
        m = self._EN_REL_LAST.search(text_lower)
        if m:
            unit = m.group(1).lower()
            if unit == "week":
                return self._subtract_unit(ref, 1, "week")
            elif unit == "month":
                return self._subtract_unit(ref, 1, "month")
            elif unit == "year":
                return self._subtract_unit(ref, 1, "year")
            elif unit in self._WEEKDAY_MAP:
                target_wd = self._WEEKDAY_MAP[unit]
                current_wd = ref.weekday()
                days_back = (current_wd - target_wd) % 7
                if days_back == 0:
                    days_back = 7
                # "last Monday" = the Monday in the previous week
                days_back += 7
                result = ref - timedelta(days=days_back)
                return result.replace(hour=0, minute=0, second=0, microsecond=0)

        return None

    def _try_zh_relative(self, text: str, ref: datetime) -> datetime | None:
        # Check word-based relative
        for word, func in self._ZH_REL_WORDS.items():
            if word in text:
                return func(ref).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

        # X天前
        m = self._ZH_REL_AGO.search(text)
        if m:
            return self._subtract_unit(ref, int(m.group(1)), "day")

        # X周前 / X个星期前
        m = self._ZH_REL_WEEK_AGO.search(text)
        if m:
            return self._subtract_unit(ref, int(m.group(1)), "week")

        # X个月前
        m = self._ZH_REL_MONTH_AGO.search(text)
        if m:
            return self._subtract_unit(ref, int(m.group(1)), "month")

        # X年前
        m = self._ZH_REL_YEAR_AGO.search(text)
        if m:
            return self._subtract_unit(ref, int(m.group(1)), "year")

        # 上周
        if self._ZH_REL_LAST_WEEK.search(text):
            return self._subtract_unit(ref, 1, "week")

        # 上月
        if self._ZH_REL_LAST_MONTH.search(text):
            return self._subtract_unit(ref, 1, "month")

        # 去年
        if self._ZH_REL_LAST_YEAR.search(text):
            return self._subtract_unit(ref, 1, "year")

        return None

    def _subtract_unit(
        self, ref: datetime, n: int, unit: str
    ) -> datetime:
        """Subtract N units from reference time, return start-of-day."""
        if unit == "day":
            result = ref - timedelta(days=n)
        elif unit == "week":
            result = ref - timedelta(weeks=n)
        elif unit == "month":
            month = ref.month - n
            year = ref.year
            while month <= 0:
                month += 12
                year -= 1
            day = min(ref.day, 28)  # Safe for all months
            result = ref.replace(year=year, month=month, day=day)
        elif unit == "year":
            result = ref.replace(year=ref.year - n)
        else:
            return ref

        return result.replace(hour=0, minute=0, second=0, microsecond=0)
