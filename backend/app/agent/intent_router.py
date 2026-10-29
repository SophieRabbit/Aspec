from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from services.synonym_expander import expand_query_details

from .llm import FunctionCallingClient


INTENT_NUMBER = "standard_number"
INTENT_NAME = "standard_name"
INTENT_TERM = "term"
INTENT_NUMERIC = "numeric"
INTENT_SCENARIO = "scenario"
INTENT_COMPARISON = "comparison"
INTENT_MATERIAL = "material"
INTENT_VERSION = "version"
INTENT_COLLOQUIAL = "colloquial"
INTENT_CHITCHAT = "chitchat"
INTENT_FALLBACK = "fallback"


class IntentType(str, Enum):
    STANDARD_NUMBER = INTENT_NUMBER
    STANDARD_NAME = INTENT_NAME
    TERM = INTENT_TERM
    NUMERIC = INTENT_NUMERIC
    SCENARIO = INTENT_SCENARIO
    COMPARISON = INTENT_COMPARISON
    MATERIAL = INTENT_MATERIAL
    VERSION = INTENT_VERSION
    COLLOQUIAL = INTENT_COLLOQUIAL
    CHITCHAT = INTENT_CHITCHAT
    FALLBACK = INTENT_FALLBACK

INTENTS = (
    INTENT_NUMBER,
    INTENT_NAME,
    INTENT_TERM,
    INTENT_NUMERIC,
    INTENT_SCENARIO,
    INTENT_COMPARISON,
    INTENT_MATERIAL,
    INTENT_VERSION,
    INTENT_COLLOQUIAL,
    INTENT_CHITCHAT,
    INTENT_FALLBACK,
)

INTENT_LABELS = {
    INTENT_NUMBER: "按编号查",
    INTENT_NAME: "按名称查",
    INTENT_TERM: "术语查询",
    INTENT_NUMERIC: "数值查询",
    INTENT_SCENARIO: "场景查询",
    INTENT_COMPARISON: "对比查询",
    INTENT_MATERIAL: "材料查询",
    INTENT_VERSION: "版本查询",
    INTENT_COLLOQUIAL: "模糊口语",
    INTENT_CHITCHAT: "闲聊问候",
    INTENT_FALLBACK: "未覆盖问题",
}

INTENT_STRATEGIES: dict[str, dict[str, Any]] = {
    INTENT_NUMBER: {
        "primary": "精确匹配索引",
        "fallback": "向量检索",
        "needs_llm": False,
        "note": "正则提取规范编号，直接定位条文",
    },
    INTENT_NAME: {
        "primary": "规范名称模糊匹配",
        "fallback": "向量检索",
        "needs_llm": False,
        "note": "按规范名称匹配本地知识库",
    },
    INTENT_TERM: {
        "primary": "RAG关键词检索",
        "fallback": "向量检索",
        "needs_llm": True,
        "note": "检索术语定义并生成解释",
    },
    INTENT_NUMERIC: {
        "primary": "RAG精准定位条文",
        "fallback": "提示补充参数",
        "needs_llm": True,
        "note": "定位指标条文并提取数值",
    },
    INTENT_SCENARIO: {
        "primary": "RAG多文档融合",
        "fallback": "拆解问题分步检索",
        "needs_llm": True,
        "note": "跨条文汇总场景要求",
    },
    INTENT_COMPARISON: {
        "primary": "并行RAG检索",
        "fallback": "分别检索后对比",
        "needs_llm": True,
        "note": "识别多规范或多地区并生成对比",
    },
    INTENT_MATERIAL: {
        "primary": "结构化数据检索",
        "fallback": "RAG检索",
        "needs_llm": True,
        "note": "优先查询材料/价格/构造数据",
    },
    INTENT_VERSION: {
        "primary": "结构化数据检索",
        "fallback": "向量检索",
        "needs_llm": False,
        "note": "从规范版本库直接返回效力信息",
    },
    INTENT_COLLOQUIAL: {
        "primary": "Query改写→RAG检索",
        "fallback": "同义词扩展→RAG检索",
        "needs_llm": True,
        "note": "改写口语表达后再检索",
    },
    INTENT_CHITCHAT: {
        "primary": "直接回复",
        "fallback": "直接回复",
        "needs_llm": False,
        "note": "问候、感谢或身份询问，不触发规范检索",
    },
    INTENT_FALLBACK: {
        "primary": "说明当前能力范围",
        "fallback": "友好提示",
        "needs_llm": True,
        "note": "无法由规范知识库处理",
    },
}

