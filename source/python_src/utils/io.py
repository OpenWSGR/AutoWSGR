import yaml


def yaml_to_dict(yaml_file):
    """ 将yaml文件转换为字典 """
    with open(yaml_file, 'r', encoding='utf-8') as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def dict_to_yaml(dict_data, yaml_file):
    """ 将字典转换为yaml文件 """
    with open(yaml_file, 'w') as f:
        yaml.dump(dict_data, f)
