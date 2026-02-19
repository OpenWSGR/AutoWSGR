map_page = PixelSignature(
    name="map_page",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.1396, 0.0574, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.2745, 0.0537, (18, 33, 56), tolerance=30.0),
        PixelRule.of(0.4042, 0.0556, (23, 37, 63), tolerance=30.0),
        PixelRule.of(0.5276, 0.0519, (25, 39, 66), tolerance=30.0),
        PixelRule.of(0.6620, 0.0556, (24, 40, 65), tolerance=30.0),
        PixelRule.of(0.8938, 0.0593, (240, 90, 63), tolerance=30.0),
    ],
)
食堂 = PixelSignature(
    name="食堂",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.7667, 0.0454, (27, 134, 228), tolerance=30.0),
        PixelRule.of(0.8734, 0.1611, (29, 119, 205), tolerance=30.0),
        PixelRule.of(0.8745, 0.2750, (29, 115, 198), tolerance=30.0),
        PixelRule.of(0.8734, 0.3806, (27, 116, 198), tolerance=30.0),
        PixelRule.of(0.7734, 0.0602, (254, 255, 255), tolerance=30.0),
    ],
)
sidebar = PixelSignature(
    name="sidebar",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.7667, 0.0454, (27, 134, 228), tolerance=30.0),
        PixelRule.of(0.8734, 0.1611, (29, 119, 205), tolerance=30.0),
        PixelRule.of(0.8745, 0.2750, (29, 115, 198), tolerance=30.0),
        PixelRule.of(0.8734, 0.3806, (27, 116, 198), tolerance=30.0),
        PixelRule.of(0.7734, 0.0602, (254, 255, 255), tolerance=30.0),
        PixelRule.of(0.0417, 0.0806, (55, 55, 55), tolerance=30.0),
        PixelRule.of(0.0422, 0.2102, (58, 58, 58), tolerance=30.0),
        PixelRule.of(0.0453, 0.3463, (0, 160, 232), tolerance=30.0),
        PixelRule.of(0.0406, 0.4676, (58, 58, 58), tolerance=30.0),
        PixelRule.of(0.0396, 0.6028, (56, 56, 56), tolerance=30.0),
        PixelRule.of(0.0432, 0.7231, (56, 56, 56), tolerance=30.0),
    ],
)