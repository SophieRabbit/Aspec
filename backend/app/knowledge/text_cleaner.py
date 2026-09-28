from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable


PREAMBLE_1 = (
    "前言 为适应国际技术法规与技术标准通行规则，2016年以来，"
    "住房和城乡建设部陆续印发《深化工程建设标准化工作改革的意见》等文件，"
    "提出政府制定强制性标准、社会团体制定自愿采用性标准的长远目标，"
    "明确了逐步用全文强制性工程建设规范取代现行标准中分散的强制性条文的改革任务，"
    "逐步形成由法律、行政法规、部门规章中的技术性规定与全文强制性工程建设规范构成的"
    "“技术法规”体系。"
    "关于规范种类。强制性工程建设规范体系覆盖工程建设领域各类建设工程项目，"
    "分为工程项目类规范（简称项目规范）和通用技术类规范（简称通用规范）两种类型。"
    "项目规范以工程建设项目整体为对象，以项目的规模、布局、功能、性能和关键技术措施等"
    "五大要素为主要内容。通用规范以实现工程建设项目功能性能要求的各专业通用技术为对象，"
    "以勘察、设计、施工、维修、养护等通用技术要求为主要内容。"
    "在全文强制性工程建设规范体系中，项目规范为主干，通用规范是对各类项目共性的、"
    "通用的专业性关键技术措施的规定。"
    "关于五大要素指标。强制性工程建设规范中各项要素是保障城乡基础设施建设体系化和"
    "效率提升的基本规定，是支撑城乡建设高质量发展的基本要求。项目的规模要求主要规定了"
    "建设工程项目应具备完整的生产或服务能力，应与经济社会发展水平相适应。"
    "项目的布局要求主要规定了产业布局、建设工程项目选址、总体设计、总平面布置以及"
    "与规模相协调的统筹性技术要求，应考虑供给能力合理分布，提高相关设施建设的整体水平。"
    "项目的功能要求主要规定项目构成和用途，明确项目的基本组成单元，"
    "是项目发挥预期作用的保障。项目的性能要求主要规定建设工程"
)

PREAMBLE_2 = (
    "项目建设水平或技术水平的高低程度，体现建设工程项目的适用性，"
    "明确项目质量、安全、节能、环保、宜居环境和可持续发展等方面应达到的基本水平。"
    "关键技术措施是实现建设项目功能、性能要求的基本技术规定，"
    "是落实城乡建设安全、绿色、韧性、智慧、宜居、公平、有效率等发展目标的基本保障。"
    "关于规范实施。强制性工程建设规范具有强制约束力，是保障人民生命财产安全、人身健康、"
    "工程安全、生态环境安全、公众权益和公众利益，以及促进能源资源节约利用、"
    "满足经济社会管理等方面的控制性底线要求，工程建设项目的勘察、设计、施工、验收、维修、"
    "养护、拆除等建设活动全过程中必须严格执行，其中，对于既有建筑改造项目"
    "（指不改变现有使用功能），当条件不具备、执行现行规范确有困难时，应不低于原建造时的标准。"
    "与强制性工程建设规范配套的推荐性工程建设标准是经过实践检验的、"
    "保障达到强制性规范要求的成熟技术措施，一般情况下也应当执行。"
    "在满足强制性工程建设规范规定的项目功能、性能要求和关键技术措施的前提下，"
    "可合理选用相关团体标准、企业标准，使项目功能、性能更加优化或达到更高水平。"
    "推荐性工程建设标准、团体标准、企业标准要与强制性工程建设规范协调配套，"
    "各项技术要求不得低于强制性工程建设规范的相关技术水平。"
    "强制性工程建设规范实施后，现行相关工程建设国家标准、行业标准中的强制性条文同时废止。"
    "现行工程建设地方标准中的强制性条文应及时修订，且不得低于强制性工程建设规范的规定。"
    "现行工程建设标准（包括强制性标准和推荐性标准）中有关规定与强制性工程建设规范的"
    "规定不一致的，以强制性工程建设规范的规定为准。"
)


TEXT_REPLACEMENTS: list[tuple[str, str]] = [
    # OCR 人/入混用
    ("流人", "流入"),
    ("侵人", "侵入"),
    ("纳人", "纳入"),
    ("投人", "投入"),
    ("进人", "进入"),
    ("深人", "深入"),
    ("渗人", "渗入"),
    ("人侵", "入侵"),
    ("浸人", "浸入"),
    ("混人", "混入"),
    ("排人", "排入"),
    ("掉人", "掉入"),
    ("吸人", "吸入"),
    ("引人", "引入"),
    ("列人", "列入"),
    ("计人", "计入"),
    ("出人", "出入"),
    ("输人", "输入"),
    ("接人", "接入"),
    ("注人", "注入"),
    ("灌人", "灌入"),
    ("滴人", "滴入"),
    ("落人", "落入"),
    ("冲人", "冲入"),
    ("涌人", "涌入"),
    ("汇人", "汇入"),
    ("溢人", "溢入"),
    ("泄人", "泄入"),
    ("穿人", "穿入"),
    ("转人", "转入"),
    ("传人", "传入"),
    ("嵌人", "嵌入"),
    ("介人", "介入"),
    ("代人", "代入"),
    # OCR 千/于混用，顺序必须先处理带“不”的复合词
    ("关千", "关于"),
    ("对千", "对于"),
    ("由千", "由于"),
    ("用千", "用于"),
    ("便千", "便于"),
    ("基千", "基于"),
    ("等千", "等于"),
    ("不大千", "不大于"),
    ("不小千", "不小于"),
    ("不少千", "不少于"),
    ("不高千", "不高于"),
    ("不低千", "不低于"),
    ("取决千", "取决于"),
    ("相当千", "相当于"),
    ("处千", "处于"),
    ("属千", "属于"),
    ("限千", "限于"),
    ("介千", "介于"),
    ("鉴千", "鉴于"),
    ("难千", "难以"),
    ("易千", "易于"),
    ("优千", "优于"),
    ("大千", "大于"),
    ("小千", "小于"),
    ("少千", "少于"),
    ("多千", "多于"),
    ("低千", "低于"),
    ("高千", "高于"),
    # 其他常见 OCR 错字
    ("质最", "质量"),
    ("限扯", "限量"),
    ("限掀", "限量"),
    ("甲醒", "甲醛"),
    ("氛", "氡"),
    ("氡围", "氛围"),
    ("气氡", "气氛"),
    ("氪", "氡"),
    ("土壤氧", "土壤氡"),
    ("室内氧", "室内氡"),
    ("表面氧", "表面氡"),
    ("氧析出率", "氡析出率"),
    ("室内高氧", "室内高氡"),
    ("土壤氢", "土壤氡"),
    ("氢浓度", "氡浓度"),
    ("氢危害", "氡危害"),
    ("室内氢", "室内氡"),
    ("氢析出率", "氡析出率"),
    ("空气中氢的", "空气中氡的"),
    ("防氢措施", "防氡措施"),
    ("氢防治", "氡防治"),
    ("除氢外", "除氡外"),
    ("岩石）氢", "岩石）氡"),
    ("氧 (Bq/m勺", "氡 (Bq/m³)"),
    ("氡 ＝Vy /Ve", "β＝Vy/Ve"),
    ("氡 ―第i 楼层", "β―第i 楼层"),
    ("土壤氧浓度", "土壤氡浓度"),
    ("环竟", "环境"),
    ("范围围", "范围"),
    ("J 睦能", "性能"),
    ("J 胜", "性"),
    ("J 睦", "性"),
    ("抗展", "抗震"),
    ("承载力抗展调整系数", "承载力抗震调整系数"),
    ("介E", "γRE"),
    ("玩— 承载力抗震调整系数", "γRE— 承载力抗震调整系数"),
    ("预理件", "预埋件"),
    ("预理", "预埋"),
    ("理件", "埋件"),
    ("相临", "相邻"),
    ("目爾次", "目次"),
    ("目尔次", "目次"),
    ("GBS", "GB 5"),
    ("CB550", "GB550"),
    ("GB 50 18", "GB 55018"),
    ("GB 50 17", "GB 55017"),
    ("GB 5021", "GB 55021"),
    ("GB 5025-202", "GB 55025-2022"),
    ("GB 502-2021", "GB 55002-2021"),
    ("GB 5041- 2019", "GB 50411-2019"),
    ("GB 50选1", "GB 50411"),
    ("JG J", "JGJ"),
    ("C JJ", "CJJ"),
    ("CJJ 166一ZOn", "CJJ 166-2011"),
    ("JGJ S一2016", "JGJ 8-2016"),
    ("G B", "GB"),
    ("h tt", "http"),
    ("h it", "http"),
    ("http:/ /", "http://"),
    ("http：//", "http://"),
    ("m/5", "m/s"),
    ("m/ s", "m/s"),
    ("mZ", "m²"),
    ("m 2", "m²"),
    ("m2", "m²"),
    ("m3", "m³"),
    ("m 3", "m³"),
    ("kN/耐", "kN/m²"),
    ("W/耐", "W/m²"),
    ("kN/mZ", "kN/m²"),
    ("W/mZ", "W/m²"),
    ("0.IOm", "0.10m"),
    ("0.巧m", "0.15m"),
    ("巧o m", "150m"),
    ("lr n l n Z", "1.5mm²"),
    ("压缩波速巧", "压缩波速vp"),
    ("剪切波速 v，", "剪切波速vs"),
    ("侧胀土性指数几", "侧胀土性指数Id"),
    ("侧胀水平应力指数Kn", "侧胀水平应力指数KD"),
    ("T(5 )", "T(s)"),
    ("T(5)", "T(s)"),
    ("一2。巧", "-2015"),
    ("。．巧g", "0.15g"),
    ("1 0。%", "100%"),
    ("。.9", "0.9"),
    ("。.5", "0.5"),
    ("2 00m", "200mm"),
    ("2 02年", "2022年"),
    ("1 0月", "10月"),
    ("202-01-01", "2022-01-01"),
    ("2.22年", "2022年"),
    ("t」DC", "UDC"),
    ("t刃C", "UDC"),
    ("总贝", "总则"),
    ("防坰塌", "防坍塌"),
    ("坰塌", "坍塌"),
    ("中国人民共和国", "中华人民共和国"),
    ("入侵入员", "入侵人员"),
    ("入员", "人员"),
    ("间题", "问题"),
    ("源千", "源于"),
    ("暴露千", "暴露于"),
    ("有利千", "有利于"),
    ("联“发布", "联合发布"),
    ("工程工验收", "工程竣工验收"),
    ("工程工预验收", "工程竣工预验收"),
    ("工程工报告", "工程竣工报告"),
    ("工程工，", "工程竣工，"),
    ("峻工", "竣工"),
    ("管道工验收", "管道竣工验收"),
    ("砌体工程工后", "砌体工程完工后"),
    ("窜人", "窜入"),
    ("呕需", "亟需"),
    ("施工工富", "施工工艺"),
    ("地皿动", "地震动"),
    ("盟洗", "盥洗"),
    ("e元sting", "existing"),
    ("CB 55022-2021", "GB 55022-2021"),
    ("CB 55022", "GB 55022"),
    ("w w.mohu rd.go v. cn", "www.mohurd.gov.cn"),
    ("w w.mohu rd.go v. c n", "www.mohurd.gov.cn"),
    ("www.mohu rd . gov.。n", "www.mohurd.gov.cn"),
    ("w w.mohu记. g ov.。n", "www.mohurd.gov.cn"),
    ("www.mohu rd.g ov . cn", "www.mohurd.gov.cn"),
    ("w . 阴ht n吐gov .c n", "www.mohurd.gov.cn"),
    ("ww .mohu rd .9ov.Cn", "www.mohurd.gov.cn"),
    ("www. mohurd. gov. en", "www.mohurd.gov.cn"),
    ("(www. mohurd. gov. en)", "www.mohurd.gov.cn"),
    ("www. mohurd. gov. cn", "www.mohurd.gov.cn"),
    ("(www. mohurd. gov. cn)", "www.mohurd.gov.cn"),
]


