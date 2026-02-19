main_page = PixelSignature(
    name="main_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8896, 0.0278, (110, 193, 255), tolerance=30.0),
        PixelRule.of(0.7885, 0.0352, (252, 144, 71), tolerance=30.0),
        PixelRule.of(0.6813, 0.0333, (82, 82, 82), tolerance=30.0),
        PixelRule.of(0.5781, 0.0389, (64, 98, 63), tolerance=30.0),
        PixelRule.of(0.4750, 0.0278, (158, 198, 109), tolerance=30.0),
        PixelRule.of(0.9719, 0.9019, (136, 143, 149), tolerance=30.0),
        PixelRule.of(0.0583, 0.8833, (250, 250, 248), tolerance=30.0),
        PixelRule.of(0.9792, 0.0389, (40, 40, 50), tolerance=30.0),
    ],
)

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

map_page = PixelSignature(
    name="map_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8938, 0.0602, (241, 96, 69), tolerance=30.0),
        PixelRule.of(0.9672, 0.0472, (21, 38, 66), tolerance=30.0),
        PixelRule.of(0.6297, 0.1046, (23, 42, 72), tolerance=30.0),
        PixelRule.of(0.3391, 0.1019, (28, 44, 69), tolerance=30.0),
        PixelRule.of(0.1833, 0.1083, (17, 33, 58), tolerance=30.0),
    ],
)

出征 = PixelSignature(
    name="出征",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1427, 0.0509, (15, 132, 228), tolerance=30.0),
    ],
)

演习 = PixelSignature(
    name="演习",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.2687, 0.0509, (15, 132, 228), tolerance=30.0),
    ],
)

远征 = PixelSignature(
    name="远征",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.3958, 0.0519, (15, 132, 228), tolerance=30.0),
    ],
)

战役 = PixelSignature(
    name="战役",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.5286, 0.0454, (15, 132, 228), tolerance=30.0),
    ],
)

战役困难 = PixelSignature(
    name="战役困难",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.7234, 0.1546, (141, 51, 51), tolerance=30.0),
    ],
)

决战 = PixelSignature(
    name="决战",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.7370, 0.0537, (16, 127, 219), tolerance=30.0),
    ],
)