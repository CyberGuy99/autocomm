from collections.abc import Iterable

def dict_append(d, key, append_value):
    if key not in d:
        d[key] = []
    d[key].append(append_value)

def dict_num_add(d, key, add_value):
    if key not in d:
        d[key] = 0 
    d[key] += add_value

def reverse_map(m, auto_convert=True):
    new_m = dict()

    for key, val in m.items():
        if isinstance(val, Iterable):
            for v in val:
                dict_append(new_m, v, key)
        else:
            dict_append(new_m, val, key)

    # convert from list values to singular values if no arrays
    if auto_convert and all([len(values) == 1 for _, values in new_m.items()]):
        for key, val in new_m.items():
            new_m[key] = val[0]

    return new_m
