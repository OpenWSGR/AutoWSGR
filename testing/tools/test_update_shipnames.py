from tools.update_shipnames import _ships_to_yaml


def test_wiki_ship_name_is_corrected_with_legacy_alias() -> None:
    result = _ships_to_yaml(
        [
            ('273', '塞尔弗里奇'),
            ('1273', '塞尔弗里奇'),
        ],
        {},
    )

    assert result.count('# 赛尔弗里吉') == 2
    assert result.count('  - "赛尔弗里吉"') == 2
    assert result.count('  - "塞尔弗里奇"') == 2
