from autocomm_v1.gate_util import *
from autocomm_v1.commute_func import *

def is_comm_block(block):
    return type(block[0]) == list

# Gates in the gate_list are either simply appended (single qubit or intra-node) or "selected"
# They are selected as a (source, node) based on which of the ctrl,target provide more "benefit"
### In ties, the ctrl is chosen
# benefit(g) := the number of consecutive 2-qubit gates with same (source, node) immediately after g.
### if benefit is 0 for both, then the gate is added on its own (block of size 1) 
######  HOWEVER, the (source, node) is never included: this is handled in beginning of linear_comm_iter
# The gate and its consecutive gates with same (source, node) are added as a block and never revisited.
# RETURNS: new_gate_block_list -- [gate U comm_block]. comm_block: [[source_qubit, target_node], [gate_i]]
def consecutive_merge(gate_list, qubit_node_mapping):
    n_gate = len(gate_list)
    gate_del_flag = [0 for i in range(n_gate)] # IGNORE Gate in bottom loop if 1
    new_gate_block_list = []
    for gidx0, g0 in enumerate(gate_list): # initial aggregation
        if gate_del_flag[gidx0] == 0:
            qb0 = gate_qubits(g0)
            if len(qb0) == 2:
                if qubit_node_mapping[qb0[0]] != qubit_node_mapping[qb0[1]]:
                    comm_block = [[],[g0]]
                    benefit = []
                    selected_gates_list = []
                    for qidx0 in [0,1]:
                        source_qb = qb0[qidx0]
                        target_node = qubit_node_mapping[qb0[1-qidx0]]
                        cnt = 0
                        selected_gates = []
                        for gidx1 in range(gidx0+1, n_gate):
                            _break_flag = True # NOTE This value is only used if len(qb1) > 2 (i.e. never)
                            if gate_del_flag[gidx1] == 0:
                                g1 = gate_list[gidx1]
                                qb1 = gate_qubits(g1)
                                if len(qb1) == 1:
                                    _break_flag = True
                                    # if qb1[0] == source_qb:
                                    #     _break_flag = False
                                    # if qubit_node_mapping[qb1[0]] == target_node:
                                    #     _break_flag = False
                                elif len(qb1) == 2:
                                    for qidx1 in [0,1]:
                                        if qb1[qidx1] == source_qb:
                                            if qubit_node_mapping[qb1[1-qidx1]] == target_node:
                                                _break_flag = False
                                                cnt += 1
                                    # if qubit_node_mapping[qb1[0]] == qubit_node_mapping[qb1[1]]:
                                    #     _break_flag = False
                            else:
                                _break_flag = False

                            if _break_flag:
                                break
                            else:
                                if gate_del_flag[gidx1] == 0:
                                    selected_gates.append(gidx1)

                        benefit.append(cnt)
                        selected_gates_list.append(selected_gates)

                    if max(benefit) == 0:
                        pass
                    else:
                        if benefit[0] >= benefit[1]:
                            selected_gates = selected_gates_list[0]
                            comm_block[0] = [qb0[0], qubit_node_mapping[qb0[1]]]
                        else:
                            selected_gates = selected_gates_list[1]
                            comm_block[0] = [qb0[1], qubit_node_mapping[qb0[0]]]
                            
                        for gidx1 in selected_gates:
                            gate_del_flag[gidx1] = 1
                            comm_block[1].append(gate_list[gidx1])
                    new_gate_block_list.append(comm_block)
                else: # IF GATE IS INSIDE ONE NODE, SIMPLY APPEND
                    new_gate_block_list.append(g0)
            else: # SIMPLY APPEND if SINGLE QUBIT GATE
                new_gate_block_list.append(g0)

    return new_gate_block_list

