
news_page = PixelSignature(
    name="news_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1437, 0.9065, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.9411, 0.0685, (253, 254, 255), tolerance=30.0),
        PixelRule.of(0.9016, 0.0704, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.8599, 0.0685, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.2010, 0.9046, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.8849, 0.0574, (247, 249, 248), tolerance=30.0),
    ],
)

not_show_news = PixelSignature(
    name="not_show_news",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0714, 0.9065, (49, 130, 211), tolerance=30.0),
        PixelRule.of(0.0620, 0.9130, (52, 130, 205), tolerance=30.0),
    ],
)

sign_page = PixelSignature(
    name="sign_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8766, 0.3046, (216, 218, 215), tolerance=30.0),
        PixelRule.of(0.1490, 0.3000, (255, 255, 255), tolerance=30.0),
        PixelRule.of(0.1786, 0.4019, (250, 255, 255), tolerance=30.0),
        PixelRule.of(0.4432, 0.4019, (254, 255, 255), tolerance=30.0),
    ],
)

sidebar_page = PixelSignature(
    name="sidebar_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0406, 0.0787, (59, 59, 59), tolerance=30.0),
        PixelRule.of(0.0443, 0.2074, (51, 51, 51), tolerance=30.0),
        PixelRule.of(0.0417, 0.3426, (56, 56, 56), tolerance=30.0),
        PixelRule.of(0.0422, 0.4583, (60, 62, 61), tolerance=30.0),
        PixelRule.of(0.0417, 0.5935, (53, 53, 53), tolerance=30.0),
        PixelRule.of(0.0422, 0.7231, (59, 59, 59), tolerance=30.0),
    ],
)

后院 = PixelSignature(
    name="后院",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.6990, 0.8389, (193, 98, 66), tolerance=30.0),
        PixelRule.of(0.2583, 0.7750, (240, 222, 146), tolerance=30.0),
        PixelRule.of(0.3344, 0.5222, (246, 119, 76), tolerance=30.0),
        PixelRule.of(0.5880, 0.2861, (255, 254, 250), tolerance=30.0),
        PixelRule.of(0.9031, 0.4380, (255, 254, 250), tolerance=30.0),
    ],
)

建造页-建造栏 = PixelSignature(
    name="建造页-建造栏",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.6724, 0.1278, (105, 203, 255), tolerance=30.0),
        PixelRule.of(0.7792, 0.1417, (220, 86, 87), tolerance=30.0),
        PixelRule.of(0.2250, 0.0556, (15, 124, 215), tolerance=30.0),
        PixelRule.of(0.8922, 0.1380, (51, 164, 240), tolerance=30.0),
    ],
)

建造页-解装栏 = PixelSignature(
    name="建造页-解装栏",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.2714, 0.0519, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.2167, 0.0556, (25, 37, 61), tolerance=30.0),
        PixelRule.of(0.0464, 0.1361, (162, 193, 126), tolerance=30.0),
        PixelRule.of(0.1443, 0.1361, (102, 140, 99), tolerance=30.0),
    ],
)

建造页-开发栏 = PixelSignature(
    name="建造页-开发栏",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.6656, 0.1278, (115, 205, 255), tolerance=30.0),
        PixelRule.of(0.7792, 0.1398, (220, 88, 86), tolerance=30.0),
        PixelRule.of(0.4802, 0.0537, (18, 125, 219), tolerance=30.0),
        PixelRule.of(0.2203, 0.0491, (20, 32, 56), tolerance=30.0),
    ],
)

建造页-废弃栏 = PixelSignature(
    name="建造页-废弃栏",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.5240, 0.0519, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.3484, 0.0676, (21, 37, 63), tolerance=30.0),
        PixelRule.of(0.8854, 0.1500, (25, 121, 208), tolerance=30.0),
        PixelRule.of(0.4526, 0.9741, (25, 120, 210), tolerance=30.0),
        PixelRule.of(0.7370, 0.9657, (54, 54, 54), tolerance=30.0),
        PixelRule.of(0.8495, 0.9713, (26, 121, 211), tolerance=30.0),
    ],
)