ENGLISH_FIXES: list[tuple[str, str]] = [
    ("Gener al code f or", "General code for"),
    ("G ener a l code f or", "General code for"),
    ("G ener a l code f o r", "General code for"),
    ("Gener a l code f or", "General code for"),
    ("Gener al codes f or", "General codes for"),
    ("G ener a l co des f or", "General codes for"),
    ("Pr o ject code f or", "Project code for"),
    ("R可ect code f or", "Project code for"),
    ("Ggnera!code f or", "General code for"),
    ("slructur es", "structures"),
    ("comPosite", "composite"),
    ("sa fe ty", "safety"),
    ("generati ng", "generating"),
    ("engineer ing", "engineering"),
    ("engi neer ing", "engineering"),
    ("eng ineer ing", "engineering"),
    ("st r Uctures", "structures"),
    ("st r uctures", "structures"),
    ("st r U ctu r e s", "structures"),
    ("str uctures", "structures"),
    ("comPosite str uctures", "composite structures"),
    ("seismic Pr eca ution", "seismic precaution"),
    ("a nd", "and"),
    ("municiPa l eng ineer ing", "municipal engineering"),
    ("munici pal engi neer ing", "municipal engineering"),
    ("ur ban r oad and tr ansP0r tatlon englneer ing", "urban road and transportation engineering"),
    ("l andscape a rchi tect ur e engi neer ing", "landscape architecture engineering"),
    ("ener g y ef iciency and r enewable ene卿 application in buildin邵", "energy efficiency and renewable energy application in buildings"),
    ("desi 邵O f bui lding water suppl y a nd 击ainage and water sa ving", "design of building water supply and drainage and water saving"),
    ("scaf o ld in constr uction", "scaffold in construction"),
    ("dor mito砂，hotel building gr ouP", "dormitory, hotel building group"),
    ("sPecia l f acilities Engineer ing", "special facilities engineering"),
    ("secur ity engineer ing", "security engineering"),
    ("accessibilit y", "accessibility"),
    ("elect r icit y", "electricity"),
    ("inteligence", "intelligence"),
    ("inteli罗nce", "intelligence"),
    ("ene卿ef iciency", "energy efficiency"),
    ("ene卿", "energy"),
    ("r enewable", "renewable"),
    ("叩pl ica tion", "application"),
    ("build ing", "building"),
    ("elect r ici t y", "electricity"),
    ("sur vey", "survey"),
    ("a ccessibili t y", "accessibility"),
    ("buildin罗", "buildings"),
    ("munici Pa l", "municipal"),
    ("Pr o jects", "Projects"),
    ("secur ity", "security"),
    ("saf e ty", "safety"),
    ("sa fe t广", "safety"),
]


