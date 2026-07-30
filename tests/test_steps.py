import pytest

from capt.record.steps import validate_steps


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
