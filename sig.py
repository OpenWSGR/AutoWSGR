绿血特征 = PixelSignature(
    name="绿血特征",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0563, 0.5944, (77, 171, 135), tolerance=30.0),
        PixelRule.of(0.0750, 0.5986, (74, 171, 102), tolerance=30.0),
        PixelRule.of(0.0969, 0.5986, (75, 166, 107), tolerance=30.0),
        PixelRule.of(0.1117, 0.5958, (69, 169, 107), tolerance=30.0),
        PixelRule.of(0.1258, 0.5986, (82, 175, 130), tolerance=30.0),
        PixelRule.of(0.1398, 0.5986, (66, 162, 114), tolerance=30.0),
        PixelRule.of(0.1758, 0.5986, (78, 173, 115), tolerance=30.0),
        PixelRule.of(0.1945, 0.5986, (71, 161, 109), tolerance=30.0),
        PixelRule.of(0.2070, 0.6000, (80, 171, 112), tolerance=30.0),
        PixelRule.of(0.2195, 0.6014, (77, 165, 140), tolerance=30.0),
        PixelRule.of(0.2367, 0.5986, (85, 176, 141), tolerance=30.0),
        PixelRule.of(0.2539, 0.5986, (80, 169, 121), tolerance=30.0),
    ],
)

空血特征 = PixelSignature(
    name="空血特征",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0914, 0.4014, (54, 55, 59), tolerance=30.0),
        PixelRule.of(0.1141, 0.4028, (52, 56, 59), tolerance=30.0),
        PixelRule.of(0.1375, 0.4028, (54, 54, 56), tolerance=30.0),
        PixelRule.of(0.1453, 0.2625, (62, 63, 67), tolerance=30.0),
        PixelRule.of(0.1789, 0.2667, (73, 73, 73), tolerance=30.0),
        PixelRule.of(0.2281, 0.2639, (77, 76, 84), tolerance=30.0),
        PixelRule.of(0.1234, 0.5444, (59, 67, 56), tolerance=30.0),
        PixelRule.of(0.1664, 0.5444, (49, 52, 57), tolerance=30.0),
        PixelRule.of(0.2391, 0.5444, (48, 47, 52), tolerance=30.0),
        PixelRule.of(0.3102, 0.5417, (91, 81, 80), tolerance=30.0),
        PixelRule.of(0.3320, 0.2625, (71, 71, 71), tolerance=30.0),
    ],
)

红血特征 = PixelSignature(
    name="红血特征",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0664, 0.2625, (156, 1, 0), tolerance=30.0),
        PixelRule.of(0.0781, 0.2639, (173, 20, 25), tolerance=30.0),
        PixelRule.of(0.0906, 0.2639, (184, 34, 36), tolerance=30.0),
        PixelRule.of(0.1070, 0.2639, (157, 14, 10), tolerance=30.0),
        PixelRule.of(0.0672, 0.4014, (155, 3, 0), tolerance=30.0),
        PixelRule.of(0.0750, 0.4014, (166, 4, 1), tolerance=30.0),
        PixelRule.of(0.0695, 0.5403, (177, 26, 19), tolerance=30.0),
        PixelRule.of(0.0844, 0.5403, (187, 31, 32), tolerance=30.0),
        PixelRule.of(0.0984, 0.5403, (183, 36, 28), tolerance=30.0),
    ],
)

