# 战斗系统专项设计

## 概述

战斗系统是最复杂的部分。一次完整的战斗流程涉及：

```
出击准备 → 选择地图 → 编队 → 出征 → [索敌 → 阵型 → 战斗 → 夜战? → 结算 → 继续?]* → 结束
```

每个节点有不同的决策（撤退/迂回/阵型选择/追击/放弃），由作战计划定义。

战斗过程中不走正常的 UIController 页面框架——它是一个独立的状态机，用自己的识别逻辑。

---

## 1. 战斗状态机

```python
# autowsgr/combat/state.py

from enum import Enum, auto


class CombatState(Enum):
    """战斗状态"""
    # ── 出征前 ──
    PREPARATIONS = auto()       # 出击准备页面
    
    # ── 航行中 ──
    MOVING = auto()             # 移动中（地图推进动画）
    
    # ── 索敌阶段 ──
    SPOT_ENEMY = auto()         # 发现敌方
    SPOT_ENEMY_SUCCESS = auto() # 索敌成功（显示敌方编成）
    
    # ── 决策阶段 ──
    FORMATION = auto()          # 选择阵型
    
    # ── 战斗阶段 ──
    DAY_BATTLE = auto()         # 昼战（动画）
    NIGHT_BATTLE_PROMPT = auto() # 夜战提示（追击/撤退）
    NIGHT_BATTLE = auto()       # 夜战（动画）
    
    # ── 结算阶段 ──
    RESULT = auto()             # 战果评价（S/A/B/C/D）
    MVP = auto()                # MVP 展示
    GET_SHIP = auto()           # 掉落舰船
    GET_LOOT = auto()           # 掉落道具
    
    # ── 继续/结束 ──
    CONTINUE_PROMPT = auto()    # 继续前进/回港
    
    # ── 特殊状态 ──
    MISSILE = auto()            # 导弹攻击动画
    AERIAL = auto()             # 航空战动画
    
    # ── 终止 ──
    FINISHED = auto()           # 战斗流程结束


# 状态转移图
STATE_TRANSITIONS: dict[CombatState, list[CombatState]] = {
    CombatState.PREPARATIONS: [CombatState.MOVING],
    CombatState.MOVING: [CombatState.SPOT_ENEMY, CombatState.SPOT_ENEMY_SUCCESS],
    CombatState.SPOT_ENEMY: [CombatState.SPOT_ENEMY_SUCCESS, CombatState.FORMATION],
    CombatState.SPOT_ENEMY_SUCCESS: [CombatState.FORMATION],
    CombatState.FORMATION: [CombatState.DAY_BATTLE, CombatState.AERIAL, CombatState.MISSILE],
    CombatState.AERIAL: [CombatState.DAY_BATTLE],
    CombatState.MISSILE: [CombatState.DAY_BATTLE],
    CombatState.DAY_BATTLE: [CombatState.NIGHT_BATTLE_PROMPT, CombatState.RESULT],
    CombatState.NIGHT_BATTLE_PROMPT: [CombatState.NIGHT_BATTLE, CombatState.RESULT],
    CombatState.NIGHT_BATTLE: [CombatState.RESULT],
    CombatState.RESULT: [CombatState.MVP],
    CombatState.MVP: [CombatState.GET_SHIP, CombatState.GET_LOOT, CombatState.CONTINUE_PROMPT, CombatState.FINISHED],
    CombatState.GET_SHIP: [CombatState.GET_LOOT, CombatState.CONTINUE_PROMPT, CombatState.FINISHED],
    CombatState.GET_LOOT: [CombatState.CONTINUE_PROMPT, CombatState.FINISHED],
    CombatState.CONTINUE_PROMPT: [CombatState.MOVING, CombatState.FINISHED],
}
```

---

## 2. 状态识别器

