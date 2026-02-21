"""Tests for the TemporalExtractor service."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from neuromemory.services.temporal import TemporalExtractor


@pytest.fixture
def extractor():
    return TemporalExtractor()


@pytest.fixture
def ref_time():
    """Fixed reference time: 2023-06-15 12:00:00 UTC (Thursday)."""
    return datetime(2023, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# ISO 8601
# ---------------------------------------------------------------------------

class TestISO:
    def test_iso_date(self, extractor, ref_time):
        result = extractor.extract("2023-05-07", ref_time)
        assert result == datetime(2023, 5, 7, tzinfo=timezone.utc)

    def test_iso_datetime(self, extractor, ref_time):
        result = extractor.extract("2023-05-07T14:30:00", ref_time)
        assert result == datetime(2023, 5, 7, 14, 30, 0, tzinfo=timezone.utc)

    def test_iso_in_sentence(self, extractor, ref_time):
        result = extractor.extract("The meeting was on 2023-05-07 at the office", ref_time)
        assert result == datetime(2023, 5, 7, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# English absolute dates
# ---------------------------------------------------------------------------

class TestEnglishAbsolute:
    def test_mdy(self, extractor, ref_time):
        result = extractor.extract("May 7, 2023", ref_time)
        assert result == datetime(2023, 5, 7, tzinfo=timezone.utc)

    def test_dmy(self, extractor, ref_time):
        result = extractor.extract("7 May 2023", ref_time)
        assert result == datetime(2023, 5, 7, tzinfo=timezone.utc)

    def test_month_abbreviation(self, extractor, ref_time):
        result = extractor.extract("Jan 15, 2023", ref_time)
        assert result == datetime(2023, 1, 15, tzinfo=timezone.utc)

    def test_ordinal_suffix(self, extractor, ref_time):
        result = extractor.extract("May 7th, 2023", ref_time)
        assert result == datetime(2023, 5, 7, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Chinese absolute dates
# ---------------------------------------------------------------------------

class TestChineseAbsolute:
    def test_zh_full(self, extractor, ref_time):
        result = extractor.extract("2023年5月7日", ref_time)
        assert result == datetime(2023, 5, 7, tzinfo=timezone.utc)

    def test_zh_partial(self, extractor, ref_time):
        result = extractor.extract("5月7日", ref_time)
        assert result == datetime(2023, 5, 7, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# English relative
# ---------------------------------------------------------------------------

class TestEnglishRelative:
    def test_yesterday(self, extractor, ref_time):
        result = extractor.extract("yesterday", ref_time)
        assert result == datetime(2023, 6, 14, tzinfo=timezone.utc)

    def test_today(self, extractor, ref_time):
        result = extractor.extract("today", ref_time)
        assert result == datetime(2023, 6, 15, tzinfo=timezone.utc)

    def test_days_ago(self, extractor, ref_time):
        result = extractor.extract("3 days ago", ref_time)
        assert result == datetime(2023, 6, 12, tzinfo=timezone.utc)

    def test_weeks_ago(self, extractor, ref_time):
        result = extractor.extract("2 weeks ago", ref_time)
        assert result == datetime(2023, 6, 1, tzinfo=timezone.utc)

    def test_months_ago(self, extractor, ref_time):
        result = extractor.extract("1 month ago", ref_time)
        assert result == datetime(2023, 5, 15, tzinfo=timezone.utc)

    def test_last_week(self, extractor, ref_time):
        result = extractor.extract("last week", ref_time)
        assert result == datetime(2023, 6, 8, tzinfo=timezone.utc)

    def test_last_year(self, extractor, ref_time):
        result = extractor.extract("last year", ref_time)
        assert result == datetime(2022, 6, 15, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Chinese relative
# ---------------------------------------------------------------------------

class TestChineseRelative:
    def test_zuotian(self, extractor, ref_time):
        result = extractor.extract("昨天", ref_time)
        assert result == datetime(2023, 6, 14, tzinfo=timezone.utc)

    def test_qiantian(self, extractor, ref_time):
        result = extractor.extract("前天", ref_time)
        assert result == datetime(2023, 6, 13, tzinfo=timezone.utc)

    def test_tian_qian(self, extractor, ref_time):
        result = extractor.extract("3天前", ref_time)
        assert result == datetime(2023, 6, 12, tzinfo=timezone.utc)

    def test_zhou_qian(self, extractor, ref_time):
        result = extractor.extract("2周前", ref_time)
        assert result == datetime(2023, 6, 1, tzinfo=timezone.utc)

    def test_yue_qian(self, extractor, ref_time):
        result = extractor.extract("1个月前", ref_time)
        assert result == datetime(2023, 5, 15, tzinfo=timezone.utc)

    def test_shang_zhou(self, extractor, ref_time):
        result = extractor.extract("上周", ref_time)
        assert result == datetime(2023, 6, 8, tzinfo=timezone.utc)

    def test_qu_nian(self, extractor, ref_time):
        result = extractor.extract("去年", ref_time)
        assert result == datetime(2022, 6, 15, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# English seasons
# ---------------------------------------------------------------------------

class TestEnglishSeasons:
    def test_summer_with_year(self, extractor, ref_time):
        result = extractor.extract("summer 2022", ref_time)
        assert result == datetime(2022, 6, 1, tzinfo=timezone.utc)

    def test_last_summer(self, extractor, ref_time):
        result = extractor.extract("last summer", ref_time)
        assert result == datetime(2022, 6, 1, tzinfo=timezone.utc)

    def test_winter_with_year(self, extractor, ref_time):
        result = extractor.extract("winter 2023", ref_time)
        assert result == datetime(2023, 12, 1, tzinfo=timezone.utc)

    def test_fall_no_year(self, extractor, ref_time):
        """Fall hasn't happened yet in June → use previous year's fall."""
        result = extractor.extract("fall", ref_time)
        assert result == datetime(2022, 9, 1, tzinfo=timezone.utc)

    def test_spring_no_year(self, extractor, ref_time):
        """Spring already passed in June → use this year's spring."""
        result = extractor.extract("spring", ref_time)
        assert result == datetime(2023, 3, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Chinese seasons
# ---------------------------------------------------------------------------

class TestChineseSeasons:
    def test_qu_nian_xia_tian(self, extractor, ref_time):
        result = extractor.extract("去年夏天", ref_time)
        assert result == datetime(2022, 6, 1, tzinfo=timezone.utc)

    def test_chun_tian(self, extractor, ref_time):
        result = extractor.extract("春天", ref_time)
        assert result == datetime(2023, 3, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Quarters
# ---------------------------------------------------------------------------

class TestQuarters:
    def test_en_quarter(self, extractor, ref_time):
        result = extractor.extract("Q3 2023", ref_time)
        assert result == datetime(2023, 7, 1, tzinfo=timezone.utc)

    def test_en_quarter_q1(self, extractor, ref_time):
        result = extractor.extract("Q1 2022", ref_time)
        assert result == datetime(2022, 1, 1, tzinfo=timezone.utc)

    def test_zh_quarter(self, extractor, ref_time):
        result = extractor.extract("2023年第三季度", ref_time)
        assert result == datetime(2023, 7, 1, tzinfo=timezone.utc)

    def test_zh_quarter_num(self, extractor, ref_time):
        result = extractor.extract("2022年3季度", ref_time)
        assert result == datetime(2022, 7, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string(self, extractor, ref_time):
        assert extractor.extract("", ref_time) is None

    def test_no_time_found(self, extractor, ref_time):
        assert extractor.extract("I love programming", ref_time) is None

    def test_none_text(self, extractor, ref_time):
        assert extractor.extract(None, ref_time) is None

    def test_no_reference_time(self, extractor):
        """Should use UTC now as reference when no ref provided."""
        result = extractor.extract("yesterday")
        assert result is not None
        assert result.tzinfo is not None

    def test_naive_reference_time(self, extractor):
        """Should handle naive reference time by adding UTC."""
        ref = datetime(2023, 6, 15, 12, 0, 0)  # No timezone
        result = extractor.extract("yesterday", ref)
        assert result == datetime(2023, 6, 14, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Time range extraction (for query-side temporal filtering)
# ---------------------------------------------------------------------------

class TestExtractTimeRange:
    def test_in_month(self, extractor, ref_time):
        after, before = extractor.extract_time_range("When did X go camping in June?", ref_time)
        assert after == datetime(2023, 6, 1, tzinfo=timezone.utc)
        assert before == datetime(2023, 7, 1, tzinfo=timezone.utc)

    def test_in_month_with_year(self, extractor, ref_time):
        after, before = extractor.extract_time_range("What happened in March 2022?", ref_time)
        assert after == datetime(2022, 3, 1, tzinfo=timezone.utc)
        assert before == datetime(2022, 4, 1, tzinfo=timezone.utc)

    def test_during_summer(self, extractor, ref_time):
        after, before = extractor.extract_time_range("When did Caroline attend a parade during the summer?", ref_time)
        assert after == datetime(2023, 6, 1, tzinfo=timezone.utc)
        assert before == datetime(2023, 9, 1, tzinfo=timezone.utc)

    def test_in_year(self, extractor, ref_time):
        after, before = extractor.extract_time_range("What did she do in 2022?", ref_time)
        assert after == datetime(2022, 1, 1, tzinfo=timezone.utc)
        assert before == datetime(2023, 1, 1, tzinfo=timezone.utc)

    def test_no_time_expression(self, extractor, ref_time):
        after, before = extractor.extract_time_range("When did Caroline go to school?", ref_time)
        assert after is None
        assert before is None

    def test_empty_query(self, extractor, ref_time):
        after, before = extractor.extract_time_range("", ref_time)
        assert after is None
        assert before is None

    def test_december_wraps_year(self, extractor, ref_time):
        after, before = extractor.extract_time_range("What happened in December 2023?", ref_time)
        assert after == datetime(2023, 12, 1, tzinfo=timezone.utc)
        assert before == datetime(2024, 1, 1, tzinfo=timezone.utc)

    # --- Chinese time range tests (ref_time = 2023-06-15 Thu) ---

    def test_zh_yesterday(self, extractor, ref_time):
        # ref_time = 2023-06-15, yesterday = 2023-06-14
        after, before = extractor.extract_time_range("昨天我们聊了什么", ref_time)
        assert after == datetime(2023, 6, 14, 0, 0, 0, tzinfo=timezone.utc)
        assert before == datetime(2023, 6, 15, 0, 0, 0, tzinfo=timezone.utc)

    def test_zh_day_before_yesterday(self, extractor, ref_time):
        after, before = extractor.extract_time_range("前天发生了什么", ref_time)
        assert after == datetime(2023, 6, 13, 0, 0, 0, tzinfo=timezone.utc)
        assert before == datetime(2023, 6, 14, 0, 0, 0, tzinfo=timezone.utc)

    def test_zh_tomorrow(self, extractor, ref_time):
        after, before = extractor.extract_time_range("明天有什么安排", ref_time)
        assert after == datetime(2023, 6, 16, 0, 0, 0, tzinfo=timezone.utc)
        assert before == datetime(2023, 6, 17, 0, 0, 0, tzinfo=timezone.utc)

    def test_zh_day_after_tomorrow(self, extractor, ref_time):
        after, before = extractor.extract_time_range("后天的计划", ref_time)
        assert after == datetime(2023, 6, 17, 0, 0, 0, tzinfo=timezone.utc)
        assert before == datetime(2023, 6, 18, 0, 0, 0, tzinfo=timezone.utc)

    def test_zh_recent(self, extractor, ref_time):
        after, before = extractor.extract_time_range("最近我们聊了什么", ref_time)
        assert after == ref_time - __import__("datetime").timedelta(days=30)
        assert before == ref_time

    def test_zh_today(self, extractor, ref_time):
        after, before = extractor.extract_time_range("今天发生了什么", ref_time)
        assert after == datetime(2023, 6, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert before == ref_time

    def test_zh_this_week(self, extractor, ref_time):
        # ref_time is Thursday 2023-06-15, Mon = 2023-06-12
        after, before = extractor.extract_time_range("这周我们聊了什么", ref_time)
        assert after == datetime(2023, 6, 12, 0, 0, 0, tzinfo=timezone.utc)
        assert before == ref_time

    def test_zh_last_week(self, extractor, ref_time):
        # last week = Mon 2023-06-05 to Mon 2023-06-12
        after, before = extractor.extract_time_range("上周有什么事", ref_time)
        assert after == datetime(2023, 6, 5, 0, 0, 0, tzinfo=timezone.utc)
        assert before == datetime(2023, 6, 12, 0, 0, 0, tzinfo=timezone.utc)

    def test_zh_this_month(self, extractor, ref_time):
        after, before = extractor.extract_time_range("这个月发生了什么", ref_time)
        assert after == datetime(2023, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert before == ref_time

    def test_zh_last_month(self, extractor, ref_time):
        # last month = May 2023
        after, before = extractor.extract_time_range("上个月的事情", ref_time)
        assert after == datetime(2023, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert before == datetime(2023, 6, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_zh_this_year(self, extractor, ref_time):
        after, before = extractor.extract_time_range("今年有什么大事", ref_time)
        assert after == datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert before == ref_time

    def test_zh_last_year(self, extractor, ref_time):
        after, before = extractor.extract_time_range("去年发生了什么", ref_time)
        assert after == datetime(2022, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert before == datetime(2023, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_zh_year_num(self, extractor, ref_time):
        after, before = extractor.extract_time_range("2022年的事", ref_time)
        assert after == datetime(2022, 1, 1, tzinfo=timezone.utc)
        assert before == datetime(2023, 1, 1, tzinfo=timezone.utc)

    def test_zh_month_num(self, extractor, ref_time):
        after, before = extractor.extract_time_range("3月我们聊了什么", ref_time)
        assert after == datetime(2023, 3, 1, tzinfo=timezone.utc)
        assert before == datetime(2023, 4, 1, tzinfo=timezone.utc)

    def test_zh_month_cn(self, extractor, ref_time):
        after, before = extractor.extract_time_range("三月份发生的事", ref_time)
        assert after == datetime(2023, 3, 1, tzinfo=timezone.utc)
        assert before == datetime(2023, 4, 1, tzinfo=timezone.utc)

    def test_zh_no_time(self, extractor, ref_time):
        after, before = extractor.extract_time_range("你叫什么名字", ref_time)
        assert after is None
        assert before is None