# WOW 200 lines of code in this one function --- BAD
# refine repeats it 3 times because the merging only happens in a DP way (between immediately consecutive common blocks)
# check_commute_func is usually commute_func_right 
# RETURNS: final anew_gate_block_list -- [comm_block]. comm_block: [[source_qubit, target_node], [gate_i]]
### [gate_i] is a list of merged gate blocks
def linear_merge_iter(new_gate_block_list, qubit_node_mapping, refine_iter_cnt, check_commute_func):
    for i in range(refine_iter_cnt):
        anew_gate_block_list = []
        n_gate = len(new_gate_block_list)
        gate_del_flag = [0 for i in range(n_gate)]
        for gidx0, gb0 in enumerate(new_gate_block_list):
            if gate_del_flag[gidx0] == 0:
                if is_comm_block(gb0): # communication block
                    # print("Current block:", gb0)
                    if gb0[0] != []:
                        source_qb0, target_node0 = gb0[0]
                        qb_to_node_pair = [[source_qb0, target_node0]]
                    else:
                        for _g_f in gb0[1]:
                            _qb_f = gate_qubits(_g_f)
                            if len(_qb_f) == 2:
                                g0 = _g_f # g0 becomes the latest 2 qubit gate in in the block
                        qb_to_node_pair = []
                        for qidx0 in [0, 1]:
                            qb0 = gate_qubits(g0)
                            source_qb0, target_node0 = qb0[qidx0], qubit_node_mapping[qb0[1-qidx0]]
                            qb_to_node_pair.append([source_qb0, target_node0])
                    # print("Current qb_to_node_pair:", qb_to_node_pair)
                    benefit = []
                    _merge_blocks_all = []
                    for source_qb0, target_node0 in qb_to_node_pair:
                        cnt = 0
                        _merge_blocks = []
                        for gidx1 in range(gidx0+1, n_gate):
                            gb1 = new_gate_block_list[gidx1]
                            if gate_del_flag[gidx1] == 0:
                                if is_comm_block(gb1): 
                                    if gb1[0] == []: # gb1 has no source, target info (must be a SINGLETON AS PER consecutive_aggregate)
                                        for _g_f in gb1[1]: # if loops more than once, then it is not a singleton
                                            _qb_f = gate_qubits(_g_f)
                                            if len(_qb_f) == 2:
                                                if _qb_f[0] == source_qb0 and qubit_node_mapping[_qb_f[1]] == target_node0:
                                                    cnt += 1
                                                    _merge_blocks.append([gidx1, 1])
                                                elif _qb_f[1] == source_qb0 and qubit_node_mapping[_qb_f[0]] == target_node0:
                                                    cnt += 1
                                                    _merge_blocks.append([gidx1, 2])
                                                break
                                    else:
                                        source_qb1, target_node1 = gb1[0]
                                        if source_qb1 == source_qb0 and target_node1 == target_node0:
                                            cnt += 1
                                            _merge_blocks.append([gidx1, 3])
                        benefit.append(cnt)
                        _merge_blocks_all.append(_merge_blocks)
                    
                    # print("Benefit:", benefit, _merge_blocks_all)
                    if len(benefit) == 1:
                        source_qb0, target_node0 = qb_to_node_pair[0]
                        _merge_blocks = _merge_blocks_all[0]
                    else:
                        if benefit[0] >= benefit[1]:
                            source_qb0, target_node0 = qb_to_node_pair[0]
                            _merge_blocks = _merge_blocks_all[0]
                        else:
                            source_qb0, target_node0 = qb_to_node_pair[1]
                            _merge_blocks = _merge_blocks_all[1]
                    
                    # start merge
                    if len(_merge_blocks) == 0:
                        anew_gate_block_list.append(gb0)
                    cur_gb0 = [[source_qb0, target_node0], gb0[1]]
                    # print("cur_gb0:", cur_gb0, _merge_blocks)
                    for gidx1, _merge_type in _merge_blocks[:1]: # NOTE only merge first one at linear step
                        if gate_del_flag[gidx1] == 0:
                            new_rblk = new_gate_block_list[gidx1][1]
                            new_lblk_list = []
                            _okay_merge = True
                            for lgidx in reversed(range(gidx0+1, gidx1)):
                                # print(lgidx, new_gate_block_list[lgidx])
                                _okay_merge = True
                                if gate_del_flag[lgidx] == 0:
                                    lg = new_gate_block_list[lgidx]
                                    if is_comm_block(lg):
                                        lg_blk = lg[1]
                                        flag, _, _, new_lblk_next, new_rblk_next = check_commute_func(lg_blk, new_rblk)
                                        if flag:
                                            new_lblk_list.append([lg[0], new_lblk_next])
                                            # print("Lueluelue:", new_lblk_list)
                                            new_rblk = new_rblk_next
                                        else:
                                            _okay_merge = False
                                    else:
                                        flag, _, _, new_lblk_next, new_rblk_next = check_commute_func([lg], new_rblk)
                                        # print("r:", flag, _, _, new_lblk_next, new_rblk_next)
                                        if flag == True:
                                            new_lblk_list.extend(new_lblk_next[::-1])
                                            new_rblk = new_rblk_next
                                        else: # EVEN IF LG doesn't commute with RBLK, merge possible  (1) if single qubit (2) elif  intra-node gate with same node as gb0
                                            lgqb = gate_qubits(lg)
                                            if len(lgqb) == 1:
                                                new_rblk = [lg] + new_rblk
                                            elif len(lgqb) == 2:
                                                if qubit_node_mapping[lgqb[0]] == qubit_node_mapping[lgqb[1]] and qubit_node_mapping[lgqb[0]] == target_node0:
                                                    new_rblk = [lg] + new_rblk
                                                else:
                                                    _okay_merge = False
                                            else:
                                                _okay_merge = False
                                        # print("r1:", new_lblk_list, _okay_merge, new_rblk)
                                    if _okay_merge == False:
                                        break
                            if _okay_merge == False:
                                new_rblk_list = []
                                new_lblk = cur_gb0[1]
                                _okay_merge = True
                                for rgidx in range(gidx0+1, gidx1):
                                    _okay_merge = True
                                    if gate_del_flag[rgidx] == 0:
                                        rg = new_gate_block_list[rgidx]
                                        if is_comm_block(rg):
                                            rg_blk = rg[1]
                                            flag, _, _, new_lblk_next, new_rblk_next = check_commute_func(new_lblk, rg_blk)
                                            if flag:
                                                new_rblk_list.append([rg[0], new_rblk_next])
                                                new_lblk = new_lblk_next
                                            else:
                                                _okay_merge = False
                                        else:
                                            flag, _, _, new_lblk_next, new_rblk_next = check_commute_func(new_lblk, [rg])
                                            if flag == True:
                                                new_rblk_list.extend(new_rblk_next)
                                                new_lblk = new_lblk_next
                                            else:
                                                rgqb = gate_qubits(rg)
                                                if len(rgqb) == 1:
                                                    new_lblk = new_lblk + [rg]
                                                elif len(rgqb) == 2:
                                                    if qubit_node_mapping[rgqb[0]] == qubit_node_mapping[rgqb[1]] and qubit_node_mapping[rgqb[0]] == target_node0:
                                                        new_lblk = new_lblk + [rg]
                                                    else:
                                                        _okay_merge = False
                                                else:
                                                    _okay_merge = False
                                        if _okay_merge == False:
                                            break
                                if _okay_merge == False:
                                    anew_gate_block_list.append(cur_gb0)
                                    break
                                else:
                                    # print("Merge from left to right")
                                    cur_gb0 = [cur_gb0[0], new_lblk+new_gate_block_list[gidx1][1]]
                                    for rg in new_rblk_list:
                                        anew_gate_block_list.append(rg)
                                    anew_gate_block_list.append(cur_gb0)
                                    for rgidx in range(gidx0, gidx1+1):
                                        gate_del_flag[rgidx] = 1 # delete them
                            else:
                                # print("Merge from right to left")
                                cur_gb0 = [cur_gb0[0], cur_gb0[1] + new_rblk]
                                anew_gate_block_list.append(cur_gb0)
                                for lg in reversed(new_lblk_list):
                                    anew_gate_block_list.append(lg)
                                for lgidx in range(gidx0, gidx1+1):
                                    gate_del_flag[lgidx] = 1 # delete them
                else: # SIMPLY APPEND gb0 if SINGLETON
                    anew_gate_block_list.append(gb0)
            else:
                pass # if gate/block deleted, nothing to do
        new_gate_block_list = anew_gate_block_list
    return new_gate_block_list