```python
# autowsgr/combat/recognizer.py

from dataclasses import dataclass
import numpy as np
from loguru import logger

from autowsgr.combat.state import CombatState
from autowsgr.vision.matcher import ImageMatcher
from autowsgr.vision.templates import FightTemplate, TemplateRegistry


@dataclass
class StateSignature:
    """状态的视觉特征"""
    template: FightTemplate
    confidence: float = 0.85
    timeout: float = 30.0       # 等待该状态的最大时间


# 每个状态对应的视觉特征
STATE_SIGNATURES: dict[CombatState, StateSignature] = {
    CombatState.SPOT_ENEMY: StateSignature(FightTemplate.SPOT_ENEMY, timeout=60),
    CombatState.SPOT_ENEMY_SUCCESS: StateSignature(FightTemplate.SPOT_ENEMY_SUCCESS, timeout=20),
    CombatState.FORMATION: StateSignature(FightTemplate.FORMATION_SELECT, timeout=20),
    CombatState.DAY_BATTLE: StateSignature(FightTemplate.DAY_BATTLE, timeout=10),
    CombatState.NIGHT_BATTLE_PROMPT: StateSignature(FightTemplate.NIGHT_PROMPT, timeout=120),
    CombatState.RESULT: StateSignature(FightTemplate.RESULT, timeout=60),
    CombatState.MVP: StateSignature(FightTemplate.RESULT_MVP, timeout=20),
    CombatState.GET_SHIP: StateSignature(FightTemplate.GET_SHIP, timeout=5),
    CombatState.CONTINUE_PROMPT: StateSignature(FightTemplate.CONTINUE, timeout=10),
    # ...
}


class CombatStateRecognizer:
    """战斗状态识别器"""
    
    def __init__(self, matcher: ImageMatcher, templates: TemplateRegistry) -> None:
        self._matcher = matcher
        self._templates = templates
    
    def identify(
        self,
        screen: np.ndarray,
        candidates: list[CombatState],
    ) -> CombatState | None:
        """从候选状态中识别当前状态"""
        for state in candidates:
            sig = STATE_SIGNATURES.get(state)
            if sig is None:
                continue
            tpl = self._templates.get(sig.template)
            result = self._matcher.match(screen, tpl, confidence=sig.confidence)
            if result:
                return state
        return None
```

---

## 3. 安全规则引擎（替代 eval()）

```python
# autowsgr/combat/rules.py

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any
from loguru import logger


class RuleResult(Enum):
    FIGHT = auto()      # 迎战
    RETREAT = auto()    # 撤退
    DETOUR = auto()     # 迂回


@dataclass
class Condition:
    """单个条件"""
    field: str          # 要检查的字段，如 "BB", "CV", "total"
    op: str             # 操作符: ">", ">=", "<", "<=", "==", "!="
    value: int | float  # 比较值


@dataclass
class Rule:
    """一条规则: 多个条件全满足 → 执行动作"""
    conditions: list[Condition]
    action: RuleResult
    
    def evaluate(self, context: dict[str, Any]) -> bool:
        """所有条件是否都满足"""
        for cond in self.conditions:
            actual = context.get(cond.field, 0)
            if not _compare(actual, cond.op, cond.value):
                return False
        return True


def _compare(a: Any, op: str, b: Any) -> bool:
    """安全比较"""
    ops = {
        ">": lambda x, y: x > y,
        ">=": lambda x, y: x >= y,
        "<": lambda x, y: x < y,
        "<=": lambda x, y: x <= y,
        "==": lambda x, y: x == y,
        "!=": lambda x, y: x != y,
    }
    if op not in ops:
        raise ValueError(f"不支持的操作符: {op}")
    return ops[op](a, b)


class RuleEngine:
    """规则引擎"""
    
    def __init__(self, rules: list[Rule], default: RuleResult = RuleResult.FIGHT) -> None:
        self._rules = rules
        self._default = default
    
    def evaluate(self, context: dict[str, Any]) -> RuleResult:
        """按顺序评估规则，返回第一个匹配的动作"""
        for rule in self._rules:
            if rule.evaluate(context):
                logger.debug("规则匹配: {} → {}", rule.conditions, rule.action)
                return rule.action
        return self._default
    
    @classmethod
    def from_dict(cls, data: list[dict]) -> "RuleEngine":
        """从 YAML 数据构建
        
        YAML 格式:
        rules:
          - conditions:
              - field: BB
                op: ">="
                value: 2
            action: retreat
          - conditions:
              - field: CV
                op: ">"
                value: 0
              - field: total
                op: ">="
                value: 5
            action: detour
        default: fight
        """
        rules = []
        for item in data:
            conditions = [Condition(**c) for c in item["conditions"]]
            action = RuleResult[item["action"].upper()]
            rules.append(Rule(conditions=conditions, action=action))
        default = RuleResult[data[-1].get("default", "FIGHT").upper()] if data else RuleResult.FIGHT
        return cls(rules, default)
```

