from smallerer.model import Line, Page
from smallerer.normalize import merge_soft_wraps, strip_running_heads


def test_cjk_soft_wrap_joins_without_space():
    text = merge_soft_wraps(["这是一个长度足够的中文句子需要继续", "连接下一行而且不应该插入空格"])
    assert text == "这是一个长度足够的中文句子需要继续连接下一行而且不应该插入空格"


def test_latin_hyphenation_and_soft_wrap():
    text = merge_soft_wraps(
        [
            "A sufficiently long introductory line with hyphen-",
            "ation continuing on the next line",
        ]
    )
    assert "hyphenation" in text


def test_sentence_end_preserves_newline():
    text = merge_soft_wraps(["This is a complete sentence.", "another paragraph starts here"])
    assert "\n" in text


def test_running_heads_removed_but_body_preserved():
    pages = [
        Page(
            number=n,
            height=100,
            lines=[
                Line("PHYS 201", y0=1, y1=3),
                Line(f"body unique {n}", y0=30, y1=35),
                Line(f"Page {n}", y0=97, y1=99),
            ],
        )
        for n in range(1, 4)
    ]
    removed = strip_running_heads(pages)
    assert "PHYS %d" in removed
    assert "Page %d" in removed
    assert all([line.text] == [f"body unique {page.number}"] for page in pages for line in page.lines)


def test_bare_page_numbers_not_stripped_as_running_heads():
    """Regression: bare page numbers like '3' should not be treated as running heads."""
    pages = [
        Page(
            number=n,
            height=100,
            lines=[
                Line(str(n), y0=97, y1=99),  # Bare page number at bottom
                Line(f"Content of page {n}", y0=30, y1=35),
            ],
        )
        for n in range(1, 5)
    ]
    removed = strip_running_heads(pages)
    # Bare "%d" should not be in removed list
    assert "%d" not in removed
    # All pages should still have both lines
    for page in pages:
        assert len(page.lines) == 2
        assert any(str(page.number) in line.text for line in page.lines)


def test_page_numbers_with_text_are_stripped():
    """Page numbers with surrounding text (e.g., 'Page 3') should still be stripped."""
    pages = [
        Page(
            number=n,
            height=100,
            lines=[
                Line(f"Page {n}", y0=97, y1=99),
                Line(f"Content {n}", y0=30, y1=35),
            ],
        )
        for n in range(1, 5)
    ]
    removed = strip_running_heads(pages)
    assert "Page %d" in removed
    # Content lines should remain
    for page in pages:
        assert len(page.lines) == 1
        assert f"Content {page.number}" in page.lines[0].text


