import yaml


def yaml_to_dict(yaml_file):
    """ 将yaml文件转换为字典 """
    with open(yaml_file, 'r', encoding='utf-8') as f:
        return yaml.load(f, Loader=yaml.FullLoader)


def dict_to_yaml(dict_data, yaml_file):
    """ 将字典转换为yaml文件 """
    with open(yaml_file, 'w') as f:
        yaml.dump(dict_data, f)


def recursive_dict_update(d, u, skip=[]):
    for k, v in u.items():
        if k in skip:
            continue
        if isinstance(v, dict):
            r = recursive_dict_update(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d