餐厅页 = PixelSignature(
    name="餐厅页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.7667, 0.0491, (27, 135, 226), tolerance=30.0),
        PixelRule.of(0.8719, 0.1593, (29, 119, 205), tolerance=30.0),
        PixelRule.of(0.8781, 0.2630, (29, 119, 205), tolerance=30.0),
        PixelRule.of(0.8719, 0.3806, (27, 116, 198), tolerance=30.0),
        PixelRule.of(0.8125, 0.0472, (172, 172, 172), tolerance=30.0),
    ],
)

浴场页 = PixelSignature(
    name="浴场页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8458, 0.1102, (74, 132, 178), tolerance=30.0),
        PixelRule.of(0.8604, 0.0889, (253, 254, 255), tolerance=30.0),
        PixelRule.of(0.8734, 0.0454, (52, 146, 198), tolerance=30.0),
        PixelRule.of(0.9875, 0.1019, (69, 133, 181), tolerance=30.0),
    ],
)

好友页 = PixelSignature(
    name="好友页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1953, 0.0444, (255, 255, 255), tolerance=30.0),
        PixelRule.of(0.1641, 0.0574, (255, 252, 243), tolerance=30.0),
        PixelRule.of(0.2094, 0.0574, (14, 131, 226), tolerance=30.0),
        PixelRule.of(0.1521, 0.0361, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.1724, 0.0389, (32, 128, 205), tolerance=30.0),
        PixelRule.of(0.1651, 0.0370, (240, 255, 255), tolerance=30.0),
    ],
)

任务页 = PixelSignature(
    name="任务页",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1474, 0.0509, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.2203, 0.0537, (17, 128, 220), tolerance=30.0),
        PixelRule.of(0.1818, 0.0593, (21, 129, 227), tolerance=30.0),
        PixelRule.of(0.1703, 0.0491, (249, 255, 255), tolerance=30.0),
        PixelRule.of(0.1734, 0.0370, (242, 251, 255), tolerance=30.0),
        PixelRule.of(0.1984, 0.0370, (252, 250, 251), tolerance=30.0),
        PixelRule.of(0.1693, 0.0657, (255, 255, 250), tolerance=30.0),
        PixelRule.of(0.4339, 0.0509, (140, 146, 146), tolerance=30.0),
        PixelRule.of(0.3021, 0.0537, (123, 126, 141), tolerance=30.0),
    ],
)

强化页-强化栏 = PixelSignature(
    name="强化页-强化栏",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1437, 0.0491, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.8141, 0.6926, (66, 66, 66), tolerance=30.0),
        PixelRule.of(0.8161, 0.8241, (33, 142, 245), tolerance=30.0),
        PixelRule.of(0.5526, 0.0444, (27, 41, 67), tolerance=30.0),
    ],
)

强化页-改造栏 = PixelSignature(
    name="强化页-改造栏",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8375, 0.8343, (33, 142, 243), tolerance=30.0),
        PixelRule.of(0.4609, 0.8324, (64, 64, 64), tolerance=30.0),
        PixelRule.of(0.2698, 0.0537, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.8281, 0.3685, (182, 213, 153), tolerance=30.0),
    ],
)

强化页-技能栏 = PixelSignature(
    name="强化页-技能栏",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.4052, 0.0472, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.2687, 0.3176, (28, 156, 247), tolerance=30.0),
        PixelRule.of(0.2745, 0.4204, (29, 157, 244), tolerance=30.0),
        PixelRule.of(0.2677, 0.5454, (24, 159, 251), tolerance=30.0),
        PixelRule.of(0.4219, 0.5194, (230, 230, 230), tolerance=30.0),
    ],
)