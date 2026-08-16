````markdown
## 测试计划

### 测试需求

- startup
- normal_fight
- campaign
- decisive
- exercise
- expedition
- build
- repair
- destroy
- cook
- reward

每个模块只有少量功能，全部做 e2e 测试即可。测试脚本统一放在 `tests/manual/ops/` 下。

| 模块 | 功能 | 状态 |
|------|------|------|
| `startup` | 游戏启动与初始化 | ✅ E2E 测试通过 |
| `normal_fight` | 常规战执行 | ✅ E2E 测试通过 |
| `campaign` | 战役执行 | ✅ E2E 测试通过 |
| `expedition` | 远征收取 | ✅ E2E 测试通过 |
| `decisive` | 决战任务 | ❌ 未做 |
| `exercise` | 演习对抗 | ✅ E2E 测试通过 |
| `build` | 建造收取 | ❌ 未做 |
| `repair` | 修理 | ❌ 部分测试通过 |
| `destroy` | 解装舰船 | ✅ E2E 测试通过 |
| `cook` | 舰食制作 | ✅ E2E 测试通过 |
| `reward` | 任务奖励 | ✅ E2E 测试通过 |

---

### startup 测试 ✅

```bash
python tests/ops/startup.py
python tests/ops/startup.py 127.0.0.1:16384
```

### normal_fight 测试 ✅

```bash
python tests/ops/normal_fight.py
python tests/ops/normal_fight.py 127.0.0.1:16384 3  # 指定设备和次数
python tests/ops/normal_fight.py --plan examples/plans/normal_fight/7-46SS-all.yaml
```

### campaign 测试 ✅

```bash
python tests/ops/campaign.py                              # 困难驱逐 x1
python tests/ops/campaign.py 127.0.0.1:16384 困难航母 3  # 指定战役和次数
python tests/ops/campaign.py "" 简单驱逐 2
```

### expedition 测试 ✅

```bash
python tests/ops/expedition.py
python tests/ops/expedition.py 127.0.0.1:16384
```

### decisive 测试 ❌

未做

### exercise 测试 ✅

```bash
python tests/ops/exercise.py --fleet 1
python tests/ops/exercise.py --fleet 1 --rival 3
```

### build 测试 ❌

```bash
python tests/ops/build.py
python tests/ops/build.py 127.0.0.1:16384
```

### repair 测试 ❌

#### 修复第一艘舰船 ✅

```bash
python tests/ops/repair.py
python tests/ops/repair.py 127.0.0.1:16384
```

#### 按照名称修复舰船 ❌

未做

### destroy 测试 ✅

```bash
python tests/ops/destroy.py
python tests/ops/destroy.py 127.0.0.1:16384
```

### cook 测试 ✅

```bash
python tests/ops/cook.py
python tests/ops/cook.py 127.0.0.1:16384 2
```

### reward 测试 ✅

```bash
python tests/ops/reward.py
python tests/ops/reward.py 127.0.0.1:16384
python tests/ops/reward.py 127.0.0.1:16384 --auto
```
