决战控制-战备舰队获取 = PixelSignature(
    name="决战控制-战备舰队获取",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.4953, 0.1083, (253, 251, 255), tolerance=30.0),
        PixelRule.of(0.5305, 0.1014, (254, 254, 254), tolerance=30.0),
        PixelRule.of(0.4031, 0.1028, (255, 252, 255), tolerance=30.0),
        PixelRule.of(0.4492, 0.1181, (254, 254, 254), tolerance=30.0),
    ],
)

决战控制-主要 = PixelSignature(
    name="决战控制-主要",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.0641, 0.0667, (218, 130, 20), tolerance=30.0),
        PixelRule.of(0.7969, 0.9194, (34, 143, 246), tolerance=30.0),
        PixelRule.of(0.9555, 0.9208, (34, 143, 246), tolerance=30.0),
        PixelRule.of(0.7055, 0.9236, (34, 143, 246), tolerance=30.0),
        PixelRule.of(0.1227, 0.0750, (215, 142, 14), tolerance=30.0),
    ],
)

决战控制-撤退 = PixelSignature(
    name="决战控制-撤退",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.3430, 0.5667, (29, 124, 214), tolerance=30.0),
        PixelRule.of(0.4180, 0.5694, (29, 124, 214), tolerance=30.0),
        PixelRule.of(0.5813, 0.5667, (152, 36, 36), tolerance=30.0),
        PixelRule.of(0.6578, 0.5639, (156, 38, 38), tolerance=30.0),
        PixelRule.of(0.4953, 0.4875, (225, 225, 225), tolerance=30.0),
        PixelRule.of(0.5023, 0.2819, (7, 117, 194), tolerance=30.0),
    ],
)

决战控制-选择前进 = PixelSignature(
    name="决战控制-选择前进",
    strategy=MatchStrategy.ALL,
    rules=[
        PixelRule.of(0.4484, 0.8333, (37, 146, 249), tolerance=30.0),
        PixelRule.of(0.4484, 0.8833, (28, 136, 237), tolerance=30.0),
        PixelRule.of(0.5492, 0.8306, (38, 147, 250), tolerance=30.0),
        PixelRule.of(0.5516, 0.8833, (28, 136, 237), tolerance=30.0),
        PixelRule.of(0.7008, 0.9028, (13, 49, 85), tolerance=30.0),
        PixelRule.of(0.7031, 0.9514, (9, 45, 79), tolerance=30.0),
        PixelRule.of(0.8695, 0.9042, (13, 49, 85), tolerance=30.0),
        PixelRule.of(0.8727, 0.9514, (9, 45, 79), tolerance=30.0),
    ],
)