from delta_backend.launcher import _build_welcome_text, _is_public_link


def test_public_link_rejects_placeholders() -> None:
    assert _is_public_link("https://t.me/your_support") is False
    assert _is_public_link("https://t.me/NoveraSupport") is True
    assert _is_public_link("tg://resolve?domain=NoveraChat") is True
    assert _is_public_link("ftp://bad.example") is False


def test_welcome_text_uses_runtime_links() -> None:
    text = _build_welcome_text(
        bot_username="NoveraBot",
        support_url="https://t.me/NoveraSupport",
        chat_url="https://t.me/+CKR1x-wkWZNiNTYx",
    )
    assert "NOVERA" in text
    assert "10% / 24H" in text
    assert "L1 8%" in text
    assert "L5 1%" in text
    assert 'href="https://t.me/NoveraBot"' in text
    assert 'href="https://t.me/NoveraSupport"' in text
    assert "Поддержка" in text
    assert 'href="https://t.me/+CKR1x-wkWZNiNTYx"' in text
    assert "your_support" not in text
    assert "DIGITAL CAPITAL ECOSYSTEM</b>" not in text
    assert "ENTER NOVERA" not in text


def test_welcome_text_hides_placeholder_links() -> None:
    text = _build_welcome_text(
        bot_username="NoveraBot",
        support_url="https://t.me/your_support",
        chat_url="https://t.me/your_chat",
    )
    assert "Поддержка" not in text
    assert "Чат" not in text
    assert 'href="https://t.me/NoveraBot"' in text