_STANDARD_CODE = re.compile(
    r"(?<![A-Za-z0-9])(?:GB|GB/T|JGJ|JG/T|CJJ|CJJ/T|JG|CJ|DB|DBJ|DGJ|T/|Q/|DB31|DB32|DB33|DB34|DB35|DB36|DB37|DB42|DB44|DB50|DB51|DB52|DB53|DB61|DB62|DB63|DB65|DB71|DB81|DB82|DB91|DB92|DB93|DB94|DB95|DB96|DB97|DB98)"
    r"[\s./-]*\d{1,5}(?:\.\d+)?(?:[—-]\d{4}(?:[A-Z])?)?",
    re.IGNORECASE,
)

_CHITCHAT_ONLY = re.compile(
    r"^(?:"
    r"你好|您好|哈喽|嗨|hello|hi|hey|"
    r"早上好|上午好|中午好|下午好|晚上好|在吗|在不在|"
    r"你是谁|你叫什么(?:名字)?|你是什么|"
    r"谢谢|多谢|感谢|好的|好|嗯+|哦+|ok|okay|收到|知道了"
    r")"
    r"[\s，,。.!！?？~～呀啊呢哈啦哟噢哦]*$",
    re.IGNORECASE,
)

_EXPLICIT_OUT_OF_SCOPE = re.compile(
    r"(?:生肖|属相|星座|占星|星座运势|塔罗|算命|八字|求签|解梦)",
    re.IGNORECASE,
)

_RULE_PATTERNS: list[tuple[str, list[str], float]] = [
    (
        INTENT_NUMBER,
        [
            r"(?:GB|GB/T|JGJ|JG/T|CJJ|CJJ/T|JG|CJ|DB|DBJ|DGJ)[\s./-]*\d{1,5}(?:\.\d+)?",
            r"第\s*[\d一二三四五六七八九十百零]+\s*[\.．、-]?\s*[\d一二三四五六七八九十百零]+\s*条",
            r"规范\s*[0-9一二三四五六七八九十]+\s*[\.．、-]\s*[0-9一二三四五六七八九十]+\s*条",
            r"规范\s*\d+(?:\.\d+)*\s*条",
        ],
        3.0,
    ),
    (
        INTENT_VERSION,
        [
            r"(?:现行|有效|废止|作废|实施|生效|替代|修订|新版|旧版|版本|什么时候|还有效吗)",
            r"(?:什么时候|何时).{0,12}(?:实施|生效|发布|废止)",
            r"(?:现行|有效|废止|作废).{0,12}(?:规范|标准|规程)",
        ],
        2.0,
    ),
    (
        INTENT_COMPARISON,
        [
            r"(?:对比|比较|区别|差异|有何不同|有什么不同|哪个更严格|哪个严|区别是什么)",
            r"(?:和|与|跟).{1,12}(?:对比|比较|区别|差异)",
            r"(?:和|与|跟).{1,12}(?:和|与|跟).{0,20}(?:区别|差异|比较)",
        ],
        2.6,
    ),
    (
        INTENT_MATERIAL,
        [
            r"(?:材料|材质|原料|单价|价格|报价|多少钱|成本|品牌|型号|规格|工艺|做法|施工工艺|验收标准|检测标准)",
            r"(?:发泡陶瓷|EPS|XPS|岩棉|岩棉板|保温板|防水卷材|涂料|砂浆|混凝土|钢材|钢筋|铝板|石材|玻璃幕墙|门窗|管材|线缆)",
        ],
        2.2,
    ),
    (
        INTENT_TERM,
        [
            r"(?:什么叫|什么是|术语|解释|含义|定义|指什么|是什么意思|概念|如何理解|怎么理解)",
        ],
        2.4,
    ),
    (
        INTENT_NUMERIC,
        [
            r"(?:多少|多大|多高|多宽|多长|多厚|多少米|最小值|最大值|面积|宽度|高度|厚度|距离|间距|数量|比例|限值|指标|参数|标准值|不应小于|不应大于|不得小于|不得大于|最小|最大)",
            r"(?:\d+(?:\.\d+)?\s*(?:m|mm|cm|m²|m³|kN|MPa|kPa|kg|t|m/s|L|h|d|年|层|度|℃|°C))",
            r"(?:面积|宽度|高度|间距|数量|比例).{0,6}(?:为|是|不应|不得|应).{0,4}\d",
        ],
        1.8,
    ),
    (
        INTENT_NAME,
        [
            r"(?:规范|标准|规程|设计规范|通用规范|技术规程|图集|验收标准|地方标准|行业标准|国家标准)",
            r"(?:无障碍|住宅|防火|消防|给水|排水|燃气|供热|建筑|结构|抗震|地基|脚手架|市政|道路|园林|电气|防水|消防设施).{0,8}(?:规范|标准|规程)",
        ],
        1.6,
    ),
    (
        INTENT_SCENARIO,
        [
            r"(?:怎么办|如何|怎么|要求|规定|需要满足|应满足|设置|配置|做法|流程|验收|设计|施工|管理|维护|保养|检查|检测)",
            r"(?:全套|全部|完整|哪些|包括|包含|应设|必须设|需设)",
        ],
        1.4,
    ),
    (
        INTENT_COLLOQUIAL,
        [
            r"(?:合适|够不够|算不算|能不能|可不可以|可以吗|行吗|能随便|可以随便|随便|一般|大概|多高合适|多少合适|怎么算|怎么弄|咋|为啥|为什么|是不是|行不行)",
            r"(?:楼梯|房子|楼|墙|门|窗|卫生间|厨房|阳台|车位).{0,6}(?:多高|多大|多宽|多少|合适|够不够)",
        ],
        1.8,
    ),
    (
        INTENT_FALLBACK,
        [
            _EXPLICIT_OUT_OF_SCOPE.pattern,
            r"(?:画图|设计图|图纸|帮我画|给个图|作图|出图|效果图)",
            r"(?:你们公司|贵公司|你是谁|你叫什么|人工|客服|投诉|电话|联系方式|怎么联系)",
            r"(?:帮我|请帮我).{0,6}(?:写|做|画|设计|制作).{0,10}(?:方案|图|报告|PPT|表格|代码)",
        ],
        3.0,
    ),
]

