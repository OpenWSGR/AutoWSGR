from types import SimpleNamespace
from utils.io import yaml_to_dict

S = SimpleNamespace()
user_settings = yaml_to_dict("data/settings/settings.yaml")
S.__dict__.update(user_settings)
