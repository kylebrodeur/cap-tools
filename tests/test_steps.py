import pytest
from unittest.mock import MagicMock, patch

from capt.record.steps import validate_steps, _run_step, drive_steps


def test_validate_steps_accepts_valid_goto():
    validate_steps([{"action": "goto", "url": "https://example.com"}])


def test_validate_steps_accepts_valid_click():
    validate_steps([{"action": "click", "selector": "#save"}])


def test_validate_steps_accepts_valid_fill():
    validate_steps([{"action": "fill", "selector": "#name", "text": "Kyle"}])


def test_validate_steps_accepts_valid_wait_variants():
    validate_steps([{"action": "wait", "selector": "#ready"}])
    validate_steps([{"action": "wait", "ms": 500}])
    validate_steps([{"action": "wait", "text": "Done"}])


def test_validate_steps_accepts_valid_mark():
    validate_steps([{"action": "mark", "label": "opened-settings"}])


def test_validate_steps_rejects_unknown_action():
    with pytest.raises(ValueError, match="unknown action"):
        validate_steps([{"action": "teleport"}])


def test_validate_steps_rejects_goto_without_url():
    with pytest.raises(ValueError, match="'goto' requires 'url'"):
        validate_steps([{"action": "goto"}])


def test_validate_steps_rejects_click_without_selector():
    with pytest.raises(ValueError, match="'click' requires 'selector'"):
        validate_steps([{"action": "click"}])


def test_validate_steps_rejects_fill_without_text():
    with pytest.raises(ValueError, match="'fill' requires"):
        validate_steps([{"action": "fill", "selector": "#x"}])


def test_validate_steps_rejects_wait_without_condition():
    with pytest.raises(ValueError, match="'wait' requires"):
        validate_steps([{"action": "wait"}])


def test_validate_steps_rejects_mark_without_label():
    with pytest.raises(ValueError, match="'mark' requires 'label'"):
        validate_steps([{"action": "mark"}])


def test_validate_steps_error_identifies_step_index():
    with pytest.raises(ValueError, match="step 1"):
        validate_steps([
            {"action": "goto", "url": "https://example.com"},
            {"action": "click"},
        ])


def test_run_step_click_calls_page_and_marks_tracker():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "click", "selector": "#save"}, tracker)
    page.click.assert_called_once_with("#save")
    tracker.mark.assert_called_once_with("click:#save")


def test_run_step_fill_calls_page_and_marks_tracker():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "fill", "selector": "#name", "text": "Kyle"}, tracker)
    page.fill.assert_called_once_with("#name", "Kyle")
    tracker.mark.assert_called_once_with("fill:#name")


def test_run_step_goto_calls_page_and_marks_tracker():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "goto", "url": "https://example.com"}, tracker)
    page.goto.assert_called_once_with("https://example.com")
    tracker.mark.assert_called_once_with("goto")


def test_run_step_mark_uses_given_label_only():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "mark", "label": "opened-settings"}, tracker)
    tracker.mark.assert_called_once_with("opened-settings")
    page.click.assert_not_called()


def test_run_step_wait_ms_calls_wait_for_timeout():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "wait", "ms": 500}, tracker)
    page.wait_for_timeout.assert_called_once_with(500)
    tracker.mark.assert_not_called()


def test_run_step_wait_selector_calls_wait_for_selector():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "wait", "selector": "#ready"}, tracker)
    page.wait_for_selector.assert_called_once_with("#ready")


def test_run_step_wait_text_calls_wait_for_selector_with_text_prefix():
    page = MagicMock()
    tracker = MagicMock()
    _run_step(page, {"action": "wait", "text": "Done"}, tracker)
    page.wait_for_selector.assert_called_once_with("text=Done")


def test_drive_steps_launches_browser_navigates_and_closes():
    tracker = MagicMock()
    fake_page = MagicMock()
    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page
    fake_chromium = MagicMock()
    fake_chromium.launch.return_value = fake_browser
    fake_pw = MagicMock()
    fake_pw.chromium = fake_chromium
    fake_pw_cm = MagicMock()
    fake_pw_cm.__enter__.return_value = fake_pw
    fake_pw_cm.__exit__.return_value = False

    with patch("capt.record.steps.sync_playwright", return_value=fake_pw_cm):
        drive_steps("https://example.com", [{"action": "click", "selector": "#go"}], tracker)

    fake_page.goto.assert_called_once_with("https://example.com")
    fake_page.click.assert_called_once_with("#go")
    fake_browser.close.assert_called_once()


def test_drive_steps_closes_browser_even_if_a_step_raises():
    tracker = MagicMock()
    fake_page = MagicMock()
    fake_page.click.side_effect = RuntimeError("boom")
    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page
    fake_chromium = MagicMock()
    fake_chromium.launch.return_value = fake_browser
    fake_pw = MagicMock()
    fake_pw.chromium = fake_chromium
    fake_pw_cm = MagicMock()
    fake_pw_cm.__enter__.return_value = fake_pw
    fake_pw_cm.__exit__.return_value = False

    with patch("capt.record.steps.sync_playwright", return_value=fake_pw_cm):
        with pytest.raises(RuntimeError, match="boom"):
            drive_steps(None, [{"action": "click", "selector": "#go"}], tracker)

    fake_browser.close.assert_called_once()


def test_drive_steps_skips_navigation_when_no_url():
    tracker = MagicMock()
    fake_page = MagicMock()
    fake_browser = MagicMock()
    fake_browser.new_page.return_value = fake_page
    fake_chromium = MagicMock()
    fake_chromium.launch.return_value = fake_browser
    fake_pw = MagicMock()
    fake_pw.chromium = fake_chromium
    fake_pw_cm = MagicMock()
    fake_pw_cm.__enter__.return_value = fake_pw
    fake_pw_cm.__exit__.return_value = False

    with patch("capt.record.steps.sync_playwright", return_value=fake_pw_cm):
        drive_steps(None, [{"action": "mark", "label": "manual-step"}], tracker)

    fake_page.goto.assert_not_called()
    tracker.mark.assert_called_once_with("manual-step")
