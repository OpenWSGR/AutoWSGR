from urllib import parse, request

import yaml


def load_config():
    with open('miao_alert.yaml', encoding='utf-8') as file:
        return yaml.safe_load(file)


def miao_alert(index):
    config = load_config()
    miao_code = config['miao_code']
    texts = config['texts']  # 从 YAML 文件中读取 texts 列表

    # 检查索引是否在列表范围内
    if 0 <= index < len(texts):
        text = texts[index]
        request.urlopen(
            'https://miaotixing.com/trigger?' + parse.urlencode({'id': miao_code, 'text': text}),
        )
    else:
        print('指定的索引超出了 texts 列表的范围。')


if __name__ == '__main__':
    # 调用函数时指定索引，例如使用列表中的第二个 text
    miao_alert(1)
