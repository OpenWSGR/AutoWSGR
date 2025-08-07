from urllib import parse, request

import yaml

from autowsgr.utils.logger import Logger


def load_config():
    with open('miao_alert.yaml', encoding='utf-8') as file:
        return yaml.safe_load(file)


def miao_alert(index, logger: Logger):
    try:
        config = load_config()
        miao_code = config['miao_code']
        texts = config['texts']  # 从 YAML 文件中读取 texts 列表

        # 检查索引是否在列表范围内
        if 0 <= index < len(texts):
            text = texts[index]
            request.urlopen(
                'https://miaotixing.com/trigger?'
                + parse.urlencode({'id': miao_code, 'text': text}),
            )
        else:
            logger.error(f'miao_alert 函数指定的索引: {index} 超出了 texts 列表的范围。')
    except Exception as e:
        logger.warning(
            f'执行 miao_alert 函数时发生错误：{e}, 如果没有配置 miao_alert.yaml 则忽略此错误',
        )
        # 可以选择记录日志或执行其他错误处理操作


if __name__ == '__main__':
    # 调用函数时指定索引，例如使用列表中的第二个 text
    miao_alert(1)