ENGLISH_PHRASE_FIXES: list[tuple[str, str]] = [
    # 封面/标题
    ("General code for seismic Pr eca ntiono f buil din邵and m u nicipa l engineering", "General code for seismic precaution of buildings and municipal engineering"),
    ("General code for seismic Pr eca ntiono f buil din", "General code for seismic precaution of building"),
    ("General code for foundation engineering of building andmunicipal projects", "General code for foundation engineering of building and municipal projects"),
    ("General code for steel str uctur es", "General code for steel structures"),
    ("General code for steel slructur es", "General code for steel structures"),
    ("general code f or timber structures", "General code for timber structures"),
    ("general code for timber structures", "General code for timber structures"),
    ("project code f or ur ban road and transportation engineering", "Project code for urban road and transportation engineering"),
    ("project code for urban road and transportation engineering", "Project code for urban road and transportation engineering"),
    ("Project code for engineering o f treatment and disPosal of municiP滋solid wastes", "Project code for engineering of treatment and disposal of municipal solid wastes"),
    ("〔七ner a l code f or engineering investigation", "General code for engineering investigation"),
    ("General code for desi 邵O f building water suppl y and 击a in age and water saving", "General code for design of building water supply and drainage and water saving"),
    ("G ene耐code f or design o f building water suPP l y and 击ai nage and wa t er sa vin g", "General code for design of building water supply and drainage and water saving"),
    ("General code for main沈nance and r enova tiono f 树st ing buildings", "General code for maintenance and renovation of existing buildings"),
    ("General code f or scaffold in construction", "General code for scaffold in construction"),
    ("G e ne司ce de f or scaf old in construction", "General code for scaffold in construction"),
    ("G e ne司ce de for scaf old in construction", "General code for scaffold in construction"),
    ("Gen er al c ode f or scaffold in construction", "General code for scaffold in construction"),
    ("Gen er al c ode for scaffold in construction", "General code for scaffold in construction"),
    ("general code for masonry structures", "General code for masonry structures"),
    ("C毛General code for assessment and rehabilitation of existing buildingsngs", "General code for assessment and rehabilitation of existing buildings"),
    ("General code for assessment and rehabilitation of existing buildings呀s", "General code for assessment and rehabilitation of existing buildings"),
    ("Project code for engineering of urban 而1 transit", "Project code for engineering of urban rail transit"),
    ("Project code for dormitory叮，hot el building group", "Project code for dormitory, hotel building group"),
    ("Project code for ur ban and r ur al sewerage", "Project code for urban and rural sewerage"),
    ("project code f o r ut ha n and r und sewerage", "Project code for urban and rural sewerage"),
    ("Project code for special f acilt ies engineering", "Project code for special facilities engineering"),
    ("f acilt ies", "facilities"),
    ("control l ing borehole", "controlling borehole"),
    ("d is as te r", "disaster"),
    ("s e cu r it yn", "security"),
    ("n agenl en t platform", "management platform"),
    ("leakage al arm", "leakage alarm"),
    ("hot el building group", "hotel building group"),
    ("General code formasonry structures", "General code for masonry structures"),
    ("General code f or timber structures", "General code for timber structures"),
    ("General code for concrete structures", "General code for concrete structures"),
    ("General code f or design of building w ater suPPly and drainage and water savin g", "General code for design of building water supply and drainage and water saving"),
    ("General code for desi g n o f bui lding water suppl y and", "General code for design of building water supply and"),
    ("General code f or mainten ance and renovation of e元sting buildings", "General code for maintenance and renovation of existing buildings"),
    ("General code for maintenance and r enovation of existing buildings", "General code for maintenance and renovation of existing buildings"),
    ("General code for assessment and rehabilitation of existing buildings", "General code for assessment and rehabilitation of existing buildings"),
    ("General code for assesslnent and rehabilitation of existing buildi", "General code for assessment and rehabilitation of existing buildings"),
    ("General code for fire protection of buildingsand constructions", "General code for fire protection of buildings and constructions"),
    ("General code for fire protection facilities", "General code for fire protection facilities"),
    ("General code for energy efficiency and renewable energy application in buildings", "General code for energy efficiency and renewable energy application in buildings"),
    ("General code for building environment", "General code for building environment"),
    ("General code for engineering investigation", "General code for engineering investigation"),
    ("General code for engineering survey", "General code for engineering survey"),
    ("General codes f or accessibility of buildi雌5 and municipal englneering Pro jects", "General codes for accessibility of buildings and municipal engineering projects"),
    ("General codes f or accessibility of buildings and municipa l engineering Pro jects", "General codes for accessibility of buildings and municipal engineering projects"),
    ("Gener a l codes f or accessibility of buildings and municipa l engineering Pro jects", "General codes for accessibility of buildings and municipal engineering projects"),
    ("General code for waterproofing of building andmunicipal engineering", "General code for waterproofing of building and municipal engineering"),
    ("General code for construction quality control of buildingsand municipal engineering", "General code for construction quality control of buildings and municipal engineering"),
    ("Generalcodeforconstructionqualitycontrolofbuildings", "General code for construction quality control of buildings"),
    ("Projectcode for heating engineering", "Project code for heating engineering"),
    ("Project code for gas engineering", "Project code for gas engineering"),
    ("Project code for urban road and transportation engineering", "Project code for urban road and transportation engineering"),
    ("Project code for engineering of tr ea tment and disPosal of municiPa l solid wastes", "Project code for engineering of treatment and disposal of municipal solid wastes"),
    ("Project code for engineering of treatment and disposal of municipal solid wastes", "Project code for engineering of treatment and disposal of municipal solid wastes"),
    ("Project code for engineering of urban appearance and environmental sanitation", "Project code for engineering of urban appearance and environmental sanitation"),
    ("Project code for landscape a rchi tect ur e engineering", "Project code for landscape architecture engineering"),
    ("Project code for urban water supply engineering", "Project code for urban water supply engineering"),
    ("Project code for urban and rural historical and cultural conservation", "Project code for urban and rural historical and cultural conservation"),
    ("Project code for urban and rural historical and culturalconservation", "Project code for urban and rural historical and cultural conservation"),
    ("Project code for urban rail transit engineering", "Project code for urban rail transit engineering"),
    ("Project code for special facilities engineering", "Project code for special facilities engineering"),
    ("Pr o ject c ode f or special f acilitiesE昭ineeri吧", "Project code for special facilities engineering"),
    ("Project code for residential building", "Project code for residential building"),
    ("General code for civil building", "General code for civil building"),
    ("General codefor safety and occupationalhealthon", "General code for safety and occupational health on"),
    ("General code for safety and occupational health on", "General code for safety and occupational health on"),
    ("Project code for engineering of ur ban r ail tr ansit", "Project code for engineering of urban rail transit"),
    ("Pro ject code f or engineering of urba n", "Project code for engineering of urban"),
    ("Pro ject code f or dormitory", "Project code for dormitory"),
    ("Project code for dorn ito", "Project code for dormitory"),
    ("dor mitory", "dormitory"),
    ("Cener al code f or main", "General code for main"),
    ("neraj code for assessment and rehabilitationof existing buildi", "General code for assessment and rehabilitation of existing buildings"),
    # 结构作用与术语
    ("design situati ons", "design situations"),
    ("persistent design Situati on", "persistent design situation"),
    ("transient design Situati on", "transient design situation"),
    ("accidental design Situati on", "accidental design situation"),
    ("ultimate l imit State", "ultimate limit state"),
    ("servi ceability l imi t State", "serviceability limit state"),
    ("i rrev ersible ser v ice abili ty", "irreversible serviceability"),
    ("reversible ser v ice abili ty", "reversible serviceability"),
    ("acti on effect", "action effect"),
    ("permanent action", "permanent action"),
    ("variable acti on", "variable action"),
    ("ombination value of a variable ac- tion", "combination value of a variable action"),
    ("permanet value of a varia- ble action", "permanent value of a variable action"),
    ("in ati on of actions", "combination of actions"),
    ("load om- bination", "load combination"),
    ("equi valent uni form live l oad", "equivalent uniform live load"),
    ("characteristic value of snow l oad on ground", "characteristic value of snow load on ground"),
    ("Be rno ul i", "Bernoulli"),
    ("uni form temperature", "uniform temperature"),
    ("International Buildi ng Code", "International Building Code"),
    ("design servi ce li fe", "design service life"),
    ("design working lifefo", "design working life"),
    ("sei smic precautionary intensi ty", "seismic precautionary intensity"),
    ("sei smic precautionary Criterion", "seismic precautionary criterion"),
    ("seismi c ground moti on parameter zonatlon maP", "seismic ground motion parameter zonation map"),
    ("basi c acceler ation of gr ound", "basic acceleration of ground"),
    ("seismic concept design of buildi ngs", "seismic concept design of buildings"),
    ("seismic fortification category for struc- tlfes", "seismic fortification category for structures"),
    ("capaci ty protecti on design method", "capacity protection design method"),
    ("capacity protecti on member", "capacity protection member"),
    # 地基、岩土与结构
    ("artificialfoundation", "artificial foundation"),
    ("pilefoundation", "pile foundation"),
    ("allowablesubsoildeformation", "allowable subsoil deformation"),
    ("characteristicvalueofsubsoilbear", "characteristic value of subsoil bearing"),
    ("c on c r ete c omposite she ar w all", "concrete composite shear wall"),
    ("oncrete StructureS", "concrete Structures"),
    ("square ti mber", "square timber"),
    ("dimensi on lumber", "dimension lumber"),
    ("cross l aminated timber", "cross-laminated timber"),
    ("prescripti ve design method", "prescriptive design method"),
    ("buckli ng", "buckling"),
    ("pretensi on force", "pretension force"),
    ("braci ng system", "bracing system"),
    ("shear wall with refined ductil ity", "shear wall with refined ductility"),
    ("slip coeffici ent of fricti on surface", "slip coefficient of friction surface"),
    ("li ght", "light"),
    ("weight buildi ng with gabled frames", "lightweight building with gabled frames"),
    ("Space l atticed structure", "space latticed structure"),
    ("space ri gid unit", "space rigid unit"),
    ("temperature of weldi ng circumstance", "temperature of welding circumstance"),
    # 砌体
    ("reinforcement seismicwallstructure", "reinforcement seismic wall structure"),
    ("reinforcedmasonrystructure", "reinforced masonry structure"),
    ("brickmasonrymemberwithmesh", "brick masonry member with mesh"),
    ("brickmasonrymemberwithhori", "brick masonry member with horizontal"),
    ("unreinforcedmasonrymember", "unreinforced masonry member"),
    ("reinforcedmasonrymember", "reinforced masonry member"),
    ("masonrystructure", "masonry structure"),
    ("unreinforcedmasonrystructure", "unreinforced masonry structure"),
    ("reinforcedblockmasonry", "reinforced block masonry"),
    ("confinedmasonrymember", "confined masonry member"),
    ("reinforcedblockmasonrymember", "reinforced block masonry member"),
    ("masonryunits", "masonry units"),
    ("autoclavedsand-limebrick", "autoclaved sand-lime brick"),
    ("autoclavedflyash-limebrick", "autoclaved fly ash-lime brick"),
    ("firedperforatedbrick", "fired perforated brick"),
    ("concretebrick", "concrete brick"),
    ("concretesmallhollowblock", "concrete small hollow block"),
    ("autoclavedaeratedconcreteblock", "autoclaved aerated concrete block"),
    ("masonrymortar", "masonry mortar"),
    ("groutforconcretesmallhollowblock", "grout for concrete small hollow block"),
    ("strengthclassesofmasonryunits", "strength classes of masonry units"),
    ("ready-mixedmortar", "ready-mixed mortar"),
    ("specialmortar", "special mortar"),
    ("strengthclassesofmortar", "strength classes of mortar"),
    ("pilasteredwall", "pilastered wall"),
    ("load-bearingwall", "load-bearing wall"),
    ("cavitywallwithinsulation", "cavity wall with insulation"),
    ("infilledwall", "infilled wall"),
    ("ratioofheight", "ratio of height"),
    ("tosectionalthick", "to sectional thick"),
    ("nessofwallorcolumn", "ness of wall or column"),
    ("corecolumn", "core column"),
    ("concretetiecolumn", "concrete tie column"),
    ("categoryofconstructionqualitycon", "category of construction quality con"),
    ("toothingindenting", "toothing indenting"),
    ("wallbeam", "wall beam"),
    ("serratedracking", "serrated racking"),
    ("cantileverbeam", "cantilever beam"),
    ("steppedracking", "stepped racking"),
    ("in-situinspection", "in-situ inspection"),
    # 混凝土
    ("Cof lCfete StrUCtUre", "Concrete Structure"),
    ("prestressi ng tendon and", "prestressing tendon and"),
    ("rei nforced", "reinforced"),
    ("rati o of shear span to effective depth", "ratio of shear span to effective depth"),
    # 道路、垃圾、园林
    ("urban road and transportati on engi - neefing", "urban road and transportation engineering"),
    ("desi gn vehi", "design vehicle"),
    ("si ght triangle", "sight triangle"),
    ("transi t hub", "transit hub"),
    ("munici pal soli d waste", "municipal solid waste"),
    ("i ncinerati on", "incineration"),
    ("resourceli zation", "resource utilization"),
    ("l andfill area", "landfill area"),
    ("l andfill capacity", "landfill capacity"),
    ("groundwater Collecti on and drainage system", "groundwater collection and drainage system"),
    ("i ncinerati on residue", "incineration residue"),
    ("pro ject of l andscape architecture en- glneering", "project of landscape architecture engineering"),
    ("zool ogical garden", "zoological garden"),
    ("structure greeni ng", "structure greening"),
    # 建筑节能与能源
    ("s ola r he at g ai n c oe f- f icient", "solar heat gain coefficient"),
    ("building envelope ther mal Performance trade -off", "building envelope thermal performance trade-off"),
    ("i n tegrate d par t l o ad v alu e", "integrated part load value"),
    ("se as on al energy efi ciency r atio", "seasonal energy efficiency ratio"),
    ("lighti ng power density", "lighting power density"),
    ("sol ar photovoltai c", "solar photovoltaic"),
    ("building energy perf ormance", "building energy performance"),
    ("ertifi ca- tion", "certification"),
    ("En er gy Sta r", "Energy Star"),
    # 建筑环境
    ("sensitive buildings of noise and vibration", "sensitive buildings of noise and vibration"),
    # 工程勘察与测量
    ("engineering investigati on", "engineering investigation"),
    ("engineering geol ogical conditi on", "engineering geological condition"),
    ("in一situ testi ng", "in-situ testing"),
    ("i dentifi ca- tion borehole", "identification borehole"),
    ("adverse geologic acti ons", "adverse geologic actions"),
    ("unfavorable geol ogical conditions", "unfavorable geological conditions"),
    ("regi onal rock and", "regional rock and"),
    ("engineering investigati on report", "engineering investigation report"),
    ("inspection of foundati on subsoi l", "inspection of foundation subsoil"),
    ("surveyi ng", "surveying"),
    ("enginering sur ve y", "engineering survey"),
    ("co ntr ol s ur ve y", "control survey"),
    ("nchmar k", "benchmark"),
    ("r ef er ence point", "reference point"),
    ("ge ograPhic i nf or mation", "geographic information"),
    ("co nstruction pro je ct settingout", "construction project setting out"),
    ("Par cel cor ner", "parcel corner"),
    ("buildi ng and structur e", "building and structure"),
    ("def or mation m e nitoring", "deformation monitoring"),
    ("def or mation point", "deformation point"),
    ("allowable def or matio n value", "allowable deformation value"),
    ("pr ewar ning def or matio n ualue", "pre-warning deformation value"),
    ("GeographiC Informati on System", "Geographic Information System"),
    ("Bui lding Information Modeling", "Building Information Modeling"),
    ("City Informati on Modeling", "City Information Modeling"),
    ("G lo ba l Na vig a- tion Satelli te System", "Global Navigation Satellite System"),
    ("D ig it al L in e Graph", "Digital Line Graph"),
    ("Digital Elevati on Model", "Digital Elevation Model"),
    ("Di gital Surface Model", "Digital Surface Model"),
    # 无障碍
    ("accessible facil ities", "accessible facilities"),
    ("i rculation facili- ties", "circulation facilities"),
    ("accessible Service faciliti es", "accessible service facilities"),
    ("ommunication facili - ties", "communication facilities"),
    ("wheelchai r accessi ble path", "wheelchair accessible path"),
    ("platform lift and Stair l ift", "platform lift and stair lift"),
    ("accessible vehicle parki ng lot", "accessible vehicle parking lot"),
    ("di rectional indicator", "directional indicator"),
    ("unisex wheelchair -accessibl e lavatory", "unisex wheelchair-accessible lavatory"),
    ("accessi ble bathtub", "accessible bathtub"),
    ("accessi ble kitchen", "accessible kitchen"),
    ("wheel chai r -accessible bathroom", "wheelchair-accessible bathroom"),
    ("low height service faciliti es", "low-height service facilities"),
    ("audible pedestrian signals for street cr Ssing", "audible pedestrian signals for street crossing"),
    # 给水排水
    ("building water suppl y and drainage facilities", "building water supply and drainage facilities"),
    ("domesti c sewage", "domestic sewage"),
    ("domesti C waste water", "domestic waste water"),
    ("domestic drai nage", "domestic drainage"),
    ("rain water management and utilizati on", "rainwater management and utilization"),
    ("reclaimed water system for buildi ngs", "reclaimed water system for buildings"),
    ("swimmi ng pool", "swimming pool"),
    ("ommunity Spa pool", "community spa pool"),
    ("bath faciliti es", "bath facilities"),
    ("verifi cation", "verification"),
    # 既有建筑
    ("inspecti on", "inspection"),
    ("repai r", "repair"),
    ("to -slopi ng roof", "to sloping roof"),
    ("renovation about adding bathroom and kitchen for exi sti ng residences", "renovation about adding bathroom and kitchen for existing residences"),
    ("storeyresidences", "storey residences"),
    ("outsi de hanging protective scaff old", "outside hanging protective scaffold"),
    # 电气
    ("earthing mai n li ne", "earthing main line"),
    ("main earthing ter minal", "main earthing terminal"),
    ("sa f et y ex tr a lo w v olt a ge", "safety extra low voltage"),
    ("protecti ve earthing", "protective earthing"),
    ("earth el ectrode", "earth electrode"),
    ("equipotenti al bonding", "equipotential bonding"),
    ("li ghtning equipotential bondi ng", "lightning equipotential bonding"),
    ("lightning protecti on Sys- tem", "lightning protection System"),
    ("el ectromagneti c shieldi ng", "electromagnetic shielding"),
    ("electronic informati on equipment", "electronic information equipment"),
    ("electronic infor mati on system", "electronic information system"),
    ("intelli gent equipment", "intelligent equipment"),
    ("i ntelli gent System", "intelligent System"),
    ("general li ghting", "general lighting"),
    ("Pr otection against electric shock", "Protection against electric shock"),
    ("additi onal Pr otection", "additional Protection"),
    ("basic pr otection", "basic protection"),
    # 特殊设施
    ("branch utili ty tunnel", "branch utility tunnel"),
    ("t ig at i on emer gency c ongregate shelter", "mitigation emergency congregate shelter"),
    ("emergency evacuati on and embarkation shelter", "emergency evacuation and embarkation shelter"),
    ("emergency functi o", "emergency function"),
    ("ensuring infra- structures f or disaster resPonse", "ensuring infrastructures for disaster response"),
    ("physi cal protection System", "physical protection System"),
    ("securi ty m anagement sys- tem inparking l ots", "security management system in parking lots"),
    ("protected obiect", "protected object"),
    ("defensing ob ject", "defensing object"),
    ("depth protecti on", "depth protection"),
    ("secu rity", "security"),
    ("China Metrology Accredidation", "China Metrology Accreditation"),
    ("China National Accreditation service for Conformi ty Assessment", "China National Accreditation Service for Conformity Assessment"),
    # 消防与住宅
    ("anindependent waterproof layer", "an independent waterproof layer"),
    ("interior clearheight", "interior clear height"),
    ("buildingcontrolline", "building control line"),
    ("residentialbuilding", "residential building"),
    ("storeyheight", "storey height"),
    ("siteboundary", "site boundary"),
    ("civilbuilding", "civil building"),
    ("mechanicalfloor", "mechanical floor"),
    ("publickitchen", "public kitchen"),
    ("infantroom", "infant room"),
    ("deformationjoint", "deformation joint"),
    ("inspectionlot", "inspection lot"),
    ("dominantitem", "dominant item"),
    ("generalitem", "general item"),
    ("constructionprojectarchives", "construction project archives"),
    ("objectbeating", "object beating"),
    ("vehicleinjury", "vehicle injury"),
    ("poisoningand", "poisoning and"),
    ("historicbuilding", "historic building"),
    ("historictown", "historic town"),
    ("historicconservation", "historic conservation"),
    ("historiccity", "historic city"),
    ("stylebuilding", "style building"),
    ("lowpressurefirewatersupplysystem", "low pressure fire water supply system"),
    ("stabilizedhighpressurefirewater", "stabilized high pressure fire water"),
    ("andhose", "and hose"),
    ("watersprayfiresystem", "water spray fire system"),
    ("powderextinguishingsystem", "powder extinguishing system"),
    ("getingjetsuppressionsystem", "jet suppression system"),
    ("foamextinguishingsystem", "foam extinguishing system"),
    ("smokeprotection system", "smoke protection system"),
    ("automaticfirealarmsystem", "automatic fire alarm system"),
    ("electricalfiremonitoringsystem", "electrical fire monitoring system"),
    ("smokeexhaust system", "smoke exhaust system"),
    ("podiumbasementlowerexplosionlimitflash", "podium basement lower explosion limit flash"),
    ("pointhigh", "point high"),
    ("buildingopen", "building open"),
    ("locationsemi", "location semi"),
    ("basementsparking", "basement parking"),
    ("lowerexplosionlimit", "lower explosion limit"),
    ("highrackstorage", "high rack storage"),
    ("enclosedstaircase", "enclosed staircase"),
    ("longitudinalevacuationwalkway", "longitudinal evacuation walkway"),
    ("parkinglot", "parking lot"),
    ("motorrepair", "motor repair"),
    ("fireaccess", "fire access"),
    ("emergencywaterresource", "emergency water resource"),
    ("alternatewaterresource", "alternate water resource"),
    ("DemandManagement", "Demand Management"),
    ("stor mwater system", "stormwater system"),
    ("stor m drainage", "storm drainage"),
    ("flowrate", "flow rate"),
    ("intercepted Stor m w ater flowrate", "intercepted storm water flow rate"),
    ("recl aimed water", "reclaimed water"),
    ("anaerobic di gestion", "anaerobic digestion"),
    ("sludge incinerati on", "sludge incineration"),
]


