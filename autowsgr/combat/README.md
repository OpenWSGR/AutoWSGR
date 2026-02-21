## 测试计划

### 需测试模块

- actions
    - detect_result_grade
    - detect_ship_stats
- engine
    - fight
    - _try_recovery
- handlers
    - _handle_fight_condition
    - _handle_spot_enemy
    - _handle_formation
    - _handle_missile_animation
    - _handle_night_prompt
    - _handle_result
    - _handle_get_ship
    - _handle_proceed
- node_tracker
- recognition
    - recognize_enemy_ships
    - recognize_enemy_formation

### 脱机测试（未做）

- recognize_enemy_ships、recognize_enemy_formation 可从截图直接测试
- detect_result_grade、detect_ship_stats 可从截图直接测试
- 决策相关，可通过 mock 数据测试

### 战役测试（已通过）

- 潜艇战役
    - _handle_spot_enemy
    - _handle_formation
    - _handle_night_prompt
    - _handle_result

### 常规图测试（已通过）

- 7-46SS
    - fight
    - node_tracker
    - _handle_get_ship
    - _handle_proceed

### 特别测试（未做）

- 旗舰大破回港测试
    - _handle_flagship_severe_damage
- 远程打击测试
    - _handle_missile_animation

### 补充测试（未做）

- 中破规则回港测试
    - 需要在 proceed 中选择回港
- 敌方阵容不匹配测试
    - 需要在 _handle_spot_enemy 中回港
- SL 测试
    - 索敌失败需要正确 SL

