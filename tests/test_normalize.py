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

