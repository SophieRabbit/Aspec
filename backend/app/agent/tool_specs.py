from __future__ import annotations

from typing import Any

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_standards",
            "description": "从工程规范知识库检索相关条文，返回标准名称、章节、条文、页码和原文片段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要检索的规范问题，例如：住宅楼梯踏步宽度和高度要求",
                    },
                    "region": {
                        "type": "string",
                        "description": "地区或城市，例如：上海市、江苏省，可省略",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "返回条文数量，1-30",
                        "minimum": 1,
                        "maximum": 30,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_expression",
            "description": "安全计算用户问题中的数值表达式，例如面积、宽度、高度等数字关系。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "包含数值表达式的问题文本，例如：3米乘2.4米是多少平方米",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_standards",
            "description": "对比不同规范或同一主题下多本规范的相关条文差异。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "需要对比的问题，例如：比较 GB 55031 和 GB 55037 的疏散宽度要求",
                    },
                    "region": {
                        "type": "string",
                        "description": "地区或城市，可省略",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_regional_standards",
            "description": "对比多个地区或城市在同一个主题下的规范条文差异，例如对比上海和北京的防水规范。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "需要对比的主题，例如：防水通用规范、防火通用规范、住宅项目规范要求",
                    },
                    "regions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要对比的地区或城市列表，例如：[\"上海市\", \"北京市\"]",
                    },
                    "top_k_per_region": {
                        "type": "integer",
                        "description": "每个地区返回的条文数量，1-10",
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["query", "regions"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "当本地知识库没有足够依据时，联网搜索公开网页资料作为参考。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，例如：住宅项目规范楼梯踏步要求",
                    },
                    "region": {
                        "type": "string",
                        "description": "地区或城市，可省略",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_LABELS: dict[str, tuple[str, str]] = {
    "retrieve_standards": ("条文检索", "从规范知识库检索相关条文"),
    "calculate_expression": ("数值计算", "对问题中的数值关系进行安全计算"),
    "compare_standards": ("横向对比", "对比多本规范的相关条文"),
    "compare_regional_standards": ("跨地区对比", "按地区分组对比同一主题的规范条文"),
    "web_search": ("联网检索", "检索公开网页资料作为参考"),
}