---

## 4. 作战计划

```python
# autowsgr/combat/plan.py

from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger

from autowsgr.combat.rules import RuleEngine, RuleResult
from autowsgr.combat.state import CombatState
from autowsgr.types import Formation
from autowsgr.infra.file_utils import load_yaml


@dataclass
class NodeDecision:
    """单节点的决策配置"""
    formation: Formation = Formation.LINE_AHEAD     # 默认阵型
    night_battle: bool = True                        # 是否夜战
    enemy_rules: RuleEngine | None = None            # 索敌规则
    formation_rules: RuleEngine | None = None        # 阵型规则
    sl_when: list[str] = field(default_factory=list) # SL 条件


@dataclass
class CombatPlan:
    """作战计划 — 定义每个节点的决策"""
    
    name: str
    nodes: dict[str, NodeDecision] = field(default_factory=dict)  # "node_1" → 决策
    default_node: NodeDecision = field(default_factory=NodeDecision)  # 未配置节点的默认值
    max_nodes: int = 10                              # 最大推进节点数
    retreat_on_heavy_damage: bool = True              # 大破撤退
    
    def get_node_decision(self, node_index: int) -> NodeDecision:
        """获取指定节点的决策"""
        key = f"node_{node_index}"
        return self.nodes.get(key, self.default_node)
    
    @classmethod
    def from_yaml(cls, path: Path) -> "CombatPlan":
        """从 YAML 文件加载"""
        data = load_yaml(path)
        nodes = {}
        for key, node_data in data.get("nodes", {}).items():
            nodes[key] = _parse_node_decision(node_data)
        
        return cls(
            name=data.get("name", path.stem),
            nodes=nodes,
            default_node=_parse_node_decision(data.get("default", {})),
            max_nodes=data.get("max_nodes", 10),
            retreat_on_heavy_damage=data.get("retreat_on_heavy_damage", True),
        )


def _parse_node_decision(data: dict) -> NodeDecision:
    """从字典解析节点决策"""
    d = NodeDecision()
    if "formation" in data:
        d.formation = Formation(data["formation"])
    if "night_battle" in data:
        d.night_battle = data["night_battle"]
    if "enemy_rules" in data:
        d.enemy_rules = RuleEngine.from_dict(data["enemy_rules"])
    return d
```

**YAML 计划文件示例 (5-4.yaml):**
```yaml
name: "5-4 周常"
max_nodes: 5
retreat_on_heavy_damage: true

default:
  formation: 1          # 单纵阵
  night_battle: false

nodes:
  node_1:
    formation: 4        # 梯形阵
    enemy_rules:
      - conditions:
          - field: BB
            op: ">="
            value: 3
        action: retreat
    night_battle: false
  
  node_3:               # Boss 节点
    formation: 1
    night_battle: true
    enemy_rules:
      - conditions:
          - field: CV
            op: ">="
            value: 2
        action: retreat
```

---

## 5. 战斗引擎