DOMAIN_WORDS = """
about above accessible accession accident accidental accommodation accompanying according across action actions active addition additional adjacent adoption adverse affiliated after against aggregate aging aimed air alarm all alternate amenity an analysis anaerobic and annual another anti any application applications appropriate architecture archives area areas around artificial as ash assessment associated attached autoclaved automatic availability backfill balanced balcony band bar barring base based basement basic basis bathroom bearing beams beam bed benchmark between beyond biogas blasting block boards boiler bonding borehole boundary branch bridge brittle buffer building buildings busbar cable cables cabinets calorific cantilever capacity car case category cavity ceiling centralized central chain chamber characteristic characteristic characteristicvalue chemical chinese circulation city civil clearance close closure coating code codes coefficient coefficient coefficient coefficients collection color colour combined combination combustion common community compact compartment composite comprehensive concrete condition conditions conductor confirm conformity connected connection conservation constant construction constructionproject constructions consumer control controlling conversion copper core corner correct countr country crane cross crossing cultural curb current cycle daily damage day daylight daylighting deck definitions deformation degree delay demolition density design designated details detection development device devices digital digestion dimensional dimension direct direction directional disaster disposal dissipative distance distribution domestic dominant door dormitory dose drainage drainage drawing dry drying ductility during each earth earthquake east ecological economic edge effective efficiency efficiency efficient elevated elevator emergency energy enforcement engine engineering engineers enhanced ensuring entrance environmental equipment equipment equipment equivalent escape evacuation evacuation evacuation event existing exit explosion exposed exposure extra extinguishing facilities facility factor factors falling false fast fault feature fiber fire fitness fixed flame flash flat floor flow flowrate flue fly foam food for force foundation frames free frequency frequent from fuel functional functions fundamental future gas gabled garden general general geographic geological geotechnical glare glued graded gradient grain gravity green greenway groundwater group groups ground grout guard guide gutter habitat hand hanging harmless health height high historical hole horizontal house housing hub humidity hydraulic if illuminance impact in incineration independent indicator indicators infant infiltration information infrastructure injury inrush in-situ inspection inspection installation insulations intake integrated interchangeability interior internal international interval into intrusion investigation iron is it its jet joint kinetic knee laboratory lamination landscape latticed lavatory layer lead leachate leakage length life light lighting lightning limit line load loads local location longitudinal low lower lumber machine main maintenance management map mapping masonry mast material materials measure measurement measures mechanical mechanism member membrane method methods migration minimum mitigation model models monitoring mortar motion municipal natural natures navigation near need neutral night noise no nominal non not number objective object of off on open operating operation operations ordinary organic other outdoor overall over panel panels parameter parameters park parking part partial passage path pedestrian performance period permanent person personnel photovoltaic physical pilastered pile pipeline piping places planning plant plastic platform point points pollution pool positive post power precaution precautionary precast prescriptive prestressed prestressing pressure prevention primary process production project projects protection protective public pump quality racking radiation radio radio activity radius rail ramp range ratio rated re reference reclaimed recovery reduced reduction reference reinforcement reinforced renovation repair representative reserve residual resistance resource response restoration retrofit reversible risk road roof room rooms run safety sanitation sanitary satellite sawn scaffold scaffold scaffold scaffolding scheme screen sea seal secondary seepage seismic semi semibasement service serviceability sewage sewerage shear shelter sheltering shield shielding shop short sight sign signal signals site slab slope smoke soil solar solid source space spatial special specialized sprinkler stability stabilized stable staircase stairs standard standards station status steel stepped storage storm stormwater strain strength stress structure structures structural style subsoil suppression supply support surface survey surveying suspended system systems tactile tank temperature temporary tendon terminal thermal thickness timber time total tower traditional transfer transient transmittance transportation treatment trench tributary truss tunnel turbine turning typical un unreinforced under underground uniform unit units universal urban urinal utility utilization value values vehicle vehicles ventilation veranda verification vibration visibility visual wall water waterproofing waterproof weather weight welding wheelchair width wind window wiring wood work working zone zones
"""


