from __future__ import annotations


def test_char_bigram_tokenizer_supports_cjk_and_words() -> None:
    from app.risk_knowledge.retrieval.tokenization import tokenize_for_bm25

    tokens = tokenize_for_bm25("贷后 风险 warning 123")

    assert "贷" in tokens
    assert "贷后" in tokens
    assert "warning" in tokens
    assert "123" in tokens


def test_char_bigram_tokenizer_filters_punctuation() -> None:
    from app.risk_knowledge.retrieval.tokenization import tokenize_for_bm25

    tokens = tokenize_for_bm25("risk, warning!!!")

    assert "," not in tokens
    assert "!" not in tokens
