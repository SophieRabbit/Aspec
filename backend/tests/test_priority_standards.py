from types import SimpleNamespace

from app.knowledge.retriever import Retriever


def test_priority_standard_matching() -> None:
    retriever = Retriever(SimpleNamespace(documents=[]))

    assert retriever._is_priority_standard("GB 55031-2022")
    assert retriever._is_priority_standard("GB55004-2021")
    assert not retriever._is_priority_standard("GB 50016-2014")
    assert not retriever._is_priority_standard("GB 99999-9999")
    assert retriever.priority_stats()["total"] == 38