def _is_tp_comm_block(blk):
    if type(blk[0]) != list:
        return False
    if type(blk[0][0]) != list:
        return False
    return blk[0][1] == 1

def tp_comm_merge_iter(gate_block_list, qubit_node_mapping, refine_iter_cnt, check_commute_func):
    for i in range(refine_iter_cnt):
        return_gate_block_list = []
        n_gate = len(gate_block_list)
        gate_del_flag = [0 for i in range(n_gate)]
        for gidx0, gb0 in enumerate(gate_block_list):
            if gate_del_flag[gidx0] == 0:
                if _is_tp_comm_block(gb0): # TP communication block
                    source_qb0 = gb0[0][0][0]
                    _merge_blocks = []
                    for gidx1 in range(gidx0+1, n_gate):
                        gb1 = gate_block_list[gidx1]
                        if gate_del_flag[gidx1] == 0:
                            if _is_tp_comm_block(gb1):
                                # ADD the FIRST tp_comm block with same source qubit
                                if gb1[0][0][0] == source_qb0: 
                                    _merge_blocks.append([gidx1, 0])
                                    break # if searching for larger scope, may be improved
                    # start merge
                    if len(_merge_blocks) == 0:
                        return_gate_block_list.append(gb0)
                    cur_gb0 = gb0
                    for gidx1, _merge_type in _merge_blocks[:1]:
                        if gate_del_flag[gidx1] == 0:
                            new_lblk_list = []
                            _okay_merge = True
                            if gidx1 == gidx0+1:
                                part_rblk = gate_block_list[gidx1][1:]
                            for lgidx in reversed(range(gidx0+1, gidx1)):
                                _okay_merge = True
                                if gate_del_flag[lgidx] == 0:
                                    lg = gate_block_list[lgidx]
                                    if is_comm_block(lg):
                                        part_lblk = lg[1:]
                                        part_rblk = []
                                        for new_rblk in gate_block_list[gidx1][1:]:
                                            new_part_lblk = []
                                            for lg_blk in reversed(part_lblk):
                                                flag, _, _, new_lblk_next, new_rblk_next = check_commute_func(lg_blk, new_rblk)
                                                if flag:
                                                    new_part_lblk.append(new_lblk_next)
                                                    new_rblk = new_rblk_next
                                                else:
                                                    _okay_merge = False
                                                    break
                                            if _okay_merge == False:
                                                break
                                            else:
                                                part_rblk.append(new_rblk)
                                                part_lblk = new_part_lblk[::-1]
                                        if _okay_merge == True:
                                            new_lblk_list.append([lg[0]]+part_lblk)
                                    else:
                                        part_rblk = []
                                        new_lblk = [lg]
                                        for nrbidx, new_rblk in enumerate(gate_block_list[gidx1][1:]):
                                            flag, _, _, new_lblk_next, new_rblk_next = check_commute_func(new_lblk, new_rblk)
                                            if flag == True:
                                                new_rblk = new_rblk_next
                                                new_lblk =  new_lblk_next                                      
                                            else: # hardly used
                                                for llg in reversed(new_lblk):
                                                    llgqb = gate_qubits(llg)
                                                    target_node0 = gate_block_list[gidx1][0][0][1+nrbidx]
                                                    if len(llgqb) == 1:
                                                        new_rblk = [llg] + new_rblk
                                                    elif len(llgqb) == 2:
                                                        if qubit_node_mapping[llgqb[0]] == qubit_node_mapping[llgqb[1]] and qubit_node_mapping[llgqb[0]] == target_node0:
                                                            new_rblk = [llg] + new_rblk
                                                            # print("lueluelue")
                                                        else:
                                                            _okay_merge = False
                                                            break
                                                    else:
                                                        _okay_merge = False
                                                        break
                                                if _okay_merge == False:
                                                    break
                                                else:
                                                    new_lblk = []
                                            part_rblk.append(new_rblk)
                                        if _okay_merge == True:
                                            new_lblk_list.extend(new_lblk[::-1])
                                    if _okay_merge == False:
                                        break
                                            
                            if _okay_merge == False:
                                return_gate_block_list.append(cur_gb0)
                                break
                            else:
                                # print("Merge from right to left")
                                cur_gb0 = [[cur_gb0[0][0]+gate_block_list[gidx1][0][0][1:],1]] + cur_gb0[1:] + part_rblk
                                return_gate_block_list.append(cur_gb0)
                                for lg in reversed(new_lblk_list):
                                    return_gate_block_list.append(lg)
                                for lgidx in range(gidx0, gidx1+1):
                                    gate_del_flag[lgidx] = 1 # delete them
                else: # NOTE cat_comm blocks are not merged
                    return_gate_block_list.append(gb0)
            else:
                pass # if gate/block deleted, nothing to do
        gate_block_list = return_gate_block_list
    return gate_block_list

