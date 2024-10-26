from numpy import nan
import pandas 

from autocomm_v2.gate_util import remove_repeated_gates, Gate

def commute_func_right(lblk:list[Gate], rblk:list[Gate]): # right to left
    global df
    if df is None: 
        df = prepare_commute_table()

    is_commute = False
    if lblk == [] or rblk == []:
        return True, -1, -1, lblk, rblk
    
    new_lblk = [] # the lblk after moving after rblk
    for lgidx, lg in enumerate(reversed(lblk)):
        cur_check_point = [lg]
        new_rblk = []
        for rgidx, rg in enumerate(rblk):
            new_rg = rg
            for cur_lg in reversed(cur_check_point):
                is_commute, new_check_point, new_rg = find_commutation(df, cur_lg, new_rg)

                if not is_commute: 
                    return False, lgidx, rgidx, [], []
                else:
                    rg = new_rg
            new_check_point = remove_repeated_gates(new_check_point)
            cur_check_point = new_check_point[::-1]
            new_rblk.append(new_rg)
        rblk = new_rblk
        new_lblk.extend(remove_repeated_gates(new_check_point))
    new_lblk = new_lblk[::-1] ## REVERSES ARRAY (not in-place)
    return True, -1, -1, new_lblk, new_rblk

COND_KEY = 'extra_conds'
LG_KEY = 'new_checkpoint'
RG_KEY = 'new_rg'

def check_conditions(conds:str, q_l:list[int], q_r:list[int]):
    if conds is nan:
        return True

    cond_list = conds.split(',')
    for cond in cond_list:
        cond = cond.strip()
        if cond == 'ctrl_eq' and q_l[0] != q_r[0]:
            return False
        if cond == 'ctrl_neq' and q_l[0] == q_r[0]:
            return False
        if cond == 'targ_eq' and q_l[1] != q_r[1]:
            return False
        if cond == 'targ_neq' and q_l[1] == q_r[1]:
            return False
        

        if cond == 'r_ctrl_in' and q_r[0] not in q_l:
            return False
        if cond == 'r_ctrl_nin' and q_r[0] in q_l:
            return False
        if cond == 'l_ctrl_in' and q_l[0] not in q_r:
            return False
        if cond == 'l_ctrl_nin' and q_l[0] in q_r:
            return False

        if cond == 'l_ctrl_eq_r_targ' and q_l[0] != q_r[1]:
            return False
        if cond == 'r_ctrl_eq_l_targ' and q_r[0] != q_l[1]:
            return False
        if cond == 'l_ctrl_neq_r_targ' and q_l[0] == q_r[1]:
            return False
        if cond == 'r_ctrl_neq_l_targ' and q_r[0] == q_l[1]:
            return False
        
        # these cond(s) are not present
        if cond == 'l_ctrl_eq_r_ctrl' and q_l[0] != q_r[0]:
            return False
        if cond == 'l_ctrl_neq_r_ctrl' and q_l[0] == q_r[0]:
            return False

    return True

def commute_transform(g:Gate, transform:str):
    if transform == 'same':
        return g
    transform = transform.replace('type', '_type')
    l_dict = {'g': g}

    exec(f'new_g = g.transform({transform})', globals(), l_dict)
    return l_dict['new_g'] if 'new_g' in l_dict else None

def find_commutation(df:pandas.DataFrame, lg:Gate, rg:Gate):
    options:pandas.Series = df.loc[lg.type, rg.type]
    opt_idx = -1
    for idx, conds in enumerate(options[COND_KEY]):
        if check_conditions(conds, lg.qubits, rg.qubits):
            opt_idx = idx
            break
    if opt_idx == -1:
        return False, lg, rg

    chosen_option:pandas.Series = options.iloc[opt_idx]


    # Looping because the left option may have multiple gates to add
    new_checkpoint = []
    left_option = chosen_option.loc[LG_KEY]
    l_idx = 0
    while l_idx < len(left_option):
        same_idx = left_option.find('same')
        r_paren_idx = left_option.find(')')
        if r_paren_idx == -1:
            new_checkpoint.append(commute_transform(lg, left_option[l_idx:]))
            break

        # if the first item is 'same'
        if same_idx != -1 and same_idx < r_paren_idx:
            new_checkpoint.append(commute_transform(lg, 'same'))
            l_idx = same_idx + 1 + 1 # go past comma
        else:
            assert left_option.index('(') == 0
            new_checkpoint.append(commute_transform(lg, left_option[1:r_paren_idx]))
            l_idx = r_paren_idx + 1 + 1

    rg = commute_transform(rg, chosen_option.loc[RG_KEY])
    return True, new_checkpoint, rg
    
            




TABLE_FILE = 'commute.xlsx'
COLS = 'A:E'
TABLE_INDEX = [0,1]
NROWS = 128

def prepare_commute_table(table_file=None):
    if not table_file:
        table_file = TABLE_FILE

    df = pandas.read_excel(table_file, index_col=TABLE_INDEX, usecols=COLS, nrows=NROWS)
    assert len(df.index[0]) + len(df.columns) == (ord(COLS[-1]) - ord(COLS[0]) + 1)
    assert len(df) == NROWS - 1
    return df.sort_index()

df = None