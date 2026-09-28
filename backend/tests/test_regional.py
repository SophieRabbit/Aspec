from types import SimpleNamespace

from app.agent.planner import Planner
from app.agent.tools import compare_regional_tool
from app.knowledge.region_hierarchy import (
    build_region_notice,
    detect_requested_region,
    extract_regions,
)


def test_extract_regions_handles_multiple_cities_and_typo() -> None:
    assert extract_regions("可以对比上海和北京的防水规范吗") == ["上海市", "北京市"]
    assert extract_regions("对比上海、北京、深圳的日照标准") == ["上海市", "北京市", "深圳市"]
    assert extract_regions("同时查询杭州和南京的容积率规定") == ["杭州市", "南京市"]


def test_detect_region_prefers_the_first_unrelated_city() -> None:
    hangzhou_first = detect_requested_region(
        "杭州成都商业建筑疏散宽度",
        [],
    )
    chengdu_first = detect_requested_region(
        "成都杭州商业建筑疏散宽度",
        [],
    )

    assert hangzhou_first is not None
    assert hangzhou_first["place"] == "杭州市"
    assert hangzhou_first["province"] == "浙江省"
    assert chengdu_first is not None
    assert chengdu_first["place"] == "成都市"


def test_city_document_suppresses_missing_province_notice() -> None:
    documents = [
        {
            "region": "杭州市",
            "province": "浙江省",
            "city": "杭州市",
            "district": "",
        }
    ]
    requested = detect_requested_region("杭州市城市规划管理技术规定", documents)
    notice = build_region_notice(requested, documents)

    assert "未找到" not in notice
    assert "杭州市规范 1 部" in notice


class FakeRegionalRetriever:
    def __init__(self) -> None:
        self.docs = [
            {
                "id": "sh-water",
                "standard": "DG/TJ08-XXX",
                "title": "上海市建筑防水工程技术规程",
                "document_type": "地方规范",
                "region": "上海市",
                "province": "上海市",
                "snippets": [
                    {
                        "chapter": "第4章",
                        "article": "4.1",
                        "page": 12,
                        "text": "上海地区屋面防水等级要求。",
                    }
                ],
            },
            {
                "id": "bj-water",
                "standard": "DB11/XXX",
                "title": "北京市建筑防水工程技术规程",
                "document_type": "地方规范",
                "region": "北京市",
                "province": "北京市",
                "snippets": [
                    {
                        "chapter": "第5章",
                        "article": "5.2",
                        "page": 18,
                        "text": "北京地区屋面防水等级要求。",
                    }
                ],
            },
        ]
        self.knowledge_base = SimpleNamespace(documents=self.docs)

    def search(self, query: str, top_k: int = 5, **kwargs):
        region_scope = kwargs.get("region_scope") or {}
        place = region_scope.get("place", "")
        return [
            {"document": doc, "snippet": doc["snippets"][0], "score": 1.0}
            for doc in self.docs
            if doc["region"] == place
        ][:top_k]

    @staticmethod
    def to_source(item):
        document = item["document"]
        snippet = item["snippet"]
        return {
            "doc_id": document["id"],
            "title": document["title"],
            "standard": document["standard"],
            "document_type": document["document_type"],
            "region": document["region"],
            "chapter": snippet["chapter"],
            "article": snippet["article"],
            "page": snippet["page"],
            "snippet": snippet["text"],
            "score": item.get("score", 0.0),
        }


def test_compare_regional_tool_groups_by_region() -> None:
    retriever = FakeRegionalRetriever()
    result = compare_regional_tool(
        "防水规范",
        ["上海市", "北京市"],
        retriever,
        top_k_per_region=3,
    )

    assert result["regions"] == ["上海市", "北京市"]
    assert result["available_region_count"] == 2
    assert len(result["sources"]) == 2
    assert result["groups"][0]["standards"][0]["standard"] == "DG/TJ08-XXX"
    assert result["groups"][1]["standards"][0]["standard"] == "DB11/XXX"


def test_rule_planner_uses_regional_comparison() -> None:
    retriever = FakeRegionalRetriever()
    planner = Planner(retriever)

    result = planner.run(
        "可以对比上海和北京的防水规范吗",
        enable_function_calling=False,
        enable_web_search=False,
    )

    assert "【上海市】" in result["reply"]
    assert "【北京市】" in result["reply"]
    assert result["steps"][0]["tool"] == "compare"
    assert len(result["sources"]) == 2
