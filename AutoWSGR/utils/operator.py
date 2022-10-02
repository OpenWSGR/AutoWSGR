
def remove_0_value_from_dict(d:dict):
    rd = {}
    for key, value in d.items():
        if(value != 0 and value != None):
            rd[key] = value
    return rd