_PRIORITY_ORDER = (
    INTENT_NUMBER,
    INTENT_VERSION,
    INTENT_COMPARISON,
    INTENT_MATERIAL,
    INTENT_TERM,
    INTENT_NUMERIC,
    INTENT_NAME,
    INTENT_SCENARIO,
    INTENT_COLLOQUIAL,
    INTENT_CHITCHAT,
    INTENT_FALLBACK,
)


@dataclass(frozen=True)
class IntentResult:
    intent: str
    confidence: float = 0.0
    matched_patterns: tuple[str, ...] = ()
    source: str = "fallback"
    query: str = ""
    strategy: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return INTENT_LABELS.get(self.intent, self.intent)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "label": self.label,
            "confidence": round(self.confidence, 3),
            "matched_patterns": list(self.matched_patterns),
            "source": self.source,
            "strategy": self.strategy,
        }


class IntentRouter:
    """三阶段意图识别：规则匹配 -> LLM 分类 -> 低置信度兜底。"""

    def __init__(
        self,
        llm_client: FunctionCallingClient | None = None,
        *,
        min_llm_confidence: float = 0.6,
        low_confidence_threshold: float = 0.68,
    ) -> None:
        self.llm_client = llm_client
        self.min_llm_confidence = min_llm_confidence
        self.low_confidence_threshold = low_confidence_threshold

    def classify(
        self,
        query: str,
        *,
        use_llm: bool = True,
    ) -> IntentResult:
        normalized = self._normalize(query)
        if self._is_chitchat(normalized):
            return IntentResult(
                intent=INTENT_CHITCHAT,
                confidence=0.99,
                matched_patterns=(_CHITCHAT_ONLY.pattern,),
                source="rules",
                query=normalized,
                strategy=INTENT_STRATEGIES[INTENT_CHITCHAT],
            )
        rule_result = self._classify_by_rules(normalized)
        if rule_result.confidence >= self.low_confidence_threshold:
            return rule_result
        if rule_result.intent == INTENT_FALLBACK and expand_query_details(normalized).matches:
            return IntentResult(
                intent=INTENT_TERM,
                confidence=0.82,
                matched_patterns=(),
                source="rules",
                query=normalized,
                strategy=INTENT_STRATEGIES[INTENT_TERM],
            )

        llm_result: IntentResult | None = None
        if use_llm and self.llm_client is not None and self.llm_client.enabled:
            llm_result = self._classify_by_llm(normalized)
            if (
                llm_result.intent in INTENTS
                and llm_result.confidence > rule_result.confidence
                and llm_result.confidence >= self.min_llm_confidence
            ):
                return llm_result

        fallback_result = self._classify_by_fallback(normalized)
        best = max(
            (item for item in (rule_result, llm_result, fallback_result) if item is not None),
            key=lambda item: item.confidence,
            default=fallback_result,
        )
        return best

    def route(
        self,
        query: str,
        *,
        use_llm: bool = True,
    ) -> IntentResult:
        """主检索入口使用的路由别名。"""
        print(f"[DEBUG] Original query: {query}")
        return self.classify(query, use_llm=use_llm)

    def _normalize(self, query: str) -> str:
        text = query.strip()
        text = re.sub(r"[\r\n]+", " ", text)
        text = re.sub(r"[ \t\u3000]+", " ", text)
        return text

    @staticmethod
    def _is_chitchat(query: str) -> bool:
        return bool(_CHITCHAT_ONLY.fullmatch(query.strip()))

    def _classify_by_rules(self, query: str) -> IntentResult:
        scores: dict[str, float] = {}
        matched: dict[str, list[str]] = {}
        for intent, patterns, weight in _RULE_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    scores[intent] = scores.get(intent, 0.0) + weight
                    matched.setdefault(intent, []).append(pattern)

        if not scores:
            return IntentResult(
                intent=INTENT_FALLBACK,
                confidence=0.55,
                source="rules",
                query=query,
                strategy=INTENT_STRATEGIES[INTENT_FALLBACK],
            )

        if scores.get(INTENT_COMPARISON, 0.0) > 0:
            if "比较" in query and ("和" in query or "与" in query):
                scores[INTENT_COMPARISON] += 2.0
            if len(_STANDARD_CODE.findall(query)) >= 2:
                scores[INTENT_COMPARISON] += 2.0
            if re.search(r"(?:新旧|旧版|新版)", query):
                scores[INTENT_COMPARISON] += 2.0

        if scores.get(INTENT_VERSION, 0.0) > 0 and (
            scores.get(INTENT_NAME, 0.0) > 0 or _STANDARD_CODE.search(query)
        ):
            scores[INTENT_VERSION] += 2.0

        if re.search(r"规范\s*\d+(?:\.\d+)*\s*条", query):
            scores[INTENT_NUMBER] = scores.get(INTENT_NUMBER, 0.0) + 2.0

        if scores.get(INTENT_COLLOQUIAL, 0.0) > 0 and re.search(
            r"(?:算不算|合适|够不够|行不行|算)",
            query,
        ):
            scores[INTENT_COLLOQUIAL] += 1.5

        best_intent = max(
            INTENTS,
            key=lambda intent: (scores.get(intent, 0.0), -_PRIORITY_ORDER.index(intent)),
        )
        score = scores.get(best_intent, 0.0)
        confidence = min(0.98, 0.55 + 0.09 * score)
        return IntentResult(
            intent=best_intent,
            confidence=confidence,
            matched_patterns=tuple(matched.get(best_intent, [])),
            source="rules",
            query=query,
            strategy=INTENT_STRATEGIES[best_intent],
        )

    def _classify_by_llm(self, query: str) -> IntentResult | None:
        if self.llm_client is None or not self.llm_client.enabled:
            return None
        system = (
            "你是规宝建筑规范检索系统的意图分类器。只输出 JSON，不要输出其他内容。"
            "格式：{\"intent\": \"standard_number\", \"confidence\": 0.9, \"reason\": \"\"}\n"
            f"意图只能是：{', '.join(INTENT_LABELS.values())}。"
        )
        try:
            response = self.llm_client.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ]
            )
            content = response.get("content") or ""
            parsed = self._parse_llm_json(content)
        except Exception:
            return None
        intent = parsed.get("intent", "")
        if intent not in INTENTS:
            return None
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return IntentResult(
            intent=intent,
            confidence=max(0.0, min(1.0, confidence)),
            source="llm",
            query=query,
            strategy=INTENT_STRATEGIES[intent],
        )

    @staticmethod
    def _parse_llm_json(content: str) -> dict[str, Any]:
        content = content.strip()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    def _classify_by_fallback(self, query: str) -> IntentResult:
        if _STANDARD_CODE.search(query):
            intent = INTENT_NUMBER
        elif re.search(r"(?:定义|术语|解释|什么叫|什么是|含义|概念)", query, re.IGNORECASE):
            intent = INTENT_TERM
        elif re.search(r"(?:对比|比较|区别|差异|和|与).{0,8}(?:区别|差异|对比)", query, re.IGNORECASE):
            intent = INTENT_COMPARISON
        elif re.search(r"(?:现行|废止|实施|生效|版本|修订|替代)", query, re.IGNORECASE):
            intent = INTENT_VERSION
        elif re.search(r"(?:材料|单价|价格|工艺|材质|多少钱)", query, re.IGNORECASE):
            intent = INTENT_MATERIAL
        elif re.search(r"(?:多少|多大|多高|多宽|面积|宽度|高度|限值|指标|参数|\d+(?:\.\d+)?\s*(?:m|mm|cm|m²|kN|MPa|kPa))", query, re.IGNORECASE):
            intent = INTENT_NUMERIC
        elif re.search(r"(?:规范|标准|规程|图集)", query, re.IGNORECASE):
            intent = INTENT_NAME
        elif re.search(r"(?:合适|够不够|算不算|可不可以|一般|大概|怎么|咋)", query, re.IGNORECASE):
            intent = INTENT_COLLOQUIAL
        elif re.search(r"(?:画图|设计图|图纸|人工|客服|你们公司|你是谁)", query, re.IGNORECASE):
            intent = INTENT_FALLBACK
        else:
            intent = INTENT_FALLBACK
        return IntentResult(
            intent=intent,
            confidence=0.55,
            source="fallback",
            query=query,
            strategy=INTENT_STRATEGIES[intent],
        )