```python
# autowsgr/combat/engine.py

import time
from dataclasses import dataclass, field
from loguru import logger

from autowsgr.combat.state import CombatState, STATE_TRANSITIONS
from autowsgr.combat.recognizer import CombatStateRecognizer, STATE_SIGNATURES
from autowsgr.combat.plan import CombatPlan, NodeDecision
from autowsgr.combat.rules import RuleResult
from autowsgr.emulator.controller import AndroidController
from autowsgr.vision.matcher import ImageMatcher
from autowsgr.vision.ocr import OCREngine
from autowsgr.ui.controller import UIController
from autowsgr.ui.recognizer import UIRecognizer
from autowsgr.infra.exceptions import ImageNotFoundError, GameError


@dataclass
class CombatResult:
    """战斗结果"""
    success: bool
    sl: bool = False
    node_count: int = 0
    ship_damage: list[int] = field(default_factory=lambda: [0] * 7)
    result_grade: str = ""    # S/A/B/C/D
    drops: list[str] = field(default_factory=list)


def run_combat(
    ctrl: UIController,     # FightPrepareController
    recognizer: UIRecognizer,
    *,
    plan: CombatPlan,
) -> tuple[UIController, CombatResult]:
    """执行一次完整的战斗流程
    
    从出击准备页面开始，执行完整战斗，返回战斗结束后的 Controller。
    """
    device = recognizer._device
    matcher = recognizer._matcher
    ocr = recognizer._ocr
    state_recognizer = CombatStateRecognizer(matcher, recognizer.templates)
    
    result = CombatResult(success=False)
    state = CombatState.PREPARATIONS
    node_index = 0
    ship_damage = [0] * 7
    
    # 点击出击
    ctrl.start_sortie()
    
    while state != CombatState.FINISHED:
        # 获取可能的后继状态
        possible = STATE_TRANSITIONS.get(state, [])
        if not possible:
            logger.warning("状态 {} 无后继，结束", state)
            break
        
        # 等待识别到后继状态之一
        next_state = _wait_for_state(device, state_recognizer, possible)
        
        logger.info("状态转移: {} → {}", state.name, next_state.name)
        
        # 根据状态执行操作
        match next_state:
            case CombatState.MOVING:
                node_index += 1
                logger.info("进入节点 {}", node_index)
            
            case CombatState.SPOT_ENEMY_SUCCESS:
                # 获取敌方信息
                screen = device.screenshot()
                enemy_info = _detect_enemy(screen, ocr)
                
                # 应用索敌规则
                decision = plan.get_node_decision(node_index)
                if decision.enemy_rules:
                    rule_result = decision.enemy_rules.evaluate(enemy_info)
                    if rule_result == RuleResult.RETREAT:
                        logger.info("索敌规则: 撤退")
                        _click_retreat(device)
                        result.node_count = node_index
                        state = CombatState.FINISHED
                        continue
                    elif rule_result == RuleResult.DETOUR:
                        logger.info("索敌规则: 迂回")
                        _click_detour(device)
                        state = next_state
                        continue
            
            case CombatState.FORMATION:
                decision = plan.get_node_decision(node_index)
                _select_formation(device, decision.formation)
            
            case CombatState.NIGHT_BATTLE_PROMPT:
                decision = plan.get_node_decision(node_index)
                if decision.night_battle:
                    _click_pursue(device)
                else:
                    _click_withdraw(device)
            
            case CombatState.RESULT:
                screen = device.screenshot()
                result.result_grade = _detect_result_grade(screen, matcher, recognizer.templates)
            
            case CombatState.MVP:
                screen = device.screenshot()
                ship_damage = _detect_ship_damage_sumup(screen, matcher)
                result.ship_damage = ship_damage
                device.click(915, 515)  # 点击继续
            
            case CombatState.GET_SHIP:
                # 记录掉落
                device.click(915, 515)
            
            case CombatState.CONTINUE_PROMPT:
                # 是否继续前进
                should_continue = (
                    node_index < plan.max_nodes
                    and not (plan.retreat_on_heavy_damage and max(ship_damage[1:7]) >= 3)
                )
                if should_continue:
                    _click_continue(device)
                else:
                    _click_return(device)
                    state = CombatState.FINISHED
                    result.success = True
                    result.node_count = node_index
                    continue
        
        state = next_state
    
    # 等待回到出击准备页面或地图页面
    end_ctrl = recognizer.wait_for_page(["fight_prepare_page", "map_page"], timeout=30)
    result.success = True
    return end_ctrl, result


def _wait_for_state(
    device: AndroidController,
    recognizer: CombatStateRecognizer,
    candidates: list[CombatState],
    timeout: float = 120.0,
) -> CombatState:
    """等待出现候选状态之一"""
    # 取所有候选的最大 timeout
    max_timeout = max(
        (STATE_SIGNATURES.get(s, StateSignature(None, timeout=timeout)).timeout for s in candidates),
        default=timeout,
    )
    
    deadline = time.time() + max_timeout
    while time.time() < deadline:
        screen = device.screenshot()
        state = recognizer.identify(screen, candidates)
        if state is not None:
            return state
        time.sleep(0.3)
    
    raise ImageNotFoundError(
        template_name=f"states: {[s.name for s in candidates]}",
        timeout=max_timeout,
    )


# ── 操作函数 ──

def _click_retreat(device: AndroidController) -> None:
    device.click(615, 350)

def _click_detour(device: AndroidController) -> None:
    device.click(325, 350)

def _click_pursue(device: AndroidController) -> None:
    device.click(325, 350)

def _click_withdraw(device: AndroidController) -> None:
    device.click(615, 350)

def _click_continue(device: AndroidController) -> None:
    device.click(325, 350)

def _click_return(device: AndroidController) -> None:
    device.click(615, 350)

def _select_formation(device: AndroidController, formation) -> None:
    # formation 值对应 UI 上的阵型按钮位置
    positions = {1: (200, 250), 2: (400, 250), 3: (600, 250), 4: (200, 400), 5: (400, 400)}
    pos = positions.get(formation.value if hasattr(formation, 'value') else formation, (200, 250))
    device.click(*pos)

def _detect_enemy(screen, ocr) -> dict[str, int]:
    """检测敌方舰队信息"""
    # 调用 OCR 或原生识别器
    return {"BB": 0, "CV": 0, "DD": 0, "total": 0}

def _detect_result_grade(screen, matcher, templates) -> str:
    """检测战果评价"""
    # 匹配 S/A/B/C/D 图标
    return "S"

def _detect_ship_damage_sumup(screen, matcher) -> list[int]:
    """检测结算时的舰船血量"""
    return [0] * 7
```

