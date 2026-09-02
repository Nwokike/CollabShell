"""Tests for OnboardingScreen and its slides."""

import sys
from unittest.mock import MagicMock

sys.path.insert(0, "src")

from screens.onboarding import OnboardingScreen
from screens.onboarding.slides import (
    build_page_1,
    build_page_2,
    build_page_3,
)


def test_build_page_1_renders():
    page_1 = build_page_1()
    assert page_1 is not None
    assert len(page_1.controls) > 0


def test_build_page_2_renders():
    page_2 = build_page_2()
    assert page_2 is not None
    assert len(page_2.controls) > 0


def test_build_page_3_renders():
    auth_ref = MagicMock()
    page_3 = build_page_3(
        auth_code_ref=auth_ref,
        auth_code_val="",
        on_auth_code_change=lambda e: None,
        show_verify=True,
        auth_status="",
        auth_status_color=None,
        is_loading_auth=False,
        on_start_auth=lambda e: None,
        on_submit_code=lambda e: None,
    )
    assert page_3 is not None
    assert len(page_3.controls) > 0


def test_onboarding_screen_callable():
    assert callable(OnboardingScreen)
