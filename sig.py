建造-解装 = PixelSignature(
    name="建造-解装",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.2708, 0.0472, (15, 132, 228), tolerance=30.0),
        PixelRule.of(0.8391, 0.9000, (29, 124, 214), tolerance=30.0),
        PixelRule.of(0.8307, 0.7778, (56, 56, 56), tolerance=30.0),
        PixelRule.of(0.8948, 0.2861, (12, 140, 227), tolerance=30.0),
        PixelRule.of(0.9396, 0.2880, (237, 237, 237), tolerance=30.0),
    ],
)