_DEFAULT_WORD_SET: set[str] | None = None


def _load_system_dictionary() -> set[str]:
    candidates = [
        Path(r"C:\Program Files\Common Files\Adobe\Acrobat\DC\Linguistics\Providers\Plugins2\AdobeHunspellPlugin\Dictionaries\en_US\en_US.dic"),
        Path(r"C:\Program Files\Adobe\Adobe Photoshop CC 2018\Required\Linguistics\Providers\Plugins2\AdobeHunspellPlugin\dictionaries\en_US\en_US.dic"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        words: set[str] = set()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[1:]:
            word = line.split("/", 1)[0].strip().lower()
            if word.isalpha():
                words.add(word)
        return words
    return set()


def _word_set() -> set[str]:
    global _DEFAULT_WORD_SET
    if _DEFAULT_WORD_SET is None:
        words = _load_system_dictionary()
        words.update(DOMAIN_WORDS.split())
        for _, replacement in ENGLISH_FIXES:
            words.update(re.findall(r"[A-Za-z]+", replacement.lower()))
        for _, replacement in ENGLISH_PHRASE_FIXES:
            words.update(re.findall(r"[A-Za-z]+", replacement.lower()))
        words.update(
            {
                "of",
                "on",
                "in",
                "to",
                "at",
                "or",
                "as",
                "if",
                "by",
                "is",
                "it",
                "no",
                "up",
                "do",
                "be",
                "an",
                "he",
                "we",
                "my",
                "us",
                "and",
                "for",
                "the",
                "with",
                "from",
                "can",
                "may",
                "not",
                "all",
                "any",
                "are",
                "was",
                "were",
                "will",
                "shall",
                "must",
                "this",
                "that",
                "than",
                "then",
                "there",
                "which",
                "when",
                "where",
                "about",
                "other",
                "such",
                "each",
                "both",
                "over",
                "under",
                "into",
                "onto",
                "after",
                "before",
                "during",
                "without",
                "within",
                "between",
                "through",
                "against",
            }
        )
        _DEFAULT_WORD_SET = words
    return _DEFAULT_WORD_SET


_SHORT_WORDS = {
    "a",
    "an",
    "as",
    "at",
    "be",
    "by",
    "do",
    "he",
    "if",
    "in",
    "is",
    "it",
    "my",
    "no",
    "of",
    "on",
    "or",
    "to",
    "up",
    "us",
    "we",
}


def _split_long_token(token: str) -> str | None:
    lowered = token.lower()
    if not lowered or not all(ch.isalpha() for ch in lowered):
        return None
    words = _word_set()
    size = len(lowered)
    dp: list[list[str] | None] = [None] * (size + 1)
    dp[0] = []
    for start in range(size):
        if dp[start] is None:
            continue
        for end in range(start + 1, min(size, start + 40) + 1):
            candidate = lowered[start:end]
            if len(candidate) == 1 and candidate not in _SHORT_WORDS:
                continue
            if candidate in words:
                if dp[end] is None or len(dp[end]) > len(dp[start]) + 1:
                    dp[end] = dp[start] + [candidate]
    result = dp[size]
    if not result or len(result) < 2:
        return None
    for part in result:
        if len(part) < 3 and part not in _SHORT_WORDS:
            return None
    return " ".join(result)


def _rejoin_tokens(tokens: list[str]) -> str:
    words = _word_set()
    output: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        lowered = token.lower()
        if lowered in words:
            best: tuple[int, str] | None = None
            for end in range(index + 1, len(tokens) + 1):
                candidate = "".join(tokens[index:end]).lower()
                if candidate in words and any(
                    not tokens[pos].lower() in words for pos in range(index, end)
                ):
                    best = (end, candidate)
            if best is None:
                output.append(token)
                index += 1
            else:
                output.append(best[1])
                index = best[0]
            continue
        merged = token.lower()
        end = index + 1
        while end < len(tokens) and merged not in words:
            merged += tokens[end].lower()
            end += 1
        if merged in words:
            output.append(merged)
            index = end
        else:
            output.append(token)
            index += 1
    return " ".join(output)


def _fix_ocr_latin_chars(text: str) -> str:
    # 这些汉字是 OCR 把字母误识别成汉字时的常见形态。
    replacements = {
        "邵": "g",
        "罗": "g",
        "卿": "rg",
        "雌": "ng",
        "飞": "ng",
        "眼": "ng",
        "昭": "ng",
        "吧": "g",
        "助": "gn",
    }
    for char, replacement in replacements.items():
        text = re.sub(
            rf"(?<=[A-Za-z]){re.escape(char)}(?=[A-Za-z])",
            replacement,
            text,
        )
    text = re.sub(r"(?<=[A-Za-z])[一－—](?=[A-Za-z])", "-", text)
    return text


def _fix_english_runs(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        phrase = match.group(0)
        normalized = re.sub(r"\s+", " ", phrase).strip()
        if len(normalized) < 4:
            return phrase
        if re.search(r"(?:http|www|\.com|\.cn|\.net)", normalized, re.I):
            return phrase
        tokens = re.split(r"[\s\-]+", normalized)
        rejoined = _rejoin_tokens([t for t in tokens if t])
        rejoined_tokens = rejoined.split()
        fixed_tokens: list[str] = []
        for token in rejoined_tokens:
            lowered = token.lower()
            split = _split_long_token(token) if lowered not in _word_set() else None
            if split:
                fixed_tokens.append(split)
            else:
                fixed_tokens.append(token)
        result = " ".join(fixed_tokens)
        if result != normalized:
            return result
        return phrase

    text = _fix_ocr_latin_chars(text)
    text = re.sub(r"[A-Za-z][A-Za-z .\-一－—]{2,}[A-Za-z]", _replace, text)
    return text


def _remove_watermarks(text: str) -> str:
    patterns = [
        r"(?:库七七|学兔兔)\s*(?:www\.)?(?:kqqw|bzfxw)\.com\s*(?:标准下载|免费下载|提供下载|提供)?",
        r"(?:www\.)?(?:kqqw|bzfxw)\.com\s*(?:标准下载|免费下载|提供下载|提供)?",
        r"(?:标准下载|免费下载|提供下载)\s*(?:库七七|学兔兔)\s*(?:www\.)?(?:kqqw|bzfxw)\.com",
        r"www\.zx3315\.cn[^\n。；;]*?(?:建设标准|真伪|增值服务)?",
        r"DZ大笨象资源圈[，,、\s]*专注精品资源[，,、\s]*提供免费下载",
        r"(?:(?:标准分享网|www\.weboos\.com)\s*)?"
        r"(?:文档来源于网络，仅做技术交流，?)?"
        r"欢迎加入暖通专业设计师执业技术交流群\s*979668941\s*\(?QQ\s*[)）]?\)?",
        r"文档来源于网络，仅做技术交流，?欢迎加入暖通专业设计师执业技术交流群\s*979668941(?:\s*[（(]?QQ\s*[)）]?)?",
        r"(?:标准分享网)?\s*(?:www\.?)?\s*bzfxw\s*\.?\s*com\s*(?:免费下载)?",
        r"标准分享网",
        r"www\.weboos\.com",
        r"www\.zaojianet\.cn",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _normalize_domains(text: str) -> str:
    replacements = [
        ("w .cabp.。0二。n", "www.cabp.com.cn"),
        ("w . chin a -building.co二。n", "www.china-building.com.cn"),
        ("w .cabp.。om.。n", "www.cabp.com.cn"),
        ("w . chi na -bui ldi 眼.。om.cn", "www.china-building.com.cn"),
        ("http P:刀w .cabp.。。二。n", "http://www.cabp.com.cn"),
        ("http://w . chin a -building.co二。n", "http://www.china-building.com.cn"),
        ("http://www. cabp. com. cn", "http://www.cabp.com.cn"),
        ("http://www. china-building, com. cn", "http://www.china-building.com.cn"),
        ("http: //www. cabp. com. cn", "http://www.cabp.com.cn"),
        ("http: //www. china-building, com. cn", "http://www.china-building.com.cn"),
        ("http://www.cabp.com. en", "http://www.cabp.com.cn"),
        ("http://www.china-building.com. en", "http://www.china-building.com.cn"),
        ("http://w . cabp.com . cn", "http://www.cabp.com.cn"),
        ("http://w - china -buildi雌.co二。n", "http://www.china-building.com.cn"),
        ("http://w . cabp·c0I n . cn", "http://www.cabp.com.cn"),
        ("http://w . chin a -buildil g.c om . cn", "http://www.china-building.com.cn"),
        ("http://w . cabp.。。二。n", "http://www.cabp.com.cn"),
        ("http://w . chi na -bui ldi飞.。or n .。n", "http://www.china-building.com.cn"),
        ("http P:刀w . e abP . c om .c n", "http://www.cabp.com.cn"),
        ("http://w . c hi n a bui ldi 眼·com cn", "http://www.china-building.com.cn"),
        ("www.i be tol.c om", "www.ibetol.com"),
        ("www.mohu rd . gov.。n", "www.mohurd.gov.cn"),
        ("www.mohu rd . gov. cn", "www.mohurd.gov.cn"),
        ("www.mohu rd . gov. en", "www.mohurd.gov.cn"),
        ("www.mohurd.gov. en", "www.mohurd.gov.cn"),
        ("www.mohurd.gov. cn", "www.mohurd.gov.cn"),
        ("w . m ol lu rd.gov‘c n", "www.mohurd.gov.cn"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _fix_units_and_numbers(text: str) -> str:
    text = text.replace("m气", "m²")
    text = text.replace("m“", "m²")
    text = text.replace("MP a", "MPa")
    text = text.replace("k Pa", "kPa")
    text = text.replace("0. lMPa", "0.1MPa")
    text = text.replace("1.imp a", "1.1MPa")
    text = text.replace("10.. skN/m", "10.5kN/m")
    text = text.replace("0.Zm", "0.2m")
    text = text.replace("0.sm", "0.5m")
    text = text.replace("1.sm", "1.5m")
    text = text.replace("2.sm", "2.5m")
    text = text.replace("3.sm", "3.5m")
    text = text.replace("3.Om", "3.0m")
    text = text.replace("2.Om", "2.0m")
    text = text.replace("0·Zmmo", "0.2mm")
    text = text.replace("2·Om", "2.0m")
    text = text.replace("0_sm", "0.5m")
    text = text.replace("2_om", "2.0m")
    text = text.replace("不小于Zm", "不小于2m")
    text = text.replace("距离其Zm", "距离其2m")
    text = text.replace("不少于s d", "不少于5d")
    text = text.replace("0.llm", "0.11m")
    text = text.replace("1.lOm", "1.10m")
    text = text.replace("lOm", "10m")
    text = text.replace("lOmin", "10min")
    text = text.replace("lOOmm", "100mm")
    text = text.replace("lOOkN", "100kN")
    text = text.replace("l8°C", "18°C")

    text = re.sub(r"(?<=\d)一(?=\d)", "-", text)
    text = re.sub(r"(?<=\d)－(?=\d)", "-", text)
    text = re.sub(r"(?<=\d) +一(?=\d)", "-", text)
    text = re.sub(r"(?<=\d)一 +(?=\d)", "-", text)
    text = re.sub(r"(?<=\d)。(?=\d)", ".", text)
    text = re.sub(r"(?<=\d)．(?=\d)", ".", text)
    text = re.sub(r"GB 5。。(\d+)", r"GB 500\1", text)
    text = re.sub(r"GB 55。。(\d+)", r"GB 5500\1", text)
    text = re.sub(r"GB 5OO(\d+)", r"GB 500\1", text)
    text = re.sub(r"GB 55OO(\d+)", r"GB 5500\1", text)
    text = re.sub(r"(?<=\d) +(?:\.)(?=\d)", ".", text)
    text = re.sub(r"(?<=\d) +(?=\.)", ".", text)
    text = re.sub(r"(?<=\.) +(?=\d)", "", text)
    text = re.sub(r"(?<=\.) +(?=[Oo0-9])", "", text)
    text = re.sub(r"(?<=\d) +(?=\d)", "", text)
    text = re.sub(r"(?<=\d)\.\.(?=\d)", ".", text)
    text = re.sub(r"(?<!施)(?<!竣)工验收", "竣工验收", text)

    # OCR 数字中的 l/O/o/S 误识
    text = re.sub(r"(?<=[0-9.])[lI](?=[0-9.])", "1", text)
    text = re.sub(r"(?<=[0-9.])[Oo](?=[0-9.])", "0", text)
    text = re.sub(r"(?<=[0-9.])S(?=[0-9.])", "5", text)
    text = re.sub(r"(?<!周)巧(?=[0-9.K%mdk]|o |年|条| |$|[\u4e00-\u9fff])", "15", text)

    text = re.sub(r"(?<=[0-9])(?:O|o)(?=[0-9])", "0", text)
    text = re.sub(r"(?<=[0-9])(?:O|o)(?=mm)", "0", text)
    text = re.sub(r"(?<=[0-9])[lI](?=mm)", "1", text)
    text = re.sub(r"(?<=[0-9])[lI](?=m\b)", "1", text)
    text = re.sub(r"(?<=[0-9])[lI](?=kN)", "1", text)
    text = re.sub(r"(?<=[0-9])[lI](?=MPa)", "1", text)
    text = re.sub(r"(?<=[0-9])[lI](?=kPa)", "1", text)
    text = re.sub(r"(?<![A-Za-z])[lI](?=[0-9])", "1", text)
    text = re.sub(r"(?<=[0-9.]) +[lI](?=[0-9])", "1", text)
    text = re.sub(r"(?<=[0-9]\.)[Oo](?=[0-9mM])", "0", text)
    text = re.sub(r"(?<=[0-9]\.)[Ss](?=[mM])", "5", text)
    text = re.sub(r"(?<![A-Za-z])S(?=O?(?:mm|m|MPa|kPa|kN|Hz|min|Om))", "5", text)
    text = re.sub(r"(?<=[0-9])[Oo](?=(?:mm|m|MPa|kPa|kN|Hz|min))", "0", text)
    text = text.replace("smm", "5mm")
    return text


def _fix_whitespace_and_punctuation(text: str) -> str:
    text = re.sub(r"(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=[，。；：、？！）】]) +", "", text)
    text = re.sub(r" +(?=[，。；：、？！（【])", "", text)
    text = re.sub(r"(?<=[（【“]) +(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff]) +(?=[（【“])", "", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff]),", "，", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff]);", "；", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff]):", "：", text)
    text = re.sub(r"(?<=[\u4e00-\u9fff]), ", "，", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


_PAREN_ITEM_PATTERN = r"(?:\d+\s*[)）]|[(（]\s*\d+\s*[)）])"

_TABLE_TITLE_RE = re.compile(
    r"^(?:续表\s*\d+(?:\.\d+)*|表\s*\d+(?:\.\d+)*)"
    r"\s*(?!中|的)(?=[\u4e00-\u9fffA-Za-z（(])"
)

_EMBEDDED_TABLE_TITLE_RE = re.compile(
    r"(?<=[。；;])"
    r"((?:续表\s*\d+(?:\.\d+)*|表\s*\d+(?:\.\d+)*)"
    r"\s*(?!中|的)(?=[\u4e00-\u9fffA-Za-z（(]))"
)

PUBLICATION_MARKERS = (
    "统一书号",
    "版权所有翻印必究",
    "本社网址",
    "网上书店",
    "定价：",
    "定价:",
    "中国建筑工业出版社出版",
    "开本：",
    "印张：",
    "字数：",
)

FIRST_CLAUSE_RE = re.compile(
    r"(?<!\d)(\d{1,2}(?:\.\d{1,2}){1,2})"
    r"(?!\s*元)(?=\s*[\u4e00-\u9fff])"
)


def strip_publication_metadata(text: str) -> str:
    """Drop publication/cover material while keeping any normative tail."""
    marker_positions = [
        text.find(marker)
        for marker in PUBLICATION_MARKERS
        if marker in text
    ]
    if not marker_positions:
        return text
    first_marker = min(marker_positions)
    before = text[:first_marker].strip()
    if FIRST_CLAUSE_RE.search(before):
        return before
    after_start = first_marker
    match = FIRST_CLAUSE_RE.search(text, after_start)
    if match:
        return text[match.start():].strip()
    return ""


def _clean_ocr_spacing(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"(?<=[\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=[，。；：、？！）】]) +", "", text)
    text = re.sub(r" +(?=[，。；：、？！（【])", "", text)
    text = re.sub(r"(?<=[（【“]) +(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"(?<=\() +(?=\d)", "", text)
    text = re.sub(r"(?<=\d) +(?=\))", "", text)
    text = re.sub(r"(?<=\d) +(?=[（(])", "", text)
    text = re.sub(r" +(?=[）)])", "", text)
    text = re.sub(r"(?<=\d) +(?=\d)", "", text)
    text = re.sub(r"\s*=\s*", "=", text)
    text = re.sub(r"(?<=\d)\s*[xX×]\s*(?=\d)", "×", text)
    text = re.sub(r"(?<=\))\s*[xX×]\s*(?=\d)", "×", text)
    text = re.sub(r"(?<=\d)\s*/\s*(?=\d)", "/", text)
    text = re.sub(r"\bm\s*[Zz]\b", "m²", text)
    text = re.sub(r"\bm\s+([23])\b", r"m\1", text)
    text = text.replace("m2", "m²").replace("m3", "m³")
    text = text.replace("(时)", "(m²)")
    text = re.sub(r"(?<=\d)[Oo](?=[xX×])", "0", text)
    text = re.sub(r"(?<=\d\.)[Ss](?=[Oo0-9])", "5", text)
    text = re.sub(r"(?<=[xX×])[Il](?=\.?\d)", "1", text)
    text = re.sub(r"(?<=[xX×])[Oo](?=\.?\d)", "0", text)
    text = re.sub(r"(?<=\d)[xX×](?=\d)", "×", text)
    return text


def normalize_ocr_paragraphs(text: str) -> str:
    """Join all prose lines into paragraphs while preserving table rows."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _EMBEDDED_TABLE_TITLE_RE.sub(r"\n\1", normalized)
    output: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output.append(_clean_ocr_spacing("".join(paragraph)))
            paragraph.clear()

    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("|") or _TABLE_TITLE_RE.match(line):
            flush_paragraph()
            output.append(line)
            continue
        paragraph.append(line)

    flush_paragraph()
    return "\n".join(output)


def _disambiguate_clause_numbers(text: str) -> str:
    pattern = re.compile(
        r"(?<![0-9.])(\d{1,2}\.\d{1,2})\.(\d)(\d)"
        r"(?=(?:层及|层以上|层|米|个|条|处|间|名|岁|年|人|户|辆|m|h|min))"
    )

    def replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}.{match.group(2)} {match.group(3)}"

    return pattern.sub(replace, text)


def _remove_glued_x_noise(text: str) -> str:
    return re.sub(
        r"(?<=[\u4e00-\u9fff。；，、：])\s*X(?=[a-z]{2,})",
        "",
        text,
    )


def _repair_misordered_items(text: str) -> str:
    pattern = re.compile(
        r"(下列规定：)([^。]{4,}?；)(2[^。]*。)(1[^。]*)$",
        re.DOTALL,
    )
    return pattern.sub(
        lambda match: (
            f"{match.group(1)}"
            f"{match.group(4)}"
            f"{match.group(2)}"
            f"{match.group(3)}"
        ),
        text,
    )


def _format_standard_clauses(text: str) -> str:
    text = _disambiguate_clause_numbers(text)
    text = re.sub(
        r"(?<=[\u4e00-\u9fff])(?<![第表图式见按依据符合号])"
        r"(\d{1,2}(?:\.\d{1,2}){1,2})"
        r"(?=[\u4e00-\u9fff（(])",
        r"\n\1 ",
        text,
    )
    text = re.sub(
        r"(?<=[\u4e00-\u9fff，。；;:：、])(?<![第表图式见按依据符合号])"
        r"([1-9]\d{0,1})"
        r"(?=(?![层米个条处间名岁年人户辆台倍%％])[\u4e00-\u9fff])",
        r"\n\1 ",
        text,
    )
    text = re.sub(
        r"(?<![0-9.])(?<![\u4e00-\u9fff])(\d{1,2}(?:\.\d{1,2}){1,3})"
        r"(?=[\u4e00-\u9fff（(])",
        r"\1 ",
        text,
    )
    text = re.sub(
        r"([。；;])(?!\n)\s*(\d{1,2}(?:\.\d{1,2}){1,3})"
        r"(?=\s*[\u4e00-\u9fff（(])",
        lambda match: f"{match.group(1)}\n{match.group(2)} ",
        text,
    )
    text = re.sub(
        r"\s+(?=(\d{1,2}(?:\.\d{1,2}){1,3})(?=\s*[\u4e00-\u9fff（(]))",
        "\n",
        text,
    )
    text = re.sub(
        rf"([。；;])(?!\n)\s*({_PAREN_ITEM_PATTERN})(?=\s*[\u4e00-\u9fff（(])",
        lambda match: f"{match.group(1)}\n{match.group(2)} ",
        text,
    )
    text = re.sub(
        rf"\s+(?=({_PAREN_ITEM_PATTERN})(?=\s*[\u4e00-\u9fff（(]))",
        "\n",
        text,
    )
    text = re.sub(
        rf"(?<![0-9A-Za-z\u4e00-\u9fff])({_PAREN_ITEM_PATTERN})"
        r"(?=[\u4e00-\u9fff])",
        lambda match: f"{match.group(1)} ",
        text,
    )
    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        if not line.strip().startswith("|"):
            line = re.sub(r"\s*\d{1,4}\s*\|(?=\s*$)", "", line)
            line = re.sub(r"\|\s*\d{1,4}(?=\s*$)", "", line)
            line = line.replace("|", "")
            line = re.sub(r"[，,、\s]+$", "", line)
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _repair_misordered_items(text)


def clean_kb_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"\s+", " ", text)
    text = _remove_watermarks(text)
    text = _normalize_domains(text)

    # 修复此前逐条替换在图片噪声串上造成的重复字母，并保持幂等。
    text = re.sub(r"design working life+", "design working life", text)
    text = re.sub(r"c+onfined concrete", "confined concrete", text)
    text = re.sub(r"c+olumn\b", "column", text)
    text = re.sub(r"c+ontrolling exploratory point", "controlling exploratory point", text)
    text = re.sub(r"c+onversion for existing buildings", "conversion for existing buildings", text)

    for old, new in TEXT_REPLACEMENTS:
        text = text.replace(old, new)
    for old, new in ENGLISH_FIXES:
        text = text.replace(old, new)
    for old, new in sorted(ENGLISH_PHRASE_FIXES, key=lambda item: len(item[0]), reverse=True):
        text = text.replace(old, new)
    text = re.sub(r"(?<![A-Za-z])design working lif(?!e)", "design working life", text)
    text = re.sub(r"(?<![A-Za-z])onfined concrete", "confined concrete", text)
    text = re.sub(r"(?<![A-Za-z])olumn\b", "column", text)
    text = re.sub(r"(?<![A-Za-z])ontrolling exploratory point", "controlling exploratory point", text)
    text = re.sub(r"(?<![A-Za-z])onversion for existing buildings", "conversion for existing buildings", text)
    text = _fix_english_runs(text)

    # 只处理英文单词中间的 OCR 空格变体，避免破坏上方逐条短语映射。
    text = re.sub(r"\bf or\b", "for", text)
    text = re.sub(r"\bur ban\b", "urban", text)
    text = re.sub(r"\br ur al\b", "rural", text)
    text = re.sub(r"\but ha n\b", "urban", text)
    text = re.sub(r"\br und\b", "rural", text)

    # 封面 OCR 乱码
    text = re.sub(r"中华人民共和国国家标准[场唇崛督国遏雪]冒", "中华人民共和国国家标准", text)
    text = text.replace("中华人民共和国国家标，唇冒", "中华人民共和国国家标准")
    text = text.replace("国家标准GB p", "国家标准")
    text = text.replace("国家标准国冒 P", "国家标准")
    text = text.replace("国家标准 (fim) p", "国家标准")
    text = re.sub(r"[t兀I」].?JDC", "UDC", text)
    text = text.replace(". 互JDC", "UDC")
    text = re.sub(r"实施富[\u4e00-\u9fff]{0,24}(?:联合发布|联“发“|联合发“)", "实施联合发布", text)
    text = re.sub(r"实施雪[\u4e00-\u9fff]{0,24}联合发布", "实施联合发布", text)
    text = text.replace(
        "实施中华人民共和国住房和城乡建设部，、.， 国家市场监督管理总局从p一汉.",
        "实施中华人民共和国住房和城乡建设部 国家市场监督管理总局 联合发布",
    )
    text = re.sub(
        r"[（(](?=[^（）()]{0,100}(?:m\s*o\s*h|mo\s*h|mohu))[^（）()]{0,100}[）)]",
        "(www.mohurd.gov.cn)",
        text,
    )
    text = text.replace("(www.mohurd.gov.cn )", "(www.mohurd.gov.cn)")
    text = text.replace("(www.mohurd.gov.cn  )", "(www.mohurd.gov.cn)")

    # 书名号 OCR
    text = re.sub(r"\(([^()（）《》]{1,60})》", r"《\1》", text)
    text = re.sub(r"《([^《》（()]{1,60})\)", r"《\1》", text)

    # 表格中常见的罗马数字 OCR 变体
    text = re.sub(r"皿(?=[类级ABC])", "Ⅲ", text)
    text = re.sub(r"(?<=数字)皿", "Ⅲ", text)
    text = re.sub(r"(?<![A-Za-z0-9])W 类", "Ⅳ类", text)
    text = re.sub(r"(?<![A-Za-z0-9])w 类", "Ⅳ类", text)
    text = re.sub(r"(?<=[0-9])W 类", "Ⅳ类", text)
    text = re.sub(r"\bm、W 类", "Ⅲ、Ⅳ类", text)
    text = re.sub(r"m、Ⅳ类", "Ⅲ、Ⅳ类", text)
    text = re.sub(r"(?<![A-Za-z0-9])W类", "Ⅳ类", text)
    text = re.sub(r"1\[ 级", "Ⅱ级", text)

    text = _fix_units_and_numbers(text)
    text = _fix_whitespace_and_punctuation(text)
    text = _remove_glued_x_noise(text)
    return _format_standard_clauses(text)