---

## 6. 事件战斗（数据驱动）

事件战斗的差异通过 YAML 配置表达，不再写独立的 Python 文件：

```python
# autowsgr/combat/event.py

from dataclasses import dataclass
from pathlib import Path
from loguru import logger
from autowsgr.infra.file_utils import load_yaml


@dataclass
class EventConfig:
    """事件配置"""
    name: str
    event_type: str           # "normal_map" | "quiz" | "patrol"
    chapter_count: int
    map_count_per_chapter: int
    
    # 事件特有的 UI 元素坐标
    enter_position: tuple[int, int]   # 进入事件的点击位置
    map_positions: dict[str, tuple[int, int]]  # 地图选择坐标
    
    # 特殊机制
    has_quiz: bool = False
    quiz_answer: str = "alpha"
    has_patrol: bool = False
    
    @classmethod
    def from_yaml(cls, path: Path) -> "EventConfig":
        data = load_yaml(path)
        return cls(**data)


class EventCombatEngine:
    """事件战斗引擎 — 基于配置驱动"""
    
    def __init__(self, event_config: EventConfig) -> None:
        self._config = event_config
    
    def enter_event(self, device, matcher) -> None:
        """进入事件页面"""
        x, y = self._config.enter_position
        device.click(x, y)
    
    def select_map(self, device, chapter: int, map_id: int) -> None:
        """选择事件地图"""
        key = f"{chapter}-{map_id}"
        pos = self._config.map_positions.get(key)
        if pos:
            device.click(*pos)
    
    def handle_quiz(self, device, matcher) -> None:
        """处理问答关卡"""
        if not self._config.has_quiz:
            return
        # 根据 quiz_answer 选择入口
        ...
```

**事件配置 YAML 示例：**
```yaml
name: "2025冬活"
event_type: "normal_map"
chapter_count: 4
map_count_per_chapter: 3

enter_position: [800, 400]
map_positions:
  "1-1": [200, 300]
  "1-2": [400, 300]
  "1-3": [600, 300]
  "2-1": [200, 300]
  # ...

has_quiz: false
has_patrol: false
```

---

## 与现有代码的映射

| 现有代码 | 新设计 |
|---------|--------|
| `fight/common.py::FightInfo` (Protocol) | `CombatState` + `CombatStateRecognizer` |
| `FightInfo.update_state()` | `_wait_for_state()` |
| `FightInfo.successor_states` dict | `STATE_TRANSITIONS` dict |
| `FightInfo.state2image` dict | `STATE_SIGNATURES` dict |
| `FightPlan` (Protocol) | `CombatPlan` dataclass + `run_combat()` 函数 |
| `DecisionBlock._check_rules()` + `eval()` | `RuleEngine.evaluate()` (安全) |
| `FightPlan._make_decision()` if-else 链 | `match state:` 模式匹配 |
| `fight/event/*.py` (17 文件) | `EventConfig` YAML + `EventCombatEngine` |
| `fight/normal_fight.py` | `CombatPlan.from_yaml()` + `run_combat()` |
| `fight/decisive_battle.py` | 单独的 `decisive/` 模块（因其复杂度特殊） |
