````markdown
## 测试计划

### 测试需求

- startup
- normal_fight
- campaign
- decisive
- exercise
- expedition
- navigate
- build
- repair
- destroy
- cook
- reward

每个模块只有少量功能，全部做 e2e 测试即可。测试脚本统一放在 `testing/ops/` 下。

| 模块 | 功能 | 状态 |
|------|------|------|
| `startup` | 游戏启动与初始化 | ✅ E2E 测试通过 |
| `normal_fight` | 常规战执行 | ✅ E2E 测试通过 |
| `campaign` | 战役执行 | ✅ E2E 测试通过 |
| `expedition` | 远征收取 | ✅ E2E 测试通过 |
| `decisive` | 决战任务 | ❌ 未做 |
| `exercise` | 演习对抗 | ❌ 未做 |
| `navigate` | 页面导航 | ❌ 未做 |
| `build` | 建造收取 | ❌ 未做 |
| `repair` | 修理 | ❌ 未做 |
| `destroy` | 解装舰船 | ❌ 未做 |
| `cook` | 舰食制作 | ❌ 未做 |
| `reward` | 任务奖励 | ✅ E2E 测试通过 |

---

### startup 测试 ✅

```bash
python testing/ops/startup.py
python testing/ops/startup.py 127.0.0.1:16384
```

### normal_fight 测试 ✅

```bash
python testing/ops/normal_fight.py
python testing/ops/normal_fight.py 127.0.0.1:16384 3  # 指定设备和次数
python testing/ops/normal_fight.py --plan examples/plans/normal_fight/7-46SS-all.yaml
```

### campaign 测试 ✅

```bash
python testing/ops/campaign.py                              # 困难驱逐 ×1
python testing/ops/campaign.py 127.0.0.1:16384 困难航母 3  # 指定战役和次数
python testing/ops/campaign.py "" 简单驱逐 2
```

### expedition 测试 ✅

```bash
python testing/ops/expedition.py
python testing/ops/expedition.py 127.0.0.1:16384
```

### decisive 测试 ❌

未做

### exercise 测试 ❌

未做

### navigate 测试 ❌

未做

### build 测试 ❌

```bash
python testing/ops/build.py
python testing/ops/build.py 127.0.0.1:16384
```

### repair 测试 ❌

```bash
python testing/ops/repair.py
python testing/ops/repair.py 127.0.0.1:16384
```

### destroy 测试 ❌

```bash
python testing/ops/destroy.py
python testing/ops/destroy.py 127.0.0.1:16384
```

### cook 测试 ❌

```bash
python testing/ops/cook.py
python testing/ops/cook.py 127.0.0.1:16384
```

### reward 测试 ✅

```bash
python testing/ops/reward.py
python testing/ops/reward.py 127.0.0.1:16384
python testing/ops/reward.py 127.0.0.1:16384 --auto
```