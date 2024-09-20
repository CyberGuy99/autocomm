def dict_append(d, key, append_value):
    if key not in d:
        d[key] = []
    d[key].append(append_value)

def dict_num_add(d, key, add_value):
    if key not in d:
        d[key] = 0 
    d[key] += add_value