if __name__ == "__main__":
    assigned_block = [
        [[[0,2],1], [["CX",[0,1]]]],['CX',[4,0]],
        [[[0,3,1],1], [["CX",[0,3]]],[["CX",[2,0]]]]
    ]
    qn = [0,2,1,3,1]
    assigned_block = [
        [[[0,2],1], [["CX",[0,1]]]],[[[2,0],1], [["CX",[0,1]]]],
        [[[0,3,1],1], [["CX",[0,3]]],[["CX",[0,2]]]],[[[2,0],1], [["CX",[0,1]]]]
    ]
    qn = [0,2,1,3,1]

    # Should be 0,2,2 or 1,0,0 (first is a qubit index, rest are node indices)
    assigned_block = [
        [[[0,2],1], [["CX",[0,1]]]],[[[2,0,0],1], [["CX",[0,1]]],[["CX",[0,1]]]],
        [[[0,3,1],1], [["CX",[0,3]]],[["CX",[0,2]]]],
        [[[2,0],1], [["CX",[0,1]]]],
        [[[0,3,1],1], [["CX",[0,3]]],[["CX",[0,2]]]],
        [[[2,0],1], [["CX",[0,1]]]]
    ]
    qn = [0,2,1,3,1]
    gbl = tp_comm_merge_iter(assigned_block, qn, 3, commute_func_right)
    print(gbl)