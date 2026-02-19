map_page决战 = PixelSignature(
    name="map_page决战",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1797, 0.1731, (247, 68, 90), tolerance=30.0),
        PixelRule.of(0.1651, 0.3907, (227, 203, 216), tolerance=30.0),
        PixelRule.of(0.1240, 0.4611, (255, 210, 253), tolerance=30.0),
        PixelRule.of(0.6583, 0.0454, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.1880, 0.3833, (229, 196, 213), tolerance=30.0),
        PixelRule.of(0.0943, 0.2417, (238, 219, 215), tolerance=30.0),
    ],
)
map_page战役 = PixelSignature(
    name="map_page战役",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.6057, 0.0491, (17, 127, 222), tolerance=30.0),
        PixelRule.of(0.9542, 0.1509, (240, 220, 11), tolerance=30.0),
        PixelRule.of(0.2260, 0.1565, (100, 99, 95), tolerance=30.0),
        PixelRule.of(0.1094, 0.1565, (104, 104, 102), tolerance=30.0),
        PixelRule.of(0.4589, 0.1574, (105, 109, 110), tolerance=30.0),
    ],
)
map_page远征 = PixelSignature(
    name="map_page远征",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.4021, 0.0509, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.0380, 0.5722, (253, 226, 47), tolerance=30.0),
        PixelRule.of(0.5208, 0.0602, (22, 38, 63), tolerance=30.0),
        PixelRule.of(0.2661, 0.0574, (21, 36, 59), tolerance=30.0),
    ],
)
map_page演习 = PixelSignature(
    name="map_page演习",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.2677, 0.0472, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.1406, 0.0509, (18, 21, 40), tolerance=30.0),
        PixelRule.of(0.0292, 0.0574, (164, 167, 176), tolerance=30.0),
        PixelRule.of(0.4161, 0.0556, (20, 34, 60), tolerance=30.0),
        PixelRule.of(0.5443, 0.0556, (20, 36, 59), tolerance=30.0),
        PixelRule.of(0.6807, 0.0444, (26, 38, 62), tolerance=30.0),
        PixelRule.of(0.4578, 0.0593, (138, 146, 165), tolerance=30.0),
        PixelRule.of(0.3208, 0.0472, (9, 130, 234), tolerance=30.0),
        PixelRule.of(0.3010, 0.0639, (15, 139, 239), tolerance=30.0),
    ],
)
map_page出征 = PixelSignature(
    name="map_page出征",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.8938, 0.0602, (241, 96, 69), tolerance=30.0),
        PixelRule.of(0.1437, 0.0519, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.0359, 0.5620, (253, 226, 47), tolerance=30.0),
    ],
)